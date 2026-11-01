"""Render evidence acceptance, expiry, and honest status derivation.

These tests exercise ``tabletwall.render_status`` alone: no sockets, servers,
databases, or live data. Each test builds its own registry so the module-level
default is never shared between cases.
"""

import json
import math

import pytest

from tabletwall import render_status
from tabletwall.render_status import (
    MAX_DEVICES,
    MAX_REPORT_BYTES,
    RenderAck,
    RenderMapping,
    RenderRegistry,
    RenderToken,
    Viewport,
)

DEVICE = "device-1"
OTHER_DEVICE = "device-2"
CONNECTION = "0f8fad5b-d9cb-469f-a165-70867728950e"
OTHER_CONNECTION = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
GENERATION = "g0001"
REVISION = 3
MAPPING_REVISION = "map:7"
ASSET = "sha256:" + "a" * 64
OTHER_ASSET = "sha256:" + "b" * 64

VIEWPORT = Viewport(
    width=1024.0,
    height=768.0,
    dpr=2.0,
    orientation=0,
    mode="fullscreen",
    visual_scale=1.0,
)
MAPPING = RenderMapping(revision=MAPPING_REVISION, viewport=VIEWPORT)


def make_token(**overrides) -> RenderToken:
    values = {
        "connection_id": CONNECTION,
        "generation": GENERATION,
        "revision": REVISION,
        "render_seq": 1,
        "mapping_revision": MAPPING_REVISION,
        "asset": ASSET,
    }
    values.update(overrides)
    return RenderToken(**values)


def make_mapping(**overrides) -> RenderMapping:
    values = {
        "revision": MAPPING_REVISION,
        "state": "ready",
        "viewport": VIEWPORT,
        "image_supported": True,
        "experimental": False,
    }
    values.update(overrides)
    return RenderMapping(**values)


def viewport_payload(viewport: Viewport = VIEWPORT) -> dict:
    return {
        "width": viewport.width,
        "height": viewport.height,
        "dpr": viewport.dpr,
        "orientation": viewport.orientation,
        "mode": viewport.mode,
        "visual_scale": viewport.visual_scale,
    }


def token_payload(token: RenderToken) -> dict:
    return {
        "connection_id": token.connection_id,
        "generation": token.generation,
        "revision": token.revision,
        "render_seq": token.render_seq,
        "mapping_revision": token.mapping_revision,
        "asset": token.asset,
    }


