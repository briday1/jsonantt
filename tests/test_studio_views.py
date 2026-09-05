"""Browser view options and milestone labels must survive rendering/export."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from jsonantt.parser import parse_chart
from jsonantt.renderer import _prepare_rows

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not shutil.which('node'), reason='Node is required for browser tests')


def run_js(script, data=None):
    result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT,
                            input=json.dumps(data), text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def test_burn_availability_uses_only_numeric_custom_fields():
    result = run_js("""
        import { parseChart } from './jsonantt/web/model.mjs';
        import { availableBurnFields } from './jsonantt/web/burn.mjs';
        const base = {name:'M1', description:'2026 release', id:'123', start:'2026-01-01',
                      duration:'1m', marker_size:14, color:'#123456'};
        console.log(JSON.stringify([
            availableBurnFields(parseChart({tasks:[base]})),
            availableBurnFields(parseChart({tasks:[{...base, cost:null, effort:'unknown'}]})),
            availableBurnFields(parseChart({tasks:[{name:'Parent', tasks:[{...base, cost:0}]}]})),
            availableBurnFields(parseChart({tasks:[{...base, cost:'$1,200', effort:30}]})),
            availableBurnFields(parseChart({tasks:[{name:'Gate', milestone:true, date:'2026-01-01', cost:50}]})),
        ]));
    """)
    assert result == [[], [], ['cost'], ['cost', 'effort'], ['cost']]


def test_settings_cover_every_python_style_field_with_matching_defaults():
    from dataclasses import asdict
    from jsonantt.models import Style
    actual = run_js("""
        import {STYLE_OPTIONS} from './jsonantt/web/style-options.mjs';
        console.log(JSON.stringify(Object.fromEntries(STYLE_OPTIONS.map(option => [option.key, option.default]))));
    """)
    assert actual == asdict(Style())
    assert asdict(parse_chart({'style': actual}).style) == actual


@pytest.mark.parametrize('amount', [0, 25, 50, 100])
def test_inherited_colours_match_cli_at_each_depth(amount):
    source = {'style': {'subtask_lightening_pct': amount}, 'tasks': [
        {'name': 'Explicit', 'color': '#223344', 'tasks': [
            {'name': 'Child', 'tasks': [{'name': 'Grandchild', 'start': '2026-01-01'}]},
            {'name': 'Override', 'color': '#654321', 'tasks': [{'name': 'Next', 'start': '2026-01-01'}]},
        ]},
        {'name': 'Palette', 'start': '2026-01-01'},
    ]}
    actual = run_js("""
        import {parseChart} from './jsonantt/web/model.mjs';
        import {readFileSync} from 'node:fs';
        const chart = parseChart(JSON.parse(readFileSync(0, 'utf8')));
        console.log(JSON.stringify(chart.flat.map(task => task.resolvedColor.toUpperCase())));
    """, source)
    assert actual == [row.color.upper() for row in _prepare_rows(parse_chart(source), 0)]


def test_structured_columns_are_not_split_at_object_commas():
    actual = run_js("""
        import {parseArraySetting} from './jsonantt/web/style-options.mjs';
        console.log(JSON.stringify(parseArraySetting('["name", {"field":"cost", "rollup":"sum", "total":true}]', 'columns')));
    """)
    assert actual == ['name', {'field': 'cost', 'rollup': 'sum', 'total': True}]


@pytest.mark.parametrize('enabled', [False, True])
def test_source_display_options_reach_renderer(tmp_path, monkeypatch, enabled):
    from datetime import date
    from jsonantt import renderer
    arrows, dates = [], []
    monkeypatch.setattr(renderer, '_draw_arrow', lambda *args: arrows.append(args))
    monkeypatch.setattr(renderer, '_draw_date_line', lambda ax, value, color: dates.append(value))
    chart = parse_chart({
        'style': {'show_arrows': enabled, 'today_marker': enabled},
        'tasks': [
            {'name': 'First', 'id': 'a', 'start': '2026-01-01', 'end': '2026-02-01'},
            {'name': 'Second', 'id': 'b', 'start': '2026-02-01', 'end': '2026-03-01'},
        ],
        'arrows': [{'from': 'a', 'to': 'b'}],
    })
    renderer.render_chart(chart, str(tmp_path / 'chart.png'), dpi=40)
    assert len(arrows) == int(enabled)
    assert dates == [date.today() if enabled else None]
    dates.clear()
    renderer.render_chart(chart, str(tmp_path / 'override.png'), dpi=40, date_line=date(2026, 2, 1))
    assert dates == [date(2026, 2, 1)]


def test_cli_uses_source_depth_and_allows_override(tmp_path):
    import csv
    from jsonantt.cli import main
    source = tmp_path / 'source.json'
    source.write_text(json.dumps({'style': {'render_depth': 1}, 'tasks': [
        {'name': 'Parent', 'tasks': [{'name': 'Child', 'start': '2026-01-01'}]},
    ]}))
    target = tmp_path / 'out.csv'
    assert main([str(source), str(target), '--table']) == 0
    with target.open() as file:
        assert [row['Name'] for row in csv.DictReader(file)] == ['Parent']
    assert main([str(source), str(target), '--table', '--renderdepth', '0']) == 0
    with target.open() as file:
        assert [row['Name'] for row in csv.DictReader(file)] == ['Parent', 'Child']


@pytest.mark.parametrize('depth', [0, 1, 2])
@pytest.mark.parametrize('rollup', [False, True])
def test_milestone_numbers_match_renderer(tmp_path, depth, rollup):
    import matplotlib
    from jsonantt.renderer import render_chart
    from tests.test_burn_preview import drawing
    chart = parse_chart({
        'style': {'number_milestones': True, 'rollup_milestones': rollup},
        'tasks': [
            {'name': 'Parent', 'tasks': [
                {'name': 'Nested gate', 'milestone': True, 'date': '2026-01-01'},
            ]},
            {'name': 'Final gate', 'milestone': True, 'date': '2026-02-01'},
        ],
    })
    with matplotlib.rc_context({'svg.hashsalt': 'milestone-parity'}):
        for interactive in (False, True):
            render_chart(chart, str(tmp_path / f'{interactive}.svg'), render_depth=depth, interactive=interactive)
    assert drawing((tmp_path / 'True.svg').read_text()) == drawing((tmp_path / 'False.svg').read_text())


def test_marker_labels_and_major_marker_size(tmp_path, monkeypatch):
    from matplotlib.axes import Axes
    from jsonantt.renderer import render_chart, render_table
    sizes = []
    original = Axes.plot

    def capture(self, *args, **kwargs):
        if 'markersize' in kwargs:
            sizes.append(kwargs['markersize'])
            assert kwargs['markerfacecolor'] == '#123456'
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Axes, 'plot', capture)
    chart = parse_chart({'style': {'number_milestones': True, 'major_milestone_size': 20, 'major_milestone_color': '#123456'},
                         'tasks': [{'name': 'Gate', 'major_milestone': True, 'date': '2026-01-01'}]})
    for render in (render_chart, render_table):
        render(chart, str(tmp_path / 'marker.svg'), interactive=True)
        assert 'M1' in (tmp_path / 'marker.svg').read_text()
    assert sizes == [20, 13]


def test_export_forwards_all_table_filters_and_rejects_old_server():
    result = run_js("""
        import { exportChart } from './jsonantt/web/export.mjs';
        const requests = [];
        globalThis.fetch = async (url, options) => {
            const params = new URL(url, 'http://localhost').searchParams;
            requests.push({params:Object.fromEntries(params), body:options.body});
            return new Response('rendered', {headers:{'X-Jsonantt-Table-Filter':params.get('table_filter')}});
        };
        for (const format of ['png','svg','csv']) for (const tableFilter of ['all','milestones','tasks']) {
            await exportChart('{"tasks":[]}', {mode:'table', format, dpi:300, renderDepth:2, tableFilter});
        }
        globalThis.fetch = async () => new Response('unfiltered');
        let error = '';
        try { await exportChart('{}', {mode:'table', format:'png', tableFilter:'milestones'}); }
        catch (e) { error = e.message; }
        console.log(JSON.stringify({requests, error}));
    """)
    assert len(result['requests']) == 9
    for request in result['requests']:
        assert request['body'] == '{"tasks":[]}'
        assert request['params']['mode'] == 'table'
        assert request['params']['dpi'] == '300'
        assert request['params']['render_depth'] == '2'
    assert [r['params']['table_filter'] for r in result['requests']] == ['all', 'milestones', 'tasks'] * 3
    assert 'Restart jsonantt serve' in result['error']


def test_burnup_and_burndown_values_and_export_modes():
    result = run_js("""
        import {burnLineValues, burnDisplayForMode} from './jsonantt/web/burn.mjs';
        import {exportChart} from './jsonantt/web/export.mjs';
        const requests = [];
        globalThis.fetch = async url => {requests.push(Object.fromEntries(new URL(url, 'http://localhost').searchParams)); return new Response('image');};
        for (const mode of ['burn','burndown','burnup']) await exportChart('{}', {mode,format:'svg',burn:{period:'quarter',group:'total',factor:2}});
        console.log(JSON.stringify({requests,
            displays:['burn','burndown','burnup'].map(burnDisplayForMode),
            down:burnLineValues([10,20,30], 'remaining'), up:burnLineValues([10,20,30], 'cumulative'),
            zero:burnLineValues([0,0], 'cumulative'), refund:burnLineValues([100,-20,30], 'cumulative')}));
    """)
    assert result['displays'] == ['spend', 'remaining', 'cumulative']
    assert result['down'] == [60, 50, 30, 0]
    assert result['up'] == [0, 10, 30, 60]
    assert result['zero'] == [0, 0, 0]
    assert result['refund'] == [0, 100, 80, 110]
    assert [request['mode'] for request in result['requests']] == ['burn', 'burndown', 'burnup']
    assert [request['burn_display'] for request in result['requests']] == result['displays']
    assert all(request['burn_period'] == 'quarter' and request['burn_factor'] == '2' for request in result['requests'])


@pytest.mark.parametrize('display,expected', [('remaining', [191, 91, 0]), ('cumulative', [0, 100, 191])])
def test_renderer_cumulative_line_values(tmp_path, monkeypatch, display, expected):
    from matplotlib.axes import Axes
    from jsonantt.renderer import render_burn_chart
    plotted = []
    original = Axes.plot
    def capture(ax, xs, ys, *args, **kwargs):
        plotted.append(list(ys))
        return original(ax, xs, ys, *args, **kwargs)
    monkeypatch.setattr(Axes, 'plot', capture)
    chart = parse_chart({'tasks': [
        {'name': 'Work', 'start': '2026-01-01', 'end': '2026-07-01', 'cost': 181},
        {'name': 'Gate', 'date': '2026-03-15', 'milestone': True, 'cost': 10},
    ]})
    render_burn_chart(chart, str(tmp_path / 'chart.png'), dpi=40, period='quarter', group_by='total', display=display)
    assert plotted[0] == pytest.approx(expected)


def test_inspector_bounds_include_the_entire_panel():
    actual = run_js("""
        import {clampInspectorPosition as clamp} from './jsonantt/web/inspector-drag.mjs';
        const bounds={width:800,height:600}, size={width:268,height:300};
        console.log(JSON.stringify([
            clamp({x:-999,y:-999},bounds,size), clamp({x:999,y:999},bounds,size),
            clamp({x:100,y:80},bounds,size), clamp({x:999,y:999},{width:280,height:310},size),
        ]));
    """)
    assert actual == [{'x': 12, 'y': 12}, {'x': 520, 'y': 288}, {'x': 100, 'y': 80}, {'x': 6, 'y': 5}]


def test_burnup_budget_is_full_task_amount_even_with_cropped_dates(tmp_path, monkeypatch):
    from matplotlib.axes import Axes
    from jsonantt.renderer import render_burn_chart
    budgets = []
    original = Axes.hlines
    def capture(ax, value, start, end, **kwargs):
        budgets.append((value, kwargs['colors'], kwargs['linestyles']))
        return original(ax, value, start, end, **kwargs)
    monkeypatch.setattr(Axes, 'hlines', capture)
    source = {'start': '2026-04-01', 'end': '2026-07-01', 'tasks': [
        {'name': 'A', 'color': '#123456', 'start': '2026-01-01', 'end': '2026-07-01', 'cost': 181},
        {'name': 'B', 'color': '#654321', 'start': '2026-01-01', 'end': '2026-07-01', 'cost': 362},
    ]}
    render_burn_chart(parse_chart(source), str(tmp_path / 'chart.png'), dpi=40,
                      period='quarter', group_by='leaf', display='cumulative', display_factor=2)
    assert budgets == [(362, '#123456', ':'), (724, '#654321', ':')]
    actual = run_js("""
        import {parseChart} from './jsonantt/web/model.mjs';
        import {buildBurn} from './jsonantt/web/burn.mjs';
        import {readFileSync} from 'node:fs';
        const chart = parseChart(JSON.parse(readFileSync(0, 'utf8')));
        console.log(JSON.stringify(buildBurn(chart, {period:'quarter',group:'leaf',factor:2}).series.map(series=>series.budget)));
    """, source)
    assert actual == [362, 724]
