"""Compare repeated GET /assets requests with a local, deterministic inventory.

Run with the project Python and --baseline-ref pointing to the revision before
content validation caching. No network, paid API, or operator data is used.
"""

import argparse
import cProfile
import hashlib
import json
import os
import pstats
import random
import statistics
import subprocess
import sys
import tempfile
import time
from io import StringIO
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", required=True)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--requests", type=int, default=3)
    parser.add_argument("--profile", action="store_true")
    arguments = parser.parse_args()
    if arguments.rounds < 5 or arguments.requests < 1:
        parser.error("use at least five rounds and one request per round")
    source = subprocess.check_output(
        ["git", "show", f"{arguments.baseline_ref}:tabletwall/assets.py"],
        cwd=ROOT, text=True,
    )
    baseline = ModuleType("tabletwall_benchmark_baseline")
    sys.modules[baseline.__name__] = baseline
    exec(compile(source, "baseline-assets.py", "exec"), baseline.__dict__)
    with tempfile.TemporaryDirectory(prefix="tablet-wall-benchmark-") as temporary:
        scratch = Path(temporary)
        for key in tuple(os.environ):
            if key.startswith("TABLET_WALL_"):
                del os.environ[key]
        os.environ.update({
            "TABLET_WALL_DB": str(scratch / "wall.db"),
            "TABLET_WALL_MEDIA_DIR": str(scratch / "media"),
            "TABLET_WALL_ASSET_DIR": str(scratch / "assets"),
        })
        os.environ.pop("TABLET_WALL_OPERATOR_ORIGIN", None)
        os.environ.pop("TABLET_WALL_TABLET_ORIGIN", None)
        from fastapi.testclient import TestClient
        from PIL import Image
        import main as server
        from tabletwall import assets as changed

        directory = scratch / "assets"
        directory.mkdir()
        generator = random.Random(170)
        expected = set()
        for index in range(4):
            path = directory / f"panel-{index}.jpg"
            Image.frombytes("RGB", (1920, 1080), generator.randbytes(1920 * 1080 * 3)).save(
                path, "JPEG", quality=80,
            )
            expected.add("sha256:" + hashlib.sha256(path.read_bytes()).hexdigest())
        dataset_bytes = sum(path.stat().st_size for path in directory.iterdir())
        results = {"baseline": [], "cached": []}
        work = {name: {"reads": 0, "decodes": 0, "responses": 0} for name in results}
        tracking = {"active": False}
        for name, module in (("baseline", baseline), ("cached", changed)):
            read, inspect = module._read_capped, module._inspect

            def count_read(path, original=read, side=name):
                if tracking["active"]:
                    work[side]["reads"] += 1
                return original(path)

            def count_decode(data, original=inspect, side=name):
                if tracking["active"]:
                    work[side]["decodes"] += 1
                return original(data)

            module._read_capped, module._inspect = count_read, count_decode
        from tabletwall.routes.assets import get_assets
        endpoint_globals = get_assets.__globals__
        original_assets = endpoint_globals["assets"]
        try:
            with TestClient(server.app) as client:
                def request(module, name):
                    endpoint_globals["assets"] = module
                    response = client.get("/assets")
                    assert response.status_code == 200, response.text
                    inventory = response.json()["assets"]
                    assert {entry["id"] for entry in inventory} == expected
                    assert all(entry["intrinsicWidth"] == 1920 and entry["intrinsicHeight"] == 1080 for entry in inventory)
                    if tracking["active"]:
                        work[name]["responses"] += 1

                request(baseline, "baseline")
                request(changed, "cached")
                for _ in range(arguments.rounds):
                    for name, module in (("baseline", baseline), ("cached", changed)):
                        tracking["active"] = True
                        started = time.perf_counter()
                        for _ in range(arguments.requests):
                            request(module, name)
                        results[name].append((time.perf_counter() - started) * 1000 / arguments.requests)
                        tracking["active"] = False
                if arguments.profile:
                    for name, module in (("baseline", baseline), ("cached", changed)):
                        profile = cProfile.Profile()
                        profile.runcall(module.list_assets)
                        output = StringIO()
                        pstats.Stats(profile, stream=output).sort_stats("cumulative").print_stats(10)
                        print(name + " untimed profile\n" + output.getvalue(), file=sys.stderr)
        finally:
            endpoint_globals["assets"] = original_assets
        print(json.dumps({
            "baseline_ref": arguments.baseline_ref,
            "dataset": {"files": 4, "width": 1920, "height": 1080, "bytes": dataset_bytes},
            "rounds": arguments.rounds, "requests_per_round": arguments.requests,
            "milliseconds_per_request": {
                name: {"median": statistics.median(values), "min": min(values), "max": max(values), "rounds": values}
                for name, values in results.items()
            },
            "timed_work": work, "failures": 0,
        }, indent=2))


if __name__ == "__main__":
    main()
