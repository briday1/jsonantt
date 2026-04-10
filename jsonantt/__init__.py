"""jsonantt – Gantt chart generation from JSON descriptions.

Quick-start example::

    from jsonantt import load_chart, render_burn_chart, render_burn_table, render_chart, render_compare_chart, render_compare_table, render_table

    config = load_chart("project.json")
    actual = load_chart("project-actual.json")
    render_chart(config, "project.png")
    render_chart(config, "summary.png", render_depth=1)
    render_table(config, "tasks.png")
    render_compare_chart(config, actual, "compare.png")
    render_compare_table(config, actual, "compare-table.png")
    render_table(config, "milestones.png", milestones_only=True)
    render_table(config, "tasks-no-milestones.png", no_milestones=True)
    render_burn_chart(config, "burn.png", field="cost", period="month", group_by=0)
    render_burn_table(config, "burn-table.csv", field="cost", period="quarter", group_by=0)

Or from the command line::

    jsonantt project.json project.png
    jsonantt --renderdepth 2 project.json project.png
    jsonantt project.json compare.png --compare project-actual.json
    jsonantt --table project.json tasks.png
    jsonantt --table project.json compare-table.png --compare project-actual.json
    jsonantt --table --milestones-only project.json milestones.png
    jsonantt --table --no-milestones project.json tasks-no-milestones.png
"""
from .parser import load_chart, parse_chart
from .renderer import render_burn_chart, render_burn_table, render_chart, render_compare_chart, render_compare_table, render_table

__all__ = [
    "load_chart",
    "parse_chart",
    "render_burn_chart",
    "render_burn_table",
    "render_chart",
    "render_compare_chart",
    "render_compare_table",
    "render_table",
]
__version__ = "0.1.0"
