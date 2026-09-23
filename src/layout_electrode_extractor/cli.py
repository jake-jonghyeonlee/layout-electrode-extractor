"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys

from .engine import extract
from .periodic import ResourceError
from .schema import ManifestError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="layout-electrode-extractor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    extraction = subparsers.add_parser("extract", help="extract a 2x2 periodic electrode map")
    extraction.add_argument("manifest")
    extraction.add_argument("output")
    args = parser.parse_args(argv)
    try:
        metadata = extract(args.manifest, args.output)
    except (ManifestError, ResourceError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "electrodes": len(metadata["electrodes"]),
                "tr": len(metadata["tr"]),
                "output": args.output,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
