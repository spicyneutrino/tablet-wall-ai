"""The approved type hierarchy distinguishes section titles from rail titles."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulator/browser"))
import renewal_acceptance as driver  # noqa: E402


class Rig:
    def check(self, _name, passed, *_args, **_kwargs):
        self.passed = passed


@pytest.mark.parametrize("root_size", [16, 32])
@pytest.mark.parametrize("regression", [None, "image", "rail", "inconsistent", "overflow", "gutter"])
def test_layout_checks_design_roles_without_accepting_wrong_sizes(root_size, regression):
    section = {"size": f"{root_size}px", "sample": "image-title"}
    rail = {"size": f"{root_size * 0.875}px", "sample": "exceptions-title"}
    measured = {
        "panel": "panel-show",
        "innerWidth": 1440,
        "scrollWidth": 1440,
        "paddings": [["panel-show", 14.4]],
        "headings": {"h2": [section, rail], "h3": [rail, section]},
        "headingRoles": {"image-section": [section], "rail-title": [rail]},
        "rootFontSize": root_size,
        "textCount": 1,
        "textOffenders": [],
    }
    if regression == "image":
        section["size"] = f"{root_size * 0.875}px"
    elif regression == "rail":
        rail["size"] = f"{root_size}px"
    elif regression == "inconsistent":
        measured["headingRoles"]["h3"] = [section, rail]
    elif regression == "overflow":
        measured["scrollWidth"] += 1
    elif regression == "gutter":
        measured["paddings"][0][1] = 11
    rig = Rig()
    driver._layout_check(rig, "Images", "matched hierarchy", measured)
    assert rig.passed is (regression is None)
