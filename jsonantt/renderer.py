"""matplotlib-based Gantt chart renderer for jsonantt."""
from __future__ import annotations

import csv
import math
import os
import textwrap
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

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

# ---------------------------------------------------------------------------
# Internal helper types
# ---------------------------------------------------------------------------


class _Row:
    """A flattened task row ready for rendering."""

    __slots__ = ("task", "depth", "row_index", "color", "number")

    def __init__(self, task: Task, depth: int, row_index: int, color: str, number: str = "") -> None:
        self.task = task
        self.depth = depth
        self.row_index = row_index
        self.color = color
        self.number = number


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_chart(
    config: ChartConfig,
    output_path: str,
    dpi: int = 150,
    render_depth: int = 0,
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

    # ---- compute label panel width from actual text content ---------------
    # Approximate character width: font is roughly 0.55× the point size wide.
    # indent_chars: how many characters each depth level is worth visually.
    char_width_in = style.font_size * 0.55 / 72.0
    indent_chars = 3
    left_margin_in = 0.15
    right_margin_in = 0.05

    max_text_in = 0.0
    for row in rows:
        label = _row_label_text(row, style)
        text_in = (row.depth * indent_chars + len(label)) * char_width_in
        max_text_in = max(max_text_in, text_in)

    label_width_in = left_margin_in + max_text_in + right_margin_in
    label_fraction = min(0.55, label_width_in / fig_w)

    # indent step as a fraction of the label panel (0-1 data coords)
    indent_step = (indent_chars * char_width_in) / label_width_in
    left_margin_frac = left_margin_in / label_width_in

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
        _write_table_csv(rows, output_path)
        return

    fig_w = style.width
    char_width_in = style.font_size * 0.55 / 72.0
    line_height_in = style.font_size * 1.5 / 72.0
    table_width_frac = 0.94
    table_width_in = fig_w * table_width_frac
    gutter_width_frac = 0.018
    gutter_gap_in = 0.05
    text_pad_frac = 0.014
    text_pad_in = table_width_in * text_pad_frac
    col_padding_in = text_pad_in * 2 + 0.05
    min_desc_width_in = max(4.0, table_width_in * 0.45)
    has_table_gutter = style.table_colorize
    gutter_width_in = table_width_in * gutter_width_frac if has_table_gutter else 0.0

    font_props = FontProperties(size=style.font_size, weight="normal")
    bold_font_props = FontProperties(size=style.font_size, weight="bold")
    number_width_in = max(
        0.55,
        _max_text_width_in([_row_table_number(row) for row in rows], font_props) + col_padding_in,
    )
    if has_table_gutter:
        number_width_in += gutter_width_in + gutter_gap_in
    name_width_in = max(
        1.6,
        max(
            _measure_text_width_in(
                row.task.name,
                bold_font_props if (row.task.bold or (style.bold_tasks and row.depth == 0)) else font_props,
            )
            for row in rows
        ) + col_padding_in,
    )

    max_non_desc_width = max(2.6, table_width_in - min_desc_width_in)
    non_desc_width = number_width_in + name_width_in
    if non_desc_width > max_non_desc_width:
        overflow = non_desc_width - max_non_desc_width
        reducible_name = max(0.0, name_width_in - 1.6)
        reduction = min(overflow, reducible_name)
        name_width_in -= reduction
        overflow -= reduction
        if overflow > 0:
            reducible_number = max(0.0, number_width_in - 0.55)
            number_width_in -= min(overflow, reducible_number)

    desc_width_in = max(2.6, table_width_in - number_width_in - name_width_in)

    task_num_fraction = number_width_in / table_width_in
    name_col_fraction = name_width_in / table_width_in
    desc_col_fraction = desc_width_in / table_width_in

    number_wrap_chars = max(4, int((number_width_in - col_padding_in) / char_width_in))
    desc_wrap_chars = max(28, int((desc_width_in - col_padding_in) / char_width_in))

    wrapped_rows = []
    total_units = 1.3  # header row
    for row in rows:
        number_lines = _wrap_text(_row_table_number(row), number_wrap_chars)
        row_font_props = bold_font_props if (row.task.bold or (style.bold_tasks and row.depth == 0)) else font_props
        name_lines = _wrap_text_measured(row.task.name, name_width_in - col_padding_in, row_font_props)
        desc_lines = _wrap_text_measured(row.task.description, desc_width_in - col_padding_in, font_props)
        line_count = max(len(number_lines), len(name_lines), len(desc_lines), 1)
        row_units = line_count + 0.6
        wrapped_rows.append((row, number_lines, name_lines, desc_lines, row_units))
        total_units += row_units

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
    task_x_end = task_num_fraction
    name_x_end = task_num_fraction + name_col_fraction
    desc_x_start = name_x_end

    ax.add_patch(mpatches.Rectangle(
        (0, 0), task_x_end, 1.3,
        facecolor=header_color,
        edgecolor=divider_color,
        linewidth=1.0,
    ))
    ax.add_patch(mpatches.Rectangle(
        (task_x_end, 0), name_col_fraction, 1.3,
        facecolor=header_color,
        edgecolor=divider_color,
        linewidth=1.0,
    ))
    ax.add_patch(mpatches.Rectangle(
        (desc_x_start, 0), desc_col_fraction, 1.3,
        facecolor=header_color,
        edgecolor=divider_color,
        linewidth=1.0,
    ))
    ax.text(text_pad_frac, 0.65, "Task", ha="left", va="center", fontsize=style.font_size, fontweight="bold")
    ax.text(task_x_end + text_pad_frac, 0.65, "Name", ha="left", va="center", fontsize=style.font_size, fontweight="bold")
    ax.text(desc_x_start + text_pad_frac, 0.65, "Description", ha="left", va="center", fontsize=style.font_size, fontweight="bold")

    y = 1.3
    for row_index, (row, number_lines, name_lines, desc_lines, row_units) in enumerate(wrapped_rows):
        band_color = style.background if row_index % 2 == 0 else style.row_band_color

        ax.add_patch(mpatches.Rectangle(
            (0, y), 1.0, row_units,
            facecolor=band_color,
            edgecolor=divider_color,
            linewidth=0.8,
        ))
        show_milestone_marker = row.task.milestone and style.table_colorize and style.table_show_markers
        if style.table_colorize and not show_milestone_marker:
            ax.add_patch(mpatches.Rectangle(
                (0, y), 0.010, row_units,
                facecolor=row.color,
                edgecolor="none",
            ))
        if show_milestone_marker:
            marker_x = gutter_width / 2.0
            marker_y = y + row_units / 2.0
            marker_color = row.color if row.color else style.milestone_color
            ax.plot(
                marker_x,
                marker_y,
                marker="D",
                markersize=max(6, style.milestone_size * 0.65),
                color=marker_color,
                markeredgecolor="none",
                linestyle="none",
                zorder=4,
            )

        ax.plot([task_x_end, task_x_end], [y, y + row_units], color=divider_color, linewidth=1.0)
        ax.plot([name_x_end, name_x_end], [y, y + row_units], color=divider_color, linewidth=1.0)

        text_y = y + row_units / 2.0
        task_weight = "bold" if (row.task.bold or (style.bold_tasks and row.depth == 0)) else "normal"
        number_clip = mpatches.Rectangle((0, y), task_x_end, row_units, transform=ax.transData)
        name_clip = mpatches.Rectangle((task_x_end, y), name_col_fraction, row_units, transform=ax.transData)
        desc_clip = mpatches.Rectangle((desc_x_start, y), desc_col_fraction, row_units, transform=ax.transData)

        number_text = ax.text(
            max(text_pad_frac, gutter_width + 0.006),
            text_y,
            "\n".join(number_lines),
            ha="left",
            va="center",
            fontsize=style.font_size,
            fontweight=task_weight,
            color="#111111",
            linespacing=1.35,
            clip_on=True,
        )
        number_text.set_clip_path(number_clip)

        name_text = ax.text(
            task_x_end + text_pad_frac,
            text_y,
            "\n".join(name_lines),
            ha="left",
            va="center",
            fontsize=style.font_size,
            fontweight=task_weight,
            color="#111111",
            linespacing=1.35,
            clip_on=True,
        )
        name_text.set_clip_path(name_clip)

        desc_text = ax.text(
            desc_x_start + text_pad_frac,
            text_y,
            "\n".join(desc_lines),
            ha="left",
            va="center",
            fontsize=style.font_size,
            color="#111111",
            linespacing=1.35,
            clip_on=True,
        )
        desc_text.set_clip_path(desc_clip)
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
) -> List[_Row]:
    rows: List[_Row] = []
    palette = style.colors or ["#4472C4"]
    max_depth_index = None if max_depth == 0 else max_depth - 1

    for task_idx, task in enumerate(tasks):
        # colour resolution: explicit > parent > palette
        if task.color:
            color = task.color
        elif parent_color and depth > 0:
            color = parent_color
        else:
            color = palette[palette_index % len(palette)]
            palette_index += 1

        number = number_prefix + str(task_idx + 1)
        row = _Row(task=task, depth=depth, row_index=0, color=color, number=number)
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


