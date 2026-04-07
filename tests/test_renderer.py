"""Tests for jsonantt.renderer."""
from __future__ import annotations

import os
import tempfile
from datetime import date

import pytest

from jsonantt.models import ChartConfig, Style, Task
from jsonantt.parser import parse_chart
from jsonantt.renderer import _darken, _flatten, _row_label_text, render_chart


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
                    "children": [
                        {"name": "Sub A", "start": "2024-01-01", "end": "2024-01-15"},
                        {"name": "Sub B", "start": "2024-01-10", "end": "2024-01-31"},
                    ],
                },
                {
                    "name": "Milestone",
                    "milestone": True,
                    "date": "2024-02-01",
                },
            ]
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

    def test_render_example_complex(self):
        here = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(here, "examples", "complex.json")
        if not os.path.exists(path):
            pytest.skip("examples/complex.json not found")
        from jsonantt.parser import load_chart
        cfg = load_chart(path)
        self._render(cfg, ".png")
