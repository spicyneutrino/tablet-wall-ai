"""Tests for the optional operator-Origin guard in ``main.py`` (Phase 3a).

The guard is **defense-in-depth, not authentication**: it proves only that a
write came from the operator page's browser origin, and there is no identity,
credential, or token scheme anywhere behind it. These tests therefore pin the
fence's own contract and nothing else:

* unset (the default) means the app behaves exactly as it did before it
  existed — nothing is required of a caller, so direct ``make dev`` is
  unchanged;
* when ``TABLET_WALL_OPERATOR_ORIGIN`` is set, every state-changing HTTP
  request and the ``/ws/controller`` handshake must present exactly that
  ``Origin``, byte for byte, or be refused with 403 (an HTTP 403 handshake for
  the socket) *before* anything is parsed, committed, persisted, or
  broadcast;
* ``POST /devices/register`` stays reachable — a tablet registers from the
  tablet origin and can never show the operator's;
* a configured value that is not exactly ``scheme://host[:port]`` fails
  closed rather than silently switching the guard off (or on in a way that
  could match the wrong caller);
* ``GET /operator-config`` reports ``TABLET_WALL_TABLET_ORIGIN`` as a value or
  ``null``, and refuses to invent an answer when the value is unusable.
"""

import pytest
from starlette.testclient import WebSocketDenialResponse

import main

OPERATOR_ORIGIN = "https://operator.wall.test"
HOSTILE_ORIGIN = "https://attacker.invalid"
DEVICE_ID = "0f8fad5b-d9cb-469f-a165-70867728950e"

MISSING_ORIGIN_DETAIL = (
    "Origin is missing or does not match the operator origin"
)


@pytest.fixture(autouse=True)
def clean_origin_env(monkeypatch):
    """Every case starts with neither origin configured, whatever the shell holds.

    The guard reads the environment per request, so an exported
    ``TABLET_WALL_OPERATOR_ORIGIN`` in the shell running ``pytest`` would
    otherwise decide these tests — and every other test in the suite —
    behind our back.
    """
    monkeypatch.delenv(main.OPERATOR_ORIGIN_ENV, raising=False)
    monkeypatch.delenv(main.TABLET_ORIGIN_ENV, raising=False)


def enable_guard(monkeypatch, value: str = OPERATOR_ORIGIN) -> None:
    monkeypatch.setenv(main.OPERATOR_ORIGIN_ENV, value)


def revision(client) -> int:
    return client.get("/wall").json()["revision"]


def call(client, method: str, path: str, origin: str | None = None, **kwargs):
    """One request, optionally carrying ``origin`` as its Origin header."""
    headers = dict(kwargs.pop("headers", {}))
    if origin is not None:
        headers["Origin"] = origin
    if headers:
        kwargs["headers"] = headers
    return getattr(client, method)(path, **kwargs)


# A spread of state-changing requests: a bodyless POST, a POST whose body is
# optional, a JSON-bodied PUT/POST, a DELETE, and a bodyless snapshot recall.
# Each entry is (method, path, kwargs).
WRITE_CASES = [
    ("post", "/wall/auto", {}),
    ("post", "/layouts/probe/recall", {}),
    ("put", "/wall", {"json": {"width": 4001}}),
    ("put", "/scene", {"json": {"content": {"type": "color"}}}),
    ("post", "/devices/color", {"json": {"color": "#3b82f6"}}),
    ("delete", f"/devices/{DEVICE_ID}", {}),
]


class TestGuardInactiveWhenUnset:
    """No variable, no guard: the pre-Phase-3a app is intact."""

    @pytest.mark.parametrize(("method", "path", "kwargs"), WRITE_CASES)
    def test_writes_need_no_origin(self, client, device_payload, method, path, kwargs):
        client.post("/devices/register", json=device_payload)

        response = call(client, method, path, **kwargs)

        assert response.status_code != 403, (
            "with TABLET_WALL_OPERATOR_ORIGIN unset nothing may answer 403"
        )

    def test_writes_succeed_and_move_the_revision(self, client):
        before = revision(client)

        assert client.put("/wall", json={"width": 4001}).status_code == 200
        assert client.post("/wall/auto").status_code == 200

        assert revision(client) > before

    def test_controller_socket_needs_no_origin(self, client):
        with client.websocket_connect("/ws/controller") as controller:
            frame = controller.receive_json()

        assert frame["type"] == "snapshot"

    def test_an_empty_variable_is_the_same_as_unset(self, client, monkeypatch):
        """``TABLET_WALL_OPERATOR_ORIGIN=`` is how a manifest switches it off."""
        monkeypatch.setenv(main.OPERATOR_ORIGIN_ENV, "")

        assert client.post("/wall/auto").status_code == 200
        with client.websocket_connect("/ws/controller") as controller:
            assert controller.receive_json()["type"] == "snapshot"


