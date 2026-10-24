import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import InputError, read_bounded, remap, write_bundle


def main(argv=None):
    parser = argparse.ArgumentParser(description="Remap SRT captions through an ordered clip list.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("source", type=Path)
    parser.add_argument("edits", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--out", type=Path, help="new output directory; parent must exist")
    group.add_argument(
        "--dry-run", action="store_true", help="validate and print summary without writing"
    )
    args = parser.parse_args(argv)
    try:
        output, receipt = remap(read_bounded(args.source), read_bounded(args.edits))
        if args.out is not None:
            write_bundle(args.out, output, receipt)
    except (InputError, OSError) as error:
        print(f"srt-splice: {error}", file=sys.stderr)
        return 2
    print(json.dumps(receipt["summary"], sort_keys=True))
    return 0
