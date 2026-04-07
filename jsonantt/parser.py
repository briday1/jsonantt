"""JSON → model parser for jsonantt."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from .models import ChartConfig, Style, Task


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

    return ChartConfig(
        tasks=tasks,
        title=data.get("title", ""),
        date_format=date_format,
        start=start,
        end=end,
        style=style,
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
    color: Optional[str] = data.get("color", None)
    milestone: bool = bool(data.get("milestone", False))

    start = _parse_date(data["start"], date_format) if "start" in data else None
    end = _parse_date(data["end"], date_format) if "end" in data else None

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
        start=start,
        end=end,
        color=color,
        milestone=milestone,
        milestone_date=milestone_date,
        children=children,
    )
