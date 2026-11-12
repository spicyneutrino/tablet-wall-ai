"""Gate arithmetic for composition_gates.py (pure functions, no browser)."""

from simulator.browser import composition_gates as g

VP = (1000, 800)


def box(x, y, w, h):
    return {"x": x, "y": y, "width": w, "height": h}


def test_area_fraction():
    assert g.area_fraction(box(0, 0, 500, 400), VP) == 0.25
    assert g.area_fraction(None, VP) == 0.0


def test_box_drift_uses_size_and_position():
    a = box(100, 100, 500, 400)
    assert g.box_drift(a, a, VP) == 0
    assert abs(g.box_drift(a, box(100, 100, 510, 400), VP) - 10 / 500) < 1e-9
    assert abs(g.box_drift(a, box(120, 100, 500, 400), VP) - 20 / 1000) < 1e-9


def test_fill_is_limiting_dimension():
    well = box(0, 0, 600, 300)
    assert g.fill_fraction(box(0, 0, 450, 300), well) == 1.0  # height-limited
    assert g.fill_fraction(box(0, 0, 300, 150), well) == 0.5
    assert g.fill_fraction(None, well) == 0.0
    assert g.fill_fraction(box(0, 0, 10, 10), box(0, 0, 0, 0)) == 0.0


def test_aspect_error():
    assert g.aspect_error(box(0, 0, 720, 480), (720, 480)) == 0
    assert g.aspect_error(box(0, 0, 720, 240), (720, 480)) > 0.3
    assert g.aspect_error(None, (720, 480)) == 1.0


def test_fully_inside_edges():
    assert g.fully_inside(box(0, 0, 1000, 800), VP)
    assert not g.fully_inside(box(0, 700, 100, 101), VP)
    assert not g.fully_inside(box(-2, 0, 10, 10), VP)
    assert not g.fully_inside(None, VP)
    assert not g.fully_inside(box(0, 0, 0, 10), VP)


def test_verdict_shape():
    v = g.verdict(0, 3, ">=4")
    assert v == {"pass": False, "value": 3, "threshold": ">=4"}
