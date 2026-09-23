"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys

from .circuit import CircuitError
from .engine import extract
from .particle_sim_adapter import export_particle_sim
from .periodic import ResourceError
from .review import ReviewError, ReviewProject
from .schema import ManifestError
from .server import serve_review
from .synthetic import make_synthetic


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="layout-electrode-extractor")
    subparsers = parser.add_subparsers(dest="command", required=True)
    extraction = subparsers.add_parser("extract", help="extract a 2x2 periodic electrode map")
    extraction.add_argument("manifest")
    extraction.add_argument("output")
    review = subparsers.add_parser("review", help="open the local naming and circuit review UI")
    review.add_argument("extraction")
    review.add_argument("--circuit", help="explicit JSON/CSV circuit table")
    review.add_argument("--schematic", help="PNG/JPEG circuit reference image")
    review.add_argument("--port", type=int, default=8765)
    export = subparsers.add_parser("export-reviewed", help="write safely named reviewed masks")
    export.add_argument("extraction")
    export.add_argument("output")
    export.add_argument("--circuit")
    export.add_argument("--schematic")
    synthetic = subparsers.add_parser(
        "make-synthetic", help="write the reproducible assumed fixture"
    )
    synthetic.add_argument("output")
    particle_export = subparsers.add_parser(
        "export-particle-sim", help="export an extraction as particle-sim schema 2.0"
    )
    particle_export.add_argument("extraction")
    particle_export.add_argument("output")
    args = parser.parse_args(argv)
    try:
        if args.command == "review":
            serve_review(
                args.extraction,
                circuit=args.circuit,
                schematic=args.schematic,
                port=args.port,
            )
            return 0
        if args.command == "export-reviewed":
            project = ReviewProject(args.extraction, args.circuit, args.schematic)
            output = project.export(args.output)
            print(json.dumps({"output": str(output)}, sort_keys=True))
            return 0
        if args.command == "make-synthetic":
            result = make_synthetic(args.output)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "export-particle-sim":
            result = export_particle_sim(args.extraction, args.output)
            print(json.dumps(result, sort_keys=True))
            return 0
        metadata = extract(args.manifest, args.output)
    except (ManifestError, ResourceError, ReviewError, CircuitError, OSError) as exc:
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
