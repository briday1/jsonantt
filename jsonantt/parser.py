"""JSON → model parser for jsonantt."""
from __future__ import annotations

import calendar
import json
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import Arrow, ChartConfig, Style, Task


def load_chart(path: str) -> ChartConfig:
    """Load and parse a Gantt JSON file, returning a :class:`ChartConfig`."""
    resolved_path = os.path.abspath(path)
    with open(resolved_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return parse_chart(data, source_path=resolved_path, _seen_files={resolved_path})


def parse_chart(
    data: Dict[str, Any],
    source_path: Optional[str] = None,
    _seen_files: Optional[Set[str]] = None,
) -> ChartConfig:
    """Parse a raw JSON dict into a :class:`ChartConfig`."""
    date_format = data.get("dateformat", data.get("date_format", "%Y-%m-%d"))
    source_dir = os.path.dirname(os.path.abspath(source_path)) if source_path else None
    seen_files = set(_seen_files or set())

    start: Optional[datetime] = None
    end: Optional[datetime] = None
    if "start" in data:
        start = _parse_date(data["start"], date_format)
    if "end" in data:
        end = _parse_date(data["end"], date_format)

    style = _parse_style(data.get("style", {}))

    tasks = _parse_task_entries(
        _nested_task_items(data),
        date_format,
        depth=0,
        source_dir=source_dir,
        seen_files=seen_files,
    )

    # Resolve not_before references now that all tasks are parsed
    all_tasks: List[Task] = []
    all_tasks_by_id: Dict[str, Task] = {}
    _collect_tasks(tasks, all_tasks, all_tasks_by_id)
    _resolve_not_before(all_tasks, all_tasks_by_id)

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


def _parse_milestone_dates(value: Any, fmt: str) -> List[date]:
    """Parse a milestone ``date`` field as one or many dates."""
    if isinstance(value, list):
        return [_parse_date(item, fmt) for item in value]
    return [_parse_date(value, fmt)]


def _nested_task_items(data: Dict[str, Any]) -> List[Any]:
    """Return nested task items, accepting both ``tasks`` and legacy ``children``."""
    items: List[Any] = []
    if "tasks" in data:
        items.extend(data.get("tasks", []))
    if "children" in data:
        items.extend(data.get("children", []))
    return items


def _parse_task_entries(
    items: List[Any],
    date_format: str,
    depth: int,
    source_dir: Optional[str],
    seen_files: Set[str],
) -> List[Task]:
    """Parse task items, expanding filename-only include entries inline."""
    tasks: List[Task] = []
    for item in items:
        tasks.extend(_parse_task_entry(item, date_format, depth, source_dir, seen_files))
    return tasks


def _parse_task_entry(
    data: Any,
    date_format: str,
    depth: int,
    source_dir: Optional[str],
    seen_files: Set[str],
) -> List[Task]:
    """Parse one task entry, optionally inlining tasks from another file."""
    if isinstance(data, dict) and _is_filename_only_task_entry(data):
        included_data, included_source_dir, branch_seen_files = _load_included_chart_data(
            data["filename"],
            source_dir,
            seen_files,
        )
        included_date_format = included_data.get("dateformat", included_data.get("date_format", "%Y-%m-%d"))
        return _parse_task_entries(
            _nested_task_items(included_data),
            included_date_format,
            depth,
            included_source_dir,
            branch_seen_files,
        )

    return [_parse_task(data, date_format, depth, source_dir, seen_files)]


def _is_filename_only_task_entry(data: Dict[str, Any]) -> bool:
    """Return True when a task entry should inline the referenced file's tasks."""
    return set(data.keys()) == {"filename"}


def _load_included_chart_data(
    filename: str,
    source_dir: Optional[str],
    seen_files: Set[str],
) -> Tuple[Dict[str, Any], str, Set[str]]:
    """Load a nested chart file used to compose tasks across files."""
    resolved_path = filename if os.path.isabs(filename) else os.path.abspath(
        os.path.join(source_dir or os.getcwd(), filename)
    )
    if resolved_path in seen_files:
        raise ValueError(f"Circular filename reference detected: {resolved_path}")

    with open(resolved_path, "r", encoding="utf-8") as fh:
        included_data = json.load(fh)

    return included_data, os.path.dirname(resolved_path), seen_files | {resolved_path}


def _parse_style(data: Dict[str, Any]) -> Style:
    style = Style()
    mapping = {
        "width": "width",
        "row_height": "row_height",
        "bar_height": "bar_height",
        "font_size": "font_size",
        "indent_size": "indent_size",
        "label_fraction": "label_fraction",
        "subtask_lightening_pct": "subtask_lightening_pct",
        "colors": "colors",
        "background": "background",
        "grid_color": "grid_color",
        "row_band_color": "row_band_color",
        "milestone_color": "milestone_color",
        "milestone_edge_color": "milestone_edge_color",
        "milestone_marker": "milestone_marker",
        "milestone_size": "milestone_size",
        "rollup_milestones": "rollup_milestones",
        "rollup_major_milestones_only": "rollup_major_milestones_only",
        "number_milestones": "number_milestones",
        "major_milestone_color": "major_milestone_color",
        "major_milestone_edge_color": "major_milestone_edge_color",
        "major_milestone_marker": "major_milestone_marker",
        "major_milestone_size": "major_milestone_size",
        "major_tick": "major_tick",
        "minor_tick": "minor_tick",
        "major_grid_width": "major_grid_width",
        "minor_grid_width": "minor_grid_width",
        "bold_tasks": "bold_tasks",
        "number_tasks": "number_tasks",
        "table_colorize": "table_colorize",
        "table_show_markers": "table_show_markers",
        "tick_position": "tick_position",
        "table_columns": "table_columns",
    }
    for json_key, attr in mapping.items():
        if json_key in data:
            setattr(style, attr, data[json_key])
    return style


def _parse_task(
    data: Any,
    date_format: str,
    depth: int,
    source_dir: Optional[str],
    seen_files: Set[str],
) -> Task:
    """Recursively parse a task dict."""
    if isinstance(data, str):
        # shorthand: just a name string with no dates
        return Task(name=data)

    name: str = data.get("name", "Unnamed")
    description: str = str(data.get("description", ""))
    task_id: Optional[str] = data.get("id", None)
    color: Optional[str] = data.get("color", None)
    edge_color: Optional[str] = data.get("edge_color", None)
    major_milestone: bool = bool(data.get("major_milestone", False))
    milestone: bool = bool(data.get("milestone", False) or major_milestone)
    not_before: Optional[str] = data.get("not_before", None)
    marker_size: Optional[float] = float(data["marker_size"]) if "marker_size" in data else None
    marker: Optional[str] = str(data["marker"]) if "marker" in data else None
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

    milestone_dates: List[date] = []
    milestone_date = None
    if milestone:
        if "date" in data:
            milestone_dates = _parse_milestone_dates(data["date"], date_format)
            milestone_date = milestone_dates[0] if milestone_dates else None
        elif start is not None:
            milestone_dates = [start]
            milestone_date = start
        elif end is not None:
            milestone_dates = [end]
            milestone_date = end

    children: List[Task] = []
    if "filename" in data:
        included_data, included_source_dir, branch_seen_files = _load_included_chart_data(
            data["filename"],
            source_dir,
            seen_files,
        )
        included_date_format = included_data.get("dateformat", included_data.get("date_format", "%Y-%m-%d"))
        children.extend(
            _parse_task_entries(
                _nested_task_items(included_data),
                included_date_format,
                depth + 1,
                included_source_dir,
                branch_seen_files,
            )
        )

    children.extend(
        _parse_task_entries(
            _nested_task_items(data),
            date_format,
            depth + 1,
            source_dir,
            seen_files,
        )
    )

    known_fields = {
        "name",
        "description",
        "id",
        "start",
        "end",
        "duration",
        "not_before",
        "color",
        "edge_color",
        "milestone",
        "major_milestone",
        "date",
        "marker",
        "marker_size",
        "bold",
        "filename",
        "tasks",
        "children",
    }
    extra_fields = {
        key: value
        for key, value in data.items()
        if key not in known_fields
    }

    return Task(
        name=name,
        description=description,
        id=task_id,
        start=start,
        end=end,
        color=color,
        edge_color=edge_color,
        milestone=milestone,
        major_milestone=major_milestone,
        milestone_date=milestone_date,
        milestone_dates=milestone_dates,
        children=children,
        not_before=not_before,
        duration_spec=duration_spec,
        marker_size=marker_size,
        marker=marker,
        bold=bold,
        fields=extra_fields,
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

def _collect_tasks(
    tasks: List[Task],
    collected: List[Task],
    mapping: Dict[str, Task],
) -> None:
    """Recursively collect all tasks and build an ``id -> Task`` mapping."""
    for task in tasks:
        collected.append(task)
        if task.id is not None:
            mapping[task.id] = task
        _collect_tasks(task.children, collected, mapping)


def _resolve_not_before(all_tasks: List[Task], all_tasks_by_id: Dict[str, Task]) -> None:
    """Resolve ``not_before`` references, filling in ``start`` (and ``end``)."""
    max_passes = len(all_tasks) + 1
    for _ in range(max_passes):
        changed = False
        for task in all_tasks:
            if task.not_before is None or task.start is not None:
                continue
            ref = all_tasks_by_id.get(task.not_before)
            if ref is None:
                raise ValueError(
                    f"not_before references unknown id: {task.not_before!r}"
                )
            ref_end = ref.effective_end
            if ref_end is None:
                continue  # ref not yet resolved; try again next pass
            task.start = ref_end
            if task.milestone and task.milestone_date is None:
                task.milestone_dates = [task.start]
                task.milestone_date = task.start
            if task.duration_spec is not None:
                task.end = _apply_duration(task.start, task.duration_spec)
                task.duration_spec = None
            changed = True
        if not changed:
            break

    # Surface any remaining unresolved tasks (circular references etc.)
    for task in all_tasks:
        if task.not_before is not None and task.start is None:
            raise ValueError(
                f"Could not resolve not_before={task.not_before!r} "
                f"for task {task.name!r}. Check for circular references."
            )
