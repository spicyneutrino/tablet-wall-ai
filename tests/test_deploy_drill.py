"""The backup/recovery drill (deploy/drill.py) as a regression test.

Runs the real script: a populated instance is backed up while running, restored
into new paths, booted again and compared. Its own output names the failing
check, so a failure here is readable without re-running anything by hand.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_backup_restore_drill_passes_end_to_end():
    done = subprocess.run(
        [sys.executable, "-I", str(ROOT / "deploy" / "drill.py")],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-1000:]
    assert "drill passed" in done.stdout
    for claim in (
        "the playlist-only upload is in the snapshot closure",
        "playlist is identical",
        "restored bytes of playlist-only match the source",
        "tablet 3 keeps its number",
    ):
        assert f"ok   {claim}" in done.stdout
