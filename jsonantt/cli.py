"""Command-line interface for jsonantt."""
from __future__ import annotations

import argparse
import sys

from .parser import load_chart
from .renderer import render_chart, render_table


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="jsonantt",
        description=(
            "Generate a Gantt chart or task table image from a JSON description.\n\n"
            "Examples:\n"
            "  jsonantt project.json chart.png\n"
            "  jsonantt -t project.json task-table.png"
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
    parser.add_argument(
        "-t", "--table",
        action="store_true",
        help="Render a task table instead of a Gantt chart",
    )
    milestone_group = parser.add_mutually_exclusive_group()
    milestone_group.add_argument(
        "--milestones-only",
        action="store_true",
        help="When used with --table, render only milestone rows",
    )
    milestone_group.add_argument(
        "--no-milestones",
        action="store_true",
        help="When used with --table, exclude milestone rows",
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
        render_fn = render_table if args.table else render_chart
        render_kwargs = {"dpi": args.dpi, "render_depth": args.renderdepth}
        if args.table:
            render_kwargs["milestones_only"] = args.milestones_only
            render_kwargs["no_milestones"] = args.no_milestones
        elif args.milestones_only:
            raise ValueError("--milestones-only requires --table")
        elif args.no_milestones:
            raise ValueError("--no-milestones requires --table")
        render_fn(config, args.output, **render_kwargs)
    except Exception as exc:  # noqa: BLE001
        target = "table" if args.table else "chart"
        print(f"error: failed to render {target}: {exc}", file=sys.stderr)
        return 1

    target = "Table" if args.table else "Chart"
    print(f"{target} saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
