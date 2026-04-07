"""JSON → model parser for jsonantt."""
from __future__ import annotations

import calendar
import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from .models import Arrow, ChartConfig, Style, Task


def load_chart(path: str) -> ChartConfig:
    """Load and parse a Gantt JSON file, returning a :class:`ChartConfig`."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return parse_chart(data)


def parse_chart(data: Dict[str, Any]) -> ChartConfig:
    """Parse a raw JSON dict into a :class:`ChartConfig`."""
    date_format = data.get("dateformat", data.get("date_format", "%Y-%m-%d"))

    start: Optional[datetime] = None
    end: Optional[datetime] = None
    if "start" in data:
        start = _parse_date(data["start"], date_format)
    if "end" in data:
        end = _parse_date(data["end"], date_format)

    style = _parse_style(data.get("style", {}))

    tasks = [
        _parse_task(t, date_format, depth=0)
        for t in data.get("tasks", [])
    ]

    # Resolve not_before references now that all tasks are parsed
    all_tasks: Dict[str, Task] = {}
    _collect_by_id(tasks, all_tasks)
    _resolve_not_before(all_tasks)

    arrows = [
        Arrow(
            from_id=a["from"],
            to_id=a["to"],
            color=a.get("color", "#888888"),
            label=a.get("label"),
        )
        for a in data.get("arrows", [])
    ]

    return ChartConfig(
        tasks=tasks,
        title=data.get("title", ""),
        date_format=date_format,
        start=start,
        end=end,
        style=style,
        arrows=arrows,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_date(value: str, fmt: str):
    """Parse *value* with *fmt*; return a :class:`datetime.date`."""
    return datetime.strptime(value, fmt).date()


def _parse_style(data: Dict[str, Any]) -> Style:
    style = Style()
    mapping = {
        "width": "width",
        "row_height": "row_height",
        "bar_height": "bar_height",
        "font_size": "font_size",
        "indent_size": "indent_size",
        "label_fraction": "label_fraction",
        "colors": "colors",
        "background": "background",
        "grid_color": "grid_color",
        "row_band_color": "row_band_color",
        "milestone_color": "milestone_color",
        "milestone_size": "milestone_size",
        "major_tick": "major_tick",
        "minor_tick": "minor_tick",
        "major_grid_width": "major_grid_width",
        "minor_grid_width": "minor_grid_width",
        "bold_tasks": "bold_tasks",
        "number_tasks": "number_tasks",
        "table_colorize": "table_colorize",
        "table_show_markers": "table_show_markers",
        "tick_position": "tick_position",
    }
    for json_key, attr in mapping.items():
        if json_key in data:
            setattr(style, attr, data[json_key])
    return style


def _parse_task(data: Any, date_format: str, depth: int) -> Task:
    """Recursively parse a task dict."""
    if isinstance(data, str):
        # shorthand: just a name string with no dates
        return Task(name=data)

    name: str = data.get("name", "Unnamed")
    description: str = str(data.get("description", ""))
    task_id: Optional[str] = data.get("id", None)
    color: Optional[str] = data.get("color", None)
    milestone: bool = bool(data.get("milestone", False))
    not_before: Optional[str] = data.get("not_before", None)
    marker_size: Optional[float] = float(data["marker_size"]) if "marker_size" in data else None
    bold: bool = bool(data.get("bold", False))

    # duration may be an integer (days) or a string like "3m", "2y", "14d"
    duration_raw = data.get("duration", None)
    duration_spec: Optional[str] = str(duration_raw) if duration_raw is not None else None

    start = _parse_date(data["start"], date_format) if "start" in data else None
    end = _parse_date(data["end"], date_format) if "end" in data else None

    # start + duration → compute end immediately
    if start is not None and duration_spec is not None and end is None:
        end = _apply_duration(start, duration_spec)
        duration_spec = None  # resolved; no need to carry it further

    milestone_date = None
    if milestone:
        if "date" in data:
            milestone_date = _parse_date(data["date"], date_format)
        elif start is not None:
            milestone_date = start
        elif end is not None:
            milestone_date = end

    children: List[Task] = [
        _parse_task(child, date_format, depth + 1)
        for child in data.get("children", [])
    ]

    return Task(
        name=name,
        description=description,
        id=task_id,
        start=start,
        end=end,
        color=color,
        milestone=milestone,
        milestone_date=milestone_date,
        children=children,
        not_before=not_before,
        duration_spec=duration_spec,
        marker_size=marker_size,
        bold=bold,
    )


# ---------------------------------------------------------------------------
# Duration helpers
# ---------------------------------------------------------------------------

_DURATION_RE = re.compile(
    r"^\s*(\d+)\s*(d|day|days|w|week|weeks|m|month|months|y|year|years)\s*$",
    re.IGNORECASE,
)


def _parse_duration(spec: str):
    """Parse a duration string and return ``(unit, value)``.

    *unit* is one of ``'d'``, ``'m'``, ``'y'``.
    Bare integers are treated as days.
    """
    spec = str(spec).strip()
    if spec.isdigit():
        return ("d", int(spec))
    m = _DURATION_RE.match(spec)
    if not m:
        raise ValueError(
            f"Invalid duration spec {spec!r}. "
            "Use e.g. '14d', '2w', '3m', '2y', or a plain integer (days)."
        )
    value = int(m.group(1))
    unit_str = m.group(2).lower()
    if unit_str in ("d", "day", "days"):
        return ("d", value)
    elif unit_str in ("w", "week", "weeks"):
        return ("d", value * 7)
    elif unit_str in ("m", "month", "months"):
        return ("m", value)
    else:
        return ("y", value)


def _apply_duration(start: date, spec: str) -> date:
    """Return the date that is *spec* after *start*."""
    unit, value = _parse_duration(spec)
    if unit == "d":
        return start + timedelta(days=value)
    elif unit == "m":
        return _add_months(start, value)
    else:
        return _add_years(start, value)


def _add_months(d: date, months: int) -> date:
    """Add *months* to *d*, clamping day to the last day of the target month."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, max_day))