def ack_payload(token: RenderToken | None = None, **overrides) -> dict:
    values = {
        "type": "render_ack",
        "token": token_payload(make_token() if token is None else token),
        "report_seq": 1,
        "status": "displayed",
        "reason": None,
        "viewport": viewport_payload(),
        "visible": True,
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("bad_width", [10**400, float("inf")])
def test_unrepresentable_viewport_report_is_rejected(bad_width):
    registry = RenderRegistry()
    expect(registry)
    payload = ack_payload()
    payload["viewport"]["width"] = bad_width
    assert accept(registry, payload=payload) is False


@pytest.mark.parametrize("wire", [False, True])
def test_surrogate_token_is_rejected_without_an_exception(wire):
    registry = RenderRegistry()
    expect(registry)
    payload = ack_payload()
    payload["token"]["generation"] = "\ud800"
    assert accept(registry, payload=json.dumps(payload) if wire else payload) is False


def test_projection_requires_a_validated_live_viewport():
    registry = RenderRegistry()
    expect(registry)
    assert accept(registry)
    status = project(registry, mapping=make_mapping(viewport=None))
    assert status.current is False
    assert status.state == "blocked"


def expect(registry: RenderRegistry, token: RenderToken | None = None, *, now=100.0):
    registry.expect(DEVICE, make_token() if token is None else token, now_mono=now)


def accept(
    registry: RenderRegistry,
    *,
    payload=None,
    token: RenderToken | None = None,
    owned=CONNECTION,
    generation=GENERATION,
    revision=REVISION,
    mapping: RenderMapping = MAPPING,
    now=101.0,
):
    if payload is None:
        payload = ack_payload(token)
    return registry.accept(
        DEVICE,
        owned_connection_id=owned,
        report=payload,
        generation=generation,
        revision=revision,
        mapping=mapping,
        now_mono=now,
    )


def project(
    registry: RenderRegistry,
    *,
    now=101.0,
    online=True,
    caps=("render_ack", "image"),
    mapping: RenderMapping | None = MAPPING,
    generation=GENERATION,
    revision=REVISION,
    **overrides,
):
    return registry.project(
        DEVICE,
        now_mono=now,
        online=online,
        caps=caps,
        mapping=mapping,
        generation=generation,
        revision=revision,
        **overrides,
    )


@pytest.fixture(autouse=True)
def clean_default_registry():
    render_status.reset()
    yield
    render_status.reset()


@pytest.fixture
def registry() -> RenderRegistry:
    return RenderRegistry()


@pytest.fixture
def expected(registry: RenderRegistry) -> RenderRegistry:
    expect(registry)
    return registry


# ---------------------------------------------------------------------------
# acceptance and projection
# ---------------------------------------------------------------------------


def test_current_displayed_report_is_fresh_truth(expected):
    assert accept(expected) is True

    status = project(expected, now=103.5)

    assert status.state == "displayed"
    assert status.current is True
    assert status.reason is None
    assert status.accepted_status == "displayed"
    assert status.accepted_token == make_token()
    assert status.expected_token == make_token()
    assert status.received_at == 101.0
    assert status.age_ms == 2500


def test_online_alone_never_becomes_displayed(expected):
    status = project(expected, now=101.0)

    assert status.state == "unknown"
    assert status.current is False
    assert status.accepted_token is None


def test_unknown_device_has_no_evidence(registry):
    status = project(registry, now=101.0)

    assert status.state == "unknown"
    assert status.current is False
    assert status.expected_token is None


def test_typed_ack_and_json_bytes_are_accepted(expected):
    ack = RenderAck(
        type="render_ack",
        token=make_token(),
        report_seq=1,
        status="displayed",
        reason=None,
        viewport=VIEWPORT,
        visible=True,
    )
    assert accept(expected, payload=ack) is True

    refreshed = {
        "type": "render_ack",
        "token": token_payload(make_token()),
        "report_seq": 2,
        "status": "displayed",
        "reason": None,
        "viewport": viewport_payload(),
        "visible": True,
    }
    assert accept(expected, payload=json.dumps(refreshed).encode("utf-8")) is True


# ---------------------------------------------------------------------------
# ownership, tokens, and ordering
# ---------------------------------------------------------------------------


def test_old_socket_and_old_token_cannot_acknowledge_a_newer_expectation(registry):
    old_token = make_token()
    new_token = make_token(connection_id=OTHER_CONNECTION, render_seq=2)
    registry.expect(DEVICE, new_token, now_mono=100.0)

    assert accept(registry, token=old_token, owned=OTHER_CONNECTION) is False
    assert accept(registry, token=old_token, owned=CONNECTION) is False
    assert accept(registry, token=new_token, owned=OTHER_CONNECTION) is True

    status = project(registry, now=101.0)
    assert status.state == "displayed"
    assert status.accepted_token == new_token


def test_missing_owned_connection_is_rejected(expected):
    assert accept(expected, owned=None) is False
    assert accept(expected, owned="") is False
    assert project(expected).state == "unknown"


def test_late_disconnect_from_an_old_socket_keeps_new_evidence(registry):
    old_token = make_token()
    registry.expect(DEVICE, old_token, now_mono=100.0)
    assert accept(registry, token=old_token) is True

    new_token = make_token(connection_id=OTHER_CONNECTION, render_seq=2)
    registry.expect(DEVICE, new_token, now_mono=100.5)
    assert accept(registry, token=new_token, owned=OTHER_CONNECTION, now=101.0)

    assert registry.disconnect(DEVICE, CONNECTION) is False
    assert project(registry).state == "displayed"
    assert registry.disconnect(DEVICE, OTHER_CONNECTION) is True
    assert project(registry).state == "unknown"


def test_new_expectation_makes_old_scene_evidence_stale(expected):
    assert accept(expected) is True

    expect(expected, make_token(render_seq=2, asset=OTHER_ASSET), now=102.0)

    status = project(expected, now=102.0)
    assert status.state == "stale"
    assert status.current is False
    assert status.reason == "superseded"
    assert status.accepted_token == make_token()

    # The old scene's acknowledgement cannot be replayed against the new token.
    assert accept(expected, token=make_token(asset=OTHER_ASSET), now=102.0) is False


def test_coalesced_expectations_cannot_be_confirmed_by_an_intermediate_token(
    registry,
):
    first = make_token(render_seq=1)
    second = make_token(render_seq=2)
    latest = make_token(render_seq=3)
    for token in (first, second, latest):
        registry.expect(DEVICE, token, now_mono=100.0)

    assert accept(registry, token=second) is False
    assert accept(registry, token=first) is False
    assert accept(registry, token=latest) is True


def test_report_sequence_must_strictly_increase(expected):
    assert accept(expected, payload=ack_payload(report_seq=2)) is True
    assert accept(expected, payload=ack_payload(report_seq=1), now=102.0) is False
    assert accept(expected, payload=ack_payload(report_seq=2), now=103.0) is False
    assert accept(expected, payload=ack_payload(report_seq=3), now=104.0) is True
    assert project(expected, now=104.0).age_ms == 0


def test_report_sequence_continues_across_a_retry_on_one_connection(expected):
    assert accept(expected, payload=ack_payload(report_seq=5)) is True

    retried = make_token(render_seq=2)
    expect(expected, retried, now=102.0)

    assert accept(
        expected, token=retried, payload=ack_payload(retried, report_seq=5), now=103.0
    ) is False
    assert accept(
        expected, token=retried, payload=ack_payload(retried, report_seq=6), now=104.0
    ) is True


def test_report_sequence_restarts_for_a_replacement_connection(registry):
    expect(registry)
    assert accept(
        registry,
        payload=ack_payload(report_seq=5),
    ) is True

    new_token = make_token(connection_id=OTHER_CONNECTION, render_seq=2)
    registry.expect(DEVICE, new_token, now_mono=102.0)
    assert accept(
        registry,
        token=new_token,
        owned=OTHER_CONNECTION,
        payload=ack_payload(new_token, report_seq=1),
        now=103.0,
    ) is True


def test_generation_and_revision_must_still_be_current(expected):
    assert accept(expected, generation="g0002") is False
    assert accept(expected, revision=REVISION + 1) is False
    assert project(expected).state == "unknown"
    assert accept(expected) is True
    assert project(expected).state == "displayed"


def test_mapping_revision_must_match_the_expected_token(expected):
    assert accept(expected, mapping=make_mapping(revision="map:8")) is False
    assert accept(expected) is True


def test_wrong_or_malformed_asset_is_rejected(registry):
    expect(registry)

    assert accept(registry, token=make_token(asset=OTHER_ASSET)) is False
    for malformed in ("", "sha256:", "sha256:xyz", ASSET[:-1] + "Z", 42):
        assert accept(registry, token=make_token(asset=malformed)) is False
    assert accept(registry) is True


def test_viewport_must_match_the_validated_mapping(expected):
    for mismatch in (
        viewport_payload(Viewport(1024.0, 766.0, 2.0, 0, "fullscreen", 1.0)),
        viewport_payload(Viewport(1024.0, 768.0, 1.5, 0, "fullscreen", 1.0)),
        viewport_payload(Viewport(1024.0, 768.0, 2.0, 90, "fullscreen", 1.0)),
        viewport_payload(Viewport(1024.0, 768.0, 2.0, 0, "tab", 1.0)),
        viewport_payload(Viewport(1024.0, 768.0, 2.0, 0, "fullscreen", 1.5)),
    ):
        assert accept(expected, payload=ack_payload(viewport=mismatch)) is False
    assert accept(expected) is True


def test_hidden_zoom_guard_is_accepted_but_cannot_claim_display(expected):
    zoomed = make_mapping(state="zoom_changed")

    assert accept(expected, mapping=zoomed) is False
    assert accept(
        expected,
        payload=ack_payload(status="hidden", reason="zoom", visible=True),
        mapping=zoomed,
    ) is True

    status = project(expected, mapping=zoomed)
    assert status.state == "blocked"
    assert status.current is False
    assert status.reason == "zoom_changed"


# ---------------------------------------------------------------------------
# displayed honesty
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state",
    ["unplaced", "needs_calibration", "viewport_mismatch", "zoom_changed",
     "unsupported_content", "unsupported_client"],
)
def test_displayed_is_rejected_for_a_non_ready_mapping(expected, state):
    assert accept(expected, mapping=make_mapping(state=state)) is False
    assert project(expected).state == "unknown"


