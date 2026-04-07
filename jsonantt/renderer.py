"""matplotlib-based Gantt chart renderer for jsonantt."""
from __future__ import annotations

import csv
from difflib import SequenceMatcher
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


def _milestone_marker(task: Task, style: Style) -> str:
    """Return the marker symbol for a milestone, preferring task override."""
    return task.marker if task.marker else style.milestone_marker


def _milestone_color(row: _Row, style: Style) -> str:
    """Return the milestone color for a row, preferring task color override."""
    return row.task.color if row.task.color else style.milestone_color

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
        _write_compare_table_csv(rows, output_path)
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
    min_desc_width_in = max(3.0, table_width_in * 0.35)
    min_offset_width_in = 1.2
    has_table_gutter = style.table_colorize
    gutter_width_in = table_width_in * gutter_width_frac if has_table_gutter else 0.0

    font_props = FontProperties(size=style.font_size, weight="normal")
    bold_font_props = FontProperties(size=style.font_size, weight="bold")
    offsets = [_format_compare_offset(row) for row in rows]

    number_width_in = max(
        0.55,
        _max_text_width_in([_compare_row_table_number(row) for row in rows] + ["Task"], font_props) + col_padding_in,
    )
    if has_table_gutter:
        number_width_in += gutter_width_in + gutter_gap_in
    name_width_in = max(
        1.6,
        max(
            _measure_text_width_in(
                _compare_display_name(row),
                bold_font_props if (row.task.bold or (style.bold_tasks and row.depth == 0)) else font_props,
            )
            for row in rows
        ) + col_padding_in,
    )
    offset_width_in = max(
        min_offset_width_in,
        _max_text_width_in(offsets + ["Offset"], font_props) + col_padding_in,
    )

    max_non_desc_width = max(3.4, table_width_in - min_desc_width_in)
    non_desc_width = number_width_in + name_width_in + offset_width_in
    if non_desc_width > max_non_desc_width:
        overflow = non_desc_width - max_non_desc_width
        reducible_name = max(0.0, name_width_in - 1.6)
        reduction = min(overflow, reducible_name)
        name_width_in -= reduction
        overflow -= reduction
        if overflow > 0:
            reducible_offset = max(0.0, offset_width_in - min_offset_width_in)
            offset_width_in -= min(overflow, reducible_offset)

    desc_width_in = max(2.6, table_width_in - number_width_in - name_width_in - offset_width_in)

    task_num_fraction = number_width_in / table_width_in
    name_col_fraction = name_width_in / table_width_in
    desc_col_fraction = desc_width_in / table_width_in
    offset_col_fraction = offset_width_in / table_width_in

    number_wrap_chars = max(4, int((number_width_in - col_padding_in) / char_width_in))
    desc_wrap_chars = max(24, int((desc_width_in - col_padding_in) / char_width_in))
    offset_wrap_chars = max(8, int((offset_width_in - col_padding_in) / char_width_in))

    wrapped_rows = []
    total_units = 1.3
    for row in rows:
        number_lines = _wrap_text(_compare_row_table_number(row), number_wrap_chars)
        row_font_props = bold_font_props if (row.task.bold or (style.bold_tasks and row.depth == 0)) else font_props
        name_lines = _wrap_text_measured(_compare_display_name(row), name_width_in - col_padding_in, row_font_props)
        desc_lines = _wrap_text_measured(row.description, desc_width_in - col_padding_in, font_props)
        offset_lines = _wrap_text(_format_compare_offset(row), offset_wrap_chars)
        line_count = max(len(number_lines), len(name_lines), len(desc_lines), len(offset_lines), 1)
        row_units = line_count + 0.6
        wrapped_rows.append((row, number_lines, name_lines, desc_lines, offset_lines, row_units))
        total_units += row_units

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
    task_x_end = task_num_fraction
    name_x_end = task_x_end + name_col_fraction
    desc_x_end = name_x_end + desc_col_fraction
    offset_x_start = desc_x_end

    ax.add_patch(mpatches.Rectangle((0, 0), task_x_end, 1.3, facecolor=header_color, edgecolor=divider_color, linewidth=1.0))
    ax.add_patch(mpatches.Rectangle((task_x_end, 0), name_col_fraction, 1.3, facecolor=header_color, edgecolor=divider_color, linewidth=1.0))
    ax.add_patch(mpatches.Rectangle((name_x_end, 0), desc_col_fraction, 1.3, facecolor=header_color, edgecolor=divider_color, linewidth=1.0))
    ax.add_patch(mpatches.Rectangle((offset_x_start, 0), offset_col_fraction, 1.3, facecolor=header_color, edgecolor=divider_color, linewidth=1.0))
    ax.text(text_pad_frac, 0.65, "Task", ha="left", va="center", fontsize=style.font_size, fontweight="bold")
    ax.text(task_x_end + text_pad_frac, 0.65, "Name", ha="left", va="center", fontsize=style.font_size, fontweight="bold")
    ax.text(name_x_end + text_pad_frac, 0.65, "Description", ha="left", va="center", fontsize=style.font_size, fontweight="bold")
    ax.text(offset_x_start + text_pad_frac, 0.65, "Offset", ha="left", va="center", fontsize=style.font_size, fontweight="bold")

    y = 1.3
    for row_index, (row, number_lines, name_lines, desc_lines, offset_lines, row_units) in enumerate(wrapped_rows):
        band_color = style.background if row_index % 2 == 0 else style.row_band_color
        ax.add_patch(mpatches.Rectangle((0, y), 1.0, row_units, facecolor=band_color, edgecolor=divider_color, linewidth=0.8))

        show_milestone_marker = row.task.milestone and style.table_colorize and style.table_show_markers
        accent_color = row.actual.color if row.actual is not None else row.planned.color
        if style.table_colorize and not show_milestone_marker:
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

        ax.plot([task_x_end, task_x_end], [y, y + row_units], color=divider_color, linewidth=1.0)
        ax.plot([name_x_end, name_x_end], [y, y + row_units], color=divider_color, linewidth=1.0)
        ax.plot([desc_x_end, desc_x_end], [y, y + row_units], color=divider_color, linewidth=1.0)

        text_y = y + row_units / 2.0
        task_weight = "bold" if (row.task.bold or (style.bold_tasks and row.depth == 0)) else "normal"
        number_clip = mpatches.Rectangle((0, y), task_x_end, row_units, transform=ax.transData)
        name_clip = mpatches.Rectangle((task_x_end, y), name_col_fraction, row_units, transform=ax.transData)
        desc_clip = mpatches.Rectangle((name_x_end, y), desc_col_fraction, row_units, transform=ax.transData)
        offset_clip = mpatches.Rectangle((offset_x_start, y), offset_col_fraction, row_units, transform=ax.transData)

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
            name_x_end + text_pad_frac,
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

        offset_text = ax.text(
            offset_x_start + text_pad_frac,
            text_y,
            "\n".join(offset_lines),
            ha="left",
            va="center",
            fontsize=style.font_size,
            color="#111111",
            linespacing=1.35,
            clip_on=True,
        )
        offset_text.set_clip_path(offset_clip)

        if row.is_removed:
            strike_font_props = FontProperties(size=style.font_size, weight=task_weight)
            _draw_strike_line(ax, max(text_pad_frac, gutter_width + 0.006), text_y, " ".join(number_lines), strike_font_props)
            _draw_strike_line(ax, task_x_end + text_pad_frac, text_y, " ".join(name_lines), strike_font_props)

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


def _write_compare_table_csv(rows: List[_CompareRow], output_path: str) -> None:
    """Write compare table rows to *output_path* as CSV."""
    with open(output_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Task", "Name", "Description", "Offset"])
        for row in rows:
            writer.writerow([
                _compare_row_table_number(row),
                _compare_display_name(row),
                row.description,
                _format_compare_offset(row),
            ])


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
