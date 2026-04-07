"""jsonantt – Gantt chart generation from JSON descriptions.

Quick-start example::

    from jsonantt import load_chart, render_chart

    config = load_chart("project.json")
    render_chart(config, "project.png")

Or from the command line::

    jsonantt project.json project.png
"""
from .parser import load_chart, parse_chart
from .renderer import render_chart

__all__ = ["load_chart", "parse_chart", "render_chart"]
__version__ = "0.1.0"
