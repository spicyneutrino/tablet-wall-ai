#!/usr/bin/env python3
"""Verified-TLS trust and origin probe for the two-origin hotspot ingress.

This tool answers a narrow question: **does this verifier, using an explicitly
named trust store, accept the tablet and operator origins, and does the tablet
ingress expose only the routes ``PROTOCOL.md``/``deploy/hotspot.Caddyfile``
allow?** It never accepts ``-k`` or an "insecure" switch as evidence. Every
graded request is a fresh TLS connection made with
``ssl.create_default_context(cafile=...)`` and hostname verification on.

The route expectations mirror ``deploy/smoke.sh`` (same allowed and denied
paths, same status codes) but are re-implemented here with Python's TLS stack
so the trust decision is never delegated to ``curl``'s switch flags:

* allowed tablet surface: ``/client/`` documents, an unknown content-addressed
  asset (404 proves the route reached the app), an invalid registration (422
  proves the route reached the app without creating an identity) and the
  device WebSocket upgrade (101);
* denied tablet surface: uploads, media, diagnostics, the asset inventory,
  rebinding, every operator route and the encoded traversal variants;
* operator listener: authentication is required for reads, writes and the
  controller WebSocket upgrade.

What a run cannot prove, and the report repeats in ``limitations``:

* a supplied CA bundle proves **verifier trust only**. It says nothing about a
  tablet's installed browser/OS trust store;
* the hostname in the URL is the host the verifier checked. A real tablet must
  open the origin with no warning while WAN is absent -- a manual step;
* route checks run from the verification host. They are not a second physical
  LAN vantage and do not test a tablet's routes;
* direct backend-port reachability and firewall rules are outside this probe.

The output is one ``tablet-wall-validation-evidence/1`` report with
``gate = installed-ca-trust`` and ``hardware_gate_status = MISSING``.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import re
import socket
import ssl
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.validation import evidence  # noqa: E402

TOOL = "trust-check"
TOOL_VERSION = "1"
GATE = "installed-ca-trust"
DEFAULT_TIMEOUT = 8.0
READ_LIMIT = 64 * 1024

FINGERPRINT_HEX = re.compile(r"^[0-9a-f]{64}$")
HOSTNAME_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

PHASES = (
    "tls",
    "certificate",
    "tablet-allowed",
    "tablet-denied",
    "tablet-websocket",
    "operator-tls",
    "operator-auth",
    "operator-websocket",
)

ZERO_ASSET = "sha256:" + ("0" * 64)
PROBE_DEVICE = "00000000-0000-4000-8000-000000000001"
REGISTER_BODY = b"{}"


# ---------------------------------------------------------------------------
# origins and fingerprints
# ---------------------------------------------------------------------------


class OriginError(ValueError):
    """A URL argument that is not a bare HTTPS origin."""


@dataclass(frozen=True)
class Origin:
    raw: str
    host: str
    port: int
    address: ipaddress.IPv4Address | ipaddress.IPv6Address | None

    @property
    def is_ip(self) -> bool:
        return self.address is not None

    @property
    def normalized(self) -> str:
        host = f"[{self.host}]" if self.is_ip and self.address.version == 6 else self.host
        return f"https://{host}:{self.port}"

    @property
    def host_header(self) -> str:
        return f"[{self.host}]" if self.is_ip and self.address.version == 6 else self.host


def parse_origin(value: str) -> Origin:
    """Accept only a bare ``https://host[:port]`` origin.

    Rejecting everything else is deliberate: a path, query, fragment, embedded
    credential or plain-HTTP scheme would make the probe's claim ambiguous, and
    ``http://`` would invite an "insecure is fine on the LAN" exception.
    """
    text = (value or "").strip()
    if not text:
        raise OriginError("origin is empty")
    if text != value:
        raise OriginError("origin must not start or end with whitespace")
    parts = urlsplit(text)
    if parts.scheme.lower() != "https":
        raise OriginError("origin must use https; an insecure exception is not evidence")
    if parts.username is not None or parts.password is not None:
        raise OriginError("origin must not embed credentials")
    if parts.path not in ("", "/"):
        raise OriginError("origin must not contain a path")
    if parts.query or parts.fragment:
        raise OriginError("origin must not contain a query or fragment")
    host = parts.hostname
    if not host:
        raise OriginError("origin has no host")
    host = host.lower().rstrip(".")
    if not host:
        raise OriginError("origin has no host")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
        labels = host.split(".")
        if len(labels) > 253 or not all(HOSTNAME_LABEL.match(label) for label in labels):
            raise OriginError(f"origin host {host!r} is not a DNS name or IP address")
    try:
        port = parts.port
    except ValueError as exc:
        raise OriginError(f"origin port is invalid: {exc}") from exc
    if port is None:
        port = 443
    if not 1 <= port <= 65535:
        raise OriginError("origin port is outside 1..65535")
    return Origin(raw=text, host=host, port=port, address=address)


def normalize_fingerprint(value: str) -> str:
    """Lowercase bare SHA-256 hex; accept colon/space/dash separated forms."""
    text = (value or "").strip().lower()
    for separator in (":", " ", "-"):
        text = text.replace(separator, "")
    if not FINGERPRINT_HEX.match(text):
        raise ValueError("fingerprint must be 64 hexadecimal characters (SHA-256)")
    return text


def origin_argument(value: str) -> Origin:
    try:
        return parse_origin(value)
    except OriginError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def fingerprint_argument(value: str) -> str:
    try:
        return normalize_fingerprint(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def positive_timeout(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a number") from exc
    if not 0 < parsed <= 120:
        raise argparse.ArgumentTypeError("timeout must be greater than 0 and at most 120")
    return parsed


# ---------------------------------------------------------------------------
# trust store and certificates
# ---------------------------------------------------------------------------


def build_context(ca_file: str | None) -> tuple[ssl.SSLContext, dict[str, Any]]:
    """Create a verifying context and name the store it actually loaded.

    When ``ca_file`` is supplied, ``ssl.create_default_context(cafile=...)``
    does **not** load the system roots. That is recorded as
    ``system_roots_loaded: false`` so a report cannot read as broader trust
    than the run exercised.
    """
    if ca_file:
        path = Path(ca_file).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"CA file does not exist: {path}")
        context = ssl.create_default_context(cafile=str(path))
        identity: dict[str, Any] = {
            "kind": "supplied-ca-bundle",
            "label": f"supplied CA bundle {path}",
            "path": str(path),
            "sha256": evidence.file_sha256(path),
            "system_roots_loaded": False,
            "proves": ("verifier trust with this file only; installed "
                       "tablet/browser trust remains manual"),
        }
    else:
        context = ssl.create_default_context()
        paths = ssl.get_default_verify_paths()
        identity = {
            "kind": "system-default",
            "label": "system default trust store",
            "cafile": paths.cafile,
            "capath": paths.capath,
            "openssl_cafile_env": paths.openssl_cafile_env,
            "openssl_capath_env": paths.openssl_capath_env,
            "system_roots_loaded": True,
            "proves": ("verifier trust with the host default store only; "
                       "installed tablet/browser trust remains manual"),
        }
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    identity["cert_store_stats"] = context.cert_store_stats()
    return context, identity


def _chain_der(tls: ssl.SSLSocket, verified: bool) -> list[bytes]:
    """Return chain certificates as DER, across Python 3.13 and 3.15 shapes.

    Python 3.13/3.14 return ``ssl._ssl.Certificate`` objects; 3.15 returns the
    DER bytes directly. Only the verified chain is authoritative; the
    unverified chain is used for diagnostics after a failed handshake.
    """
    getter = getattr(tls, "get_verified_chain" if verified else "get_unverified_chain", None)
    chain: list[bytes] = []
    if getter is not None:
        try:
            raw = getter()
        except (ssl.SSLError, ValueError):
            raw = []
        for item in raw or []:
            if isinstance(item, (bytes, bytearray)):
                chain.append(bytes(item))
                continue
            try:
                chain.append(item.public_bytes(ssl._ssl.ENCODING_DER))
            except (AttributeError, ssl.SSLError):
                continue
    if not chain:
        leaf = tls.getpeercert(binary_form=True)
        if leaf:
            chain.append(leaf)
    return chain


def _name_text(name: Any) -> str:
    if not name:
        return ""
    parts: list[str] = []
    for rdn in name:
        for key, value in rdn:
            if isinstance(value, bytes):
                value = value.decode("utf-8", "replace")
            parts.append(f"{key}={value}")
    return ", ".join(parts)


def _parse_cert_time(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(ssl.cert_time_to_seconds(value))
    except (ValueError, OverflowError):
        return None


def decode_certificate(der: bytes, *, parser_note: dict[str, Any]) -> dict[str, Any]:
    """Decode one DER certificate with the standard library (no dependencies)."""
    sha256 = hashlib.sha256(der).hexdigest()
    pem = ssl.DER_cert_to_PEM_cert(der)
    row: dict[str, Any] = {
        "sha256": sha256,
        "pem": pem,
        "subject": None,
        "issuer": None,
        "subject_alt_names": [],
        "not_before": None,
        "not_after": None,
        "self_signed": None,
        "decode_error": None,
    }
    decoder = getattr(getattr(ssl, "_ssl", None), "_test_decode_cert", None)
    if decoder is None:
        row["decode_error"] = (
            "ssl._ssl._test_decode_cert is unavailable; only the fingerprint is recorded"
        )
        parser_note["parser"] = "fingerprint-only"
        return row
    handle = None
    try:
        handle = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
        handle.write(pem)
        handle.close()
        decoded = decoder(handle.name)
        parser_note["parser"] = "python-ssl-stdlib"
    except (OSError, ValueError, ssl.SSLError) as exc:
        row["decode_error"] = f"certificate decode failed: {type(exc).__name__}: {exc}"
        parser_note["parser"] = "fingerprint-only"
        return row
    finally:
        if handle is not None:
            try:
                Path(handle.name).unlink()
            except OSError:
                pass
    row["subject"] = _name_text(decoded.get("subject"))
    row["issuer"] = _name_text(decoded.get("issuer"))
    row["subject_alt_names"] = [
        f"{kind}:{value}" for kind, value in (decoded.get("subjectAltName") or ())
    ]
    row["not_before"] = decoded.get("notBefore")
    row["not_after"] = decoded.get("notAfter")
    row["self_signed"] = bool(row["subject"]) and row["subject"] == row["issuer"]
    return row


def certificate_view(der: bytes, *, parser_note: dict[str, Any]) -> dict[str, Any]:
    row = decode_certificate(der, parser_note=parser_note)
    not_before = _parse_cert_time(row["not_before"])
    not_after = _parse_cert_time(row["not_after"])
    now = time.time()
    row["validity"] = {
        "not_before_epoch": not_before,
        "not_after_epoch": not_after,
        "valid_now": bool(not_before is not None and not_after is not None
                          and not_before <= now <= not_after),
        "expires_in_days": round((not_after - now) / 86400, 2) if not_after is not None else None,
    }
    row.pop("pem", None)
    return row


@dataclass
class Inspection:
    origin: Origin
    verified: bool
    error: dict[str, Any] | None
    certificate: dict[str, Any] | None
    chain: list[dict[str, Any]] = field(default_factory=list)
    tls_version: str | None = None
    cipher: list[Any] | None = None
    transport_source: str | None = None
    hostname_verification: str = "not-run"
    duration_ms: int = 0

    def detail(self) -> dict[str, Any]:
        return {
            "origin": self.origin.normalized,
            "verified": self.verified,
            "error": self.error,
            "certificate": self.certificate,
            "chain": self.chain,
            "tls_version": self.tls_version,
            "cipher": self.cipher,
            "transport_source": self.transport_source,
            "hostname_verification": self.hostname_verification,
            "duration_ms": self.duration_ms,
        }


def _handshake(origin: Origin, context: ssl.SSLContext, timeout: float,
               *, verified: bool, parser_note: dict[str, Any]) -> tuple[Inspection, ssl.SSLSocket]:
    started = time.monotonic()
    inspection = Inspection(origin=origin, verified=verified, error=None, certificate=None)
    raw = socket.create_connection((origin.host, origin.port), timeout=timeout)
    try:
        tls = context.wrap_socket(raw, server_hostname=origin.host)
    except (ssl.SSLError, OSError):
        raw.close()
        raise
    tls.settimeout(timeout)
    try:
        inspection.tls_version = tls.version()
        inspection.cipher = list(tls.cipher()) if tls.cipher() else None
        inspection.transport_source = (
            "verified-handshake" if verified else "unverified-diagnostic-handshake"
        )
        chain = _chain_der(tls, verified=verified)
        if chain:
            inspection.chain = [certificate_view(der, parser_note=parser_note) for der in chain]
            inspection.certificate = inspection.chain[0]
        inspection.hostname_verification = "passed" if verified else "unknown"
    except (ssl.SSLError, OSError) as exc:
        # Inspection is best-effort; the trust decision already happened in
        # wrap_socket above, so a metadata error cannot turn into a pass.
        inspection.error = {"type": type(exc).__name__, "message": str(exc)}
    inspection.duration_ms = int((time.monotonic() - started) * 1000)
    return inspection, tls


def inspect_origin(origin: Origin, context: ssl.SSLContext, timeout: float,
                   parser_note: dict[str, Any]) -> tuple[Inspection, bool]:
    """Verify one origin; on failure collect descriptions from an unverified peek.

    The second handshake exists only so the report can show the fingerprint and
    chain that *were offered*. It is labelled ``unverified-diagnostic-handshake``
    and can never satisfy a trust check.
    """
    try:
        inspection, tls = _handshake(
            origin, context, timeout, verified=True, parser_note=parser_note,
        )
        tls.close()
        return inspection, True
    except (ssl.SSLError, OSError) as exc:
        failure = {
            "type": type(exc).__name__,
            "message": str(exc),
            "verify_code": getattr(exc, "verify_code", None),
            "verify_message": getattr(exc, "verify_message", None),
        }
        diagnostic = Inspection(
            origin=origin, verified=False, error=failure, certificate=None,
        )
        verify_code = getattr(exc, "verify_code", None)
        verify_message = (getattr(exc, "verify_message", "") or "").lower()
        diagnostic.hostname_verification = (
            "failed"
            if verify_code in (62, 64) or "mismatch" in verify_message
            else "not-established"
        )
        try:
            unverified = ssl._create_unverified_context()
            peek, sock = _handshake(
                origin, unverified, timeout, verified=False, parser_note=parser_note,
            )
            sock.close()
            diagnostic.certificate = peek.certificate
            diagnostic.chain = peek.chain
            diagnostic.tls_version = peek.tls_version
            diagnostic.cipher = peek.cipher
            diagnostic.transport_source = "unverified-diagnostic-handshake"
        except (ssl.SSLError, OSError):
            pass
        return diagnostic, False


# ---------------------------------------------------------------------------
# HTTP(S) probes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Probe:
    name: str
    method: str
    path: str
    expected: int
    body: bytes = b""
    headers: tuple[tuple[str, str], ...] = ()
    ws: bool = False


@dataclass(frozen=True)
class ProbeResult:
    status: int | None
    tls_version: str | None
    cipher: str | None
    duration_ms: int
    error: dict[str, Any] | None = None


def _read_head(tls: ssl.SSLSocket) -> bytes:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = tls.recv(4096)
        if not chunk:
            break
        data += chunk
        if len(data) > READ_LIMIT:
            break
    return data


def request_probe(origin: Origin, context: ssl.SSLContext, timeout: float,
                  probe: Probe) -> ProbeResult:
    started = time.monotonic()
    tls: ssl.SSLSocket | None = None
    try:
        raw = socket.create_connection((origin.host, origin.port), timeout=timeout)
        tls = context.wrap_socket(raw, server_hostname=origin.host)
        tls.settimeout(timeout)
        lines = [
            f"{probe.method} {probe.path} HTTP/1.1",
            f"Host: {origin.host_header}",
            "User-Agent: tablet-wall-trust-check/1",
            "Connection: Upgrade" if probe.ws else "Connection: close",
        ]
        for key, value in probe.headers:
            lines.append(f"{key}: {value}")
        if probe.ws:
            lines.extend([
                "Upgrade: websocket",
                "Sec-WebSocket-Version: 13",
                "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
            ])
        if probe.body:
            lines.append(f"Content-Length: {len(probe.body)}")
        request = ("\r\n".join(lines) + "\r\n\r\n").encode("ascii") + probe.body
        tls.sendall(request)
        head = _read_head(tls)
        if not head:
            return ProbeResult(
                status=None, tls_version=tls.version(),
                cipher=tls.cipher()[0] if tls.cipher() else None,
                duration_ms=int((time.monotonic() - started) * 1000),
                error={"type": "EmptyResponse",
                       "message": "server closed without a response"},
            )
        head_text = head.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1")
        lines_head = head_text.split("\r\n")
        try:
            status = int(lines_head[0].split(" ", 2)[1])
        except (IndexError, ValueError):
            return ProbeResult(
                status=None, tls_version=tls.version(),
                cipher=tls.cipher()[0] if tls.cipher() else None,
                duration_ms=int((time.monotonic() - started) * 1000),
                error={"type": "BadStatusLine", "message": lines_head[0][:200]},
            )
        return ProbeResult(
            status=status, tls_version=tls.version(),
            cipher=tls.cipher()[0] if tls.cipher() else None,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except (ssl.SSLError, OSError) as exc:
        return ProbeResult(
            status=None, tls_version=None, cipher=None,
            duration_ms=int((time.monotonic() - started) * 1000),
            error={
                "type": type(exc).__name__,
                "message": str(exc),
                "verify_code": getattr(exc, "verify_code", None),
                "verify_message": getattr(exc, "verify_message", None),
            },
        )
    finally:
        if tls is not None:
            try:
                tls.close()
            except OSError:
                pass


def tablet_routes() -> tuple[list[Probe], list[Probe]]:
    """The allowlist and default-deny matrix, mirroring deploy/smoke.sh."""
    allowed = [
        Probe("client-index", "GET", "/client/", 200),
        Probe("client-html", "GET", "/client/index.html", 200),
        Probe("client-js", "GET", "/client/client.js", 200),
        Probe("client-css", "GET", "/client/client.css", 200),
        Probe("client-view-js", "GET", "/client/view.js", 200),
        Probe(
            "register-invalid", "POST", "/devices/register", 422,
            body=REGISTER_BODY, headers=(("Content-Type", "application/json"),),
        ),
        Probe("asset-unknown", "GET", f"/assets/{ZERO_ASSET}", 404),
        Probe(
            "device-websocket", "GET",
            f"/ws/device?device_id={PROBE_DEVICE}&protocol=2", 101, ws=True,
        ),
    ]
    denied = [
        Probe("uploads-get", "GET", "/uploads", 403),
        Probe(
            "uploads-post", "POST", "/uploads", 403,
            body=b"{}", headers=(("Content-Type", "application/json"),),
        ),
        Probe("media", "GET", "/media", 403),
        Probe("media-verify", "POST", "/media/verify", 403),
        Probe("diagnostics", "GET", "/diagnostics", 403),
        Probe("asset-inventory", "GET", "/assets", 403),
        Probe("rebind-root", "GET", "/rebind", 403),
        Probe(
            "rebind-device", "POST", f"/devices/{PROBE_DEVICE}/rebind", 403,
            body=b"{}", headers=(("Content-Type", "application/json"),),
        ),
        Probe("wall", "GET", "/wall", 403),
        Probe("wall-put", "PUT", "/wall", 403),
        Probe("wall-auto", "POST", "/wall/auto", 403),
        Probe("scene-put", "PUT", "/scene", 403),
        Probe("devices-color", "POST", "/devices/color", 403),
        Probe("device-color", "POST", f"/devices/{PROBE_DEVICE}/color", 403),
        Probe("device-placement-put", "PUT",
              f"/devices/{PROBE_DEVICE}/placement", 403),
        Probe("device-placement-delete", "DELETE",
              f"/devices/{PROBE_DEVICE}/placement", 403),
        Probe("device-delete", "DELETE", f"/devices/{PROBE_DEVICE}", 403),
        Probe("register-get", "GET", "/devices/register", 403),
        Probe("client-post", "POST", "/client/", 403),
        Probe("layout-put", "PUT", "/layouts/Probe", 403),
        Probe("layout-delete", "DELETE", "/layouts/Probe", 403),
        Probe("layout-recall", "POST", "/layouts/probe/recall", 403),
        Probe("scene-save", "PUT", "/scenes/Probe", 403),
        Probe("scene-recall", "POST", "/scenes/Probe/recall", 403),
        Probe("scene-delete", "DELETE", "/scenes/Probe", 403),
        Probe("controller-page", "GET", "/controller/", 403),
        Probe("controller-socket", "GET", "/ws/controller?protocol=2", 403, ws=True),
        Probe("operator-config", "GET", "/operator-config", 403),
        Probe("devices", "GET", "/devices", 403),
        Probe("device-read", "GET", f"/device/{PROBE_DEVICE}", 403),
        Probe("layouts", "GET", "/layouts", 403),
        Probe("scenes", "GET", "/scenes", 403),
        Probe("docs", "GET", "/docs", 403),
        Probe("openapi", "GET", "/openapi.json", 403),
        Probe("v3-config", "GET", "/api/v3/config", 403),
        Probe("root", "GET", "/", 403),
        Probe("encoded-wall", "GET", "/%77all", 403),
        Probe("dot-wall", "GET", "/./wall", 403),
        Probe("dotdot-wall", "GET", "/x/../wall", 403),
        Probe("double-slash", "GET", "//wall", 403),
        Probe("client-dotdot-controller", "GET", "/client/%2e%2e/controller/", 403),
        Probe("client-dotdot-wall", "GET", "/client/..%2fwall", 403),
        Probe("client-encoded-dotdot-wall", "GET", "/client/%2e%2e%2fwall", 403),
        Probe("client-double-encoded", "GET", "/client/%252e%252e/wall", 403),
        Probe("client-backslash", "GET", "/client/..%5cwall", 403),
        Probe("asset-dotdot-wall", "GET", "/assets/%2e%2e%2fwall", 403),
        Probe("asset-traversal", "GET", f"/assets/{ZERO_ASSET}/../wall", 403),
    ]
    return allowed, denied


def operator_routes() -> list[Probe]:
    """Unauthenticated operator requests that must be refused by the listener."""
    return [
        Probe("operator-controller", "GET", "/controller/", 401),
        Probe("operator-wall", "GET", "/wall", 401),
        Probe("operator-config", "GET", "/operator-config", 401),
        Probe("operator-diagnostics", "GET", "/diagnostics", 401),
        Probe("operator-media", "GET", "/media", 401),
        Probe("operator-wall-auto", "POST", "/wall/auto", 401),
        Probe("operator-uploads", "POST", "/uploads", 401, body=b"{}",
              headers=(("Content-Type", "application/json"),)),
        Probe("operator-controller-websocket", "GET", "/ws/controller?protocol=2", 401, ws=True),
    ]


# ---------------------------------------------------------------------------
# checks and report
# ---------------------------------------------------------------------------


class Recorder:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []
        self._phases: dict[str, list[bool]] = {}

    def record(self, phase: str, name: str, passed: bool, **detail: Any) -> None:
        self.checks.append(evidence.check_row(name, passed, phase=phase, **detail))
        self._phases.setdefault(phase, []).append(bool(passed))

    def scenarios(self, *, expected: Sequence[str], unobserved: list[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for phase in expected:
            results = self._phases.get(phase)
            if not results:
                rows.append(evidence.scenario_row(
                    phase, "skipped", detail="not observed; see unobserved intervals",
                ))
                unobserved.append(f"scenario {phase}: no observation")
                continue
            failed = [index for index, ok in enumerate(results) if not ok]
            rows.append(evidence.scenario_row(
                phase, "failed" if failed else "passed",
                detail={
                    "checks": len(results),
                    "failed_checks": len(failed),
                    "policy": "TLS and route checks require a verified handshake",
                },
            ))
        for phase, results in self._phases.items():
            if phase in expected:
                continue
            failed = [index for index, ok in enumerate(results) if not ok]
            rows.append(evidence.scenario_row(
                phase, "failed" if failed else "passed",
                detail={"checks": len(results), "failed_checks": len(failed),
                        "optional_vantage": True},
            ))
        return rows


def check_inspection(
    recorder: Recorder, name: str, inspection: Inspection,
    expected_fingerprint: str | None, *, tls_phase: str, cert_phase: str,
    pin: bool,
) -> None:
    detail = inspection.detail()
    origin_label = inspection.origin.normalized
    if inspection.verified:
        recorder.record(
            tls_phase, f"{name}: {origin_label} verified with the named trust store",
            True, detail=detail,
        )
        recorder.record(
            cert_phase, f"{name}: hostname {inspection.origin.host} verified",
            inspection.hostname_verification == "passed",
            detail={"hostname": inspection.origin.host,
                    "hostname_verification": inspection.hostname_verification},
        )
    else:
        recorder.record(
            tls_phase, f"{name}: {origin_label} failed TLS verification", False,
            detail=detail,
        )
        recorder.record(
            cert_phase, f"{name}: hostname verification did not pass", False,
            detail={"hostname": inspection.origin.host,
                    "hostname_verification": inspection.hostname_verification,
                    "error": inspection.error},
        )
    certificate = inspection.certificate
    if certificate is None:
        recorder.record(
            cert_phase, f"{name}: leaf certificate could not be inspected", False,
            detail={"reason": "no certificate was offered or the handshake did not complete"},
        )
        return
    recorder.record(
        cert_phase, f"{name}: leaf SHA-256 {certificate['sha256']}", True,
        detail={
            "subject": certificate["subject"],
            "issuer": certificate["issuer"],
            "subject_alt_names": certificate["subject_alt_names"],
            "chain": inspection.chain,
            "transport_source": inspection.transport_source,
            "decode_error": certificate["decode_error"],
        },
    )
    if not inspection.verified:
        # Validity and pinning cannot turn an untrusted handshake into a pass.
        return
    recorder.record(
        cert_phase, f"{name}: certificate validity window",
        bool(certificate["validity"]["valid_now"]),
        detail={"not_before": certificate["not_before"],
                "not_after": certificate["not_after"],
                **certificate["validity"]},
    )
    if pin and expected_fingerprint:
        match = certificate["sha256"] == expected_fingerprint
        recorder.record(
            cert_phase, f"{name}: leaf fingerprint matches --expect-fingerprint",
            match,
            detail={"expected": expected_fingerprint, "actual": certificate["sha256"]},
        )


def run_vantage(
    recorder: Recorder, vantage: str, origin: Origin, context: ssl.SSLContext,
    timeout: float, parser_note: dict[str, Any],
    expected_fingerprint: str | None, *, primary: bool,
    unobserved: list[str],
) -> None:
    inspection, verified = inspect_origin(origin, context, timeout, parser_note)
    label = "tablet" if primary else vantage
    check_inspection(
        recorder, label, inspection, expected_fingerprint,
        tls_phase="tls" if primary else f"{vantage}-tls",
        cert_phase="certificate" if primary else f"{vantage}-certificate",
        pin=primary,
    )
    suffix_allowed = "tablet-allowed" if primary else f"{vantage}-tablet-allowed"
    suffix_denied = "tablet-denied" if primary else f"{vantage}-tablet-denied"
    suffix_ws = "tablet-websocket" if primary else f"{vantage}-tablet-websocket"
    if not verified:
        for suffix in (suffix_allowed, suffix_denied, suffix_ws):
            unobserved.append(
                f"{suffix}: not run because TLS trust failed for {origin.normalized}"
            )
        return

    allowed, denied = tablet_routes()
    for probe in allowed:
        result = request_probe(origin, context, timeout, probe)
        passed = result.status == probe.expected
        recorder.record(
            suffix_allowed,
            f"{label} {probe.method} {probe.path} -> {probe.expected}",
            passed,
            detail={"route": probe.name, "expected": probe.expected,
                    "actual": result.status, "elapsed_ms": result.duration_ms,
                    "tls_version": result.tls_version, "cipher": result.cipher,
                    "error": result.error},
        )
        if probe.ws:
            recorder.record(
                suffix_ws,
                f"{label} WS upgrade {probe.path} -> {probe.expected}",
                passed,
                detail={"route": probe.name, "expected": probe.expected,
                        "actual": result.status, "tls_version": result.tls_version,
                        "cipher": result.cipher, "error": result.error},
            )
    for probe in denied:
        result = request_probe(origin, context, timeout, probe)
        passed = result.status == probe.expected
        recorder.record(
            suffix_denied,
            f"{label} {probe.method} {probe.path} -> {probe.expected}",
            passed,
            detail={"route": probe.name, "expected": probe.expected,
                    "actual": result.status, "elapsed_ms": result.duration_ms,
                    "tls_version": result.tls_version, "cipher": result.cipher,
                    "error": result.error},
        )


def run_operator(
    recorder: Recorder, origin: Origin, context: ssl.SSLContext, timeout: float,
    parser_note: dict[str, Any], *, unobserved: list[str],
) -> None:
    inspection, verified = inspect_origin(origin, context, timeout, parser_note)
    check_inspection(
        recorder, "operator", inspection, None,
        tls_phase="operator-tls", cert_phase="operator-tls", pin=False,
    )
    if not verified:
        for phase in ("operator-auth", "operator-websocket"):
            unobserved.append(f"{phase}: not run because operator TLS trust failed")
        return
    for probe in operator_routes():
        result = request_probe(origin, context, timeout, probe)
        passed = result.status == probe.expected
        recorder.record(
            "operator-websocket" if probe.ws else "operator-auth",
            f"operator {probe.method} {probe.path} -> {probe.expected}",
            passed,
            detail={"route": probe.name, "expected": probe.expected,
                    "actual": result.status, "elapsed_ms": result.duration_ms,
                    "tls_version": result.tls_version, "cipher": result.cipher,
                    "error": result.error},
        )


def build_report_from_recorder(
    recorder: Recorder, *, started_at: str, evidence_kind: str,
    tools: dict[str, Any], artifacts: dict[str, dict[str, Any]],
    cohort: list[str], expected: Sequence[str], unobserved: list[str],
    limitations: list[str], error: dict[str, Any] | None,
) -> dict[str, Any]:
    scenarios = recorder.scenarios(expected=expected, unobserved=unobserved)
    return evidence.build_report(
        tool=TOOL,
        tool_version=TOOL_VERSION,
        gate=GATE,
        evidence_kind=evidence_kind,
        started_at=started_at,
        checks=recorder.checks,
        scenarios=scenarios,
        expected_scenarios=list(expected),
        tools=tools,
        artifacts=artifacts,
        cohort=cohort,
        skipped=[],
        unobserved=unobserved,
        limitations=limitations,
        error=error,
        repository=evidence.repository_state(ROOT),
    )


def _limitations(identity: dict[str, Any]) -> list[str]:
    return [
        "A supplied CA bundle proves verifier trust only; installed tablet/browser "
        "trust is a separate operator step.",
        f"Trust store exercised: {identity['label']} "
        f"({identity['kind']}; system_roots_loaded={identity['system_roots_loaded']}).",
        "Route checks ran from this verification host, not from a tablet or a "
        "second physical LAN vantage.",
        "A real browser must open the tablet origin with no certificate warning "
        "while WAN is absent; this tool cannot observe the browser UI.",
        "Backend port binding and firewall reachability are outside this probe; "
        "only paths through the tested ingress were exercised.",
        "The negative matrix proves this ingress configuration and certificate; "
        "it does not generalize to another deployment.",
    ]


def run(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    started_at = evidence.iso_now()
    parser_note: dict[str, Any] = {}
    recorder = Recorder()
    unobserved: list[str] = [
        "installed tablet/browser certificate trust: manual",
        "no-warning browser visit with WAN absent: manual",
        "registration, WebSocket welcome and content on a real tablet: manual",
        "direct backend-port reachability and firewall rules from the LAN: manual",
    ]
    tools: dict[str, Any] = {
        "python": sys.version.split()[0],
        "openssl": ssl.OPENSSL_VERSION,
        "timeout_s": args.timeout,
        "route_matrix_source": (
            "deploy/smoke.sh expectations re-implemented with verified Python TLS; "
            "no -k or insecure switch is accepted"
        ),
        "certificate_parser": parser_note,
        "vantages": [
            {"id": "tablet", "origin": args.tablet_origin.normalized, "tested": False},
            {"id": "ipv6", "origin": (args.ipv6_tablet_origin.normalized
                                      if args.ipv6_tablet_origin else None),
             "tested": False},
            {"id": "second-vantage", "origin": (args.second_vantage_tablet_origin.normalized
                                                if args.second_vantage_tablet_origin else None),
             "tested": False},
        ],
    }
    error: dict[str, Any] | None = None
    identity: dict[str, Any] = {"kind": "unresolved", "label": "unresolved",
                                "system_roots_loaded": None, "proves": "nothing"}
    artifacts: dict[str, dict[str, Any]] = {}
    cohort = [args.tablet_origin.normalized, args.operator_origin.normalized]

    try:
        context, identity = build_context(args.ca_file)
        tools["trust_store"] = identity
        if identity.get("path"):
            artifacts = evidence.artifact_hashes([Path(identity["path"])])
    except (OSError, ssl.SSLError, ValueError) as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
        recorder.record("tls", f"trust store could not be loaded: {identity['label']}", False,
                        trust_store=identity, error=error)
        report = build_report_from_recorder(
            recorder, started_at=started_at, evidence_kind=args.evidence_kind,
            tools=tools, artifacts=artifacts, cohort=cohort,
            expected=PHASES, unobserved=unobserved,
            limitations=_limitations(identity) + [
                "No TLS or route check ran because the trust store could not be loaded.",
            ],
            error=error,
        )
        return report, identity

    if args.tablet_origin.normalized == args.operator_origin.normalized:
        error = {"type": "OriginError", "message": "tablet and operator origins must differ"}
        recorder.record("tls", "tablet and operator origins are distinct", False,
                        detail={"origin": args.tablet_origin.normalized})
        report = build_report_from_recorder(
            recorder, started_at=started_at, evidence_kind=args.evidence_kind,
            tools=tools, artifacts=artifacts, cohort=cohort,
            expected=PHASES, unobserved=unobserved,
            limitations=_limitations(identity), error=error,
        )
        return report, identity

    run_vantage(
        recorder, "tablet", args.tablet_origin, context, args.timeout, parser_note,
        args.expect_fingerprint, primary=True, unobserved=unobserved,
    )
    tools["vantages"][0]["tested"] = True
    vantages = [args.tablet_origin]
    if args.ipv6_tablet_origin is not None:
        if (args.ipv6_tablet_origin.address is None
                or args.ipv6_tablet_origin.address.version != 6):
            recorder.record(
                "ipv6-tls", "IPv6 vantage origin is an IPv6 literal", False,
                detail={"origin": args.ipv6_tablet_origin.normalized},
            )
            unobserved.append("IPv6 tablet vantage: supplied origin is not an IPv6 literal")
        else:
            vantages.append(args.ipv6_tablet_origin)
            run_vantage(
                recorder, "ipv6", args.ipv6_tablet_origin, context, args.timeout,
                parser_note, None, primary=False, unobserved=unobserved,
            )
            tools["vantages"][1]["tested"] = True
    if args.second_vantage_tablet_origin is not None:
        if args.second_vantage_tablet_origin.normalized in {v.normalized for v in vantages}:
            recorder.record(
                "second-vantage-tls", "second vantage differs from the primary", False,
                detail={"origin": args.second_vantage_tablet_origin.normalized},
            )
        else:
            run_vantage(
                recorder, "second-vantage", args.second_vantage_tablet_origin, context,
                args.timeout, parser_note, None, primary=False, unobserved=unobserved,
            )
            tools["vantages"][2]["tested"] = True

    run_operator(
        recorder, args.operator_origin, context, args.timeout, parser_note,
        unobserved=unobserved,
    )
    if args.ipv6_tablet_origin is None:
        unobserved.append("IPv6 tablet vantage: not supplied (--ipv6-tablet-origin)")
    if args.second_vantage_tablet_origin is None:
        unobserved.append("second LAN vantage: not supplied (--second-vantage-tablet-origin)")

    report = build_report_from_recorder(
        recorder, started_at=started_at, evidence_kind=args.evidence_kind,
        tools=tools, artifacts=artifacts, cohort=cohort,
        expected=PHASES, unobserved=unobserved,
        limitations=_limitations(identity), error=error,
    )
    return report, identity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trust_check.py",
        description=(
            "Verify the tablet and operator origins with a named trust store and "
            "probe the two-origin route matrix without -k. A supplied CA proves "
            "verifier trust only; installed tablet trust stays manual."
        ),
    )
    parser.add_argument("--tablet-origin", type=origin_argument, required=True,
                        help="bare https origin served by the tablet listener")
    parser.add_argument("--operator-origin", type=origin_argument, required=True,
                        help="bare https origin served by the operator listener")
    parser.add_argument("--ca-file", default=None,
                        help="PEM CA bundle to verify with; omitted means the system default store")
    parser.add_argument("--expect-fingerprint", type=fingerprint_argument, default=None,
                        help="expected leaf SHA-256 (colons/spaces allowed)")
    parser.add_argument("--json-out", required=True,
                        help="path for the evidence JSON report")
    parser.add_argument("--timeout", type=positive_timeout, default=DEFAULT_TIMEOUT,
                        help=f"per-connection timeout in seconds (default {DEFAULT_TIMEOUT})")
    parser.add_argument("--evidence-kind", choices=("disposable-ingress", "operator-hardware"),
                        default="disposable-ingress",
                        help="evidence kind for the report (default disposable-ingress)")
    parser.add_argument("--ipv6-tablet-origin", type=origin_argument, default=None,
                        help="optional IPv6 literal vantage for the same tablet route matrix")
    parser.add_argument("--second-vantage-tablet-origin", type=origin_argument, default=None,
                        help="optional second LAN vantage for the same tablet route matrix")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    report, identity = run(args)
    out = Path(args.json_out)
    evidence.write_report(out, report)
    digest = evidence.file_sha256(out)
    print(f"trust-check: {report['completion']} "
          f"({report['checks_passed']}/{report['checks_total']} checks, "
          f"{report['scenarios_passed']}/{report['scenarios_total']} scenarios)")
    for reason in report["failure_reasons"]:
        print(f"FAIL {reason}")
    if report["unobserved"]:
        print(f"unobserved: {len(report['unobserved'])} item(s)")
    print(f"trust store: {identity['label']} ({identity['kind']})")
    print(f"report: {out} sha256:{digest}")
    return 0 if report["completion"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
