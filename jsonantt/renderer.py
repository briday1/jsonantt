"""matplotlib-based Gantt chart renderer for jsonantt."""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import List, Optional, Tuple

import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.figure import Figure

from .models import ChartConfig, Style, Task

# ---------------------------------------------------------------------------
# Internal helper types
# ---------------------------------------------------------------------------


class _Row:
    """A flattened task row ready for rendering."""

    __slots__ = ("task", "depth", "row_index", "color")

    def __init__(self, task: Task, depth: int, row_index: int, color: str) -> None:
        self.task = task
        self.depth = depth
        self.row_index = row_index
        self.color = color


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_chart(config: ChartConfig, output_path: str, dpi: int = 150) -> None:
    """Render *config* to *output_path* (PNG, PDF, SVG …)."""
    rows = _flatten(config.tasks, config.style)
    if not rows:
        raise ValueError("No tasks to render.")

    n = len(rows)
    style = config.style

    # ---- figure dimensions ------------------------------------------------
    row_h_in = style.row_height
    top_pad = 0.6 if config.title else 0.25
    bottom_pad = 0.65
    fig_h = n * row_h_in + top_pad + bottom_pad
    fig_w = style.width

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
        width_ratios=[style.label_fraction, 1.0 - style.label_fraction],
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

    # ---- y-axis range (top row = highest y value) -------------------------
    y_min = -0.5
    y_max = n - 0.5

    # ---- style both axes --------------------------------------------------
    _style_label_axis(ax_lbl, y_min, y_max, style, n)
    _style_bar_axis(ax_bar, x_start, x_end, y_min, y_max, style, n)

    # ---- alternating row bands --------------------------------------------
    for i in range(n):
        if i % 2 == 1:
            _row_band(ax_bar, i, style)

    # ---- draw each row ----------------------------------------------------
    for row in rows:
        _draw_row(ax_lbl, ax_bar, row, n, style)

    # ---- title ------------------------------------------------------------
    if config.title:
        fig.suptitle(
            config.title,
            fontsize=style.font_size + 3,
            fontweight="bold",
            x=0.5,
            y=1 - (top_pad * 0.35) / fig_h,
            va="top",
            ha="center",
        )

    fig.savefig(output_path, dpi=dpi, bbox_inches="tight",
                facecolor=style.background)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Flatten task tree → ordered list of _Row
# ---------------------------------------------------------------------------


def _flatten(
    tasks: List[Task],
    style: Style,
    depth: int = 0,
    palette_index: int = 0,
    parent_color: Optional[str] = None,
) -> List[_Row]:
    rows: List[_Row] = []
    palette = style.colors or ["#4472C4"]

    for task_idx, task in enumerate(tasks):
        # colour resolution: explicit > parent > palette
        if task.color:
            color = task.color
        elif parent_color and depth > 0:
            color = parent_color
        else:
            color = palette[palette_index % len(palette)]
            palette_index += 1

        row = _Row(task=task, depth=depth, row_index=0, color=color)
        rows.append(row)

        if task.children:
            child_rows = _flatten(
                task.children,
                style,
                depth=depth + 1,
                palette_index=palette_index,
                parent_color=color,
            )
            rows.extend(child_rows)

    # assign row_index top-to-bottom
    for i, r in enumerate(rows):
        r.row_index = i

    return rows


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
    ax.set_facecolor(style.background)


