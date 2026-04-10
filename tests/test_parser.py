"""Tests for jsonantt.parser and jsonantt.models."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date

import pytest

from jsonantt.models import ChartConfig, Style, Task
from jsonantt.parser import load_chart, parse_chart


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_file(data: dict) -> str:
    """Write *data* to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh)
    return path


# ---------------------------------------------------------------------------
# Task effective_start / effective_end
# ---------------------------------------------------------------------------

class TestTaskEffectiveDates:
    def test_leaf_with_explicit_dates(self):
        t = Task(name="T", start=date(2024, 1, 1), end=date(2024, 1, 31))
        assert t.effective_start == date(2024, 1, 1)
        assert t.effective_end == date(2024, 1, 31)

    def test_parent_infers_from_children(self):
        child1 = Task(name="C1", start=date(2024, 1, 5), end=date(2024, 1, 15))
        child2 = Task(name="C2", start=date(2024, 1, 10), end=date(2024, 1, 25))
        parent = Task(name="P", children=[child1, child2])

        assert parent.effective_start == date(2024, 1, 5)
        assert parent.effective_end == date(2024, 1, 25)

    def test_deeply_nested_inference(self):
        leaf = Task(name="leaf", start=date(2024, 3, 1), end=date(2024, 3, 31))
        mid = Task(name="mid", children=[leaf])
        root = Task(name="root", children=[mid])

        assert root.effective_start == date(2024, 3, 1)
        assert root.effective_end == date(2024, 3, 31)

    def test_parent_explicit_overrides_children(self):
        child = Task(name="C", start=date(2024, 1, 10), end=date(2024, 1, 20))
        parent = Task(name="P", start=date(2024, 1, 1), end=date(2024, 2, 28), children=[child])
        assert parent.effective_start == date(2024, 1, 1)
        assert parent.effective_end == date(2024, 2, 28)

    def test_no_dates_returns_none(self):
        t = Task(name="T")
        assert t.effective_start is None
        assert t.effective_end is None

    def test_milestone_returns_milestone_date(self):
        t = Task(name="M", milestone=True, milestone_date=date(2024, 6, 15))
        assert t.effective_start == date(2024, 6, 15)
        assert t.effective_end == date(2024, 6, 15)

    def test_is_parent_true_with_children(self):
        child = Task(name="C")
        parent = Task(name="P", children=[child])
        assert parent.is_parent is True

    def test_is_parent_false_without_children(self):
        t = Task(name="T")
        assert t.is_parent is False


# ---------------------------------------------------------------------------
# Parser: parse_chart
# ---------------------------------------------------------------------------