class TestAuthorizedRequests:
    """A matching Origin changes nothing: the caller gets the real answer."""

    @pytest.fixture
    def guarded(self, client, monkeypatch):
        enable_guard(monkeypatch)
        return client

    def test_json_body_put(self, guarded):
        before = revision(guarded)

        response = call(guarded, "put", "/wall", OPERATOR_ORIGIN, json={"width": 4001})

        assert response.status_code == 200
        assert response.json()["width"] == 4001
        assert revision(guarded) == before + 1

    def test_bodyless_auto_post(self, guarded, device_payload):
        guarded.post("/devices/register", json=device_payload)
        before = revision(guarded)

        response = call(guarded, "post", "/wall/auto", OPERATOR_ORIGIN)

        # Offline devices keep whatever they had, so an unconnected roster
        # still commits an arrangement — and only the fence's own answer may
        # differ from an unguarded run.
        assert response.status_code == 200
        assert revision(guarded) == before + 1

    def test_bodyless_recall_post(self, guarded):
        assert call(guarded, "put", "/layouts/base", OPERATOR_ORIGIN).status_code == 200
        before = revision(guarded)

        response = call(guarded, "post", "/layouts/base/recall", OPERATOR_ORIGIN)

        assert response.status_code == 200
        assert revision(guarded) == before + 1

    def test_delete(self, guarded, device_payload):
        guarded.post("/devices/register", json=device_payload)

        response = call(guarded, "delete", f"/devices/{DEVICE_ID}", OPERATOR_ORIGIN)

        assert response.status_code == 200
        assert response.json() == {"removed": True, "device_id": DEVICE_ID}

    @pytest.mark.parametrize(
        ("method", "path", "kwargs"),
        [
            ("post", "/wall/auto", {"content": b"", "headers": {"Content-Type": "application/json"}}),
            ("put", "/wall", {"content": b"", "headers": {"Content-Type": "application/json"}}),
            ("put", "/wall", {"json": {"width": -5}}),
            ("put", "/wall", {"content": b"{not json", "headers": {"Content-Type": "application/json"}}),
            ("post", "/layouts/probe/recall", {}),
        ],
    )
    def test_guard_only_adds_403s(
        self, client, monkeypatch, method, path, kwargs
    ):
        """Same request with the guard off and with a matching Origin: identical.

        A JSON content type with no body at all, a body that is not JSON, and
        a body that fails validation must all reach the route exactly as they
        did before the guard existed. The fence decides from the ``Origin``
        header alone; it never inspects, requires, or alters a body.
        """
        off = call(client, method, path, **kwargs).status_code

        enable_guard(monkeypatch)
        on = call(client, method, path, OPERATOR_ORIGIN, **kwargs).status_code

        assert on == off


