"""Command-line interface for jsonantt."""
from __future__ import annotations

import argparse
import sys

from .parser import load_chart
from .renderer import render_chart


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="jsonantt",
        description=(
            "Generate a Gantt chart image from a JSON description.\n\n"
            "Example:\n  jsonantt project.json chart.png\n  jsonantt project.json chart.pdf"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="Path to the JSON chart description file")
    parser.add_argument("output", help="Output image path (e.g. chart.png, chart.pdf)")
    parser.add_argument(
        "--dpi", type=int, default=150,
        help="Image resolution in DPI (default: 150, raster formats only)",
    )
    parser.add_argument(
        "-r", "--renderdepth",
        type=int,
        default=0,
        help=(
            "Maximum nesting depth to render: 0 renders all levels, 1 renders only "
            "top-level tasks, 2 includes one level of children, and so on"
        ),
    )

    args = parser.parse_args(argv)

    try:
        config = load_chart(args.input)
    except FileNotFoundError:
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"error: failed to parse {args.input}: {exc}", file=sys.stderr)
        return 1

    try:
        render_chart(config, args.output, dpi=args.dpi, render_depth=args.renderdepth)
    except Exception as exc:  # noqa: BLE001
        print(f"error: failed to render chart: {exc}", file=sys.stderr)
        return 1

    print(f"Chart saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