def test_displayed_is_rejected_for_an_experimental_presentation(expected):
    assert accept(expected, mapping=make_mapping(experimental=True)) is False


def test_displayed_is_rejected_without_image_support(expected):
    assert accept(expected, mapping=make_mapping(image_supported=False)) is False


def test_color_content_does_not_require_image_support(expected):
    token = make_token(asset=None)
    expect(expected, token, now=100.0)

    assert accept(
        expected,
        token=token,
        mapping=make_mapping(image_supported=False),
    ) is True


def test_displayed_must_be_visible(expected):
    assert accept(expected, payload=ack_payload(visible=False)) is False
    assert accept(expected, payload=ack_payload(status="failed", reason="decode",
                                                visible=False)) is True


def test_displayed_cannot_carry_a_failure_reason(expected):
    assert accept(expected, payload=ack_payload(reason="decode")) is False


@pytest.mark.parametrize(
    "status,reason",
    [("loading", None), ("failed", "decode"), ("hidden", "zoom"), ("blocked", "auth")],
)
def test_less_healthy_states_are_accepted_and_projected(expected, status, reason):
    assert accept(expected, payload=ack_payload(status=status, reason=reason)) is True

    projected = project(expected)
    assert projected.state == status
    assert projected.reason == reason
    assert projected.current is False


