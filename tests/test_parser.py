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

    def test_milestone_list_uses_min_and_max_dates(self):
        t = Task(
            name="M",
            milestone=True,
            milestone_date=date(2024, 6, 15),
            milestone_dates=[date(2024, 6, 20), date(2024, 6, 15), date(2024, 6, 18)],
        )
        assert t.effective_start == date(2024, 6, 15)
        assert t.effective_end == date(2024, 6, 20)

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

    def test_unknown_task_fields_are_preserved(self):
        data = {
            "tasks": [
                {
                    "name": "Task A",
                    "start": "2024-01-01",
                    "end": "2024-01-31",
                    "cost": 1200,
                    "assignee": "Morgan",
                }
            ]
        }
        cfg = parse_chart(data)
        assert cfg.tasks[0].fields == {"cost": 1200, "assignee": "Morgan"}

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

    def test_nested_tasks_alias(self):
        data = {
            "tasks": [
                {
                    "name": "Parent",
                    "tasks": [
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

    def test_top_level_children_alias(self):
        data = {
            "children": [
                {"name": "Task A", "start": "2024-01-01", "end": "2024-01-31"}
            ]
        }
        cfg = parse_chart(data)
        assert len(cfg.tasks) == 1
        assert cfg.tasks[0].name == "Task A"

    def test_nested_tasks_and_children_are_combined(self):
        data = {
            "tasks": [
                {
                    "name": "Parent",
                    "tasks": [
                        {"name": "Child 1", "start": "2024-01-01", "end": "2024-01-05"}
                    ],
                    "children": [
                        {"name": "Child 2", "start": "2024-01-06", "end": "2024-01-10"}
                    ],
                }
            ]
        }
        cfg = parse_chart(data)
        assert [child.name for child in cfg.tasks[0].children] == ["Child 1", "Child 2"]

    def test_filename_only_task_entry_inlines_tasks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            child_path = os.path.join(temp_dir, "child.json")
            with open(child_path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "title": "Included Plan",
                        "style": {"width": 20},
                        "tasks": [
                            {"name": "Child 1", "start": "2024-01-01", "end": "2024-01-05"},
                            {"name": "Child 2", "start": "2024-01-06", "end": "2024-01-10"},
                        ],
                    },
                    fh,
                )

            parent_path = os.path.join(temp_dir, "parent.json")
            with open(parent_path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "tasks": [
                            {"filename": "child.json"},
                            {"name": "Local", "start": "2024-01-11", "end": "2024-01-12"},
                        ]
                    },
                    fh,
                )

            cfg = load_chart(parent_path)

        assert [task.name for task in cfg.tasks] == ["Child 1", "Child 2", "Local"]
        assert cfg.style.width == Style().width

    def test_task_filename_nests_included_tasks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            child_path = os.path.join(temp_dir, "child.json")
            with open(child_path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "dateformat": "%d/%m/%Y",
                        "tasks": [
                            {"name": "Child 1", "start": "01/02/2024", "end": "03/02/2024"},
                            {"name": "Child 2", "start": "04/02/2024", "end": "08/02/2024"},
                        ],
                    },
                    fh,
                )

            parent_path = os.path.join(temp_dir, "parent.json")
            with open(parent_path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "tasks": [
                            {
                                "name": "Program",
                                "filename": "child.json",
                                "children": [
                                    {"name": "Local", "start": "2024-02-09", "end": "2024-02-10"}
                                ],
                            }
                        ]
                    },
                    fh,
                )

            cfg = load_chart(parent_path)

        parent = cfg.tasks[0]
        assert parent.name == "Program"
        assert [child.name for child in parent.children] == ["Child 1", "Child 2", "Local"]
        assert parent.children[0].start == date(2024, 2, 1)
        assert parent.children[1].end == date(2024, 2, 8)

    def test_filename_include_cycle_raises(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            a_path = os.path.join(temp_dir, "a.json")
            b_path = os.path.join(temp_dir, "b.json")

            with open(a_path, "w", encoding="utf-8") as fh:
                json.dump({"tasks": [{"filename": "b.json"}]}, fh)

            with open(b_path, "w", encoding="utf-8") as fh:
                json.dump({"tasks": [{"filename": "a.json"}]}, fh)

            with pytest.raises(ValueError, match="Circular filename reference"):
                load_chart(a_path)

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
        assert t.milestone_dates == [date(2024, 7, 1)]
        assert t.color == "#FF0000"

    def test_major_milestone_implies_milestone(self):
        data = {
            "tasks": [
                {"name": "Executive Gate", "major_milestone": True, "date": "2024-07-01"}
            ]
        }
        cfg = parse_chart(data)
        t = cfg.tasks[0]
        assert t.milestone is True
        assert t.major_milestone is True
        assert t.milestone_dates == [date(2024, 7, 1)]

    def test_milestone_date_list_parsed(self):
        data = {
            "tasks": [
                {
                    "name": "Go live",
                    "milestone": True,
                    "date": ["2024-07-01", "2024-07-15", "2024-08-01"],
                }
            ]
        }
        cfg = parse_chart(data)
        t = cfg.tasks[0]
        assert t.milestone is True
        assert t.milestone_date == date(2024, 7, 1)
        assert t.milestone_dates == [date(2024, 7, 1), date(2024, 7, 15), date(2024, 8, 1)]

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
            "style": {"width": 20, "font_size": 12, "indent_size": 4, "number_tasks": False, "table_colorize": False, "table_show_markers": False, "milestone_color": "#FFFF00", "milestone_edge_color": "#222222", "milestone_marker": "o", "rollup_milestones": True, "rollup_major_milestones_only": True, "number_milestones": True, "major_milestone_color": "#C0504D", "major_milestone_edge_color": "#7F3128", "major_milestone_marker": "s", "major_milestone_size": 18, "subtask_lightening_pct": 20, "table_columns": ["task", "name", {"field": "cost", "title": "Cost"}]},
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
        assert cfg.style.milestone_edge_color == "#222222"
        assert cfg.style.milestone_marker == "o"
        assert cfg.style.rollup_milestones is True
        assert cfg.style.rollup_major_milestones_only is True
        assert cfg.style.number_milestones is True
        assert cfg.style.major_milestone_color == "#C0504D"
        assert cfg.style.major_milestone_edge_color == "#7F3128"
        assert cfg.style.major_milestone_marker == "s"
        assert cfg.style.major_milestone_size == 18
        assert cfg.style.subtask_lightening_pct == 20
        assert cfg.style.table_columns == ["task", "name", {"field": "cost", "title": "Cost"}]

    def test_task_edge_color_override_parsed(self):
        data = {
            "tasks": [
                {"name": "Go live", "milestone": True, "date": "2024-07-01", "edge_color": "#111111"}
            ]
        }
        cfg = parse_chart(data)
        assert cfg.tasks[0].edge_color == "#111111"

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
        assert milestone.milestone_dates == [date(2024, 1, 10)]


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

    def test_example_chained_milestones_json(self):
        """Smoke-test the bundled chained-milestones.json example."""
        here = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(here, "examples", "chained-milestones.json")
        if os.path.exists(path):
            cfg = load_chart(path)
            assert cfg.tasks
            assert cfg.tasks[0].children

    def test_example_composed_plan_json(self):
        """Smoke-test the bundled composed-plan.json example."""
        here = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(here, "examples", "composed-plan.json")
        if os.path.exists(path):
            cfg = load_chart(path)
            assert cfg.tasks
