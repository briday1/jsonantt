"""matplotlib-based Gantt chart renderer for jsonantt."""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import json
import math
import os
import re
import textwrap
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.font_manager import FontProperties
from matplotlib.figure import Figure
from matplotlib.text import Text

from .models import Arrow, ChartConfig, Style, Task


def _milestone_marker(task: Task, style: Style) -> str:
    """Return the marker symbol for a milestone, preferring task override."""
    return task.marker if task.marker else style.milestone_marker


def _milestone_color(row: _Row, style: Style) -> str:
    """Return the milestone color for a row, preferring task color override."""
    return row.task.color if row.task.color else style.milestone_color


def _lighten(color: str, amount: float = 0.0) -> str:
    """Lighten *color* toward white by *amount* in the range 0..1."""
    try:
        color = color.lstrip("#")
        if len(color) != 6:
            return color
        amount = max(0.0, min(1.0, amount))
        red = int(color[0:2], 16)
        green = int(color[2:4], 16)
        blue = int(color[4:6], 16)
        red = round(red + (255 - red) * amount)
        green = round(green + (255 - green) * amount)
        blue = round(blue + (255 - blue) * amount)
        return f"#{red:02X}{green:02X}{blue:02X}"
    except Exception:
        return color if color.startswith("#") else f"#{color}"

# ---------------------------------------------------------------------------
# Internal helper types
# ---------------------------------------------------------------------------


class _Row:
    """A flattened task row ready for rendering."""

    __slots__ = ("task", "depth", "row_index", "color", "number", "path_key")

    def __init__(
        self,
        task: Task,
        depth: int,
        row_index: int,
        color: str,
        number: str = "",
        path_key: Tuple[str, ...] = (),
    ) -> None:
        self.task = task
        self.depth = depth
        self.row_index = row_index
        self.color = color
        self.number = number
        self.path_key = path_key


class _CompareRow:
    """A merged row representing planned and/or actual task state."""

    __slots__ = ("planned", "actual", "depth", "row_index", "number")

    def __init__(
        self,
        planned: Optional[_Row] = None,
        actual: Optional[_Row] = None,
        row_index: int = 0,
    ) -> None:
        self.planned = planned
        self.actual = actual
        base_row = actual if actual is not None else planned
        if base_row is None:
            raise ValueError("compare row requires planned and/or actual data")
        self.depth = base_row.depth
        self.row_index = row_index
        self.number = planned.number if planned is not None else base_row.number

    @property
    def task(self) -> Task:
        return self.actual.task if self.actual is not None else self.planned.task

    @property
    def description(self) -> str:
        actual_desc = self.actual.task.description if self.actual is not None else ""
        planned_desc = self.planned.task.description if self.planned is not None else ""
        return actual_desc or planned_desc

    @property
    def is_removed(self) -> bool:
        return self.planned is not None and self.actual is None

    @property
    def is_added(self) -> bool:
        return self.actual is not None and self.planned is None


def _default_table_title(field: str) -> str:
    """Return the default display title for a table field."""
    titles = {
        "task": "Task",
        "name": "Name",
        "description": "Description",
        "id": "ID",
        "not_before": "Not Before",
        "effective_start": "Effective Start",
        "effective_end": "Effective End",
        "milestone_date": "Date",
        "date": "Date",
        "offset": "Offset",
    }
    return titles.get(field, field.replace("_", " ").title())


def _coerce_display_factor(value: Any) -> Decimal:
    """Return a validated numeric display factor for a table column."""
    if value is None:
        return Decimal("1")
    if isinstance(value, bool):
        raise ValueError("style.table_columns display_factor must be numeric when provided")
    try:
        factor = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("style.table_columns display_factor must be numeric when provided") from exc
    if factor.is_nan() or factor.is_infinite():
        raise ValueError("style.table_columns display_factor must be a finite number")
    return factor


def _resolve_table_columns(style: Style, include_offset: bool = False) -> List[Dict[str, str]]:
    """Return normalized table columns from ``style.table_columns``."""
    raw_columns = style.table_columns or ["task", "name", "description"]
    columns: List[Dict[str, str]] = []

    for item in raw_columns:
        if isinstance(item, str):
            field = item.strip()
            if not field:
                raise ValueError("style.table_columns cannot contain blank field names")
            columns.append({
                "field": field,
                "title": _default_table_title(field),
                "rollup": None,
                "total": False,
                "total_level": None,
                "display_factor": Decimal("1"),
            })
            continue

        if isinstance(item, dict):
            field = str(item.get("field", "")).strip()
            if not field:
                raise ValueError("style.table_columns object entries require a non-empty 'field'")
            title = str(item.get("title", _default_table_title(field)))
            rollup = item.get("rollup")
            if rollup is True:
                rollup = "sum"
            if rollup not in (None, False, "sum"):
                raise ValueError("style.table_columns rollup must be 'sum' or true when provided")

            total_level = item.get("total_level")
            if total_level is not None:
                if not isinstance(total_level, int) or total_level < 0:
                    raise ValueError("style.table_columns total_level must be a non-negative integer")

            display_factor = _coerce_display_factor(item.get("display_factor"))

            columns.append({
                "field": field,
                "title": title,
                "rollup": rollup,
                "total": bool(item.get("total", False)),
                "total_level": total_level,
                "display_factor": display_factor,
            })
            continue

        raise ValueError("style.table_columns entries must be strings or objects with 'field'")

    if not columns:
        raise ValueError("style.table_columns must contain at least one column")

    if include_offset and not any(column["field"] == "offset" for column in columns):
        columns.append({
            "field": "offset",
            "title": "Offset",
            "rollup": None,
            "total": False,
            "total_level": None,
            "display_factor": Decimal("1"),
        })
    return columns


_NUMERIC_VALUE_RE = re.compile(
    r"^\s*(?P<prefix>[^\d+\-.]*)?(?P<number>[+\-]?(?:\d+(?:,\d{3})*|\d+)(?:\.\d+)?)\s*(?P<suffix>[^\d]*)\s*$"
)


def _parse_numeric_table_value(value: Any) -> Optional[Dict[str, Any]]:
    """Parse a numeric or currency-like value for rollup and totals."""
    if isinstance(value, bool) or value is None:
        return None

    if isinstance(value, int):
        return {
            "amount": Decimal(value),
            "prefix": "",
            "suffix": "",
            "places": 0,
            "thousands": False,
        }

    if isinstance(value, float):
        text = format(value, "f").rstrip("0").rstrip(".")
        places = len(text.split(".", 1)[1]) if "." in text else 0
        return {
            "amount": Decimal(str(value)),
            "prefix": "",
            "suffix": "",
            "places": places,
            "thousands": False,
        }

    if isinstance(value, Decimal):
        normalized = format(value, "f")
        places = len(normalized.split(".", 1)[1].rstrip("0")) if "." in normalized else 0
        return {
            "amount": value,
            "prefix": "",
            "suffix": "",
            "places": places,
            "thousands": False,
        }

    if not isinstance(value, str):
        return None

    match = _NUMERIC_VALUE_RE.match(value)
    if not match:
        return None

    number_text = match.group("number")
    try:
        amount = Decimal(number_text.replace(",", ""))
    except InvalidOperation:
        return None

    places = len(number_text.split(".", 1)[1]) if "." in number_text else 0
    return {
        "amount": amount,
        "prefix": (match.group("prefix") or "").strip(),
        "suffix": (match.group("suffix") or "").strip(),
        "places": places,
        "thousands": "," in number_text,
    }


