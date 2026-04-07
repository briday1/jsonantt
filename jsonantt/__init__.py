"""jsonantt – Gantt chart generation from JSON descriptions.

Quick-start example::

    from jsonantt import load_chart, render_chart, render_table

    config = load_chart("project.json")
    render_chart(config, "project.png")
    render_chart(config, "summary.png", render_depth=1)
    render_table(config, "tasks.png")
    render_table(config, "milestones.png", milestones_only=True)
    render_table(config, "tasks-no-milestones.png", no_milestones=True)

Or from the command line::

    jsonantt project.json project.png
    jsonantt --renderdepth 2 project.json project.png
    jsonantt --table project.json tasks.png
    jsonantt --table --milestones-only project.json milestones.png
    jsonantt --table --no-milestones project.json tasks-no-milestones.png
"""
from .parser import load_chart, parse_chart
from .renderer import render_chart, render_table

__all__ = ["load_chart", "parse_chart", "render_chart", "render_table"]
__version__ = "0.1.0"
