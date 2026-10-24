"""Clock estimation and suspend-epoch rules."""

from tabletwall import clock


def test_symmetric_delay_recovers_the_offset():
    sample = clock.estimate(0, 5110, 5110, 220)
    assert sample is not None
    assert abs(sample.offset_ms - 5000) < 1e-9
    assert sample.rtt_ms == 220
    assert sample.uncertainty_ms == 110


def test_an_impossible_negative_delay_is_invalid():
    assert clock.estimate(100, 100, 100, 50) is None
    assert clock.estimate(None, 1, 2, 3) is None
    assert clock.estimate(0, 100, 90, 200) is None  # server received after it sent
    assert clock.estimate(200, 100, 100, 100) is None  # client clock ran backwards


def test_best_sample_rejects_nonfinite_values():
    now = 1000
    assert clock.best_sample([
        {"server_ms": now, "offset_ms": float("nan"), "rtt_ms": 1,
         "uncertainty_ms": 1},
    ], now) is None


def test_best_sample_prefers_the_lowest_delay_fresh_valid_sample():
    now = 100_000
    samples = [
        {"server_ms": now - 1000, "offset_ms": 10, "rtt_ms": 80, "uncertainty_ms": 40},
        {"server_ms": now - 2000, "offset_ms": 12, "rtt_ms": 20, "uncertainty_ms": 10},
        {"server_ms": now - 20000, "offset_ms": 99, "rtt_ms": 1, "uncertainty_ms": 1},
        {"server_ms": now, "offset_ms": 5, "rtt_ms": 30, "uncertainty_ms": 40},
    ]
    chosen = clock.best_sample(samples, now)
    assert chosen is not None
    assert chosen["offset_ms"] == 12
    assert chosen["fresh"] is True


def test_suspend_advances_the_epoch_and_ordinary_time_does_not():
    readings = iter([
        (1000.0, 1000.0),
        (2000.0, 2000.0),   # ordinary 1 s
        (9000.0, 3000.0),   # boottime jumps 7 s while monotonic moves 1 s
        (10000.0, 4000.0),
    ])
    server = clock.ServerClock(sample=lambda: next(readings))
    first = server.epoch
    assert server.check_suspend() is False
    assert server.epoch == first
    assert server.check_suspend() is True
    assert server.epoch != first
    assert server.suspended is True
    assert server.check_suspend() is False