# ---------------------------------------------------------------------------
# malformed and hostile reports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("report_seq", True),
        ("visible", 1),
        ("status", "painted"),
        ("status", None),
        ("reason", "network"),
        ("reason", 7),
        ("type", "wall"),
    ],
)
def test_unknown_enums_and_booleans_are_rejected(expected, field, value):
    assert accept(expected, payload=ack_payload(**{field: value})) is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"revision": True},
        {"revision": -1},
        {"render_seq": True},
        {"render_seq": 0},
        {"connection_id": ""},
        {"generation": 5},
        {"mapping_revision": None},
        {"asset": 7},
    ],
)
def test_malformed_token_fields_are_rejected(expected, overrides):
    payload = ack_payload()
    payload["token"] = {**payload["token"], **overrides}
    assert accept(expected, payload=payload) is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"width": True},
        {"width": 0},
        {"height": -1.0},
        {"dpr": 0},
        {"dpr": math.nan},
        {"width": math.inf},
        {"visual_scale": math.nan},
        {"orientation": 45},
        {"orientation": True},
        {"mode": "kiosk"},
    ],
)
def test_booleans_nonfinite_and_unknown_viewports_are_rejected(expected, overrides):
    payload = ack_payload()
    payload["viewport"] = {**payload["viewport"], **overrides}
    assert accept(expected, payload=payload) is False


def test_unknown_keys_are_rejected_at_every_level(expected):
    top = ack_payload()
    top["extra"] = 1
    token = ack_payload()
    token["token"] = {**token["token"], "extra": 1}
    viewport = ack_payload()
    viewport["viewport"] = {**viewport["viewport"], "extra": 1}

    assert accept(expected, payload=top) is False
    assert accept(expected, payload=token) is False
    assert accept(expected, payload=viewport) is False


def test_oversized_report_is_rejected_before_parsing(expected):
    raw = json.dumps(ack_payload())
    padded = raw + " " * (MAX_REPORT_BYTES - len(raw))
    assert len(padded.encode("utf-8")) == MAX_REPORT_BYTES

    assert accept(expected, payload=padded + " ") is False
    assert accept(expected, payload=padded) is True


def test_dictionary_reports_are_bounded_too(expected):
    payload = ack_payload()
    payload["token"] = {**payload["token"], "generation": "g" * 5000}

    assert accept(expected, payload=payload) is False


