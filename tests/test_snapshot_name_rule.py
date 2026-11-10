"""The saved-name rule as the client states it, checked against the server.

``tests/snapshot_names.json`` is the one table both runtimes read. The client
sends ``sent = raw.trim()`` and accepts exactly when the server's parser
returns that same string; the server stays the authority. Python's ``strip``
and JavaScript's ``trim`` disagree on a few characters (U+FEFF, U+001C to
U+001F, U+0085), so the table defines the contract on ``sent`` and this test
asserts the acceptance relation rather than a second, imaginary rule.
"""

import json
from pathlib import Path

from tabletwall.protocol import _parse_snapshot_name

CASES = json.loads(Path(__file__).with_name("snapshot_names.json").read_text(encoding="utf-8"))


def test_table_is_shared_and_complete():
    assert len(CASES) >= 16
    assert all(set(case) == {"raw", "sent", "expect"} for case in CASES)
    assert len({case["raw"] for case in CASES}) == len(CASES)


def test_server_accepts_exactly_the_string_the_client_sends():
    for case in CASES:
        parsed = _parse_snapshot_name(case["sent"])
        if case["expect"] is None:
            assert parsed != case["sent"], case
        else:
            assert parsed == case["expect"], case


def test_measured_trim_divergences_stay_in_the_table():
    by_raw = {case["raw"]: case for case in CASES}
    assert by_raw["\ufeffa"] == {"raw": "\ufeffa", "sent": "a", "expect": "a"}
    assert by_raw["\x1ca"] == {"raw": "\x1ca", "sent": "\x1ca", "expect": None}
    assert by_raw["\x1fa"] == {"raw": "\x1fa", "sent": "\x1fa", "expect": None}
    assert by_raw["\x85a"] == {"raw": "\x85a", "sent": "\x85a", "expect": None}
