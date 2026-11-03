"""Global fit coordinates must survive projection onto separate physical panels."""

import pytest

from tabletwall import geometry


@pytest.mark.parametrize("bounds,source", [
    ((0, 0, 200, 100), (400, 400)),
    ((0, 0, 100, 200), (1600, 400)),
    ((-50, 20, 200, 100), (1000, 1500)),
])
@pytest.mark.parametrize("fit", ["cover", "contain"])
def test_physical_panels_share_one_global_fit(bounds, source, fit):
    x, y, width, height = bounds
    scale = (min if fit == "contain" else max)(width / source[0], height / source[1])
    expected = (source[0] * scale, source[1] * scale)
    plans = [geometry.normalized_source_to_panel(
        active_size=(width / 2, height),
        bezels={"left": 0, "right": 0, "top": 0, "bottom": 0},
        center_mm=(x + width * fraction, y + height / 2),
        nudge_mm=(0, 0), mount_angle=0,
        bounds=bounds, source_size=source, fit=fit,
    ) for fraction in (0.25, 0.75)]
    for point in ((0, 0), (1, 1), (0.5, 0.5)):
        mapped = [geometry.apply(tuple(plan["panel_to_wall"]), geometry.apply(
            tuple(plan["panel_from_source"]), point
        )) for plan in plans]
        assert mapped[0] == pytest.approx(mapped[1])
        assert mapped[0] == pytest.approx((
            x + (width - expected[0]) / 2 + point[0] * expected[0],
            y + (height - expected[1]) / 2 + point[1] * expected[1],
        ))
    if fit == "contain":
        assert expected[0] <= width
        assert expected[1] <= height
