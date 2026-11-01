"""Focused checks for the TWR-16 evidence arithmetic and byte matching."""

from types import SimpleNamespace

from simulator.browser.image_efficiency import PageMeter, nearest_rank, summary, summaries


class FakePage:
    def __init__(self):
        self.handlers = {}

    def on(self, event, handler):
        self.handlers[event] = handler


def test_nearest_rank_uses_the_ranked_sample_not_interpolation():
    values = [float(value) for value in range(1, 11)]
    assert nearest_rank(values, 50) == 5.0
    assert nearest_rank(values, 95) == 10.0
    assert nearest_rank([], 50) is None


def test_summary_reports_count_p50_p95_range_and_handles_empty():
    result = summary([10.0, 1.0, 4.0, 7.0, 2.0])
    assert result["n"] == 5
    assert result["p50_ms"] == 4.0
    assert result["p95_ms"] == 10.0
    assert result["range_ms"] == 9.0
    assert summary([])["n"] == 0


def test_summaries_keep_errors_out_of_latency_samples():
    measurements = [
        {"tablets": 1, "condition": "cold", "sample_count": 1,
         "samples": [{"sent_to_ack_ms": 10.0}], "fleet_from_first_send_ms": 10.0},
        {"tablets": 1, "condition": "cold", "error": "timeout"},
        {"tablets": 1, "condition": "warm", "sample_count": 1,
         "samples": [{"sent_to_ack_ms": 2.0}], "fleet_from_first_send_ms": 2.0},
    ]
    result = summaries(measurements)
    assert result["1t-cold"]["samples"] == 1
    assert result["1t-cold"]["errors"] == ["timeout"]
    assert result["1t-cold"]["time_to_painted"]["p50_ms"] == 10.0
    assert result["1t-warm"]["time_to_painted"]["p50_ms"] == 2.0


def test_asset_bytes_are_attributed_across_resets_and_both_id_forms():
    meter = PageMeter(FakePage())
    meter.watch_asset("sha256:" + "a" * 64)
    response = SimpleNamespace(
        url="http://127.0.0.1:9/assets/sha256:" + "a" * 64,
        headers={"content-length": "2792004"},
    )
    meter._response(response)
    assert (meter.asset_requests, meter.asset_bytes) == (1, 2792004)
    meter.reset()
    assert meter.asset_requests == 0
    meter._response(response)
    assert (meter.asset_requests, meter.asset_bytes) == (1, 2792004)