class TestParseChart:
    def test_minimal_chart(self):
        data = {"tasks": [{"name": "Task A", "start": "2024-01-01", "end": "2024-01-31"}]}
        cfg = parse_chart(data)
        assert isinstance(cfg, ChartConfig)
        assert len(cfg.tasks) == 1
        assert cfg.tasks[0].name == "Task A"
        assert cfg.tasks[0].start == date(2024, 1, 1)
        assert cfg.tasks[0].end == date(2024, 1, 31)

    def test_description_parsed(self):
        data = {
            "tasks": [
                {
                    "name": "Task A",
                    "description": "Detailed summary",
                    "start": "2024-01-01",
                    "end": "2024-01-31",
                }
            ]
        }
        cfg = parse_chart(data)
        assert cfg.tasks[0].description == "Detailed summary"

    def test_custom_date_format(self):
        data = {
            "dateformat": "%d/%m/%Y",
            "tasks": [{"name": "T", "start": "15/03/2024", "end": "30/03/2024"}],
        }
        cfg = parse_chart(data)
        assert cfg.tasks[0].start == date(2024, 3, 15)
        assert cfg.tasks[0].end == date(2024, 3, 30)

    def test_title_parsed(self):
        data = {"title": "My Chart", "tasks": []}
        cfg = parse_chart(data)
        assert cfg.title == "My Chart"

    def test_nested_children(self):
        data = {
            "tasks": [
                {
                    "name": "Parent",
                    "children": [
                        {"name": "Child 1", "start": "2024-01-01", "end": "2024-01-15"},
                        {"name": "Child 2", "start": "2024-01-10", "end": "2024-01-25"},
                    ],
                }
            ]
        }
        cfg = parse_chart(data)
        parent = cfg.tasks[0]
        assert len(parent.children) == 2
        assert parent.children[0].name == "Child 1"
        assert parent.effective_start == date(2024, 1, 1)
        assert parent.effective_end == date(2024, 1, 25)

    def test_deep_nesting(self):
        data = {
            "tasks": [
                {
                    "name": "L1",
                    "children": [
                        {
                            "name": "L2",
                            "children": [
                                {
                                    "name": "L3",
                                    "children": [
                                        {
                                            "name": "L4",
                                            "start": "2024-02-01",
                                            "end": "2024-02-28",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        cfg = parse_chart(data)
        l1 = cfg.tasks[0]
        assert l1.effective_start == date(2024, 2, 1)
        assert l1.effective_end == date(2024, 2, 28)

    def test_milestone_parsed(self):
        data = {
            "tasks": [
                {"name": "Go live", "milestone": True, "date": "2024-07-01", "color": "#FF0000"}
            ]
        }
        cfg = parse_chart(data)
        t = cfg.tasks[0]
        assert t.milestone is True
        assert t.milestone_date == date(2024, 7, 1)
        assert t.color == "#FF0000"

    def test_chart_start_end_parsed(self):
        data = {
            "start": "2024-01-01",
            "end": "2024-12-31",
            "tasks": [],
        }
        cfg = parse_chart(data)
        assert cfg.start == date(2024, 1, 1)
        assert cfg.end == date(2024, 12, 31)

    def test_style_parsed(self):
        data = {
            "style": {"width": 20, "font_size": 12, "indent_size": 4, "number_tasks": False, "table_colorize": False, "table_show_markers": False, "milestone_color": "#FFFF00", "milestone_marker": "o", "subtask_lightening_pct": 20},
            "tasks": [],
        }
        cfg = parse_chart(data)
        assert cfg.style.width == 20
        assert cfg.style.font_size == 12
        assert cfg.style.indent_size == 4
        assert cfg.style.number_tasks is False
        assert cfg.style.table_colorize is False
        assert cfg.style.table_show_markers is False
        assert cfg.style.milestone_color == "#FFFF00"
        assert cfg.style.milestone_marker == "o"
        assert cfg.style.subtask_lightening_pct == 20

    def test_task_marker_override_parsed(self):
        data = {
            "tasks": [
                {"name": "Go live", "milestone": True, "date": "2024-07-01", "marker": "*"}
            ]
        }
        cfg = parse_chart(data)
        assert cfg.tasks[0].marker == "*"

    def test_not_before_resolves_idless_child_milestone(self):
        data = {
            "tasks": [
                {
                    "name": "Parent",
                    "id": "prom0",
                    "start": "2024-01-01",
                    "end": "2024-01-10",
                    "children": [
                        {
                            "name": "Child milestone",
                            "milestone": True,
                            "not_before": "prom0",
                        }
                    ],
                }
            ]
        }

        cfg = parse_chart(data)
        milestone = cfg.tasks[0].children[0]

        assert milestone.start == date(2024, 1, 10)
        assert milestone.milestone_date == date(2024, 1, 10)


    def test_shorthand_string_task(self):
        data = {"tasks": ["Quick task"]}
        cfg = parse_chart(data)
        assert cfg.tasks[0].name == "Quick task"


# ---------------------------------------------------------------------------
# Parser: load_chart (file I/O)
# ---------------------------------------------------------------------------

class TestLoadChart:
    def test_load_from_file(self):
        data = {
            "title": "File test",
            "tasks": [{"name": "T", "start": "2024-01-01", "end": "2024-01-07"}],
        }
        path = _json_file(data)
        try:
            cfg = load_chart(path)
            assert cfg.title == "File test"
            assert len(cfg.tasks) == 1
        finally:
            os.unlink(path)

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            load_chart("/tmp/does_not_exist_xyzzy.json")

    def test_example_simple_json(self):
        """Smoke-test the bundled simple.json example."""
        here = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(here, "examples", "simple.json")
        if os.path.exists(path):
            cfg = load_chart(path)
            assert cfg.title
            assert cfg.tasks

    def test_example_complex_json(self):
        """Smoke-test the bundled complex.json example."""
        here = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(here, "examples", "complex.json")
        if os.path.exists(path):
            cfg = load_chart(path)
            assert cfg.tasks
