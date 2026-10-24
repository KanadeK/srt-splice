"""A complete CLI acceptance example with manually authored expected timestamps."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

example = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as scratch:
    destination = Path(scratch) / "captions"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "srt_splice",
            str(example / "source.srt"),
            str(example / "edits.json"),
            "--out",
            str(destination),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    actual = (destination / "output.srt").read_text(encoding="utf-8")
    expected = (example / "expected.srt").read_text(encoding="utf-8")
    if actual.rstrip("\n") != expected.rstrip("\n"):
        raise SystemExit("Unexpected transformed captions")
    report = json.loads((destination / "receipt.json").read_text(encoding="utf-8"))
    if report["summary"] != {
        "input_cues": 4,
        "output_cues": 4,
        "clips": 2,
        "duration_ms": 8000,
        "dropped_cues": 1,
        "clipped_cues": 2,
        "multi_fragment_cues": 1,
    }:
        raise SystemExit("Unexpected receipt counts")
    print(process.stdout.strip())
    print("Example verified: exact timestamps, split cue, dropped cue and receipt")
