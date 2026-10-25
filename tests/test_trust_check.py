"""Verified-TLS trust/origin probe: no bypass, explicit trust store, real routes.

Every HTTPS fixture is a local loopback server with a freshly generated CA and
leaf. The tests prove the tool's claims rather than a deployment's:

* an untrusted certificate fails closed -- the reachable route matrix is not
  silently reported as passing;
* a supplied CA is named as verifier trust only, never as tablet trust;
* the allowed and denied route expectations mirror ``deploy/smoke.sh``;
* hostname failure and a wrong fingerprint are separate, visible failures.

Nothing here creates a tablet or claims the installed-ca-trust gate.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import ssl
import subprocess
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

from deploy import trust_check
from tools.validation import evidence

OPENSSL = shutil.which("openssl")


# ---------------------------------------------------------------------------
# local PKI
# ---------------------------------------------------------------------------


def _run(*args: str) -> None:
    done = subprocess.run([OPENSSL, *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"openssl {' '.join(args)} failed: {done.stderr}")


def _leaf(directory: Path, name: str, san: str) -> tuple[Path, Path, Path]:
    key = directory / f"{name}.key"
    csr = directory / f"{name}.csr"
    cert = directory / f"{name}.pem"
    extension = directory / f"{name}.cnf"
    extension.write_text(
        f"subjectAltName={san}\n"
        "basicConstraints=CA:FALSE\n"
        "keyUsage=digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        "subjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid,issuer\n"
    )
    _run("req", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
         "-out", str(csr), "-subj", "/CN=127.0.0.1")
    _run("x509", "-req", "-in", str(csr), "-CA", str(directory / "ca.pem"),
         "-CAkey", str(directory / "ca.key"), "-CAcreateserial", "-days", "2",
         "-sha256", "-extfile", str(extension), "-out", str(cert))
    return key, cert, extension


@pytest.fixture(scope="module")
def pki(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path | str]:
    if OPENSSL is None:
        pytest.skip("openssl CLI is required for the local PKI fixture")
    directory = tmp_path_factory.mktemp("trust-pki")
    ca_key = directory / "ca.key"
    ca = directory / "ca.pem"
    _run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
         "-sha256", "-keyout", str(ca_key), "-out", str(ca),
         "-subj", "/CN=Tablet Wall Test Root",
         "-addext", "basicConstraints=critical,CA:TRUE",
         "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    key, cert, _ = _leaf(directory, "leaf", "IP:127.0.0.1,DNS:localhost")
    wrong_key, wrong_cert, _ = _leaf(directory, "wrong", "DNS:wrong.test")
    chain = directory / "chain.pem"
    chain.write_text(cert.read_text() + ca.read_text())
    wrong_chain = directory / "wrong-chain.pem"
    wrong_chain.write_text(wrong_cert.read_text() + ca.read_text())
    return {
        "dir": directory,
        "ca": ca,
        "ca_key": ca_key,
        "leaf_key": key,
        "leaf": cert,
        "chain": chain,
        "wrong_chain": wrong_chain,
        "wrong_key": wrong_key,
        "leaf_der": ssl.PEM_cert_to_DER_cert(cert.read_text()),
    }


# ---------------------------------------------------------------------------
# local ingress double
# ---------------------------------------------------------------------------


def _expected_status(method: str, path: str) -> int:
    allowed, denied = trust_check.tablet_routes()
    for probe in (*allowed, *denied):
        if probe.method == method and probe.path == path:
            return probe.expected
    return 403


def _handler(role: str, *, leak: bool, operator_ok: bool):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:  # noqa: D401 - silence the test log
            return

        def _serve(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            if role == "operator":
                status = 200 if operator_ok else 401
            elif leak and self.path.split("?", 1)[0] in ("/media", "/diagnostics"):
                status = 200
            else:
                status = _expected_status(self.command, self.path)
            if status == 101:
                self.send_response(101, "Switching Protocols")
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.end_headers()
                return
            body = b""
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            if body:
                self.wfile.write(body)
            self.close_connection = True

        do_GET = _serve
        do_POST = _serve
        do_PUT = _serve
        do_DELETE = _serve

    return Handler


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        # Probe clients close early (especially after 101); that is expected.
        return


def _start(handler, chain: Path, key: Path) -> ThreadingHTTPServer:
    server = _QuietServer(("127.0.0.1", 0), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(chain), str(key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _origin(server: ThreadingHTTPServer) -> str:
    return f"https://127.0.0.1:{server.server_address[1]}"


@contextmanager
def ingress(pki: dict[str, Path | str], *, leak: bool = False,
            operator_ok: bool = False, tablet_chain: str | None = None,
            tablet_key: str = "leaf_key") -> Iterator[tuple[str, str]]:
    chain = Path(pki[tablet_chain or "chain"])
    tablet = _start(_handler("tablet", leak=leak, operator_ok=False),
                    chain, Path(pki[tablet_key]))
    operator = _start(_handler("operator", leak=False, operator_ok=operator_ok),
                      Path(pki["chain"]), Path(pki["leaf_key"]))
    try:
        yield _origin(tablet), _origin(operator)
    finally:
        for server in (tablet, operator):
            server.shutdown()
            server.server_close()


def _run_cli(tmp_path: Path, tablet: str, operator: str, *extra: str) -> tuple[int, Path]:
    out = tmp_path / "trust.json"
    code = trust_check.main([
        "--tablet-origin", tablet,
        "--operator-origin", operator,
        "--json-out", str(out),
        "--timeout", "3",
        *extra,
    ])
    return code, out


# ---------------------------------------------------------------------------
# URL, fingerprint and trust-store units
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "host", "port", "normalized"),
    [
        ("https://192.168.137.1:8443", "192.168.137.1", 8443,
         "https://192.168.137.1:8443"),
        ("https://localhost:8444/", "localhost", 8444, "https://localhost:8444"),
        ("https://[fd00::1]:8443", "fd00::1", 8443, "https://[fd00::1]:8443"),
        ("https://tablet.example", "tablet.example", 443,
         "https://tablet.example:443"),
    ],
)
def test_origins_are_parsed_into_one_unambiguous_https_form(
    value: str, host: str, port: int, normalized: str,
) -> None:
    origin = trust_check.parse_origin(value)
    assert (origin.host, origin.port, origin.normalized) == (host, port, normalized)
    assert origin.host_header == (f"[{host}]" if ":" in host else host)


@pytest.mark.parametrize(
    "value",
    [
        "http://192.168.137.1:8443",
        "https://192.168.137.1:8443/client/",
        "https://192.168.137.1:8443?x=1",
        "https://192.168.137.1:8443#fragment",
        "https://user:pass@192.168.137.1:8443",
        "https://",
        "ftp://192.168.137.1:8443",
        "https://host:0",
        "https://host:70000",
        "https://bad_host:8443",
        " https://host:8443",
        "https://host:8443 ",
    ],
)
def test_ambiguous_or_insecure_origins_are_rejected(value: str) -> None:
    with pytest.raises(trust_check.OriginError):
        trust_check.parse_origin(value)


def test_fingerprint_normalization_strips_common_separators() -> None:
    bare = "ab" * 32
    assert trust_check.normalize_fingerprint(bare) == bare
    assert trust_check.normalize_fingerprint(bare.upper()) == bare
    assert trust_check.normalize_fingerprint(
        ":".join(bare[i:i + 2] for i in range(0, 64, 2))) == bare
    assert trust_check.normalize_fingerprint(
        " ".join(bare[i:i + 8] for i in range(0, 64, 8))) == bare
    for bad in ("", "abc", "zz" * 32, bare[:-1], bare + "0"):
        with pytest.raises(ValueError):
            trust_check.normalize_fingerprint(bad)


def test_the_parser_offers_no_insecure_or_bypass_switch() -> None:
    parser = trust_check.build_parser()
    assert "insecure" not in parser.format_help().lower()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "--tablet-origin", "https://127.0.0.1:1",
            "--operator-origin", "https://127.0.0.1:2",
            "--json-out", "/tmp/x.json",
            "--insecure",
        ])


def test_trust_store_identity_names_the_store_actually_loaded(pki: dict[str, Path | str]) -> None:
    system_context, system = trust_check.build_context(None)
    assert system["kind"] == "system-default"
    assert system["system_roots_loaded"] is True
    assert "verifier trust" in system["proves"]
    assert system_context.check_hostname is True
    assert system_context.verify_mode == ssl.CERT_REQUIRED
    assert system["cert_store_stats"]["x509"] >= 1

    supplied_context, supplied = trust_check.build_context(str(pki["ca"]))
    assert supplied["kind"] == "supplied-ca-bundle"
    assert supplied["path"] == str(pki["ca"])
    assert supplied["sha256"] == hashlib.sha256(Path(pki["ca"]).read_bytes()).hexdigest()
    assert supplied["system_roots_loaded"] is False
    assert "installed tablet" in supplied["proves"]
    assert supplied_context.check_hostname is True
    assert supplied_context.verify_mode == ssl.CERT_REQUIRED


def test_certificate_parsing_records_chain_subjects_issuers_sans_and_validity(
    pki: dict[str, Path | str],
) -> None:
    note: dict[str, str] = {}
    leaf = trust_check.certificate_view(pki["leaf_der"], parser_note=note)
    assert leaf["subject"] == "commonName=127.0.0.1"
    assert leaf["issuer"] == "commonName=Tablet Wall Test Root"
    assert leaf["self_signed"] is False
    assert "IP Address:127.0.0.1" in leaf["subject_alt_names"]
    assert "DNS:localhost" in leaf["subject_alt_names"]
    assert leaf["validity"]["valid_now"] is True
    assert leaf["validity"]["expires_in_days"] > 0
    assert leaf["sha256"] == hashlib.sha256(pki["leaf_der"]).hexdigest()
    assert note["parser"] == "python-ssl-stdlib"

    ca_der = ssl.PEM_cert_to_DER_cert(Path(pki["ca"]).read_text())
    ca = trust_check.certificate_view(ca_der, parser_note={})
    assert ca["self_signed"] is True
    assert ca["subject"] == ca["issuer"] == "commonName=Tablet Wall Test Root"


# ---------------------------------------------------------------------------
# end-to-end dry runs
# ---------------------------------------------------------------------------


def test_a_verified_disposable_ingress_run_is_complete_but_never_tablet_trust(
    pki: dict[str, Path | str], tmp_path: Path,
) -> None:
    fingerprint = " ".join(
        hashlib.sha256(pki["leaf_der"]).hexdigest()[i:i + 8] for i in range(0, 64, 8)
    )
    with ingress(pki) as (tablet, operator):
        code, out = _run_cli(
            tmp_path, tablet, operator,
            "--ca-file", str(pki["ca"]),
            "--expect-fingerprint", fingerprint,
        )
    assert code == 0
    report = evidence.load_report(out)
    assert report["completion"] == "complete"
    assert report["gate"] == "installed-ca-trust"
    assert report["evidence_kind"] == "disposable-ingress"
    assert report["hardware_gate_status"] == "MISSING"
    assert report["hardware_claim"] is False
    assert report["failure_reasons"] == []
    assert report["checks_total"] >= 40
    assert report["scenarios_passed"] == report["scenarios_total"]

    store = report["tools"]["trust_store"]
    assert store["kind"] == "supplied-ca-bundle"
    assert store["system_roots_loaded"] is False
    assert store["sha256"] == hashlib.sha256(Path(pki["ca"]).read_bytes()).hexdigest()
    assert report["artifacts"][str(pki["ca"])]["sha256"] == store["sha256"]

    names = {check["name"] for check in report["checks"]}
    assert any("tablet GET /media -> 403" in name for name in names)
    assert any("tablet POST /uploads -> 403" in name for name in names)
    assert any("tablet GET /diagnostics -> 403" in name for name in names)
    assert any("tablet GET /assets -> 403" in name for name in names)
    assert any("tablet GET /rebind -> 403" in name for name in names)
    assert any("tablet POST /devices/00000000-0000-4000-8000-000000000001/rebind -> 403"
               in name for name in names)
    assert any("tablet GET /client/ -> 200" in name for name in names)
    assert any("tablet GET /assets/sha256:" in name and "-> 404" in name for name in names)
    assert any("operator GET /wall -> 401" in name for name in names)
    assert any("WS upgrade" in name and "-> 101" in name for name in names)

    detail = next(check["detail"] for check in report["checks"]
                  if check["name"].startswith("tablet: leaf SHA-256"))
    assert detail["subject"] == "commonName=127.0.0.1"
    assert detail["issuer"] == "commonName=Tablet Wall Test Root"
    assert detail["chain"][-1]["self_signed"] is True
    assert detail["transport_source"] == "verified-handshake"

    limitations = " ".join(report["limitations"]).lower()
    assert "verifier trust" in limitations
    assert "installed tablet" in limitations
    assert "wan" in limitations
    unobserved = " ".join(report["unobserved"]).lower()
    assert "ipv6" in unobserved and "second lan vantage" in unobserved
    vantages = {row["id"]: row for row in report["tools"]["vantages"]}
    assert vantages["ipv6"]["tested"] is False
    assert vantages["second-vantage"]["tested"] is False


def test_an_untrusted_server_fails_closed_and_never_borrows_the_route_matrix(
    pki: dict[str, Path | str], tmp_path: Path,
) -> None:
    with ingress(pki) as (tablet, operator):
        code, out = _run_cli(tmp_path, tablet, operator)
    assert code == 1
    report = evidence.load_report(out)
    assert report["completion"] == "incomplete"
    assert report["tools"]["trust_store"]["kind"] == "system-default"
    tls_checks = [check for check in report["checks"]
                  if check["name"].startswith("tablet:")
                  and "failed TLS verification" in check["name"]]
    assert tls_checks and tls_checks[0]["passed"] is False
    assert "Hostname" in json.dumps(tls_checks[0]) or "self-signed" in json.dumps(tls_checks[0])

    # The certificate was described by an unverified diagnostic peek and is
    # labelled as such; the route matrix was not graded through a bypass.
    leaf = next(check for check in report["checks"]
                if check["name"].startswith("tablet: leaf SHA-256"))
    assert leaf["detail"]["transport_source"] == "unverified-diagnostic-handshake"
    assert not any("tablet GET /client/ -> 200" == check["name"]
                   for check in report["checks"])
    tablet_scenarios = [row for row in report["scenarios"]
                        if row["id"].startswith("tablet-")]
    assert tablet_scenarios and all(row["status"] == "skipped" for row in tablet_scenarios)
    assert any("installed tablet" in item for item in report["limitations"])


def test_a_wrong_pinned_fingerprint_fails_while_tls_remains_verified(
    pki: dict[str, Path | str], tmp_path: Path,
) -> None:
    with ingress(pki) as (tablet, operator):
        code, out = _run_cli(
            tmp_path, tablet, operator,
            "--ca-file", str(pki["ca"]),
            "--expect-fingerprint", "00" * 32,
        )
    assert code == 1
    report = evidence.load_report(out)
    assert report["completion"] == "incomplete"
    pin = next(check for check in report["checks"]
               if "matches --expect-fingerprint" in check["name"])
    assert pin["passed"] is False
    assert pin["detail"]["expected"] == "00" * 32
    assert any("failed TLS verification" in check["name"]
               for check in report["checks"]) is False


def test_a_leaky_tablet_ingress_fails_the_denied_routes(
    pki: dict[str, Path | str], tmp_path: Path,
) -> None:
    with ingress(pki, leak=True) as (tablet, operator):
        code, out = _run_cli(tmp_path, tablet, operator, "--ca-file", str(pki["ca"]))
    assert code == 1
    report = evidence.load_report(out)
    assert report["completion"] == "incomplete"
    failed = {check["name"] for check in report["checks"] if not check["passed"]}
    assert any("/media -> 403" in name for name in failed)
    assert any("/diagnostics -> 403" in name for name in failed)
    assert any("/uploads -> 403" in name for name in failed) is False


def test_an_unauthenticated_operator_listener_fails_the_auth_matrix(
    pki: dict[str, Path | str], tmp_path: Path,
) -> None:
    with ingress(pki, operator_ok=True) as (tablet, operator):
        code, out = _run_cli(tmp_path, tablet, operator, "--ca-file", str(pki["ca"]))
    assert code == 1
    report = evidence.load_report(out)
    failed = {check["name"] for check in report["checks"] if not check["passed"]}
    assert any("operator GET /wall -> 401" in name for name in failed)
    assert any("operator GET /ws/controller?protocol=2 -> 401" in name for name in failed)


def test_hostname_mismatch_is_reported_as_its_own_failure(
    pki: dict[str, Path | str], tmp_path: Path,
) -> None:
    with ingress(pki, tablet_chain="wrong_chain",
                 tablet_key="wrong_key") as (tablet, operator):
        code, out = _run_cli(tmp_path, tablet, operator, "--ca-file", str(pki["ca"]))
    assert code == 1
    report = evidence.load_report(out)
    host = next(check for check in report["checks"]
                if check["name"].startswith("tablet: hostname"))
    assert host["passed"] is False
    assert host["detail"]["hostname_verification"] == "failed"
    tls = next(check for check in report["checks"]
               if "failed TLS verification" in check["name"])
    assert tls["detail"]["error"]["verify_code"] in (62, 64)


def test_a_supplied_second_vantage_runs_its_own_matrix(
    pki: dict[str, Path | str], tmp_path: Path,
) -> None:
    extra = None
    with ingress(pki) as (tablet, operator):
        extra = _start(_handler("tablet", leak=False, operator_ok=False),
                       Path(pki["chain"]), Path(pki["leaf_key"]))
        try:
            code, out = _run_cli(
                tmp_path, tablet, operator,
                "--ca-file", str(pki["ca"]),
                "--second-vantage-tablet-origin", _origin(extra),
            )
        finally:
            extra.shutdown()
            extra.server_close()
    assert code == 0
    report = evidence.load_report(out)
    assert report["completion"] == "complete"
    vantages = {row["id"]: row for row in report["tools"]["vantages"]}
    assert vantages["second-vantage"]["tested"] is True
    assert any(row["id"] == "second-vantage-tablet-allowed"
               and row["status"] == "passed" for row in report["scenarios"])
    assert any("second-vantage GET /media -> 403" in check["name"]
               for check in report["checks"])


def test_an_ipv4_argument_cannot_masquerade_as_the_ipv6_vantage(
    pki: dict[str, Path | str], tmp_path: Path,
) -> None:
    with ingress(pki) as (tablet, operator):
        code, out = _run_cli(
            tmp_path, tablet, operator,
            "--ca-file", str(pki["ca"]),
            "--ipv6-tablet-origin", "https://127.0.0.1:8443",
        )
    assert code == 1
    report = evidence.load_report(out)
    check = next(check for check in report["checks"]
                 if "IPv6 vantage origin" in check["name"])
    assert check["passed"] is False
    assert any("IPv6" in item for item in report["unobserved"])


def test_a_trust_store_that_cannot_be_loaded_fails_with_an_explicit_error(
    pki: dict[str, Path | str], tmp_path: Path,
) -> None:
    with ingress(pki) as (tablet, operator):
        code, out = _run_cli(
            tmp_path, tablet, operator,
            "--ca-file", str(tmp_path / "missing-ca.pem"),
        )
    assert code == 1
    report = evidence.load_report(out)
    assert report["completion"] == "incomplete"
    assert report["error"]["type"] in {"FileNotFoundError", "SSLError"}
    assert "could not be loaded" in report["failure_reasons"][0]


def test_the_same_origin_for_both_roles_is_rejected_before_probing(
    pki: dict[str, Path | str], tmp_path: Path,
) -> None:
    with ingress(pki) as (tablet, _):
        code, out = _run_cli(tmp_path, tablet, tablet, "--ca-file", str(pki["ca"]))
    assert code == 1
    report = evidence.load_report(out)
    assert report["error"]["type"] == "OriginError"
    assert report["completion"] == "incomplete"