def _add_years(d: date, years: int) -> date:
    """Add *years* to *d* (handles Feb-29 in non-leap years)."""
    try:
        return date(d.year + years, d.month, d.day)
    except ValueError:
        return date(d.year + years, d.month, 28)


# ---------------------------------------------------------------------------
# not_before resolution helpers
# ---------------------------------------------------------------------------

def _collect_by_id(tasks: List[Task], mapping: Dict[str, Task]) -> None:
    """Recursively build a flat ``id -> Task`` mapping."""
    for task in tasks:
        if task.id is not None:
            mapping[task.id] = task
        _collect_by_id(task.children, mapping)


def _resolve_not_before(all_tasks: Dict[str, Task]) -> None:
    """Resolve ``not_before`` references, filling in ``start`` (and ``end``)."""
    max_passes = len(all_tasks) + 1
    for _ in range(max_passes):
        changed = False
        for task in all_tasks.values():
            if task.not_before is None or task.start is not None:
                continue
            ref = all_tasks.get(task.not_before)
            if ref is None:
                raise ValueError(
                    f"not_before references unknown id: {task.not_before!r}"
                )
            ref_end = ref.effective_end
            if ref_end is None:
                continue  # ref not yet resolved; try again next pass
            task.start = ref_end
            if task.milestone and task.milestone_date is None:
                task.milestone_date = task.start
            if task.duration_spec is not None:
                task.end = _apply_duration(task.start, task.duration_spec)
                task.duration_spec = None
            changed = True
        if not changed:
            break

    # Surface any remaining unresolved tasks (circular references etc.)
    for task in all_tasks.values():
        if task.not_before is not None and task.start is None:
            raise ValueError(
                f"Could not resolve not_before={task.not_before!r} "
                f"for task {task.name!r}. Check for circular references."
            )