def _merge_numeric_specs(values: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Merge formatting metadata across multiple numeric-like values."""
    if not values:
        return None

    prefix = values[0]["prefix"]
    suffix = values[0]["suffix"]
    if any(value["prefix"] != prefix or value["suffix"] != suffix for value in values):
        return None

    return {
        "prefix": prefix,
        "suffix": suffix,
        "places": max(value["places"] for value in values),
        "thousands": any(value["thousands"] for value in values),
    }


def _format_numeric_table_value(amount: Decimal, spec: Dict[str, Any]) -> str:
    """Format an aggregated numeric value using merged metadata."""
    min_places = int(spec.get("min_places", spec["places"]))
    max_places = int(spec.get("max_places", spec["places"]))
    places = max(min_places, max_places)
    quantizer = Decimal("1") if places == 0 else Decimal("1").scaleb(-places)
    quantized = amount.quantize(quantizer)

    number_text = f"{quantized:,.{places}f}" if spec["thousands"] else f"{quantized:.{places}f}"
    if "." in number_text and max_places > min_places:
        whole, fraction = number_text.split(".", 1)
        trimmed_fraction = fraction.rstrip("0")
        if len(trimmed_fraction) < min_places:
            trimmed_fraction = fraction[:min_places]
        number_text = whole if not trimmed_fraction else f"{whole}.{trimmed_fraction}"

    sign = "-" if quantized < 0 else ""
    if sign:
        number_text = number_text[1:]

    prefix = spec["prefix"]
    suffix = spec["suffix"]
    if prefix:
        prefix += " " if prefix.endswith(":") else ""
    if suffix:
        suffix = " " + suffix

    return f"{sign}{prefix}{number_text}{suffix}".strip()


def _display_numeric_table_value(numeric_value: Dict[str, Any], column: Dict[str, Any]) -> str:
    """Format a numeric table value after applying any display conversion."""
    display_factor = column["display_factor"]
    base_spec = numeric_value.get("spec", numeric_value)
    display_spec = _numeric_display_spec(base_spec, display_factor)
    return _format_numeric_table_value(
        numeric_value["amount"] * display_factor,
        display_spec,
    )


def _numeric_display_spec(spec: Dict[str, Any], display_factor: Decimal) -> Dict[str, Any]:
    """Return a numeric format spec adjusted for a display-time scale factor."""
    scale_places = max(0, -display_factor.normalize().as_tuple().exponent) if display_factor != 0 else 0
    display_spec = dict(spec)
    display_spec["min_places"] = int(display_spec["places"])
    display_spec["max_places"] = int(display_spec["places"]) + scale_places
    return display_spec


def _table_column_min_width(field: str) -> float:
    """Return the minimum width in inches for a table column."""
    if field == "task":
        return 0.55
    if field == "name":
        return 1.6
    if field == "description":
        return 2.6
    if field == "offset":
        return 1.2
    return 1.4


def _table_expand_index(columns: List[Dict[str, str]]) -> int:
    """Return the index of the column that should absorb extra width."""
    for index, column in enumerate(columns):
        if column["field"] == "description":
            return index
    return len(columns) - 1


def _has_table_value(value: Any) -> bool:
    """Return True when *value* should be preferred in compare-table fallback."""
    return value is not None and value != "" and value != [] and value != {}


def _format_table_value(value: Any) -> str:
    """Convert a task field value to display text for tables and CSV."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _task_field_value(task: Task, field: str) -> Any:
    """Return a raw field value from *task* for table rendering."""
    if field == "date":
        return task.milestone_date
    if hasattr(task, field):
        return getattr(task, field)
    return task.fields.get(field)


def _task_rollup_value(task: Task, field: str) -> Optional[Dict[str, Any]]:
    """Return a recursively summed numeric value for *task* and *field*."""
    parsed_values: List[Dict[str, Any]] = []
    total = Decimal("0")

    own_value = _parse_numeric_table_value(_task_field_value(task, field))
    if own_value is not None:
        parsed_values.append(own_value)
        total += own_value["amount"]

    for child in task.children:
        child_value = _task_rollup_value(child, field)
        if child_value is None:
            continue
        parsed_values.append(child_value["spec"])
        total += child_value["amount"]

    if not parsed_values:
        return None

    spec = _merge_numeric_specs(parsed_values)
    if spec is None:
        return None

    return {"amount": total, "spec": spec}


def _task_table_numeric_value(task: Task, column: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a numeric table value for *task* and *column* when possible."""
    if column["rollup"] == "sum":
        return _task_rollup_value(task, column["field"])
    return _parse_numeric_table_value(_task_field_value(task, column["field"]))


def _compare_table_numeric_value(row: _CompareRow, column: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a numeric table value for a compare row and column when possible."""
    if column["field"] in ("task", "name", "description", "offset"):
        return None

    tasks: List[Task] = []
    if row.actual is not None:
        tasks.append(row.actual.task)
    if row.planned is not None:
        tasks.append(row.planned.task)

    for task in tasks:
        numeric_value = _task_table_numeric_value(task, column)
        if numeric_value is not None:
            return numeric_value
    return None


def _row_table_cell(row: _Row, column: Dict[str, Any]) -> str:
    """Return the rendered table cell text for *row* and *field*."""
    field = column["field"]
    if field == "task":
        return _row_table_number(row)
    if field == "name":
        return row.task.name
    numeric_value = _task_table_numeric_value(row.task, column)
    if numeric_value is not None:
        return _display_numeric_table_value(numeric_value, column)
    return _format_table_value(_task_field_value(row.task, field))


def _compare_row_table_cell(row: _CompareRow, column: Dict[str, Any]) -> str:
    """Return the rendered compare-table cell text for *row* and *field*."""
    field = column["field"]
    if field == "task":
        return _compare_row_table_number(row)
    if field == "name":
        return _compare_display_name(row)
    if field == "description":
        return row.description
    if field == "offset":
        return _format_compare_offset(row)

    numeric_value = _compare_table_numeric_value(row, column)
    if numeric_value is not None:
        return _display_numeric_table_value(numeric_value, column)

    candidates: List[Task] = []
    if row.actual is not None:
        candidates.append(row.actual.task)
    if row.planned is not None:
        candidates.append(row.planned.task)

    fallback: Any = None
    for task in candidates:
        value = _task_field_value(task, field)
        if _has_table_value(value):
            return _format_table_value(value)
        if fallback is None:
            fallback = value
    return _format_table_value(fallback)


def _table_footer_label_index(columns: List[Dict[str, Any]]) -> int:
    """Return the preferred footer label column index."""
    for preferred in ("name", "description", "task"):
        for index, column in enumerate(columns):
            if column["field"] == preferred:
                return index
    return 0


def _table_total_candidate_rows(rows, column: Dict[str, Any]):
    """Return the rows that contribute to a column footer total."""
    level = column["total_level"]
    if level is not None:
        return [row for row in rows if row.depth == level]
    if column["rollup"] == "sum":
        return [row for row in rows if row.depth == 0]
    return list(rows)


def _build_table_footer_cells(rows, columns: List[Dict[str, Any]], numeric_value_fn) -> Optional[List[str]]:
    """Build footer cells for configured totals, or return None."""
    footer_cells = ["" for _ in columns]
    has_total = False

    for index, column in enumerate(columns):
        if not column["total"]:
            continue

        numeric_values: List[Dict[str, Any]] = []
        total_amount = Decimal("0")
        for row in _table_total_candidate_rows(rows, column):
            numeric_value = numeric_value_fn(row, column)
            if numeric_value is None:
                continue
            numeric_values.append(numeric_value["spec"])
            total_amount += numeric_value["amount"]

        if not numeric_values:
            continue

        spec = _merge_numeric_specs(numeric_values)
        if spec is None:
            continue

        display_factor = column["display_factor"]
        footer_spec = _numeric_display_spec(spec, display_factor)
        footer_cells[index] = _format_numeric_table_value(total_amount * display_factor, footer_spec)
        has_total = True

    if not has_total:
        return None

    footer_cells[_table_footer_label_index(columns)] = "Total"
    return footer_cells


def _table_cell_font_props(row, field: str, style: Style, font_props: FontProperties, bold_font_props: FontProperties) -> FontProperties:
    """Return the font properties for a table cell."""
    if field in ("task", "name") and (row.task.bold or (style.bold_tasks and row.depth == 0)):
        return bold_font_props
    return font_props


def _fit_table_widths(
    natural_widths: List[float],
    min_widths: List[float],
    total_width: float,
    expand_index: int,
) -> List[float]:
    """Fit measured table widths into the available table width."""
    if not natural_widths:
        return []

    widths = list(natural_widths)
    current_total = sum(widths)
    if current_total < total_width:
        widths[expand_index] += total_width - current_total
        return widths

    overflow = current_total - total_width
    reducible = [max(0.0, width - min_width) for width, min_width in zip(widths, min_widths)]
    total_reducible = sum(reducible)
    if total_reducible >= overflow and total_reducible > 0:
        remaining = overflow
        while remaining > 1e-6:
            active = [index for index, room in enumerate(reducible) if room > 1e-6]
            if not active:
                break
            active_total = sum(reducible[index] for index in active)
            reduced = 0.0
            for index in active:
                share = remaining * (reducible[index] / active_total)
                delta = min(share, reducible[index])
                widths[index] -= delta
                reducible[index] -= delta
                reduced += delta
            if reduced <= 1e-6:
                break
            remaining -= reduced
        return widths

    min_total = sum(min_widths)
    if min_total <= 0:
        return [total_width / len(min_widths)] * len(min_widths)
    scale = total_width / min_total
    return [min_width * scale for min_width in min_widths]


def _measure_table_column_widths(
    rows,
    columns: List[Dict[str, str]],
    style: Style,
    table_width_in: float,
    col_padding_in: float,
    gutter_extra_in: float,
    cell_value_fn,
    footer_cells: Optional[List[str]] = None,
) -> List[float]:
    """Return fitted column widths for a table."""
    font_props = FontProperties(size=style.font_size, weight="normal")
    bold_font_props = FontProperties(size=style.font_size, weight="bold")
    natural_widths: List[float] = []
    min_widths: List[float] = []

    for index, column in enumerate(columns):
        field = column["field"]
        measured_width = _measure_text_width_in(column["title"], bold_font_props)
        for row in rows:
            cell_text = cell_value_fn(row, column)
            cell_font_props = _table_cell_font_props(row, field, style, font_props, bold_font_props)
            measured_width = max(measured_width, _measure_text_width_in(cell_text, cell_font_props))

        if footer_cells is not None:
            measured_width = max(measured_width, _measure_text_width_in(footer_cells[index], bold_font_props))

        width = measured_width + col_padding_in
        min_width = _table_column_min_width(field)
        if index == 0:
            width += gutter_extra_in
            min_width += gutter_extra_in

        natural_widths.append(max(min_width, width))
        min_widths.append(min_width)

    return _fit_table_widths(natural_widths, min_widths, table_width_in, _table_expand_index(columns))


def _wrap_table_rows(
    rows,
    columns: List[Dict[str, str]],
    widths_in: List[float],
    style: Style,
    col_padding_in: float,
    cell_value_fn,
    footer_cells: Optional[List[str]] = None,
):
    """Wrap table cell text to fitted widths and return row layout info."""
    font_props = FontProperties(size=style.font_size, weight="normal")
    bold_font_props = FontProperties(size=style.font_size, weight="bold")
    wrapped_rows = []
    total_units = 1.3

    for row in rows:
        wrapped_cells: List[List[str]] = []
        line_count = 1
        for column, width_in in zip(columns, widths_in):
            field = column["field"]
            cell_text = cell_value_fn(row, column)
            cell_font_props = _table_cell_font_props(row, field, style, font_props, bold_font_props)
            lines = _wrap_text_measured(cell_text, width_in - col_padding_in, cell_font_props)
            wrapped_cells.append(lines)
            line_count = max(line_count, len(lines))
        row_units = line_count + 0.6
        wrapped_rows.append((row, wrapped_cells, row_units, False))
        total_units += row_units

    if footer_cells is not None:
        wrapped_footer: List[List[str]] = []
        line_count = 1
        for cell_text, width_in in zip(footer_cells, widths_in):
            lines = _wrap_text_measured(cell_text, width_in - col_padding_in, bold_font_props)
            wrapped_footer.append(lines)
            line_count = max(line_count, len(lines))
        row_units = line_count + 0.6
        wrapped_rows.append((None, wrapped_footer, row_units, True))
        total_units += row_units

    return wrapped_rows, total_units


def _normalize_burn_period(period: str) -> str:
    """Return a validated burn reporting period key."""
    key = str(period).strip().lower()
    aliases = {
        "day": "day",
        "days": "day",
        "week": "week",
        "weeks": "week",
        "month": "month",
        "months": "month",
        "quarter": "quarter",
        "quarters": "quarter",
        "year": "year",
        "years": "year",
    }
    if key not in aliases:
        raise ValueError("burn period must be one of day, week, month, quarter, or year")
    return aliases[key]


def _normalize_burn_group_by(group_by: Any) -> Any:
    """Return a validated burn grouping selector."""
    if isinstance(group_by, int):
        if group_by < 0:
            raise ValueError("burn group depth must be >= 0")
        return group_by

    key = str(group_by).strip().lower()
    if key in ("", "0"):
        return 0
    if key in ("total", "sum"):
        return "total"
    if key in ("leaf", "leaves", "all"):
        return "leaf"
    if key.isdigit():
        return int(key)
    raise ValueError("burn group must be 'total', 'leaf', or a non-negative integer depth")


def _next_period_start(start: date, period: str) -> date:
    """Return the start of the next reporting period."""
    key = _normalize_burn_period(period)
    if key == "day":
        return start + timedelta(days=1)
    if key == "week":
        return start + timedelta(weeks=1)
    if key == "month":
        month = start.month + 1
        year = start.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        return date(year, month, 1)
    if key == "quarter":
        month = start.month + 3
        year = start.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        return date(year, month, 1)
    return date(start.year + 1, 1, 1)


def _format_period_label(start: date, period: str) -> str:
    """Return the display label for a reporting period."""
    key = _normalize_burn_period(period)
    if key == "day":
        return start.isoformat()
    if key == "week":
        return f"Week of {start.isoformat()}"
    if key == "month":
        return start.strftime("%Y-%m")
    if key == "quarter":
        quarter = ((start.month - 1) // 3) + 1
        return f"{start.year}-Q{quarter}"
    return str(start.year)


def _task_burn_span(task: Task) -> Optional[Tuple[date, date]]:
    """Return the half-open burn interval for a task."""
    start = task.effective_start
    end = task.effective_end

    if task.milestone:
        if start is None:
            return None
        return start, start + timedelta(days=1)

    if start is None and end is None:
        return None
    if start is None:
        start = end
    if end is None:
        end = start + timedelta(days=1)
    if end <= start:
        end = start + timedelta(days=1)
    return start, end


def _collect_burn_sources(tasks: List[Task], style: Style, field: str) -> List[Dict[str, Any]]:
    """Return direct-cost burn sources with hierarchy metadata."""
    palette = style.colors or ["#4472C4"]
    palette_index = 0
    lighten_amount = max(0.0, min(100.0, style.subtask_lightening_pct)) / 100.0
    sources: List[Dict[str, Any]] = []

    def visit(
        branch: List[Task],
        depth: int = 0,
        parent_color: Optional[str] = None,
        number_prefix: str = "",
        ancestors: Tuple[Dict[str, Any], ...] = (),
    ) -> None:
        nonlocal palette_index

        for task_idx, task in enumerate(branch):
            if task.color:
                color = task.color
            elif parent_color and depth > 0:
                color = _lighten(parent_color, lighten_amount)
            else:
                color = palette[palette_index % len(palette)]
                palette_index += 1

            number = number_prefix + str(task_idx + 1)
            ancestor = {
                "depth": depth,
                "name": task.name,
                "number": number,
                "color": color,
            }
            lineage = ancestors + (ancestor,)

            numeric_value = _parse_numeric_table_value(_task_field_value(task, field))
            if numeric_value is not None:
                span = _task_burn_span(task)
                if span is None:
                    raise ValueError(f"Task {task.name!r} has numeric field {field!r} but no dates for burn allocation")
                start, end = span
                sources.append({
                    "task": task,
                    "depth": depth,
                    "name": task.name,
                    "number": number,
                    "color": color,
                    "amount": numeric_value["amount"],
                    "spec": numeric_value,
                    "start": start,
                    "end": end,
                    "ancestors": lineage,
                })

            if task.children:
                visit(
                    task.children,
                    depth=depth + 1,
                    parent_color=color,
                    number_prefix=number + ".",
                    ancestors=lineage,
                )

    visit(tasks)
    return sources


def _burn_series_for_source(source: Dict[str, Any], group_by: Any) -> Dict[str, Any]:
    """Return the target series metadata for a burn source."""
    if group_by == "total":
        return {
            "key": "__total__",
            "number": "",
            "name": "Total",
            "depth": -1,
            "color": source["color"],
        }

    if group_by == "leaf":
        ancestor = source["ancestors"][-1]
    else:
        ancestor = source["ancestors"][min(int(group_by), len(source["ancestors"]) - 1)]

    return {
        "key": ancestor["number"],
        "number": ancestor["number"],
        "name": ancestor["name"],
        "depth": ancestor["depth"],
        "color": ancestor["color"],
    }


def _format_burn_amount(amount: Decimal, spec: Dict[str, Any], display_factor: Decimal) -> str:
    """Format a burn amount using the shared numeric display rules."""
    return _format_numeric_table_value(amount * display_factor, _numeric_display_spec(spec, display_factor))


def _build_burn_matrix(
    config: ChartConfig,
    field: str = "cost",
    period: str = "month",
    group_by: Any = 0,
    display_factor: Any = 1,
) -> Dict[str, Any]:
    """Build grouped burn data for charts and matrix tables."""
    period_key = _normalize_burn_period(period)
    group_key = _normalize_burn_group_by(group_by)
    display_factor_decimal = _coerce_display_factor(display_factor)
    sources = _collect_burn_sources(config.tasks, config.style, field)

    if not sources:
        raise ValueError(f"No numeric {field!r} values available for burn output")

    spec = _merge_numeric_specs([source["spec"] for source in sources])
    if spec is None:
        raise ValueError(f"Cannot mix incompatible numeric formats in burn field {field!r}")

    period_start = config.start if config.start else min(source["start"] for source in sources)
    period_end = config.end if config.end else max(source["end"] for source in sources)
    period_start = _snap_to_tick_start(period_start, period_key)
    period_end = _snap_to_tick_end(period_end, period_key)
    if period_end <= period_start:
        period_end = _next_period_start(period_start, period_key)

    periods: List[Dict[str, Any]] = []
    cursor = period_start
    while cursor < period_end:
        next_cursor = _next_period_start(cursor, period_key)
        periods.append({
            "start": cursor,
            "end": next_cursor,
            "label": _format_period_label(cursor, period_key),
        })
        cursor = next_cursor

    series_map: Dict[str, Dict[str, Any]] = {}
    for source in sources:
        series_meta = _burn_series_for_source(source, group_key)
        series = series_map.get(series_meta["key"])
        if series is None:
            series = dict(series_meta)
            series["values"] = [Decimal("0") for _ in periods]
            series_map[series_meta["key"]] = series

        duration_days = (source["end"] - source["start"]).days
        if duration_days <= 0:
            duration_days = 1
        daily_rate = source["amount"] / Decimal(duration_days)

        for index, bucket in enumerate(periods):
            overlap_start = max(source["start"], bucket["start"])
            overlap_end = min(source["end"], bucket["end"])
            overlap_days = (overlap_end - overlap_start).days
            if overlap_days > 0:
                series["values"][index] += daily_rate * Decimal(overlap_days)

    series_list = list(series_map.values())
    totals = [sum((series["values"][idx] for series in series_list), Decimal("0")) for idx in range(len(periods))]
    return {
        "field": field,
        "period": period_key,
        "group_by": group_key,
        "display_factor": display_factor_decimal,
        "spec": spec,
        "periods": periods,
        "series": series_list,
        "totals": totals,
        "style": config.style,
        "title": config.title,
    }


def _burn_series_label(series: Dict[str, Any], style: Style) -> str:
    """Return the display label for a burn series."""
    if not series["number"] or not style.number_tasks:
        return series["name"]
    number_str = series["number"] + "." if "." not in series["number"] else series["number"]
    return f"{number_str}  {series['name']}"


def _write_burn_table_csv(burn: Dict[str, Any], output_path: str) -> None:
    """Write burn matrix output to CSV."""
    headers = ["Task", "Name"] + [period["label"] for period in burn["periods"]]
    include_footer = not (len(burn["series"]) == 1 and burn["series"][0]["key"] == "__total__")

    with open(output_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for series in burn["series"]:
            writer.writerow(
                [series["number"] + "." if series["number"] and "." not in series["number"] else series["number"], series["name"]]
                + [_format_burn_amount(value, burn["spec"], burn["display_factor"]) for value in series["values"]]
            )
        if include_footer:
            writer.writerow(["", "Total"] + [_format_burn_amount(value, burn["spec"], burn["display_factor"]) for value in burn["totals"]])


def render_burn_chart(
    config: ChartConfig,
    output_path: str,
    dpi: int = 150,
    field: str = "cost",
    period: str = "month",
    group_by: Any = 0,
    display_factor: Any = 1,
) -> None:
    """Render a funded burn chart from a numeric task field over time buckets."""
    burn = _build_burn_matrix(config, field=field, period=period, group_by=group_by, display_factor=display_factor)
    style = config.style
    period_labels = [bucket["label"] for bucket in burn["periods"]]
    x_values = list(range(len(period_labels)))
    fig_w = max(style.width, 4.5 + len(period_labels) * 0.65)
    fig_h = max(4.8, 3.6 + max(0, len(burn["series"]) - 1) * 0.2)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor=style.background)
    ax.set_facecolor(style.background)

    bottoms = [0.0 for _ in x_values]
    if len(burn["series"]) == 1 and burn["series"][0]["key"] == "__total__":
        series = burn["series"][0]
        values = [float(value * burn["display_factor"]) for value in series["values"]]
        ax.bar(x_values, values, color=series["color"], width=0.72, edgecolor="white", linewidth=0.8)
    else:
        for series in burn["series"]:
            values = [float(value * burn["display_factor"]) for value in series["values"]]
            ax.bar(
                x_values,
                values,
                bottom=bottoms,
                color=series["color"],
                width=0.72,
                edgecolor="white",
                linewidth=0.7,
                label=_burn_series_label(series, style),
            )
            bottoms = [bottom + value for bottom, value in zip(bottoms, values)]

    ax.set_xticks(x_values)
    ax.set_xticklabels(period_labels, rotation=35, ha="right", fontsize=max(style.font_size - 1, 8))
    ax.grid(axis="y", color=style.grid_color, linewidth=1.0, alpha=0.8)
    ax.set_axisbelow(True)
    ylabel = f"{_default_table_title(field)} per {burn['period'].title()}"
    ax.set_ylabel(ylabel, fontsize=style.font_size)

    display_spec = _numeric_display_spec(burn["spec"], burn["display_factor"])
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda value, _: _format_numeric_table_value(Decimal(str(value)), display_spec)))

    title = config.title.strip() if config.title else _default_table_title(field)
    ax.set_title(f"{title} Burn by {burn['period'].title()}", fontsize=style.font_size + 2, fontweight="bold")

    if len(burn["series"]) > 1:
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=max(style.font_size - 1, 8))
        fig.subplots_adjust(right=0.80)
    else:
        fig.subplots_adjust(right=0.96)

    fig.subplots_adjust(left=0.10, bottom=0.22, top=0.88)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor=style.background)
    plt.close(fig)


