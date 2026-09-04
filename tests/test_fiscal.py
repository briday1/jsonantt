"""Tests for the fiscal-year time scale (``style.fiscal_year_start``)."""
from __future__ import annotations

from datetime import date, datetime

import matplotlib.dates as mdates
import pytest

from jsonantt.parser import parse_chart
from jsonantt.renderer import (
    _fiscal_quarter_info,
    _fiscal_style_start,
    _fiscal_year_info,
    _iter_ticks,
    _parse_fiscal_year_start,
    _snap_to_tick_end,
    _snap_to_tick_start,
    _tick_locator_fmt,
    render_chart,
)

FY_OCT = (10, 1)


class TestParseFiscalYearStart:
    def test_month_only_defaults_to_first(self):
        assert _parse_fiscal_year_start("10") == (10, 1)

    def test_month_day(self):
        assert _parse_fiscal_year_start("04-01") == (4, 1)
        assert _parse_fiscal_year_start("10-15") == (10, 15)

    def test_invalid_specs_raise(self):
        for spec in ("13-01", "00-01", "10-40", "oct", "", 10):
            with pytest.raises(ValueError, match="fiscal_year_start"):
                _parse_fiscal_year_start(spec)

    def test_style_helper_defaults_to_none(self):
        assert _fiscal_style_start(parse_chart({"tasks": []}).style) is None
        config = parse_chart({"style": {"fiscal_year_start": "10-01"}, "tasks": []})
        assert _fiscal_style_start(config.style) == FY_OCT


class TestFiscalCalendar:
    def test_year_named_after_ending_calendar_year(self):
        assert _fiscal_year_info(date(2025, 10, 1), FY_OCT) == (2026, date(2025, 10, 1))
        assert _fiscal_year_info(date(2026, 9, 30), FY_OCT) == (2026, date(2025, 10, 1))
        assert _fiscal_year_info(date(2025, 9, 30), FY_OCT) == (2025, date(2024, 10, 1))

    def test_quarters(self):
        assert _fiscal_quarter_info(date(2025, 10, 1), FY_OCT)[1] == 1
        assert _fiscal_quarter_info(date(2026, 1, 1), FY_OCT)[1] == 2
        assert _fiscal_quarter_info(date(2026, 4, 1), FY_OCT)[1] == 3
        assert _fiscal_quarter_info(date(2026, 7, 1), FY_OCT)[1] == 4

    def test_snap_start_quarter_and_year(self):
        assert _snap_to_tick_start(date(2025, 11, 5), "quarter", FY_OCT) == date(2025, 10, 1)
        assert _snap_to_tick_start(date(2026, 2, 5), "quarter", FY_OCT) == date(2026, 1, 1)
        assert _snap_to_tick_start(date(2025, 11, 5), "year", FY_OCT) == date(2025, 10, 1)
        assert _snap_to_tick_start(date(2025, 3, 1), "year", FY_OCT) == date(2024, 10, 1)

    def test_snap_end_quarter_and_year(self):
        assert _snap_to_tick_end(date(2025, 11, 5), "quarter", FY_OCT) == date(2026, 1, 1)
        assert _snap_to_tick_end(date(2025, 11, 5), "year", FY_OCT) == date(2026, 10, 1)
        # dates already on a boundary stay put
        assert _snap_to_tick_end(date(2025, 10, 1), "quarter", FY_OCT) == date(2025, 10, 1)

    def test_iter_ticks_uses_fiscal_quarters(self):
        ticks = list(_iter_ticks(datetime(2025, 1, 1), datetime(2027, 1, 1), "quarter", FY_OCT))[:5]
        assert [t.date() for t in ticks] == [
            date(2025, 1, 1),
            date(2025, 4, 1),
            date(2025, 7, 1),
            date(2025, 10, 1),
            date(2026, 1, 1),
        ]

    def test_without_fiscal_start_behavior_is_unchanged(self):
        assert _snap_to_tick_start(date(2025, 11, 5), "quarter") == date(2025, 10, 1)
        assert _snap_to_tick_start(date(2025, 11, 5), "quarter", None) == date(2025, 10, 1)


class TestFiscalTicks:
    def test_year_formatter_labels_fy(self):
        locator, fmt = _tick_locator_fmt("year", 400, FY_OCT)
        label = fmt(mdates.date2num(datetime(2025, 10, 1)))
        assert label == "FY26"

    def test_quarter_formatter_labels_fiscal_quarter(self):
        locator, fmt = _tick_locator_fmt("quarter", 400, FY_OCT)
        assert fmt(mdates.date2num(datetime(2025, 10, 1))) == "Q1 FY26"
        assert fmt(mdates.date2num(datetime(2026, 4, 1))) == "Q3 FY26"

    def test_calendar_formatter_is_unchanged(self):
        locator, fmt = _tick_locator_fmt("quarter", 400)
        assert fmt(mdates.date2num(datetime(2025, 10, 1))) == "Q4 2025"


class TestFiscalRendering:
    def test_render_chart_with_fiscal_year(self, tmp_path):
        config = parse_chart({
            "title": "FY plan",
            "style": {"fiscal_year_start": "10-01", "major_tick": "quarter", "minor_tick": "month"},
            "tasks": [
                {"name": "A", "start": "2025-09-01", "end": "2025-12-15"},
                {"name": "B", "start": "2026-01-05", "end": "2026-06-30"},
            ],
        })
        out = tmp_path / "fy.png"
        render_chart(config, str(out))
        assert out.stat().st_size > 0

    def test_render_chart_with_fiscal_year_tick(self, tmp_path):
        config = parse_chart({
            "style": {"fiscal_year_start": "04-01", "major_tick": "year", "minor_tick": "quarter"},
            "tasks": [{"name": "A", "start": "2024-01-01", "end": "2027-01-01"}],
        })
        out = tmp_path / "fy-year.png"
        render_chart(config, str(out))
        assert out.stat().st_size > 0

    def test_invalid_fiscal_start_surfaces_error(self, tmp_path):
        config = parse_chart({
            "style": {"fiscal_year_start": "13-40"},
            "tasks": [{"name": "A", "start": "2025-01-01", "end": "2025-06-01"}],
        })
        with pytest.raises(ValueError, match="fiscal_year_start"):
            render_chart(config, str(tmp_path / "bad.png"))
