"""Command-line interface for jsonantt."""
from __future__ import annotations

import argparse
from datetime import date, datetime
import sys

from .parser import load_chart
from .renderer import render_chart, render_compare_chart, render_compare_table, render_table


def _parse_cli_date(value: str, date_format: str) -> date:
    """Parse a CLI date-line value using the chart date format or the special token today."""
    if value.strip().lower() == "today":
        return date.today()
    return datetime.strptime(value, date_format).date()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="jsonantt",
        description=(
            "Generate a Gantt chart or task table image from a JSON description.\n\n"
            "Examples:\n"
            "  jsonantt project.json chart.png\n"
            "  jsonantt -t project.json task-table.png\n"
            "  jsonantt project-agreed.json compare.png --compare project-actual.json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="Path to the JSON chart description file")
    parser.add_argument("output", help="Output image path (e.g. chart.png, chart.pdf)")
    parser.add_argument(
        "-c", "--compare",
        help=(
            "Optional second JSON input for compare mode. The first input is treated as the "
            "planned/agreed baseline and the --compare file is treated as the updated/actual state"
        ),
    )
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
    parser.add_argument(
        "--date-line",
        help="Optional single vertical line date for chart output, using the input dateformat or the special value 'today'",
    )
    parser.add_argument(
        "--date-line-color",
        default="#C00000",
        help="Color for --date-line (default: #C00000)",
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

    compare_config = None
    if args.compare:
        try:
            compare_config = load_chart(args.compare)
        except FileNotFoundError:
            print(f"error: compare input file not found: {args.compare}", file=sys.stderr)
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"error: failed to parse {args.compare}: {exc}", file=sys.stderr)
            return 1

    line_date = None
    if args.date_line:
        if args.table:
            print("error: --date-line is only supported for chart output", file=sys.stderr)
            return 1
        try:
            line_date = _parse_cli_date(args.date_line, config.date_format)
        except ValueError as exc:
            print(f"error: failed to parse --date-line {args.date_line!r}: {exc}", file=sys.stderr)
            return 1

    try:
        render_kwargs = {"dpi": args.dpi, "render_depth": args.renderdepth}
        if line_date is not None:
            render_kwargs["date_line"] = line_date
            render_kwargs["date_line_color"] = args.date_line_color
        if args.table:
            render_kwargs["milestones_only"] = args.milestones_only
            render_kwargs["no_milestones"] = args.no_milestones
        elif args.milestones_only:
            raise ValueError("--milestones-only requires --table")
        elif args.no_milestones:
            raise ValueError("--no-milestones requires --table")

        if compare_config is not None:
            render_fn = render_compare_table if args.table else render_compare_chart
            render_fn(config, compare_config, args.output, **render_kwargs)
        else:
            render_fn = render_table if args.table else render_chart
            render_fn(config, args.output, **render_kwargs)
    except Exception as exc:  # noqa: BLE001
        target = "compare table" if args.table and compare_config is not None else (
            "compare chart" if compare_config is not None else ("table" if args.table else "chart")
        )
        print(f"error: failed to render {target}: {exc}", file=sys.stderr)
        return 1

    target = "Compare table" if args.table and compare_config is not None else (
        "Compare chart" if compare_config is not None else ("Table" if args.table else "Chart")
    )
    print(f"{target} saved to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