def render_burn_table(
    config: ChartConfig,
    output_path: str,
    dpi: int = 150,
    field: str = "cost",
    period: str = "month",
    group_by: Any = 0,
    display_factor: Any = 1,
) -> None:
    """Render a burn matrix table with period columns and grouped task rows."""
    burn = _build_burn_matrix(config, field=field, period=period, group_by=group_by, display_factor=display_factor)
    if os.path.splitext(output_path)[1].lower() == ".csv":
        _write_burn_table_csv(burn, output_path)
        return

    headers = ["Task", "Name"] + [bucket["label"] for bucket in burn["periods"]]
    rows: List[Tuple[List[str], bool, Optional[str]]] = []
    for series in burn["series"]:
        number = series["number"] + "." if series["number"] and "." not in series["number"] else series["number"]
        row_cells = [number, series["name"]] + [
            _format_burn_amount(value, burn["spec"], burn["display_factor"]) for value in series["values"]
        ]
        rows.append((row_cells, False, series["color"]))

    include_footer = not (len(burn["series"]) == 1 and burn["series"][0]["key"] == "__total__")
    if include_footer:
        footer_cells = ["", "Total"] + [
            _format_burn_amount(value, burn["spec"], burn["display_factor"]) for value in burn["totals"]
        ]
        rows.append((footer_cells, True, None))

    style = config.style
    fig_w = max(style.width, 3.8 + len(headers) * 1.1)
    fig_h = max(2.4, 1.0 + 0.45 * (len(rows) + 1))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor=style.background)
    ax.axis("off")

    task_width = 0.08
    name_width = 0.24
    remaining_width = max(0.20, 1.0 - task_width - name_width)
    period_width = remaining_width / max(1, len(headers) - 2)
    col_widths = [task_width, name_width] + [period_width for _ in headers[2:]]

    table = ax.table(
        cellText=[row_cells for row_cells, _, _ in rows],
        colLabels=headers,
        colLoc="left",
        cellLoc="left",
        colWidths=col_widths,
        bbox=[0.0, 0.0, 1.0, 0.92],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(style.font_size)
    table.scale(1.0, 1.5)

    header_color = _darken(style.row_band_color, 0.08)
    for (row_index, col_index), cell in table.get_celld().items():
        cell.set_edgecolor(style.grid_color)
        cell.set_linewidth(0.8)
        if row_index == 0:
            cell.set_facecolor(header_color)
            cell.set_text_props(weight="bold", color="#111111")
            continue

        row_cells, is_footer, accent = rows[row_index - 1]
        if is_footer:
            cell.set_facecolor(header_color)
            cell.set_text_props(weight="bold", color="#111111")
        else:
            band_color = style.background if (row_index - 1) % 2 == 0 else style.row_band_color
            cell.set_facecolor(band_color)
            if col_index in (0, 1):
                cell.set_text_props(weight="bold" if rows[row_index - 1][0][0] and col_index == 1 and rows[row_index - 1][0][0].count(".") <= 1 else "normal")
            if accent is not None and col_index == 0:
                cell.set_facecolor(_lighten(accent, 0.78))

    if config.title:
        fig.suptitle(
            f"{config.title} Burn Matrix",
            fontsize=style.font_size + 3,
            fontweight="bold",
            x=0.5,
            y=0.98,
            ha="center",
            va="top",
        )

    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor=style.background)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_chart(
    config: ChartConfig,
    output_path: str,
    dpi: int = 150,
    render_depth: int = 0,
    date_line: Optional[date] = None,
    date_line_color: str = "#C00000",
) -> None:
    """Render *config* to *output_path* (PNG, PDF, SVG …)."""
    rows = _prepare_rows(config, render_depth)

    n = len(rows)
    style = config.style

    # ---- figure dimensions ------------------------------------------------
    row_h_in = style.row_height
    tick_pos = (style.tick_position or "top").lower()
    # extra room at top: title alone needs 0.6in; ticks-on-top need additional space
    tick_on_top = tick_pos in ("top", "both")
    top_pad = (0.9 if tick_on_top else 0.6) if config.title else (0.55 if tick_on_top else 0.25)
    bottom_pad = 0.55 if tick_pos in ("bottom", "both") else 0.25
    fig_h = n * row_h_in + top_pad + bottom_pad
    fig_w = style.width

    label_fraction, indent_step, left_margin_frac = _compute_chart_label_layout(
        rows,
        style,
        fig_w,
        _row_label_text,
    )

    # ---- figure & grid ----------------------------------------------------
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=style.background)
    fig.subplots_adjust(
        left=0, right=1,
        top=1 - top_pad / fig_h,
        bottom=bottom_pad / fig_h,
        wspace=0,
    )

    gs = gridspec.GridSpec(
        1, 2,
        figure=fig,
        width_ratios=[label_fraction, 1.0 - label_fraction],
        wspace=0,
    )

    ax_lbl = fig.add_subplot(gs[0, 0])   # label panel
    ax_bar = fig.add_subplot(gs[0, 1])   # bar panel

    # ---- x-axis date range ------------------------------------------------
    x_min, x_max = _compute_date_range(rows, config)
    # add small padding so bars don't touch the edge
    pad = max(1, (x_max - x_min).days * 0.02)
    x_start = x_min - timedelta(days=pad)
    x_end = x_max + timedelta(days=pad)
    # snap to minor-tick boundary so the first minor gridline is visible at the left edge
    span_days_raw = (x_end - x_start).days
    minor_key = config.style.minor_tick
    if not minor_key:
        if span_days_raw > 365:
            minor_key = "quarter"
        elif span_days_raw > 90:
            minor_key = "month"
        elif span_days_raw > 21:
            minor_key = "week"
    if minor_key:
        x_start = _snap_to_tick_start(x_start, minor_key)
        x_end = _snap_to_tick_end(x_end, minor_key)

    # convert to datetime so matplotlib locators can call .replace(hour=0, ...)
    if not isinstance(x_start, datetime):
        x_start = datetime(x_start.year, x_start.month, x_start.day)
    if not isinstance(x_end, datetime):
        x_end = datetime(x_end.year, x_end.month, x_end.day)

    # ---- y-axis range (top row = highest y value) -------------------------
    y_min = -0.5
    y_max = n - 0.5

    # ---- style both axes --------------------------------------------------
    _style_label_axis(ax_lbl, y_min, y_max, style, n)
    _style_bar_axis(ax_bar, x_start, x_end, y_min, y_max, style, n)
    _draw_date_line(ax_bar, date_line, date_line_color)

    # ---- alternating row bands (bar panel only; label panel has its own tint) -
    for i in range(n):
        if i % 2 == 1:
            _row_band(ax_bar, i, style)

    # ---- draw each row ----------------------------------------------------
    for row in rows:
        _draw_row(ax_lbl, ax_bar, row, n, style, indent_step, left_margin_frac)

    # ---- dependency arrows (drawing disabled) -----------------------------

    # ---- title ------------------------------------------------------------
    if config.title:
        title_y = 1 - (top_pad * (0.2 if tick_on_top else 0.35)) / fig_h
        fig.suptitle(
            config.title,
            fontsize=style.font_size + 3,
            fontweight="bold",
            x=0.5,
            y=title_y,
            va="top",
            ha="center",
        )

    fig.savefig(output_path, dpi=dpi, bbox_inches="tight",
                facecolor=style.background)
    plt.close(fig)