class TestDeniedRequests:
    """Missing or wrong Origin: 403, and nothing else happens."""

    @pytest.fixture
    def guarded(self, client, monkeypatch):
        enable_guard(monkeypatch)
        return client

    @pytest.mark.parametrize(("method", "path", "kwargs"), WRITE_CASES)
    def test_missing_origin_is_403(self, guarded, device_payload, method, path, kwargs):
        guarded.post("/devices/register", json=device_payload)
        before = revision(guarded)

        response = call(guarded, method, path, **kwargs)

        assert response.status_code == 403
        assert response.json() == {"detail": MISSING_ORIGIN_DETAIL}
        assert revision(guarded) == before

    @pytest.mark.parametrize(
        "origin",
        [
            HOSTILE_ORIGIN,
            # Trailing slash: an origin never has a path, so this is a
            # different (and unsendable) value, not the same one.
            OPERATOR_ORIGIN + "/",
            # The literal a sandboxed iframe or file:// page sends.
            "null",
            # Right host, wrong scheme / wrong port / look-alike host.
            "http://operator.wall.test",
            OPERATOR_ORIGIN + ":8443",
            "https://operator.wall.test.evil.invalid",
            "https://evil.invalid/?x=" + OPERATOR_ORIGIN,
        ],
    )
    def test_non_matching_origin_is_403(self, guarded, origin):
        before = revision(guarded)

        response = call(guarded, "post", "/wall/auto", origin)

        assert response.status_code == 403
        assert revision(guarded) == before

    @pytest.mark.parametrize(
        "headers",
        [
            [("Origin", OPERATOR_ORIGIN), ("Origin", OPERATOR_ORIGIN)],
            [("Origin", OPERATOR_ORIGIN), ("Origin", HOSTILE_ORIGIN)],
            {"Origin": OPERATOR_ORIGIN + ", " + HOSTILE_ORIGIN},
        ],
    )
    def test_duplicate_or_combined_origin_headers_are_403(self, guarded, headers):
        before = revision(guarded)

        response = guarded.post("/wall/auto", headers=headers)

        assert response.status_code == 403
        assert revision(guarded) == before

    def test_denied_delete_leaves_the_device_registered(self, guarded, device_payload):
        guarded.post("/devices/register", json=device_payload)

        assert guarded.delete(f"/devices/{DEVICE_ID}").status_code == 403

        assert DEVICE_ID in guarded.get("/devices").json()

    def test_registration_exception_is_exact_path_only(self, guarded, device_payload):
        response = guarded.post(
            "/devices/register/", json=device_payload, follow_redirects=False
        )
        assert response.status_code == 403
        assert DEVICE_ID not in guarded.get("/devices").json()

    def test_bad_tablet_link_config_does_not_disable_operator_fence(
        self, guarded, monkeypatch
    ):
        monkeypatch.setenv(main.TABLET_ORIGIN_ENV, "https://tablets.wall.test/client/")
        assert guarded.get("/operator-config").status_code == 500
        assert guarded.post("/wall/auto").status_code == 403
        assert guarded.post(
            "/wall/auto", headers={"Origin": OPERATOR_ORIGIN}
        ).status_code == 200

    def test_denial_precedes_body_validation(self, guarded):
        """A rejected request never learns how the route would have answered.

        403 rather than the route's 422 — the fence runs before the body is
        read, so a hostile caller cannot probe validation, and cannot tell a
        protected route from a missing one.
        """
        assert guarded.put("/wall", json={"width": -5}).status_code == 403
        assert (
            guarded.put(
                "/wall",
                content=b"{not json",
                headers={"Content-Type": "application/json"},
            ).status_code
            == 403
        )
        # Not even the route's 404 for an unsaved name.
        assert guarded.post("/layouts/probe/recall").status_code == 403

    @pytest.mark.parametrize(
        "path",
        ["/", "/wall", "/devices", "/assets", "/layouts", "/scenes", "/nope"],
    )
    def test_reads_are_not_guarded(self, guarded, path):
        response = guarded.get(path)

        assert response.status_code != 403

    @pytest.mark.parametrize(
        "origin",
        [None, HOSTILE_ORIGIN, "null", OPERATOR_ORIGIN],
    )
    def test_registration_is_always_reachable(self, guarded, device_payload, origin):
        """The tablet's own write is exempt — whatever shows up at the door."""
        response = call(guarded, "post", "/devices/register", origin, json=device_payload)

        assert response.status_code == 200
        assert response.json()["registered"] is True

    def test_the_exemption_is_the_exact_post_path_only(self, guarded, device_payload):
        """Nothing else under ``/devices`` rides along with registration."""
        guarded.post("/devices/register", json=device_payload)

        assert guarded.post("/devices/color", json={"color": "#3b82f6"}).status_code == 403
        assert guarded.delete(f"/devices/{DEVICE_ID}").status_code == 403


