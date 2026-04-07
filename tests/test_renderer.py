"""Tests for jsonantt.renderer."""
from __future__ import annotations

import os
import tempfile
from datetime import date

import pytest

from jsonantt.models import ChartConfig, Style, Task
from jsonantt.parser import parse_chart
from jsonantt.renderer import (
    _compute_chart_label_layout,
    _compare_row_label_text,
    _darken,
    _flatten,
    _format_compare_offset,
    _lighten,
    _milestone_color,
    _milestone_marker,
    _prepare_compare_rows,
    _row_label_text,
    _row_table_number,
    render_chart,
    render_compare_chart,
    render_compare_table,
    render_table,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_config() -> ChartConfig:
    return parse_chart(
        {
            "title": "Test Chart",
            "tasks": [
                {"name": "Task A", "start": "2024-01-01", "end": "2024-01-31"},
                {"name": "Task B", "start": "2024-02-01", "end": "2024-02-29"},
            ],
        }
    )


def _config_with_children() -> ChartConfig:
    return parse_chart(
        {
            "tasks": [
                {
                    "name": "Phase 1",
                    "description": "Plan and sequence the first delivery wave.",
                    "children": [
                        {"name": "Sub A", "description": "Define scope for the first track.", "start": "2024-01-01", "end": "2024-01-15"},
                        {"name": "Sub B", "description": "Resolve staffing and sequencing.", "start": "2024-01-10", "end": "2024-01-31"},
                    ],
                },
                {
                    "name": "Milestone",
                    "description": "Decision gate for the release plan.",
                    "milestone": True,
                    "date": "2024-02-01",
                },
            ]
        }
    )


def _planned_compare_config() -> ChartConfig:
    return parse_chart(
        {
            "title": "Planned",
            "tasks": [
                {"id": "design", "name": "Design", "description": "Baseline design window.", "start": "2024-01-01", "end": "2024-01-10"},
                {"id": "build", "name": "Build", "description": "Baseline build window.", "start": "2024-01-11", "end": "2024-01-20"},
                {"id": "release", "name": "Release", "description": "Go/no-go checkpoint.", "milestone": True, "date": "2024-01-21"},
            ],
        }
    )


def _actual_compare_config() -> ChartConfig:
    return parse_chart(
        {
            "title": "Actual",
            "tasks": [
                {"id": "design", "name": "Design", "description": "Design finished on plan.", "start": "2024-01-01", "end": "2024-01-12"},
                {"id": "release", "name": "Release", "description": "Gate slipped by one day.", "milestone": True, "date": "2024-01-22"},
                {"id": "hardening", "name": "Hardening", "description": "Unplanned stabilization task.", "start": "2024-01-23", "end": "2024-01-29"},
            ],
        }
    )


# ---------------------------------------------------------------------------
# _flatten
# ---------------------------------------------------------------------------

class TestFlatten:
    def test_flat_tasks_order(self):
        cfg = _simple_config()
        rows = _flatten(cfg.tasks, cfg.style)
        assert len(rows) == 2
        assert rows[0].task.name == "Task A"
        assert rows[1].task.name == "Task B"

    def test_children_follow_parent(self):
        cfg = _config_with_children()
        rows = _flatten(cfg.tasks, cfg.style)
        names = [r.task.name for r in rows]
        # Phase 1 first, then its children, then Milestone
        assert names[0] == "Phase 1"
        assert names[1] == "Sub A"
        assert names[2] == "Sub B"
        assert names[3] == "Milestone"

    def test_depth_assigned(self):
        cfg = _config_with_children()
        rows = _flatten(cfg.tasks, cfg.style)
        assert rows[0].depth == 0   # Phase 1
        assert rows[1].depth == 1   # Sub A
        assert rows[2].depth == 1   # Sub B
        assert rows[3].depth == 0   # Milestone

    def test_row_index_sequential(self):
        cfg = _config_with_children()
        rows = _flatten(cfg.tasks, cfg.style)
        for i, row in enumerate(rows):
            assert row.row_index == i

    def test_color_from_palette(self):
        cfg = _simple_config()
        rows = _flatten(cfg.tasks, cfg.style)
        for row in rows:
            assert row.color.startswith("#")
            assert len(row.color) == 7

    def test_explicit_color_respected(self):
        cfg = parse_chart(
            {
                "tasks": [
                    {"name": "Colored", "start": "2024-01-01", "end": "2024-01-31",
                     "color": "#ABCDEF"}
                ]
            }
        )
        rows = _flatten(cfg.tasks, cfg.style)
        assert rows[0].color == "#ABCDEF"

    def test_child_inherits_parent_color(self):
        cfg = parse_chart(
            {
                "tasks": [
                    {
                        "name": "Parent",
                        "color": "#112233",
                        "children": [
                            {"name": "Child", "start": "2024-01-01", "end": "2024-01-10"}
                        ],
                    }
                ]
            }
        )
        rows = _flatten(cfg.tasks, cfg.style)
        parent_color = rows[0].color
        child_color = rows[1].color
        assert parent_color == "#112233"
        assert child_color == "#112233"

    def test_child_inherited_color_lightens_when_configured(self):
        cfg = parse_chart(
            {
                "style": {"subtask_lightening_pct": 20},
                "tasks": [
                    {
                        "name": "Parent",
                        "color": "#112233",
                        "children": [
                            {"name": "Child", "start": "2024-01-01", "end": "2024-01-10"}
                        ],
                    }
                ]
            }
        )
        rows = _flatten(cfg.tasks, cfg.style)
        assert rows[0].color == "#112233"
        assert rows[1].color == _lighten("#112233", 0.20)

    def test_nested_inherited_color_lightens_recursively(self):
        cfg = parse_chart(
            {
                "style": {"subtask_lightening_pct": 20},
                "tasks": [
                    {
                        "name": "Parent",
                        "color": "#112233",
                        "children": [
                            {
                                "name": "Child",
                                "children": [
                                    {"name": "Grandchild", "start": "2024-01-01", "end": "2024-01-10"}
                                ],
                            }
                        ],
                    }
                ]
            }
        )
        rows = _flatten(cfg.tasks, cfg.style)
        assert rows[1].color == _lighten("#112233", 0.20)
        assert rows[2].color == _lighten(rows[1].color, 0.20)

    def test_explicit_child_color_does_not_lighten(self):
        cfg = parse_chart(
            {
                "style": {"subtask_lightening_pct": 20},
                "tasks": [
                    {
                        "name": "Parent",
                        "color": "#112233",
                        "children": [
                            {"name": "Child", "color": "#ABCDEF", "start": "2024-01-01", "end": "2024-01-10"}
                        ],
                    }
                ]
            }
        )
        rows = _flatten(cfg.tasks, cfg.style)
        assert rows[1].color == "#ABCDEF"

    def test_default_milestone_color_is_yellow(self):
        cfg = parse_chart({"tasks": [{"name": "M", "milestone": True, "date": "2024-01-01"}]})
        assert cfg.style.milestone_color == "#FFD700"

    def test_default_milestone_marker_is_diamond(self):
        cfg = parse_chart({"tasks": [{"name": "M", "milestone": True, "date": "2024-01-01"}]})
        assert cfg.style.milestone_marker == "D"

    def test_milestone_uses_style_color_not_inherited_parent_color(self):
        cfg = parse_chart(
            {
                "tasks": [
                    {
                        "name": "Parent",
                        "color": "#112233",
                        "children": [
                            {"name": "Release", "milestone": True, "date": "2024-01-10"}
                        ],
                    }
                ]
            }
        )
        rows = _flatten(cfg.tasks, cfg.style)
        milestone_row = rows[1]
        assert milestone_row.color == "#112233"
        assert _milestone_color(milestone_row, cfg.style) == "#FFD700"

    def test_milestone_task_color_overrides_style_color(self):
        cfg = parse_chart(
            {
                "tasks": [
                    {"name": "Release", "milestone": True, "date": "2024-01-10", "color": "#00FF00"}
                ]
            }
        )
        row = _flatten(cfg.tasks, cfg.style)[0]
        assert _milestone_color(row, cfg.style) == "#00FF00"

    def test_milestone_task_marker_overrides_style_marker(self):
        cfg = parse_chart(
            {
                "style": {"milestone_marker": "o"},
                "tasks": [
                    {"name": "Release", "milestone": True, "date": "2024-01-10", "marker": "*"}
                ]
            }
        )
        row = _flatten(cfg.tasks, cfg.style)[0]
        assert _milestone_marker(row.task, cfg.style) == "*"

    def test_render_depth_zero_includes_all_levels(self):
        cfg = _config_with_children()
        rows = _flatten(cfg.tasks, cfg.style, max_depth=0)
        assert [row.task.name for row in rows] == ["Phase 1", "Sub A", "Sub B", "Milestone"]

    def test_render_depth_one_keeps_top_level_only(self):
        cfg = _config_with_children()
        rows = _flatten(cfg.tasks, cfg.style, max_depth=1)
        assert [row.task.name for row in rows] == ["Phase 1", "Milestone"]

    def test_render_depth_two_includes_one_child_level(self):
        cfg = parse_chart(
            {
                "tasks": [
                    {
                        "name": "Phase 1",
                        "children": [
                            {
                                "name": "Sub A",
                                "children": [
                                    {
                                        "name": "Leaf",
                                        "start": "2024-01-01",
                                        "end": "2024-01-05",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        )
        rows = _flatten(cfg.tasks, cfg.style, max_depth=2)
        assert [row.task.name for row in rows] == ["Phase 1", "Sub A"]

    def test_row_label_text_omits_numbers_when_disabled(self):
        cfg = _config_with_children()
        cfg.style.number_tasks = False
        rows = _flatten(cfg.tasks, cfg.style)
        assert _row_label_text(rows[0], cfg.style) == "Phase 1"
        assert _row_label_text(rows[1], cfg.style) == "Sub A"

    def test_row_table_number_keeps_numbering(self):
        cfg = _config_with_children()
        cfg.style.number_tasks = False
        rows = _flatten(cfg.tasks, cfg.style)
        assert _row_table_number(rows[0]) == "1."
        assert _row_table_number(rows[1]) == "1.1"


# ---------------------------------------------------------------------------
# _darken
# ---------------------------------------------------------------------------

class TestDarken:
    def test_darkens_colour(self):
        result = _darken("#FFFFFF", 0.5)
        assert result == "#7F7F7F"

    def test_zero_amount(self):
        result = _darken("#4472C4", 0.0)
        assert result == "#4472C4"

    def test_full_amount(self):
        result = _darken("#FFFFFF", 1.0)
        assert result == "#000000"

    def test_invalid_color_returns_original(self):
        result = _darken("not-a-color")
        assert result == "not-a-color"


# ---------------------------------------------------------------------------
# render_chart – output file tests
# ---------------------------------------------------------------------------

class TestRenderChart:
    def _render(self, config, suffix=".png"):
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            render_chart(config, path, dpi=72)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_simple_png(self):
        self._render(_simple_config(), ".png")

    def test_render_with_children_png(self):
        self._render(_config_with_children(), ".png")

    def test_render_pdf(self):
        self._render(_simple_config(), ".pdf")

    def test_render_no_tasks_raises(self):
        cfg = parse_chart({"tasks": []})
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            with pytest.raises(ValueError, match="No tasks"):
                render_chart(cfg, path)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_deeply_nested(self):
        cfg = parse_chart(
            {
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
                                                "name": "L4 leaf",
                                                "start": "2024-01-01",
                                                "end": "2024-01-31",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        )
        self._render(cfg, ".png")

    def test_render_milestone_only(self):
        cfg = parse_chart(
            {
                "tasks": [
                    {"name": "Launch", "milestone": True, "date": "2024-06-01"}
                ]
            }
        )
        self._render(cfg, ".png")

    def test_render_chart_rejects_negative_render_depth(self):
        cfg = _simple_config()
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            with pytest.raises(ValueError, match="render_depth must be >= 0"):
                render_chart(cfg, path, render_depth=-1)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_chart_with_limited_depth(self):
        self._render(_config_with_children(), ".png")
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            render_chart(_config_with_children(), path, dpi=72, render_depth=1)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_example_simple(self):
        here = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(here, "examples", "simple.json")
        if not os.path.exists(path):
            pytest.skip("examples/simple.json not found")
        from jsonantt.parser import load_chart
        cfg = load_chart(path)
        self._render(cfg, ".png")

    def test_long_label_layout_stays_reasonable_for_dependencies_example(self):
        here = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(here, "examples", "dependencies.json")
        if not os.path.exists(path):
            pytest.skip("examples/dependencies.json not found")
        from jsonantt.parser import load_chart

        cfg = load_chart(path)
        rows = _flatten(cfg.tasks, cfg.style)
        label_fraction, _, _ = _compute_chart_label_layout(rows, cfg.style, cfg.style.width, _row_label_text)

        assert label_fraction > 0.14
        assert label_fraction < 0.32

    def test_render_with_date_lines(self):
        cfg = parse_chart(
            {
                "tasks": [
                    {"name": "Task A", "start": "2024-01-01", "end": "2024-01-31"}
                ],
            }
        )
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            render_chart(cfg, path, dpi=72, date_line=date(2024, 1, 15), date_line_color="#C00000")
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)


class TestRenderTable:
    def _render(self, config, suffix=".png", render_depth=0):
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            render_table(config, path, dpi=72, render_depth=render_depth)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_table_png(self):
        self._render(_config_with_children(), ".png")

    def test_render_table_pdf(self):
        self._render(_config_with_children(), ".pdf")

    def test_render_table_csv(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            render_table(_config_with_children(), path, dpi=72)
            assert os.path.exists(path)
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
            assert "Task,Name,Description" in content
            assert "1.,Phase 1,Plan and sequence the first delivery wave." in content
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_table_with_limited_depth(self):
        self._render(_config_with_children(), ".png", render_depth=1)

    def test_render_table_without_colorize(self):
        cfg = _config_with_children()
        cfg.style.table_colorize = False
        self._render(cfg, ".png")

    def test_render_table_without_markers(self):
        cfg = _config_with_children()
        cfg.style.table_show_markers = False
        self._render(cfg, ".png")

    def test_render_table_without_colorize_hides_markers_too(self):
        cfg = _config_with_children()
        cfg.style.table_colorize = False
        cfg.style.table_show_markers = True
        self._render(cfg, ".png")

    def test_render_milestones_only_table(self):
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            render_table(_config_with_children(), path, dpi=72, milestones_only=True)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_milestones_only_table_raises_without_milestones(self):
        cfg = _simple_config()
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            with pytest.raises(ValueError, match="No milestones"):
                render_table(cfg, path, milestones_only=True)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_no_milestones_table(self):
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            render_table(_config_with_children(), path, dpi=72, no_milestones=True)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_no_milestones_table_raises_without_tasks(self):
        cfg = parse_chart({"tasks": [{"name": "Launch", "milestone": True, "date": "2024-06-01"}]})
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            with pytest.raises(ValueError, match="No non-milestone tasks"):
                render_table(cfg, path, no_milestones=True)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_table_rejects_negative_render_depth(self):
        cfg = _simple_config()
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            with pytest.raises(ValueError, match="render_depth must be >= 0"):
                render_table(cfg, path, render_depth=-1)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_example_complex(self):
        here = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(here, "examples", "complex.json")
        if not os.path.exists(path):
            pytest.skip("examples/complex.json not found")
        from jsonantt.parser import load_chart
        cfg = load_chart(path)
        self._render(cfg, ".png")


class TestRenderCompare:
    def _render_chart(self, planned, actual, suffix=".png"):
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            render_compare_chart(planned, actual, path, dpi=72)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def _render_table(self, planned, actual, suffix=".png"):
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            render_compare_table(planned, actual, path, dpi=72)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_compare_chart_png(self):
        self._render_chart(_planned_compare_config(), _actual_compare_config(), ".png")

    def test_render_compare_chart_with_date_lines(self):
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            render_compare_chart(
                _planned_compare_config(),
                _actual_compare_config(),
                path,
                dpi=72,
                date_line=date(2024, 1, 16),
                date_line_color="#C00000",
            )
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_compare_table_png(self):
        self._render_table(_planned_compare_config(), _actual_compare_config(), ".png")

    def test_render_compare_table_csv(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            render_compare_table(_planned_compare_config(), _actual_compare_config(), path, dpi=72)
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
            assert "Task,Name,Description,Offset" in content
            assert "1.,Design,Design finished on plan.,+2d" in content
            assert "2.,Build,Baseline build window.,Removed" in content
            assert "3.,Release,Gate slipped by one day.,+1d" in content
            assert "3.,(Hardening),Unplanned stabilization task.,Added" in content
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_render_compare_rejects_negative_render_depth(self):
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            with pytest.raises(ValueError, match="render_depth must be >= 0"):
                render_compare_chart(_planned_compare_config(), _actual_compare_config(), path, render_depth=-1)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_format_compare_offset_removed_and_added(self):
        planned = _planned_compare_config()
        actual = _actual_compare_config()
        rows = _prepare_compare_rows(planned, actual, 0)
        assert _format_compare_offset(rows[1]) == "Removed"
        assert _format_compare_offset(rows[3]) == "Added"

    def test_compare_label_text_parenthesizes_added_rows(self):
        planned = _planned_compare_config()
        actual = _actual_compare_config()
        rows = _prepare_compare_rows(planned, actual, 0)
        assert _compare_row_label_text(rows[3], planned.style) == "3.  (Hardening)"