def render_table(
    config: ChartConfig,
    output_path: str,
    dpi: int = 150,
    render_depth: int = 0,
    milestones_only: bool = False,
    no_milestones: bool = False,
) -> None:
    """Render *config* to *output_path* as a task table image."""
    rows = _prepare_rows(config, render_depth)
    rows = _filter_rows_for_table(rows, milestones_only, no_milestones)
    style = config.style

    if os.path.splitext(output_path)[1].lower() == ".csv":
        _write_table_csv(rows, output_path, style)
        return

    fig_w = style.width
    line_height_in = style.font_size * 1.5 / 72.0
    table_width_frac = 0.94
    table_width_in = fig_w * table_width_frac
    gutter_width_frac = 0.018
    gutter_gap_in = 0.05
    text_pad_frac = 0.014
    text_pad_in = table_width_in * text_pad_frac
    col_padding_in = text_pad_in * 2 + 0.05
    has_table_gutter = style.table_colorize
    gutter_width_in = table_width_in * gutter_width_frac if has_table_gutter else 0.0
    columns = _resolve_table_columns(style)
    footer_cells = _build_table_footer_cells(rows, columns, lambda row, column: _task_table_numeric_value(row.task, column))
    widths_in = _measure_table_column_widths(
        rows,
        columns,
        style,
        table_width_in,
        col_padding_in,
        (gutter_width_in + gutter_gap_in) if has_table_gutter else 0.0,
        _row_table_cell,
        footer_cells=footer_cells,
    )
    fractions = [width_in / table_width_in for width_in in widths_in]
    wrapped_rows, total_units = _wrap_table_rows(
        rows,
        columns,
        widths_in,
        style,
        col_padding_in,
        _row_table_cell,
        footer_cells=footer_cells,
    )

    fig_h = total_units * line_height_in + (0.8 if config.title else 0.35)
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=style.background)
    top_margin = 0.88 if config.title else 0.96
    ax = fig.add_axes([0.03, 0.05, 0.94, top_margin - 0.08])
    ax.set_xlim(0, 1)
    ax.set_ylim(total_units, 0)
    ax.axis("off")
    ax.set_facecolor(style.background)

    if config.title:
        fig.suptitle(
            config.title,
            fontsize=style.font_size + 3,
            fontweight="bold",
            x=0.5,
            y=0.97,
            va="top",
            ha="center",
        )

    header_color = _darken(style.row_band_color, 0.08)
    divider_color = style.grid_color
    gutter_width = gutter_width_frac if has_table_gutter else 0.0
    x_starts: List[float] = []
    x = 0.0
    for fraction, column in zip(fractions, columns):
        x_starts.append(x)
        ax.add_patch(mpatches.Rectangle(
            (x, 0), fraction, 1.3,
            facecolor=header_color,
            edgecolor=divider_color,
            linewidth=1.0,
        ))
        ax.text(x + text_pad_frac, 0.65, column["title"], ha="left", va="center", fontsize=style.font_size, fontweight="bold")
        x += fraction

    y = 1.3
    visible_row_index = 0
    for row, wrapped_cells, row_units, is_footer in wrapped_rows:
        band_color = header_color if is_footer else (style.background if visible_row_index % 2 == 0 else style.row_band_color)

        ax.add_patch(mpatches.Rectangle(
            (0, y), 1.0, row_units,
            facecolor=band_color,
            edgecolor=divider_color,
            linewidth=0.8,
        ))
        show_milestone_marker = bool(
            not is_footer and row is not None and row.task.milestone and style.table_colorize and style.table_show_markers
        )
        if not is_footer and style.table_colorize and not show_milestone_marker:
            ax.add_patch(mpatches.Rectangle(
                (0, y), 0.010, row_units,
                facecolor=row.color,
                edgecolor="none",
            ))
        if show_milestone_marker:
            marker_x = gutter_width / 2.0
            marker_y = y + row_units / 2.0
            marker_color = _milestone_color(row, style)
            ax.plot(
                marker_x,
                marker_y,
                marker=_milestone_marker(row.task, style),
                markersize=max(6, style.milestone_size * 0.65),
                color=marker_color,
                markeredgecolor="none",
                linestyle="none",
                zorder=4,
            )

        for boundary in x_starts[1:]:
            ax.plot([boundary, boundary], [y, y + row_units], color=divider_color, linewidth=1.0)

        text_y = y + row_units / 2.0
        task_weight = "bold" if is_footer or (row is not None and (row.task.bold or (style.bold_tasks and row.depth == 0))) else "normal"
        for column_index, (column, x_start, fraction, lines) in enumerate(zip(columns, x_starts, fractions, wrapped_cells)):
            clip = mpatches.Rectangle((x_start, y), fraction, row_units, transform=ax.transData)
            fontweight = task_weight if column["field"] in ("task", "name") else ("bold" if is_footer else "normal")
            text_x = max(x_start + text_pad_frac, gutter_width + 0.006) if column_index == 0 else x_start + text_pad_frac
            cell_text = ax.text(
                text_x,
                text_y,
                "\n".join(lines),
                ha="left",
                va="center",
                fontsize=style.font_size,
                fontweight=fontweight,
                color="#111111",
                linespacing=1.35,
                clip_on=True,
            )
            cell_text.set_clip_path(clip)

        if not is_footer:
            visible_row_index += 1
        y += row_units

    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor=style.background)
    plt.close(fig)