@pytest.mark.parametrize(
    "payload",
    [b"\xff\xfe", b"{", "[]", "null", "42", b"\x00" * 4097, [], {}],
)
def test_non_object_and_non_json_reports_are_rejected(expected, payload):
    assert accept(expected, payload=payload) is False


def test_raw_nan_json_is_rejected(expected):
    raw = json.dumps(ack_payload()).replace('"dpr": 2.0', '"dpr": NaN')

    assert accept(expected, payload=raw) is False


def test_invalid_server_inputs_are_rejected(expected):
    assert accept(expected, mapping=object()) is False
    assert accept(expected, mapping=make_mapping(revision="")) is False
    assert accept(expected, now=math.nan) is False
    assert accept(expected, revision=True) is False
    assert accept(expected, generation="") is False

    with pytest.raises(ValueError):
        project(expected, revision=True)
    with pytest.raises(ValueError):
        project(expected, now=math.nan)


def test_expect_rejects_invalid_construction(registry):
    with pytest.raises(ValueError):
        registry.expect("", make_token(), now_mono=100.0)
    with pytest.raises(ValueError):
        registry.expect(DEVICE, make_token(revision=True), now_mono=100.0)
    with pytest.raises(ValueError):
        registry.expect(DEVICE, make_token(asset="not-an-asset"), now_mono=100.0)
    with pytest.raises(ValueError):
        registry.expect(DEVICE, make_token(), now_mono=math.nan)


# ---------------------------------------------------------------------------
# expiry and refresh
# ---------------------------------------------------------------------------


def test_evidence_expires_by_monotonic_receipt_time(expected):
    assert accept(expected, now=100.0) is True

    boundary = project(expected, now=115.0)
    assert boundary.state == "displayed"
    assert boundary.current is True
    assert boundary.age_ms == 15000

    expired = project(expected, now=115.001)
    assert expired.state == "stale"
    assert expired.current is False
    assert expired.reason == "expired"


def test_expiry_follows_the_current_heartbeat_timeout(expected, monkeypatch):
    monkeypatch.setattr(render_status, "HEARTBEAT_TIMEOUT_S", 5)
    assert accept(expected, now=100.0) is True

    assert project(expected, now=105.0).state == "displayed"
    assert project(expected, now=105.5).state == "stale"


def test_valid_refresh_updates_receipt_age(expected):
    assert accept(expected, payload=ack_payload(report_seq=1), now=100.0) is True
    assert accept(expected, payload=ack_payload(report_seq=2), now=104.0) is True

    status = project(expected, now=104.0)
    assert status.state == "displayed"
    assert status.age_ms == 0
    assert status.received_at == 104.0


# ---------------------------------------------------------------------------
# lifecycle and bounded storage
# ---------------------------------------------------------------------------


def test_clear_and_reset_remove_evidence(expected):
    assert accept(expected) is True
    assert expected.clear(DEVICE) is True
    assert project(expected).state == "unknown"
    assert expected.clear(DEVICE) is False

    expect(expected)
    assert accept(expected) is True
    expected.reset()
    assert project(expected).state == "unknown"


def test_replace_clears_old_and_new_identities(registry):
    other = make_token(connection_id=OTHER_CONNECTION)
    expect(registry)
    registry.expect(OTHER_DEVICE, other, now_mono=100.0)
    assert accept(registry) is True

    registry.replace(DEVICE, OTHER_DEVICE)

    assert project(registry).state == "unknown"
    assert registry.project(OTHER_DEVICE, now_mono=101.0, online=True).state == (
        "unknown"
    )


def test_cache_holds_one_latest_record_per_device(expected):
    assert accept(expected) is True
    expect(expected, make_token(render_seq=2), now=102.0)
    assert accept(expected, payload=ack_payload(report_seq=2, token=make_token(
        render_seq=2)), now=103.0)

    assert len(expected._evidence) == 1
    status = project(expected, now=103.0)
    assert status.expected_token == make_token(render_seq=2)
    assert status.accepted_token == make_token(render_seq=2)