def _write_table_csv(rows: List[_Row], output_path: str) -> None:
    """Write table rows to *output_path* as CSV."""
    with open(output_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Task", "Name", "Description"])
        for row in rows:
            writer.writerow([_row_table_number(row), row.task.name, row.task.description])


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


def _draw_milestone(ax_bar, row: _Row, y: float, style: Style) -> None:
    task = row.task
    if task.milestone_date is None and task.start is None:
        return

    ms_date = task.milestone_date or task.start
    color = row.color if row.color else style.milestone_color
    size = task.marker_size if task.marker_size is not None else style.milestone_size
    x = mdates.date2num(ms_date)

    ax_bar.plot(
        x, y,
        marker="D",
        markersize=size,
        color=color,
        markeredgecolor="none",
        zorder=5,
        linestyle="none",
    )


def _row_label_text(row: _Row, style: Style) -> str:
    """Return the rendered label text for a row."""
    if not style.number_tasks:
        return row.task.name

    number_str = row.number + "." if "." not in row.number else row.number
    return number_str + "  " + row.task.name


def _row_table_number(row: _Row) -> str:
    """Return the numbering shown in the table Task column."""
    return row.number + "." if "." not in row.number else row.number


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


def _measure_text_width_in(text: str, font_properties: FontProperties) -> float:
    """Measure *text* width in inches using matplotlib's text renderer."""
    fig = Figure(figsize=(1, 1), dpi=100)
    canvas = FigureCanvasAgg(fig)
    renderer = canvas.get_renderer()
    text_artist = Text(0, 0, text, fontproperties=font_properties)
    text_artist.set_figure(fig)
    bbox = text_artist.get_window_extent(renderer=renderer)
    return bbox.width / fig.dpi


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
