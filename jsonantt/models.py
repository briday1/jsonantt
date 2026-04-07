"""Data models for jsonantt."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


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
class Task:
    """A single task (or milestone) in the Gantt chart.

    ``start`` / ``end`` are explicit dates.  When absent the values are
    derived recursively from *children* via :pymeth:`effective_start` /
    :pymeth:`effective_end`.
    """

    name: str
    start: Optional[date] = None
    end: Optional[date] = None
    color: Optional[str] = None
    milestone: bool = False
    milestone_date: Optional[date] = None
    children: List["Task"] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    #  Computed properties                                                 #
    # ------------------------------------------------------------------ #

    @property
    def effective_start(self) -> Optional[date]:
        """Earliest start date, resolving through children if needed."""
        if self.milestone:
            return self.milestone_date
        if self.start is not None:
            return self.start
        starts = [c.effective_start for c in self.children if c.effective_start is not None]
        return min(starts) if starts else None

    @property
    def effective_end(self) -> Optional[date]:
        """Latest end date, resolving through children if needed."""
        if self.milestone:
            return self.milestone_date
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
    row_height: float = 0.45     # height of each row in inches
    bar_height: float = 0.5      # bar height as fraction of row_height
    font_size: float = 9.0       # base font size in pts
    indent_size: int = 3         # spaces added per depth level
    label_fraction: float = 0.28 # fraction of figure width used for labels
    colors: List[str] = field(default_factory=lambda: list(DEFAULT_PALETTE))
    background: str = "#FFFFFF"  # figure background colour
    grid_color: str = "#E0E0E0"  # vertical gridline colour
    row_band_color: str = "#F5F5F5"  # alternating row band colour
    milestone_color: str = "#E65100"  # default milestone colour


@dataclass
class ChartConfig:
    """Top-level chart configuration parsed from JSON."""

    tasks: List[Task] = field(default_factory=list)
    title: str = ""
    date_format: str = "%Y-%m-%d"
    start: Optional[date] = None    # force chart x-axis start
    end: Optional[date] = None      # force chart x-axis end
    style: Style = field(default_factory=Style)