def test_cache_is_bounded_by_the_device_ceiling(registry):
    for index in range(MAX_DEVICES + 1):
        registry.expect(
            f"device-{index}",
            make_token(render_seq=1),
            now_mono=100.0 + index,
        )

    assert len(registry._evidence) == MAX_DEVICES


# ---------------------------------------------------------------------------
# derivation rules
# ---------------------------------------------------------------------------


def test_offline_overrides_valid_evidence(expected):
    assert accept(expected) is True

    status = project(expected, online=False)

    assert status.state == "offline"
    assert status.current is False
    assert status.accepted_status == "displayed"


def test_unsupported_capability_is_never_displayed(expected):
    assert accept(expected) is True

    unsupported = project(expected, caps=("image",))
    unnegotiated_image = project(expected, caps=("render_ack",))
    unknown = project(expected, caps=None)

    assert unsupported.state == "unsupported"
    assert unsupported.reason == "capability"
    assert unsupported.current is False
    assert unnegotiated_image.state == "unsupported"
    assert unnegotiated_image.reason == "capability"
    assert unknown.state == "displayed"


@pytest.mark.parametrize(
    "mapping_state,state,reason",
    [
        ("unplaced", "unplaced", "no_slot"),
        ("unsupported_content", "unsupported", "unsupported_content"),
        ("unsupported_client", "unsupported", "unsupported_client"),
        ("needs_calibration", "blocked", "needs_calibration"),
    ],
)
def test_mapping_fence_distinguishes_unplaced_blocked_and_unsupported(
    registry, mapping_state, state, reason
):
    expect(registry)

    status = project(registry, mapping=make_mapping(state=mapping_state))

    assert status.state == state
    assert status.reason == reason
    assert status.current is False


def test_identify_and_presentation_suppress_contribution(expected):
    assert accept(expected) is True

    identifying = project(expected, identify_active=True)
    presenting = project(expected, presentation_active=True)

    assert identifying.state == "identifying"
    assert identifying.current is False
    assert presenting.state == "blocked"
    assert presenting.reason == "playback"
    assert presenting.current is False


def test_projection_marks_an_old_expected_token_stale(expected):
    assert accept(expected) is True

    stale_generation = project(expected, generation="g0002")
    stale_revision = project(expected, revision=REVISION + 1)
    stale_mapping = project(expected, mapping=make_mapping(revision="map:8"))

    for status in (stale_generation, stale_revision, stale_mapping):
        assert status.state == "stale"
        assert status.reason == "superseded"
        assert status.current is False


def test_mapping_viewport_change_blocks_an_old_display_claim(expected):
    assert accept(expected) is True

    moved = make_mapping(viewport=Viewport(
        width=1024.0, height=768.0, dpr=2.0, orientation=90, mode="fullscreen",
        visual_scale=1.0,
    ))
    assert moved.revision == MAPPING_REVISION

    status = project(expected, mapping=moved)
    assert status.state == "blocked"
    assert status.reason == "viewport"
    assert status.current is False


def test_loading_transitions_to_failed_then_refreshed_display(expected):
    assert accept(expected, payload=ack_payload(status="loading"), now=100.0)
    assert project(expected).state == "loading"

    assert accept(expected, payload=ack_payload(
        status="failed", reason="decode", report_seq=2), now=101.0)
    failed = project(expected, now=101.0)
    assert failed.state == "failed"
    assert failed.reason == "decode"
    assert failed.current is False

    assert accept(expected, payload=ack_payload(
        status="displayed", report_seq=3), now=102.0)
    assert project(expected, now=102.0).state == "displayed"


def test_default_registry_wrappers_round_trip():
    render_status.expect(DEVICE, make_token(), now_mono=100.0)
    assert render_status.accept(
        DEVICE,
        owned_connection_id=CONNECTION,
        report=ack_payload(),
        generation=GENERATION,
        revision=REVISION,
        mapping=MAPPING,
        now_mono=101.0,
    ) is True

    status = render_status.project(
        DEVICE,
        now_mono=101.0,
        online=True,
        caps=("render_ack", "image"),
        mapping=MAPPING,
        generation=GENERATION,
        revision=REVISION,
    )
    assert status.state == "displayed"
    assert render_status.clear(DEVICE) is True
