"""Data models for jsonantt."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Default colour palette (can be overridden in JSON "style" block)
# ---------------------------------------------------------------------------
DEFAULT_PALETTE: List[str] = [
    "#4472C4",  # steel blue
    "#ED7D31",  # orange
    "#70AD47",  # green
    "#FF5757",  # coral red
    "#9DC3E6",  # sky blue
    "#FFC000",  # amber
    "#7030A0",  # purple
    "#00B0F0",  # cyan
    "#FF0066",  # hot pink
    "#00B050",  # emerald
]


@dataclass
class Arrow:
    """A dependency arrow connecting the end of one task to the start of another."""

    from_id: str
    to_id: str
    color: str = "#888888"
    label: Optional[str] = None


@dataclass
class Task:
    """A single task (or milestone) in the Gantt chart.

    Date resolution modes
    ---------------------
    1. ``start`` + ``end``   – explicit dates (original behaviour)
    2. ``start`` + ``duration`` – ``end`` computed from ``start`` + duration
    3. ``not_before`` + ``duration`` – ``start`` set to the ``effective_end``
       of the task whose ``id`` matches ``not_before``, then ``end`` computed.

    When absent the values are derived recursively from *children* via
    :pymeth:`effective_start` / :pymeth:`effective_end`.
    """

    name: str
    description: str = ""
    id: Optional[str] = None           # unique identifier for cross-referencing
    start: Optional[date] = None
    end: Optional[date] = None
    color: Optional[str] = None
    edge_color: Optional[str] = None
    milestone: bool = False
    major_milestone: bool = False
    milestone_date: Optional[date] = None
    milestone_dates: List[date] = field(default_factory=list)
    children: List["Task"] = field(default_factory=list)
    # -- deferred-resolution fields (set by parser, consumed during resolve) --
    not_before: Optional[str] = None   # id of task whose end becomes this start
    duration_spec: Optional[str] = None  # raw duration string e.g. "3m", "14d"
    marker_size: Optional[float] = None  # override milestone diamond size (pts)
    marker: Optional[str] = None         # override milestone marker symbol
    bold: bool = False                    # render label in bold
    fields: Dict[str, Any] = field(default_factory=dict)  # extra JSON fields available to tables

    # ------------------------------------------------------------------ #
    #  Computed properties                                                 #
    # ------------------------------------------------------------------ #

    @property
    def effective_start(self) -> Optional[date]:
        """Earliest start date, resolving through children if needed."""
        if self.milestone:
            if self.milestone_dates:
                return min(self.milestone_dates)
            return self.milestone_date or self.start
        if self.start is not None:
            return self.start
        starts = [c.effective_start for c in self.children if c.effective_start is not None]
        return min(starts) if starts else None

    @property
    def effective_end(self) -> Optional[date]:
        """Latest end date, resolving through children if needed."""
        if self.milestone:
            if self.milestone_dates:
                return max(self.milestone_dates)
            return self.milestone_date or self.start
        if self.end is not None:
            return self.end
        ends = [c.effective_end for c in self.children if c.effective_end is not None]
        return max(ends) if ends else None

    @property
    def is_parent(self) -> bool:
        """True when this task has sub-tasks."""
        return bool(self.children)


@dataclass
class Style:
    """Visual style configuration for the chart."""

    width: float = 14.0          # figure width in inches
    row_height: float = 0.3      # height of each row in inches
    bar_height: float = 0.5      # bar height as fraction of row_height
    font_size: float = 12.0      # base font size in pts
    indent_size: int = 3         # spaces added per depth level
    label_fraction: float = 0.0  # 0 = auto-size label area from measured text width
    subtask_lightening_pct: float = 0.0  # percentage to lighten inherited child colors per depth step
    colors: List[str] = field(default_factory=lambda: list(DEFAULT_PALETTE))
    background: str = "#FFFFFF"  # figure background colour
    grid_color: str = "#E0E0E0"  # vertical gridline colour
    row_band_color: str = "#F5F5F5"  # alternating row band colour
    milestone_color: str = "#FFD700"  # default milestone colour
    milestone_edge_color: Optional[str] = None  # default milestone outline colour
    milestone_marker: str = "D"       # default milestone marker symbol
    milestone_size: float = 14.0       # default milestone marker size (pts)
    rollup_milestones: bool = False    # draw hidden descendant milestones on rolled-up ancestor bars
    rollup_major_milestones_only: bool = False  # restrict milestone rollup overlays to major milestones
    number_milestones: bool = False    # label milestones as M1, M2, ... in markers and tables
    major_milestone_color: Optional[str] = None  # default major milestone fill colour
    major_milestone_edge_color: Optional[str] = None  # default major milestone outline colour
    major_milestone_marker: Optional[str] = None  # default major milestone marker symbol
    major_milestone_size: Optional[float] = None  # default major milestone marker size (pts)
    major_tick: Optional[str] = None  # e.g. "year", "quarter", "month", "week"
    minor_tick: Optional[str] = None  # e.g. "quarter", "month", "week", "day"
    major_grid_width: float = 2.0     # major gridline linewidth
    minor_grid_width: float = 1.5     # minor gridline linewidth
    bold_tasks: bool = True           # auto-bold top-level (depth 0) tasks
    number_tasks: bool = True         # prefix task labels with hierarchy numbers
    table_colorize: bool = True       # show task colors in the table accent gutter
    table_show_markers: bool = True   # draw milestone diamonds in table output
    tick_position: str = "top"        # x-axis label position: "top", "bottom", or "both"
    table_columns: List[Any] = field(default_factory=list)  # ordered table columns; empty keeps default columns


@dataclass
class ChartConfig:
    """Top-level chart configuration parsed from JSON."""

    tasks: List[Task] = field(default_factory=list)
    title: str = ""
    date_format: str = "%Y-%m-%d"
    start: Optional[date] = None    # force chart x-axis start
    end: Optional[date] = None      # force chart x-axis end
    style: Style = field(default_factory=Style)
    arrows: List[Arrow] = field(default_factory=list)
