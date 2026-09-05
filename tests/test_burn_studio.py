"""The interactive burn calculations must agree with the export renderer."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from jsonantt.parser import parse_chart
from jsonantt.renderer import _build_burn_matrix

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not shutil.which('node'), reason='Node is required for browser model tests')
@pytest.mark.parametrize('period', ['day', 'week', 'month', 'quarter', 'year'])
@pytest.mark.parametrize('group', ['total', 'leaf', '0', '1'])
def test_browser_burn_matches_python(period, group):
    source = {
        'tasks': [
            {'name': 'Phase', 'tasks': [
                {'name': 'Work', 'start': '2026-01-15', 'end': '2026-03-01', 'cost': '$1,200'},
                {'name': 'Overlap', 'start': '2026-02-01', 'duration': '2m', 'cost': '$600'},
                {'name': 'Gate', 'milestone': True, 'date': '2026-03-15', 'cost': '$150'},
            ]},
        ],
    }
    options = {'period': period, 'group': group, 'factor': 0.001}
    script = """
        import { parseChart } from './jsonantt/web/model.mjs';
        import { buildBurn } from './jsonantt/web/burn.mjs';
        import { readFileSync } from 'node:fs';
        const { source, options } = JSON.parse(readFileSync(0, 'utf8'));
        console.log(JSON.stringify(buildBurn(parseChart(source), options), (key, value) => key === 'task' ? undefined : value));
    """
    result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT,
                            input=json.dumps({'source': source, 'options': options}),
                            text=True, capture_output=True, check=True)
    actual = json.loads(result.stdout)
    expected = _build_burn_matrix(parse_chart(source), period=period, group_by=group, display_factor=0.001)
    assert [p['label'] for p in actual['periods']] == [p['label'] for p in expected['periods']]
    assert [s['name'] for s in actual['series']] == [s['name'] for s in expected['series']]
    for browser, python in zip(actual['series'], expected['series']):
        assert browser['budget'] == pytest.approx(float(python['budget'] * expected['display_factor']))
        assert browser['values'] == pytest.approx([float(v * expected['display_factor']) for v in python['values']])
    assert actual['totals'] == pytest.approx([float(v * expected['display_factor']) for v in expected['totals']])
