"""Currency/unit display is optional and never changes numeric calculations."""
from dataclasses import asdict
from decimal import Decimal
import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from jsonantt.models import Style
from jsonantt.parser import parse_chart
from jsonantt.renderer import _build_burn_matrix, render_burn_chart, render_burn_table, render_table
from jsonantt.value_format import format_value, value_unit_label

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('scale,expected', [('units', '$1,250,000.00'), ('thousands', '$1,250.00K'), ('millions', '$1.25M'), ('billions', '$0.00B')])
def test_scale_and_currency(scale, expected):
    style = Style(value_prefix='$', value_scale=scale, value_decimals=2)
    assert format_value(1250000, style, 'cost') == expected
    assert format_value(1250000, style, 'effort') is None


def test_defaults_and_already_scaled_amounts():
    assert format_value(1250, Style(), 'cost') is None
    style = Style(value_prefix='$', value_suffix='million')
    assert format_value(1.25, style, 'cost') == '$1.25 million'
    assert value_unit_label(style, 'cost') == '$ million'
    assert format_value(Decimal('-0.0001'), style, 'cost') == '$0 million'
    assert format_value(1250000, Style(value_scale='millions'), 'cost', {'prefix':'$', 'suffix':''}) == '$1.25M'
    assert format_value(123, Style(value_prefix='$', value_fields=[]), 'id') is None


@pytest.mark.parametrize('settings', [
    {'value_scale':'wrong'}, {'value_decimals':-1}, {'value_decimals':1.5},
    {'value_decimals':True}, {'value_fields':'cost'}, {'value_fields':['']}, {'value_prefix':42},
])
def test_invalid_options_fail_clearly(settings):
    with pytest.raises(ValueError, match='value_'):
        parse_chart({'style': settings, 'tasks': []})


@pytest.mark.skipif(not shutil.which('node'), reason='Node required')
def test_browser_formatter_matches_python():
    cases = [
        {'amount': value, 'style': asdict(Style(value_prefix='$', value_scale=scale, value_decimals=places))}
        for value in [0, 1.005, 2.675, -0.005, 1250000, -1355000]
        for scale in ['units', 'thousands', 'millions'] for places in [None, 0, 2]
    ]
    script = """
      import {readFileSync} from 'node:fs';
      import {formatValue} from './jsonantt/web/value-format.mjs';
      const cases=JSON.parse(readFileSync(0,'utf8'));
      console.log(JSON.stringify(cases.map(({amount,style})=>formatValue(amount,style,'cost'))));
    """
    result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT,
                            input=json.dumps(cases), text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == [format_value(case['amount'], Style(**case['style']), 'cost') for case in cases]


SOURCE = {'tasks': [
    {'name': 'A', 'start': '2026-01-01', 'end': '2026-04-01', 'cost': 1250000, 'effort': 10},
    {'name': 'B', 'start': '2026-01-01', 'end': '2026-04-01', 'cost': 250000, 'effort': 5},
]}


def test_formatting_does_not_change_amounts_or_budgets():
    base = _build_burn_matrix(parse_chart(SOURCE), period='quarter')
    formatted = _build_burn_matrix(parse_chart({**SOURCE, 'style': {'value_prefix':'$', 'value_scale':'millions'}}), period='quarter')
    assert formatted['series'] == base['series']
    assert formatted['totals'] == base['totals']


def test_table_and_burn_csv_use_format_without_scaling_effort(tmp_path):
    source = {**SOURCE, 'style': {'value_prefix':'$', 'value_scale':'millions', 'value_decimals':2,
        'table_columns':['name', {'field':'cost', 'total':True}, 'effort']}}
    chart = parse_chart(source)
    target = tmp_path / 'table.csv'
    render_table(chart, str(target))
    with target.open() as file:
        rows = list(csv.DictReader(file))
    assert [row['Cost'] for row in rows] == ['$1.25M', '$0.25M', '$1.50M']
    assert [row['Effort'] for row in rows[:2]] == ['10', '5']
    render_burn_table(chart, str(target), period='quarter', group_by='total')
    with target.open() as file:
        rows = list(csv.DictReader(file))
    assert rows[0]['2026-Q1'] == '$1.50M'


def test_existing_multiplier_remains_display_only(tmp_path):
    chart = parse_chart({**SOURCE, 'style': {'value_prefix':'$', 'value_suffix':'thousand'}})
    target = tmp_path / 'burn.csv'
    render_burn_table(chart, str(target), period='quarter', group_by='total', display_factor='0.001')
    with target.open() as file:
        row = next(csv.DictReader(file))
    assert row['2026-Q1'] == '$1,500 thousand'


@pytest.mark.parametrize('display', ['spend','remaining','cumulative'])
def test_default_formatting_keeps_png_bytes_unchanged(tmp_path, display):
    one, two = tmp_path / 'one.png', tmp_path / 'two.png'
    render_burn_chart(parse_chart(SOURCE), str(one), dpi=40, display=display)
    defaults = {key:value for key,value in asdict(Style()).items() if key.startswith('value_')}
    render_burn_chart(parse_chart({**SOURCE, 'style':defaults}), str(two), dpi=40, display=display)
    assert one.read_bytes() == two.read_bytes()


@pytest.mark.parametrize('display', ['spend','remaining','cumulative'])
def test_graph_svg_labels_include_currency_and_scale(tmp_path, display):
    chart = parse_chart({**SOURCE, 'style': {'value_prefix':'$', 'value_scale':'millions', 'value_decimals':2}})
    target = tmp_path / 'graph.svg'
    render_burn_chart(chart, str(target), display=display, period='quarter', group_by='total')
    svg = target.read_text()
    assert '$0.00M' in svg
    assert '($ millions)' in svg


@pytest.mark.parametrize('mode', ['--burn', '--burndown', '--burnup', '--burn-table'])
def test_cli_currency_scale_overrides(tmp_path, mode):
    from jsonantt.cli import main
    source = tmp_path / 'project.json'
    source.write_text(json.dumps({**SOURCE, 'style': {'value_scale': 'thousands'}}))
    original = source.read_bytes()
    output = tmp_path / 'output.svg'
    assert main([mode, str(source), str(output), '--burn-period', 'quarter',
                 '--value-scale', 'millions', '--value-prefix', '$', '--value-decimals', '2']) == 0
    svg = output.read_text()
    if mode == '--burn-table':
        assert '$1.25M' in svg
    else:
        assert '$0.00M' in svg
        assert '($ millions)' in svg
    assert source.read_bytes() == original


def test_cli_formats_selected_burn_field_and_validates_decimals(tmp_path, capsys):
    from jsonantt.cli import main
    source = tmp_path / 'project.json'
    source.write_text(json.dumps(SOURCE))
    output = tmp_path / 'output.csv'
    args = ['--burn-table', str(source), str(output), '--burn-period', 'quarter',
            '--burn-field', 'effort', '--burn-group', 'total']
    assert main(args + ['--value-prefix', '$', '--value-decimals', '2']) == 0
    assert '$15.00' in output.read_text()
    assert main(args + ['--value-decimals', '-1']) == 1
    assert 'value_decimals' in capsys.readouterr().err