def render_compare_chart(
    planned_config: ChartConfig,
    actual_config: ChartConfig,
    output_path: str,
    dpi: int = 150,
    render_depth: int = 0,
    date_line: Optional[date] = None,
    date_line_color: str = "#C00000",
) -> None:
    """Render an outline-vs-actual comparison Gantt chart."""
    rows = _prepare_compare_rows(planned_config, actual_config, render_depth)

    n = len(rows)
    style = planned_config.style

    row_h_in = style.row_height
    tick_pos = (style.tick_position or "top").lower()
    tick_on_top = tick_pos in ("top", "both")
    title = _compare_title(planned_config, actual_config)
    top_pad = (0.9 if tick_on_top else 0.6) if title else (0.55 if tick_on_top else 0.25)
    bottom_pad = 0.55 if tick_pos in ("bottom", "both") else 0.25
    fig_h = n * row_h_in + top_pad + bottom_pad
    fig_w = style.width

    label_fraction, indent_step, left_margin_frac = _compute_chart_label_layout(
        rows,
        style,
        fig_w,
        _compare_row_label_text,
    )

    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=style.background)
    fig.subplots_adjust(
        left=0,
        right=1,
        top=1 - top_pad / fig_h,
        bottom=bottom_pad / fig_h,
        wspace=0,
    )

    gs = gridspec.GridSpec(
        1, 2,
        figure=fig,
        width_ratios=[label_fraction, 1.0 - label_fraction],
        wspace=0,
    )

    ax_lbl = fig.add_subplot(gs[0, 0])
    ax_bar = fig.add_subplot(gs[0, 1])

    x_min, x_max = _compute_compare_date_range(rows, planned_config, actual_config)
    pad = max(1, (x_max - x_min).days * 0.02)
    x_start = x_min - timedelta(days=pad)
    x_end = x_max + timedelta(days=pad)
    span_days_raw = (x_end - x_start).days
    minor_key = style.minor_tick
    if not minor_key:
        if span_days_raw > 365:
            minor_key = "quarter"
        elif span_days_raw > 90:
            minor_key = "month"
        elif span_days_raw > 21:
            minor_key = "week"
    if minor_key:
        x_start = _snap_to_tick_start(x_start, minor_key)
        x_end = _snap_to_tick_end(x_end, minor_key)

    if not isinstance(x_start, datetime):
        x_start = datetime(x_start.year, x_start.month, x_start.day)
    if not isinstance(x_end, datetime):
        x_end = datetime(x_end.year, x_end.month, x_end.day)

    y_min = -0.5
    y_max = n - 0.5

    _style_label_axis(ax_lbl, y_min, y_max, style, n)
    _style_bar_axis(ax_bar, x_start, x_end, y_min, y_max, style, n)
    _draw_date_line(ax_bar, date_line, date_line_color)

    for i in range(n):
        if i % 2 == 1:
            _row_band(ax_bar, i, style)

    for row in rows:
        _draw_compare_row(ax_lbl, ax_bar, row, style, indent_step, left_margin_frac)

    if title:
        title_y = 1 - (top_pad * (0.2 if tick_on_top else 0.35)) / fig_h
        fig.suptitle(
            title,
            fontsize=style.font_size + 3,
            fontweight="bold",
            x=0.5,
            y=title_y,
            va="top",
            ha="center",
        )

    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor=style.background)
    plt.close(fig)


def render_compare_table(
    planned_config: ChartConfig,
    actual_config: ChartConfig,
    output_path: str,
    dpi: int = 150,
    render_depth: int = 0,
    milestones_only: bool = False,
    no_milestones: bool = False,
) -> None:
    """Render a comparison task table with duration or milestone offsets."""
    rows = _prepare_compare_rows(planned_config, actual_config, render_depth)
    rows = _filter_compare_rows_for_table(rows, milestones_only, no_milestones)
    style = planned_config.style

    if os.path.splitext(output_path)[1].lower() == ".csv":
        _write_compare_table_csv(rows, output_path, style)
        return

    fig_w = style.width
    line_height_in = style.font_size * 1.5 / 72.0
    table_width_frac = 0.94
    table_width_in = fig_w * table_width_frac
    gutter_width_frac = 0.018
    gutter_gap_in = 0.05
    text_pad_frac = 0.014
    text_pad_in = table_width_in * text_pad_frac
    col_padding_in = text_pad_in * 2 + 0.05
    has_table_gutter = style.table_colorize
    gutter_width_in = table_width_in * gutter_width_frac if has_table_gutter else 0.0
    columns = _resolve_table_columns(style, include_offset=True)
    footer_cells = _build_table_footer_cells(rows, columns, _compare_table_numeric_value)
    widths_in = _measure_table_column_widths(
        rows,
        columns,
        style,
        table_width_in,
        col_padding_in,
        (gutter_width_in + gutter_gap_in) if has_table_gutter else 0.0,
        _compare_row_table_cell,
        footer_cells=footer_cells,
    )
    fractions = [width_in / table_width_in for width_in in widths_in]
    wrapped_rows, total_units = _wrap_table_rows(
        rows,
        columns,
        widths_in,
        style,
        col_padding_in,
        _compare_row_table_cell,
        footer_cells=footer_cells,
    )

    title = _compare_title(planned_config, actual_config)
    fig_h = total_units * line_height_in + (0.8 if title else 0.35)
    fig = plt.figure(figsize=(fig_w, fig_h), facecolor=style.background)
    top_margin = 0.88 if title else 0.96
    ax = fig.add_axes([0.03, 0.05, 0.94, top_margin - 0.08])
    ax.set_xlim(0, 1)
    ax.set_ylim(total_units, 0)
    ax.axis("off")
    ax.set_facecolor(style.background)

    if title:
        fig.suptitle(
            title,
            fontsize=style.font_size + 3,
            fontweight="bold",
            x=0.5,
            y=0.97,
            va="top",
            ha="center",
        )

    header_color = _darken(style.row_band_color, 0.08)
    divider_color = style.grid_color
    gutter_width = gutter_width_frac if has_table_gutter else 0.0
    x_starts: List[float] = []
    x = 0.0
    for fraction, column in zip(fractions, columns):
        x_starts.append(x)
        ax.add_patch(mpatches.Rectangle((x, 0), fraction, 1.3, facecolor=header_color, edgecolor=divider_color, linewidth=1.0))
        ax.text(x + text_pad_frac, 0.65, column["title"], ha="left", va="center", fontsize=style.font_size, fontweight="bold")
        x += fraction

    y = 1.3
    visible_row_index = 0
    for row, wrapped_cells, row_units, is_footer in wrapped_rows:
        band_color = header_color if is_footer else (style.background if visible_row_index % 2 == 0 else style.row_band_color)
        ax.add_patch(mpatches.Rectangle((0, y), 1.0, row_units, facecolor=band_color, edgecolor=divider_color, linewidth=0.8))

        show_milestone_marker = bool(
            not is_footer and row is not None and row.task.milestone and style.table_colorize and style.table_show_markers
        )
        accent_color = row.actual.color if row is not None and row.actual is not None else row.planned.color if row is not None and row.planned is not None else "none"
        if not is_footer and style.table_colorize and not show_milestone_marker:
            ax.add_patch(mpatches.Rectangle((0, y), 0.010, row_units, facecolor=accent_color, edgecolor="none"))
        if show_milestone_marker:
            marker_x = gutter_width / 2.0
            marker_y = y + row_units / 2.0
            ax.plot(
                marker_x,
                marker_y,
                marker=_milestone_marker(row.task, style),
                markersize=max(6, style.milestone_size * 0.65),
                color=_milestone_color(row.actual if row.actual is not None else row.planned, style),
                markeredgecolor="none",
                linestyle="none",
                zorder=4,
            )

        for boundary in x_starts[1:]:
            ax.plot([boundary, boundary], [y, y + row_units], color=divider_color, linewidth=1.0)

        text_y = y + row_units / 2.0
        task_weight = "bold" if is_footer or (row is not None and (row.task.bold or (style.bold_tasks and row.depth == 0))) else "normal"
        for column_index, (column, x_start, fraction, lines) in enumerate(zip(columns, x_starts, fractions, wrapped_cells)):
            clip = mpatches.Rectangle((x_start, y), fraction, row_units, transform=ax.transData)
            fontweight = task_weight if column["field"] in ("task", "name") else ("bold" if is_footer else "normal")
            text_x = max(x_start + text_pad_frac, gutter_width + 0.006) if column_index == 0 else x_start + text_pad_frac
            cell_text = ax.text(
                text_x,
                text_y,
                "\n".join(lines),
                ha="left",
                va="center",
                fontsize=style.font_size,
                fontweight=fontweight,
                color="#111111",
                linespacing=1.35,
                clip_on=True,
            )
            cell_text.set_clip_path(clip)

        if not is_footer and row is not None and row.is_removed:
            strike_font_props = FontProperties(size=style.font_size, weight=task_weight)
            for column_index, (column, x_start, lines) in enumerate(zip(columns, x_starts, wrapped_cells)):
                if column["field"] == "offset":
                    continue
                strike_x = max(x_start + text_pad_frac, gutter_width + 0.006) if column_index == 0 else x_start + text_pad_frac
                _draw_strike_line(ax, strike_x, text_y, " ".join(lines), strike_font_props)

        if not is_footer:
            visible_row_index += 1
        y += row_units

    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor=style.background)
    plt.close(fig)


