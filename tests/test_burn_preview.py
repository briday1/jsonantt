"""The interactive preview annotates, but must never redraw, CLI artwork."""
import xml.etree.ElementTree as ET
from datetime import date
from copy import deepcopy

import matplotlib
import pytest

from jsonantt.parser import parse_chart
from jsonantt.renderer import render_burn_chart, render_burn_table, render_chart, render_table
from jsonantt.renderer import _burn_date_position


SOURCE = {'title': 'Budget', 'style': {
    'value_prefix': '$', 'value_scale': 'millions', 'value_decimals': 2,
    'row_band_color': '#eef2f6', 'grid_color': '#345678',
}, 'tasks': [
    {'name': 'Discovery', 'tasks': [
        {'name': 'Research', 'start': '2026-01-01', 'end': '2026-06-01', 'cost': 1250000},
    ]},
    {'name': 'Build', 'start': '2026-02-01', 'end': '2026-06-01', 'cost': 750000},
]}


def drawing(svg):
    root = ET.fromstring(svg)
    for node in root.iter():
        node.attrib.pop('id', None)
        if node.tag.endswith('}date'):
            node.text = ''
    return ET.tostring(root)


@pytest.mark.parametrize('day,expected', [
    (date(2026, 1, 1), 0), (date(2026, 2, 15), 0.5),
    (date(2026, 4, 1), 1), (date(2026, 7, 1), 2),
    (date(2025, 12, 31), None), (date(2026, 7, 2), None), (None, None),
])
def test_burn_date_position(day, expected):
    periods = [{'start': date(2026, 1, 1), 'end': date(2026, 4, 1)},
               {'start': date(2026, 4, 1), 'end': date(2026, 7, 1)}]
    assert _burn_date_position(periods, day) == expected


@pytest.mark.parametrize('mode', ['remaining', 'cumulative'])
def test_today_marker_preview_export_parity(tmp_path, monkeypatch, mode):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 2, 15)

    monkeypatch.setattr('jsonantt.renderer.date', FixedDate)
    source = deepcopy(SOURCE)
    source['style']['today_marker'] = True
    chart = parse_chart(source)
    with matplotlib.rc_context({'svg.hashsalt': 'today-parity'}):
        for interactive in (False, True):
            for extension in ('svg', 'png'):
                render_burn_chart(chart, str(tmp_path / f'{interactive}.{extension}'),
                                  display=mode, period='quarter', interactive=interactive, dpi=40)
    exported = (tmp_path / 'False.svg').read_text()
    assert 'chart-date-marker' in exported and 'Today' in exported
    assert drawing(exported) == drawing((tmp_path / 'True.svg').read_text())
    assert (tmp_path / 'True.png').read_bytes() == (tmp_path / 'False.png').read_bytes()
    for options in ({'date_line': date(2027, 1, 1)}, {'display': 'spend'}):
        render_burn_chart(chart, str(tmp_path / 'absent.svg'), **{'display': mode, **options})
        assert 'chart-date-marker' not in (tmp_path / 'absent.svg').read_text()
    source['style']['today_marker'] = False
    render_burn_chart(parse_chart(source), str(tmp_path / 'off.svg'), display=mode)
    assert 'chart-date-marker' not in (tmp_path / 'off.svg').read_text()


@pytest.mark.parametrize('mode', ['spend', 'remaining', 'cumulative', 'table'])
@pytest.mark.parametrize('group', ['total', 'leaf', '0'])
def test_preview_and_export_have_identical_drawing(tmp_path, mode, group):
    render = render_burn_table if mode == 'table' else render_burn_chart
    options = {} if mode == 'table' else {'display': mode}
    chart = parse_chart(SOURCE)
    with matplotlib.rc_context({'svg.hashsalt': 'preview-parity'}):
        for interactive in (False, True):
            render(chart, str(tmp_path / f'{interactive}.svg'), period='quarter',
                   group_by=group, interactive=interactive, **options)
            render(chart, str(tmp_path / f'{interactive}.png'), period='quarter',
                   group_by=group, interactive=interactive, dpi=40, **options)
    exported = (tmp_path / 'False.svg').read_text()
    preview = (tmp_path / 'True.svg').read_text()
    assert 'studio-series-' in preview
    assert 'studio-series-' not in exported
    assert drawing(preview) == drawing(exported)
    assert (tmp_path / 'True.png').read_bytes() == (tmp_path / 'False.png').read_bytes()


CHART_SOURCE = {'title': 'Delivery plan', 'style': {
    'number_milestones': True, 'rollup_milestones': True, 'show_arrows': True,
    'row_band_color': '#eef2f6', 'grid_color': '#345678',
    'table_columns': ['task', 'name', 'description', 'start', 'end', {'field': 'cost', 'total': True}],
}, 'tasks': [
    {'name': 'Discovery', 'tasks': [
        {'id': 'research', 'name': 'Research', 'description': 'A long description that should wrap onto multiple lines in a narrow table column.',
         'start': '2026-01-01', 'end': '2026-03-01', 'cost': 1250000},
        {'name': 'Gate', 'major_milestone': True, 'date': ['2026-03-01', '2026-04-01']},
    ]},
    {'id': 'build', 'name': 'Build', 'start': '2026-03-01', 'end': '2026-06-01', 'cost': 750000},
], 'arrows': [{'from': 'research', 'to': 'build', 'color': '#ac1234'}]}


@pytest.mark.parametrize('mode,options', [
    ('gantt', {}), ('gantt', {'render_depth': 1}),
    ('table', {}), ('table', {'render_depth': 1}),
    ('table', {'milestones_only': True}), ('table', {'no_milestones': True}),
])
def test_gantt_table_preview_drawing_is_identical(tmp_path, mode, options):
    render = render_chart if mode == 'gantt' else render_table
    chart = parse_chart(CHART_SOURCE)
    with matplotlib.rc_context({'svg.hashsalt': 'chart-preview-parity'}):
        for interactive in (False, True):
            for extension in ('svg', 'png'):
                render(chart, str(tmp_path / f'{interactive}.{extension}'), interactive=interactive, dpi=40, **options)
    exported = (tmp_path / 'False.svg').read_text()
    preview = (tmp_path / 'True.svg').read_text()
    assert 'studio-task-' in preview and 'studio-task-' not in exported
    assert drawing(preview) == drawing(exported)
    assert (tmp_path / 'True.png').read_bytes() == (tmp_path / 'False.png').read_bytes()
    if mode == 'gantt':
        assert ('studio-arrow-0--shape-' in preview) == (options.get('render_depth') != 1)
        if options.get('render_depth') == 1:
            assert 'studio-task-1.2--rolled-' in preview
    elif options.get('milestones_only'):
        assert 'studio-task-1.2--cell-' in preview
        assert 'studio-task-1.1--cell-' not in preview
    elif options.get('no_milestones'):
        assert 'studio-task-1.2--cell-' not in preview