def _style_bar_axis(ax, x_start, x_end, y_min, y_max, style: Style, n: int) -> None:
    """Configure the bar / chart panel (right side)."""
    ax.set_facecolor(style.background)
    ax.set_ylim(y_min, y_max)
    ax.invert_yaxis()

    # x-axis as dates
    ax.set_xlim(x_start, x_end)
    ax.xaxis_date()

    span_days = (x_end - x_start).days

    # choose sensible date tick locator & formatter
    if span_days <= 21:
        locator = mdates.DayLocator(interval=1)
        fmt = mdates.DateFormatter("%b %d")
    elif span_days <= 90:
        locator = mdates.WeekdayLocator(byweekday=mdates.MO)
        fmt = mdates.DateFormatter("%b %d")
    elif span_days <= 365:
        locator = mdates.MonthLocator()
        fmt = mdates.DateFormatter("%b '%y")
    elif span_days <= 365 * 3:
        locator = mdates.MonthLocator(interval=3)
        fmt = mdates.DateFormatter("%b '%y")
    else:
        locator = mdates.YearLocator()
        fmt = mdates.DateFormatter("%Y")

    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(fmt)
    ax.xaxis.set_tick_params(labelsize=style.font_size - 1, rotation=30)

    # gridlines
    ax.yaxis.set_visible(False)
    ax.grid(axis="x", color=style.grid_color, linewidth=0.6, zorder=0)

    # clean up spines
    for spine in ["left", "right", "top"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(style.grid_color)


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


def _draw_row(ax_lbl, ax_bar, row: _Row, n: int, style: Style) -> None:
    task = row.task
    y = row.row_index

    # ---- label ------------------------------------------------------------
    indent = " " * (style.indent_size * row.depth)
    label_text = indent + task.name

    # bold for parent tasks
    weight = "bold" if task.is_parent and not task.milestone else "normal"
    ax_lbl.text(
        0.97, y,
        label_text,
        ha="right",
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
    if task.is_parent:
        # thinner "summary" bar with a darker outline
        bar_h = bar_h * 0.45
        edge_color = _darken(row.color, 0.4)
        alpha = 0.85
        lw = 1.2
        # draw arrow-cap triangles at both ends (MS-Project style summary bar)
        _draw_summary_caps(ax_bar, start, end, y, row.color, edge_color, bar_h)
    else:
        edge_color = _darken(row.color, 0.25)
        alpha = 0.90
        lw = 0.8

    bar = mpatches.FancyBboxPatch(
        (mdates.date2num(start), y - bar_h / 2),
        mdates.date2num(end) - mdates.date2num(start),
        bar_h,
        boxstyle="round,pad=0.02",
        facecolor=row.color,
        edgecolor=edge_color,
        linewidth=lw,
        alpha=alpha,
        zorder=3,
    )
    ax_bar.add_patch(bar)


def _draw_summary_caps(ax_bar, start: date, end: date, y: float,
                       color: str, edge_color: str, bar_h: float) -> None:
    """Draw small downward triangles at start/end of a parent (summary) bar."""
    cap_h = bar_h * 2.2
    cap_w = mdates.date2num(start + timedelta(days=1)) - mdates.date2num(start)
    cap_w = cap_w * 0.8

    for x_centre in [mdates.date2num(start), mdates.date2num(end)]:
        tri = plt.Polygon(
            [
                [x_centre - cap_w * 0.5, y - bar_h / 2],
                [x_centre + cap_w * 0.5, y - bar_h / 2],
                [x_centre, y + cap_h / 2],
            ],
            closed=True,
            facecolor=color,
            edgecolor=edge_color,
            linewidth=0.8,
            zorder=4,
        )
        ax_bar.add_patch(tri)


def _draw_milestone(ax_bar, row: _Row, y: float, style: Style) -> None:
    task = row.task
    if task.milestone_date is None:
        return

    color = row.color if row.color else style.milestone_color
    x = mdates.date2num(task.milestone_date)

    diamond_half = style.bar_height * 0.55
    diamond = plt.Polygon(
        [
            [x, y - diamond_half],
            [x + diamond_half * 0.65, y],
            [x, y + diamond_half],
            [x - diamond_half * 0.65, y],
        ],
        closed=True,
        facecolor=color,
        edgecolor=_darken(color, 0.35),
        linewidth=1.0,
        zorder=5,
    )
    ax_bar.add_patch(diamond)

    # thin vertical dashed line dropping from the diamond to x-axis
    ax_bar.axvline(
        x=x,
        color=color,
        linewidth=0.7,
        linestyle="--",
        alpha=0.5,
        zorder=2,
    )


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