def _snap_to_tick_start(d: date, key: str) -> date:
    """Snap *d* back to the start of the enclosing tick period."""
    k = key.strip().lower()
    if k in ("year", "years"):
        return date(d.year, 1, 1)
    elif k in ("quarter", "quarters"):
        q_start_month = ((d.month - 1) // 3) * 3 + 1
        return date(d.year, q_start_month, 1)
    elif k in ("month", "months"):
        return date(d.year, d.month, 1)
    elif k in ("week", "weeks"):
        return d - timedelta(days=d.weekday())  # Monday
    else:
        return d


def _snap_to_tick_end(d: date, key: str) -> date:
    """Snap *d* forward to the start of the next tick period (covers the date)."""
    start = _snap_to_tick_start(d, key)
    if start >= d:
        return d  # already on a boundary
    k = key.strip().lower()
    if k in ("year", "years"):
        return date(d.year + 1, 1, 1)
    elif k in ("quarter", "quarters"):
        q_start_month = ((d.month - 1) // 3) * 3 + 1
        next_month = q_start_month + 3
        if next_month > 12:
            return date(d.year + 1, 1, 1)
        return date(d.year, next_month, 1)
    elif k in ("month", "months"):
        if d.month == 12:
            return date(d.year + 1, 1, 1)
        return date(d.year, d.month + 1, 1)
    elif k in ("week", "weeks"):
        return d + timedelta(days=(7 - d.weekday()))  # next Monday
    else:
        return d


def _iter_ticks(x_start: datetime, x_end: datetime, key: str):
    """Yield datetime positions from x_start to x_end for the given tick key."""
    k = key.strip().lower()
    # start at the first tick on or before x_start
    d = _snap_to_tick_start(x_start, key)
    if not isinstance(d, datetime):
        d = datetime(d.year, d.month, d.day)
    end = x_end if isinstance(x_end, datetime) else datetime(x_end.year, x_end.month, x_end.day)

    while d <= end:
        yield d
        if k in ("year", "years"):
            d = datetime(d.year + 1, 1, 1)
        elif k in ("quarter", "quarters"):
            m = d.month + 3
            y = d.year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            d = datetime(y, m, 1)
        elif k in ("month", "months"):
            m = d.month + 1
            y = d.year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            d = datetime(y, m, 1)
        elif k in ("week", "weeks"):
            d = d + timedelta(weeks=1)
        elif k in ("day", "days"):
            d = d + timedelta(days=1)
        else:
            break


# ---------------------------------------------------------------------------
# Flatten task tree → ordered list of _Row
# ---------------------------------------------------------------------------


def _flatten(
    tasks: List[Task],
    style: Style,
    depth: int = 0,
    palette_index: int = 0,
    parent_color: Optional[str] = None,
    number_prefix: str = "",
    max_depth: int = 0,
    path_prefix: Tuple[str, ...] = (),
) -> List[_Row]:
    rows: List[_Row] = []
    palette = style.colors or ["#4472C4"]
    max_depth_index = None if max_depth == 0 else max_depth - 1
    lighten_amount = max(0.0, min(100.0, style.subtask_lightening_pct)) / 100.0

    for task_idx, task in enumerate(tasks):
        # colour resolution: explicit > parent > palette
        if task.color:
            color = task.color
        elif parent_color and depth > 0:
            color = _lighten(parent_color, lighten_amount)
        else:
            color = palette[palette_index % len(palette)]
            palette_index += 1

        number = number_prefix + str(task_idx + 1)
        path_key = path_prefix + (task.name,)
        row = _Row(task=task, depth=depth, row_index=0, color=color, number=number, path_key=path_key)
        rows.append(row)

        if task.children and (max_depth_index is None or depth < max_depth_index):
            child_rows = _flatten(
                task.children,
                style,
                depth=depth + 1,
                palette_index=palette_index,
                parent_color=color,
                number_prefix=number + ".",
                max_depth=max_depth,
                path_prefix=path_key,
            )
            rows.extend(child_rows)

    # assign row_index top-to-bottom
    for i, r in enumerate(rows):
        r.row_index = i

    return rows


def _prepare_rows(config: ChartConfig, render_depth: int) -> List[_Row]:
    """Validate depth and return flattened rows for rendering."""
    if render_depth < 0:
        raise ValueError("render_depth must be >= 0")

    rows = _flatten(config.tasks, config.style, max_depth=render_depth)
    if not rows:
        raise ValueError("No tasks to render.")
    return rows


def _filter_rows_for_table(
    rows: List[_Row],
    milestones_only: bool,
    no_milestones: bool,
) -> List[_Row]:
    """Return rows for table output, applying milestone filters."""
    if milestones_only and no_milestones:
        raise ValueError("Cannot use milestones_only and no_milestones together.")

    if milestones_only:
        filtered_rows = [row for row in rows if row.task.milestone]
        if not filtered_rows:
            raise ValueError("No milestones to render.")
        return filtered_rows

    if no_milestones:
        filtered_rows = [row for row in rows if not row.task.milestone]
        if not filtered_rows:
            raise ValueError("No non-milestone tasks to render.")
        return filtered_rows

    return rows


def _prepare_compare_rows(
    planned_config: ChartConfig,
    actual_config: ChartConfig,
    render_depth: int,
) -> List[_CompareRow]:
    """Validate depth and return merged comparison rows."""
    if render_depth < 0:
        raise ValueError("render_depth must be >= 0")

    planned_rows = _flatten(planned_config.tasks, planned_config.style, max_depth=render_depth)
    actual_rows = _flatten(actual_config.tasks, actual_config.style, max_depth=render_depth)

    if not planned_rows and not actual_rows:
        raise ValueError("No tasks to render.")

    return _merge_compare_rows(planned_rows, actual_rows)


def _filter_compare_rows_for_table(
    rows: List[_CompareRow],
    milestones_only: bool,
    no_milestones: bool,
) -> List[_CompareRow]:
    """Return compare rows for table output, applying milestone filters."""
    if milestones_only and no_milestones:
        raise ValueError("Cannot use milestones_only and no_milestones together.")

    if milestones_only:
        filtered_rows = [row for row in rows if row.task.milestone]
        if not filtered_rows:
            raise ValueError("No milestones to render.")
        return filtered_rows

    if no_milestones:
        filtered_rows = [row for row in rows if not row.task.milestone]
        if not filtered_rows:
            raise ValueError("No non-milestone tasks to render.")
        return filtered_rows

    return rows


def _write_compare_table_csv(rows: List[_CompareRow], output_path: str, style: Style) -> None:
    """Write compare table rows to *output_path* as CSV."""
    columns = _resolve_table_columns(style, include_offset=True)
    footer_cells = _build_table_footer_cells(rows, columns, _compare_table_numeric_value)
    with open(output_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([column["title"] for column in columns])
        for row in rows:
            writer.writerow([_compare_row_table_cell(row, column) for column in columns])
        if footer_cells is not None:
            writer.writerow(footer_cells)


def _compare_key(row: _Row) -> str:
    """Return the logical matching key for a row across compare inputs."""
    if row.task.id:
        return f"id:{row.task.id}"
    return "path:" + "\x1f".join(row.path_key)


def _merge_compare_rows(planned_rows: List[_Row], actual_rows: List[_Row]) -> List[_CompareRow]:
    """Merge planned and actual rows using ids or hierarchical name paths."""
    if not planned_rows:
        return [_CompareRow(actual=row, row_index=index) for index, row in enumerate(actual_rows)]
    if not actual_rows:
        return [_CompareRow(planned=row, row_index=index) for index, row in enumerate(planned_rows)]

    planned_keys = [_compare_key(row) for row in planned_rows]
    actual_keys = [_compare_key(row) for row in actual_rows]
    matcher = SequenceMatcher(a=planned_keys, b=actual_keys, autojunk=False)

    merged_rows: List[_CompareRow] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for planned_row, actual_row in zip(planned_rows[i1:i2], actual_rows[j1:j2]):
                merged_rows.append(_CompareRow(planned=planned_row, actual=actual_row))
        elif tag == "delete":
            for planned_row in planned_rows[i1:i2]:
                merged_rows.append(_CompareRow(planned=planned_row))
        elif tag == "insert":
            for actual_row in actual_rows[j1:j2]:
                merged_rows.append(_CompareRow(actual=actual_row))
        else:
            for planned_row in planned_rows[i1:i2]:
                merged_rows.append(_CompareRow(planned=planned_row))
            for actual_row in actual_rows[j1:j2]:
                merged_rows.append(_CompareRow(actual=actual_row))

    for row_index, row in enumerate(merged_rows):
        row.row_index = row_index
    return merged_rows


def _write_table_csv(rows: List[_Row], output_path: str, style: Style) -> None:
    """Write table rows to *output_path* as CSV."""
    columns = _resolve_table_columns(style)
    footer_cells = _build_table_footer_cells(rows, columns, lambda row, column: _task_table_numeric_value(row.task, column))
    with open(output_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([column["title"] for column in columns])
        for row in rows:
            writer.writerow([_row_table_cell(row, column) for column in columns])
        if footer_cells is not None:
            writer.writerow(footer_cells)


# ---------------------------------------------------------------------------
# Date range computation
# ---------------------------------------------------------------------------


def _compute_date_range(rows: List[_Row], config: ChartConfig) -> Tuple[date, date]:
    dates: List[date] = []
    for row in rows:
        s = row.task.effective_start
        e = row.task.effective_end
        if s:
            dates.append(s)
        if e:
            dates.append(e)
    if not dates:
        today = date.today()
        dates = [today, today + timedelta(days=30)]

    x_min = config.start if config.start else min(dates)
    x_max = config.end if config.end else max(dates)
    if x_min >= x_max:
        x_max = x_min + timedelta(days=1)
    return x_min, x_max


def _compute_compare_date_range(
    rows: List[_CompareRow],
    planned_config: ChartConfig,
    actual_config: ChartConfig,
) -> Tuple[date, date]:
    """Return the combined date range for planned and actual compare rows."""
    dates: List[date] = []
    for row in rows:
        for side in (row.planned, row.actual):
            if side is None:
                continue
            start = side.task.effective_start
            end = side.task.effective_end
            if start:
                dates.append(start)
            if end:
                dates.append(end)

    if not dates:
        today = date.today()
        dates = [today, today + timedelta(days=30)]

    explicit_starts = [cfg_start for cfg_start in (planned_config.start, actual_config.start) if cfg_start is not None]
    explicit_ends = [cfg_end for cfg_end in (planned_config.end, actual_config.end) if cfg_end is not None]
    x_min = min(explicit_starts) if explicit_starts else min(dates)
    x_max = max(explicit_ends) if explicit_ends else max(dates)
    if x_min >= x_max:
        x_max = x_min + timedelta(days=1)
    return x_min, x_max


# ---------------------------------------------------------------------------
# Axis styling helpers
# ---------------------------------------------------------------------------


def _style_label_axis(ax, y_min, y_max, style: Style, n: int) -> None:
    """Configure the label panel (left side)."""
    ax.set_xlim(0, 1)
    ax.set_ylim(y_min, y_max)
    ax.invert_yaxis()
    ax.axis("off")
    # slightly tinted background so the label column reads as a distinct zone
    ax.set_facecolor(style.row_band_color)


def _style_bar_axis(ax, x_start, x_end, y_min, y_max, style: Style, n: int) -> None:
    """Configure the bar / chart panel (right side)."""
    ax.set_facecolor(style.background)
    ax.set_ylim(y_min, y_max)
    ax.invert_yaxis()

    # x-axis as dates
    ax.set_xlim(x_start, x_end)
    ax.xaxis_date()

    span_days = (x_end - x_start).days

    # ---- resolve major / minor keys, defaulting to year / quarter ----------
    major_key = style.major_tick or "year"
    minor_key = style.minor_tick or "quarter"

    major_loc, major_fmt = _tick_locator_fmt(major_key, span_days)
    minor_loc, _         = _tick_locator_fmt(minor_key, span_days)

    ax.xaxis.set_major_locator(major_loc)
    ax.xaxis.set_major_formatter(major_fmt)
    ax.xaxis.set_minor_locator(minor_loc)
    ax.xaxis.set_minor_formatter(ticker.NullFormatter())

    pos = (style.tick_position or "top").lower()

    # position ticks and labels
    ax.xaxis.set_ticks_position(pos)   # "top", "bottom", or "both"
    labeltop    = pos in ("top",    "both")
    labelbottom = pos in ("bottom", "both")

    ax.tick_params(axis="x", which="major", labelsize=style.font_size,
                   rotation=0, pad=4, labeltop=labeltop, labelbottom=labelbottom)
    ax.tick_params(axis="x", which="minor", length=4, width=0.6,
                   color=style.grid_color, pad=0)
    # force font size on any already-generated tick labels
    for lbl in ax.get_xticklabels(which="both"):
        lbl.set_fontsize(style.font_size)

    ax.yaxis.set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(pos in ("top", "both"))
    ax.spines["top"].set_color(style.grid_color)
    ax.spines["bottom"].set_visible(pos in ("bottom", "both"))
    ax.spines["bottom"].set_color(style.grid_color)

    # ---- draw gridlines by iterating dates directly -----------------------
    for dt in _iter_ticks(x_start, x_end, major_key):
        ax.axvline(mdates.date2num(dt), color=style.grid_color,
                   linewidth=style.major_grid_width, linestyle="-", zorder=1)

    for dt in _iter_ticks(x_start, x_end, minor_key):
        ax.axvline(mdates.date2num(dt), color=style.grid_color,
                   linewidth=style.minor_grid_width, linestyle=":", zorder=1)


def _draw_date_line(ax_bar, line_date: Optional[date], line_color: str) -> None:
    """Draw a single vertical reference line on the chart axis."""
    if line_date is None:
        return

    ax_bar.axvline(
        mdates.date2num(line_date),
        color=line_color,
        linewidth=2.0,
        linestyle="--",
        zorder=2.2,
        alpha=0.95,
    )


def _tick_locator_fmt(key: str, span_days: int):
    """Return (locator, formatter) for a tick key string."""
    k = key.strip().lower()
    if k in ("year", "years"):
        return mdates.YearLocator(), mdates.DateFormatter("%Y")
    elif k in ("quarter", "quarters"):
        def _qfmt(x, pos=None):
            d = mdates.num2date(x)
            q = (d.month - 1) // 3 + 1
            return f"Q{q} {d.year}"
        return mdates.MonthLocator(bymonth=[1, 4, 7, 10]), ticker.FuncFormatter(_qfmt)
    elif k in ("month", "months"):
        return mdates.MonthLocator(), mdates.DateFormatter("%b '%y")
    elif k in ("week", "weeks"):
        return mdates.WeekdayLocator(byweekday=mdates.MO), mdates.DateFormatter("%b %d")
    elif k in ("day", "days"):
        return mdates.DayLocator(), mdates.DateFormatter("%b %d")
    else:
        raise ValueError(f"Unknown tick spec {key!r}. Use: year, quarter, month, week, day")


# ---------------------------------------------------------------------------
# Row-level drawing
# ---------------------------------------------------------------------------


def _row_band(ax, row_index: int, style: Style) -> None:
    """Draw a light background band for *row_index*."""
    ax.axhspan(
        row_index - 0.5, row_index + 0.5,
        facecolor=style.row_band_color,
        edgecolor="none",
        zorder=0,
    )


def _draw_row(ax_lbl, ax_bar, row: _Row, n: int, style: Style,
             indent_step: float = 0.05, left_margin: float = 0.04) -> None:
    task = row.task
    y = row.row_index

    # ---- label ------------------------------------------------------------
    x = left_margin + row.depth * indent_step

    label_text = _row_label_text(row, style)

    # bold: explicit task flag, or auto-bold depth-0 when style.bold_tasks is on
    weight = "bold" if (task.bold or (style.bold_tasks and row.depth == 0)) else "normal"
    ax_lbl.text(
        x, y,
        label_text,
        ha="left",
        va="center",
        fontsize=style.font_size,
        fontweight=weight,
        color="#111111",
        clip_on=True,
    )

    # ---- bar or milestone -------------------------------------------------
    if task.milestone:
        _draw_milestone(ax_bar, row, y, style)
    else:
        _draw_bar(ax_bar, row, y, style)


def _draw_compare_row(
    ax_lbl,
    ax_bar,
    row: _CompareRow,
    style: Style,
    indent_step: float = 0.05,
    left_margin: float = 0.04,
) -> None:
    """Draw a compare-mode row with planned outline and actual fill."""
    task = row.task
    y = row.row_index
    x = left_margin + row.depth * indent_step

    label_text = _compare_row_label_text(row, style)
    weight = "bold" if (task.bold or (style.bold_tasks and row.depth == 0)) else "normal"
    ax_lbl.text(
        x,
        y,
        label_text,
        ha="left",
        va="center",
        fontsize=style.font_size,
        fontweight=weight,
        color="#111111",
        clip_on=True,
    )
    if row.is_removed:
        font_props = FontProperties(size=style.font_size, weight=weight)
        _draw_strike_line(ax_lbl, x, y, label_text, font_props)

    if row.planned is not None:
        if row.planned.task.milestone:
            _draw_compare_milestone(ax_bar, row.planned, y, style, outlined=True)
        else:
            _draw_compare_bar(ax_bar, row.planned, y, style, outlined=True)

    if row.actual is not None:
        if row.actual.task.milestone:
            _draw_compare_milestone(ax_bar, row.actual, y, style, outlined=False)
        else:
            _draw_compare_bar(ax_bar, row.actual, y, style, outlined=False)


def _draw_bar(ax_bar, row: _Row, y: float, style: Style) -> None:
    task = row.task
    start = task.effective_start
    end = task.effective_end

    if start is None or end is None:
        return

    if start == end:
        end = start + timedelta(days=1)

    bar_h = style.bar_height
    bar = mpatches.FancyBboxPatch(
        (mdates.date2num(start), y - bar_h / 2),
        mdates.date2num(end) - mdates.date2num(start),
        bar_h,
        boxstyle="round,pad=0.02",
        facecolor=row.color,
        edgecolor="none",
        linewidth=0,
        alpha=0.90,
        zorder=3,
    )
    ax_bar.add_patch(bar)


def _draw_compare_bar(ax_bar, row: _Row, y: float, style: Style, outlined: bool) -> None:
    """Draw a compare bar, either planned outline or actual filled bar."""
    task = row.task
    start = task.effective_start
    end = task.effective_end

    if start is None or end is None:
        return

    if start == end:
        end = start + timedelta(days=1)

    bar_h = min(0.85, style.bar_height * (1.18 if outlined else 0.64))
    bar = mpatches.FancyBboxPatch(
        (mdates.date2num(start), y - bar_h / 2),
        mdates.date2num(end) - mdates.date2num(start),
        bar_h,
        boxstyle="round,pad=0.02",
        facecolor="none" if outlined else row.color,
        edgecolor=row.color,
        linewidth=2.0 if outlined else 0,
        alpha=1.0 if outlined else 0.90,
        zorder=2.8 if outlined else 3.2,
    )
    ax_bar.add_patch(bar)


def _draw_milestone(ax_bar, row: _Row, y: float, style: Style) -> None:
    task = row.task
    if task.milestone_date is None and task.start is None:
        return

    ms_date = task.milestone_date or task.start
    color = _milestone_color(row, style)
    marker = _milestone_marker(task, style)
    size = task.marker_size if task.marker_size is not None else style.milestone_size
    x = mdates.date2num(ms_date)

    ax_bar.plot(
        x, y,
        marker=marker,
        markersize=size,
        color=color,
        markeredgecolor="none",
        zorder=5,
        linestyle="none",
    )


def _draw_compare_milestone(ax_bar, row: _Row, y: float, style: Style, outlined: bool) -> None:
    """Draw a compare milestone, either planned outline or actual fill."""
    task = row.task
    if task.milestone_date is None and task.start is None:
        return

    ms_date = task.milestone_date or task.start
    color = _milestone_color(row, style)
    marker = _milestone_marker(task, style)
    size = task.marker_size if task.marker_size is not None else style.milestone_size
    x = mdates.date2num(ms_date)

    ax_bar.plot(
        x,
        y,
        marker=marker,
        markersize=size * (1.22 if outlined else 1.0),
        markerfacecolor="none" if outlined else color,
        markeredgecolor=color,
        markeredgewidth=1.8 if outlined else 0.0,
        color=color,
        zorder=4.8 if outlined else 5.2,
        linestyle="none",
    )


def _row_label_text(row: _Row, style: Style) -> str:
    """Return the rendered label text for a row."""
    if not style.number_tasks:
        return row.task.name

    number_str = row.number + "." if "." not in row.number else row.number
    return number_str + "  " + row.task.name


def _compare_row_label_text(row: _CompareRow, style: Style) -> str:
    """Return the rendered label text for a compare row."""
    if not style.number_tasks:
        return _compare_display_name(row)

    number_str = row.number + "." if "." not in row.number else row.number
    return number_str + "  " + _compare_display_name(row)


def _compare_display_name(row: _CompareRow) -> str:
    """Return the displayed compare row name, marking added items with parentheses."""
    if row.is_added:
        return f"({row.task.name})"
    return row.task.name


def _row_table_number(row: _Row) -> str:
    """Return the numbering shown in the table Task column."""
    return row.number + "." if "." not in row.number else row.number


def _compare_row_table_number(row: _CompareRow) -> str:
    """Return the numbering shown in the compare table Task column."""
    return row.number + "." if "." not in row.number else row.number


def _compare_title(planned_config: ChartConfig, actual_config: ChartConfig) -> str:
    """Return the best title for compare output."""
    planned_title = planned_config.title.strip()
    actual_title = actual_config.title.strip()
    if planned_title and actual_title and planned_title != actual_title:
        return f"{planned_title} vs {actual_title}"
    return planned_title or actual_title


def _task_duration_days(task: Task) -> int:
    """Return task duration in whole days for compare-table offsets."""
    start = task.effective_start
    end = task.effective_end
    if start is None or end is None:
        return 0
    return (end - start).days


def _format_compare_offset(row: _CompareRow) -> str:
    """Return the compare offset string shown in table and CSV output."""
    if row.is_removed:
        return "Removed"
    if row.is_added:
        return "Added"

    if row.planned is None or row.actual is None:
        return "0d"

    planned_task = row.planned.task
    actual_task = row.actual.task
    if planned_task.milestone or actual_task.milestone:
        planned_date = planned_task.effective_start
        actual_date = actual_task.effective_start
        if planned_date is None or actual_date is None:
            return "0d"
        return _format_signed_days((actual_date - planned_date).days)

    delta = _task_duration_days(actual_task) - _task_duration_days(planned_task)
    return _format_signed_days(delta)


def _format_signed_days(days: int) -> str:
    """Format a signed day delta using the cleanest whole-unit label."""
    if days == 0:
        return "0d"

    sign = "+" if days > 0 else "-"
    abs_days = abs(days)

    if abs_days >= 365 and abs_days % 365 == 0:
        return f"{sign}{abs_days // 365}y"
    if abs_days >= 30 and abs_days % 30 == 0:
        return f"{sign}{abs_days // 30}mo"
    if abs_days >= 7 and abs_days % 7 == 0:
        return f"{sign}{abs_days // 7}w"
    return f"{sign}{abs_days}d"


def _wrap_text(text: str, width: int) -> List[str]:
    """Wrap *text* to approximately *width* characters per line."""
    if not text:
        return [""]

    lines: List[str] = []
    for paragraph in str(text).splitlines():
        wrapped = textwrap.wrap(
            paragraph,
            width=max(8, width),
            break_long_words=False,
            break_on_hyphens=False,
        )
        lines.extend(wrapped or [""])
    return lines or [""]


def _wrap_text_measured(text: str, width_in: float, font_properties: FontProperties) -> List[str]:
    """Wrap *text* to *width_in* inches using measured text widths."""
    if not text:
        return [""]

    if width_in <= 0:
        return [str(text)]

    lines: List[str] = []
    for paragraph in str(text).splitlines():
        words = paragraph.split()
        if not words:
            lines.append("")
            continue

        current = words[0]
        for word in words[1:]:
            candidate = current + " " + word
            if _measure_text_width_in(candidate, font_properties) <= width_in:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines or [""]


def _compute_chart_label_layout(rows, style: Style, fig_w: float, label_text_fn) -> Tuple[float, float, float]:
    """Return label panel fraction, indent step, and left margin fraction for chart labels."""
    indent_chars = 3
    char_width_in = style.font_size * 0.55 / 72.0
    indent_width_in = indent_chars * char_width_in
    left_margin_in = 0.15
    right_margin_in = 0.05

    measured_widths = []
    for row in rows:
        weight = "bold" if (row.task.bold or (style.bold_tasks and row.depth == 0)) else "normal"
        font_props = FontProperties(size=style.font_size, weight=weight)
        measured_widths.append(row.depth * indent_width_in + _measure_text_width_in(label_text_fn(row, style), font_props))

    label_width_in = max(0.8, left_margin_in + (max(measured_widths) if measured_widths else 0.0) + right_margin_in)
    requested_fraction = max(0.0, style.label_fraction)
    label_fraction = min(0.6, max(requested_fraction, label_width_in / fig_w))
    indent_step = indent_width_in / label_width_in
    left_margin_frac = left_margin_in / label_width_in
    return label_fraction, indent_step, left_margin_frac


def _measure_text_width_in(text: str, font_properties: FontProperties) -> float:
    """Measure *text* width in inches using matplotlib's text renderer."""
    fig = Figure(figsize=(1, 1), dpi=100)
    canvas = FigureCanvasAgg(fig)
    renderer = canvas.get_renderer()
    text_artist = Text(0, 0, text, fontproperties=font_properties)
    text_artist.set_figure(fig)
    bbox = text_artist.get_window_extent(renderer=renderer)
    return bbox.width / fig.dpi


def _draw_strike_line(ax, x_start: float, y: float, text: str, font_properties: FontProperties) -> None:
    """Draw a strike-through line across *text* positioned on *ax*."""
    if not text:
        return

    axis_width_in = ax.get_position().width * ax.figure.get_figwidth()
    if axis_width_in <= 0:
        return

    width_fraction = _measure_text_width_in(text, font_properties) / axis_width_in
    x_end = min(0.99, x_start + width_fraction)
    ax.plot([x_start, x_end], [y, y], color="#111111", linewidth=1.2, zorder=6, clip_on=True)


def _max_text_width_in(values: List[str], font_properties: FontProperties) -> float:
    """Return the maximum measured width in inches across *values*."""
    if not values:
        return 0.0
    return max(_measure_text_width_in(value, font_properties) for value in values)


# ---------------------------------------------------------------------------
# Dependency arrow drawing
# ---------------------------------------------------------------------------


def _draw_arrow(
    ax_bar,
    arrow: Arrow,
    id_to_row: dict,
    style: Style,
) -> None:
    """Draw a cubic-bezier S-curve from the end of one task to the start of another."""
    from matplotlib.path import Path

    from_row = id_to_row.get(arrow.from_id)
    to_row   = id_to_row.get(arrow.to_id)
    if from_row is None or to_row is None:
        return

    from_end  = from_row.task.effective_end
    to_start  = to_row.task.effective_start
    if from_end is None or to_start is None:
        return

    x0 = mdates.date2num(from_end)
    y0 = from_row.row_index
    x1 = mdates.date2num(to_start)
    y1 = to_row.row_index

    # S-curve: control points at mid-x, anchored horizontally at each end
    xm = (x0 + x1) / 2.0
    verts = [(x0, y0), (xm, y0), (xm, y1), (x1, y1)]
    codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4]

    patch = mpatches.PathPatch(
        Path(verts, codes),
        facecolor="none",
        edgecolor=arrow.color,
        linewidth=1.4,
        zorder=6,
    )
    ax_bar.add_patch(patch)


# ---------------------------------------------------------------------------
# Colour utilities
# ---------------------------------------------------------------------------


def _darken(hex_color: str, amount: float = 0.2) -> str:
    """Return *hex_color* darkened by *amount* (0–1)."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r = max(0, int(r * (1 - amount)))
        g = max(0, int(g * (1 - amount)))
        b = max(0, int(b * (1 - amount)))
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return hex_color