class TestControllerSocket:
    """``/ws/controller`` is fenced on the handshake, before it accepts."""

    @pytest.fixture
    def guarded(self, client, monkeypatch):
        enable_guard(monkeypatch)
        return client

    def test_missing_origin_is_rejected_with_403(self, guarded):
        with pytest.raises(WebSocketDenialResponse) as exc_info:
            with guarded.websocket_connect("/ws/controller"):
                pass  # pragma: no cover - the handshake must not complete

        assert exc_info.value.status_code == 403

    @pytest.mark.parametrize(
        "origin",
        [HOSTILE_ORIGIN, OPERATOR_ORIGIN + "/", "null", "http://operator.wall.test"],
    )
    def test_non_matching_origin_is_rejected_with_403(self, guarded, origin):
        with pytest.raises(WebSocketDenialResponse) as exc_info:
            with guarded.websocket_connect(
                "/ws/controller", headers={"Origin": origin}
            ):
                pass  # pragma: no cover - the handshake must not complete

        assert exc_info.value.status_code == 403

    def test_rejected_handshake_registers_nothing(self, guarded):
        with pytest.raises(WebSocketDenialResponse):
            with guarded.websocket_connect(
                "/ws/controller", headers={"Origin": HOSTILE_ORIGIN}
            ):
                pass  # pragma: no cover

        assert set(main.controller_sockets) == set()
        assert set(main.controller_protocols) == set()

    def test_matching_origin_is_accepted_and_gets_the_snapshot(self, guarded):
        with guarded.websocket_connect(
            "/ws/controller", headers={"Origin": OPERATOR_ORIGIN}
        ) as controller:
            frame = controller.receive_json()

        assert frame["type"] == "snapshot"
        assert frame["devices"] == []

    def test_device_socket_is_not_guarded(self, guarded, device_payload):
        """A tablet shows the *tablet* origin; it must still connect."""
        guarded.post("/devices/register", json=device_payload)

        with guarded.websocket_connect(
            f"/ws/device?device_id={DEVICE_ID}",
            headers={"Origin": "https://tablet.wall.test"},
        ) as device:
            welcome = device.receive_json()

        assert welcome["type"] == "welcome"
        assert welcome["device_id"] == DEVICE_ID


class TestMalformedConfiguration:
    """A configured value that is not an origin fails closed, loudly."""

    @pytest.mark.parametrize(
        "value",
        [
            # No scheme at all, and a scheme that is not http(s).
            "operator.wall.test",
            "ftp://operator.wall.test",
            # Path — even the bare trailing slash an origin never carries.
            "https://operator.wall.test/",
            "https://operator.wall.test/client/",
            # Query and fragment would change where a comparison lands.
            "https://operator.wall.test?next=/wall",
            "https://operator.wall.test#/wall",
            # Credentials never belong in an origin.
            "https://user:secret@operator.wall.test",
            "https://operator.wall.test@evil.invalid",
            # Wildcards are not origins.
            "*.wall.test",
            "https://*.wall.test",
            # No host, no port, and a port no browser will ever send.
            "https://",
            "https://operator.wall.test:notaport",
            "https://operator.wall.test:99999",
            "https://operator.wall.test:0",
            # Whitespace (which URL parsing would silently swallow) and a
            # scheme/urlsplit would normalise rather than reject.
            "https://operator wall.test",
            "\thttps://operator.wall.test\n",
            "HTTPS://operator.wall.test",
            "https://operator.wall.test\\evil",
            # An IPv6 literal that is not one.
            "https://[not-ipv6]:8443",
        ],
    )
    def test_malformed_operator_origin_denies_every_write(
        self, client, monkeypatch, value
    ):
        """Never "unset": a broken value must not open the gate."""
        enable_guard(monkeypatch, value)
        before = revision(client)

        # Even the request that *claims* the right Origin is refused: there
        # is no configured value it could have matched.
        for origin in (OPERATOR_ORIGIN, HOSTILE_ORIGIN, None):
            assert call(client, "post", "/wall/auto", origin).status_code == 403
            assert (
                call(
                    client,
                    "put",
                    "/wall",
                    origin,
                    json={"width": 4001},
                ).status_code
                == 403
            )

        assert revision(client) == before
        # Reads and the public registration endpoint are unaffected.
        assert client.get("/wall").status_code == 200
        assert client.post("/devices/register", json={}).status_code == 422

    @pytest.mark.parametrize("value", ["*.wall.test", "https://operator.wall.test/"])
    def test_malformed_operator_origin_denies_the_controller_socket(
        self, client, monkeypatch, value
    ):
        enable_guard(monkeypatch, value)

        with pytest.raises(WebSocketDenialResponse) as exc_info:
            with client.websocket_connect(
                "/ws/controller", headers={"Origin": OPERATOR_ORIGIN}
            ):
                pass  # pragma: no cover

        assert exc_info.value.status_code == 403

    @pytest.mark.parametrize(
        ("configured", "sent", "expected"),
        [
            # Byte for byte, and nothing else: the comparison is a string
            # equality, so what the browser will send is what must be set.
            (OPERATOR_ORIGIN, OPERATOR_ORIGIN, 200),
            (OPERATOR_ORIGIN, OPERATOR_ORIGIN.upper(), 403),
            # Hosts are case-insensitive in DNS but are sent lowercase; a
            # differently-cased configured value is a config mistake, and a
            # mistake denies rather than guesses.
            ("https://Operator.Wall.test", OPERATOR_ORIGIN, 403),
            ("https://Operator.Wall.test", "https://Operator.Wall.test", 200),
        ],
    )
    def test_a_valid_value_is_compared_exactly(
        self, client, monkeypatch, configured, sent, expected
    ):
        enable_guard(monkeypatch, configured)

        response = client.post("/wall/auto", headers={"Origin": sent})

        assert response.status_code == expected


class TestOperatorConfig:
    """``GET /operator-config`` — the tablet origin, or an honest refusal."""

    def test_unset_returns_null(self, client):
        response = client.get("/operator-config")

        assert response.status_code == 200
        assert response.json() == {"tablet_origin": None}

    def test_empty_returns_null(self, client, monkeypatch):
        monkeypatch.setenv(main.TABLET_ORIGIN_ENV, "")

        assert client.get("/operator-config").json() == {"tablet_origin": None}

    @pytest.mark.parametrize(
        "value",
        [
            "https://tablets.wall.test",
            "http://localhost:8443",
            "https://192.168.137.1:8443",
        ],
    )
    def test_configured_origin_is_returned_verbatim(self, client, monkeypatch, value):
        monkeypatch.setenv(main.TABLET_ORIGIN_ENV, value)

        response = client.get("/operator-config")

        assert response.status_code == 200
        assert response.json() == {"tablet_origin": value}

    @pytest.mark.parametrize(
        "value",
        [
            "tablets.wall.test",
            "https://tablets.wall.test/client/",
            "https://tablets.wall.test?x=1",
            "https://tablets.wall.test#frag",
            "https://user:pw@tablets.wall.test",
            "https://*.wall.test",
            "https://",
            "\thttps://tablets.wall.test\n",
        ],
    )
    def test_malformed_value_is_refused_rather_than_echoed(
        self, client, monkeypatch, value
    ):
        """Not ``null`` (that would read as "unset") and not the raw string.

        The controller page falls back to its own origin on ``null``; in a
        two-origin deployment that hands the operator a URL pointing at the
        wrong host, so a broken value must fail loudly instead.
        """
        monkeypatch.setenv(main.TABLET_ORIGIN_ENV, value)

        response = client.get("/operator-config")

        assert response.status_code == 500
        assert response.json() == {
            "detail": (
                f"{main.TABLET_ORIGIN_ENV} is not an origin of the form "
                "scheme://host[:port]"
            )
        }

    def test_the_read_is_not_guarded_by_the_operator_origin(
        self, client, monkeypatch
    ):
        """Reads are the proxy's call; this guard only fences writes."""
        enable_guard(monkeypatch)
        monkeypatch.setenv(main.TABLET_ORIGIN_ENV, "https://tablets.wall.test")

        response = client.get("/operator-config")

        assert response.status_code == 200
        assert response.json() == {"tablet_origin": "https://tablets.wall.test"}
