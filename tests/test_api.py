"""Public data API covers CLI render modes and options without altering input."""
from copy import deepcopy
from datetime import date
import json

import pytest

from jsonantt import render_document
from jsonantt.cli import main
from jsonantt.api import MODES
from tests.test_burn_preview import CHART_SOURCE


@pytest.mark.parametrize('mode,flags', [
    ('gantt', []), ('table', ['--table']), ('burn', ['--burn']),
    ('burndown', ['--burndown']), ('burnup', ['--burnup']), ('burn-table', ['--burn-table']),
    ('compare-gantt', ['--compare']), ('compare-table', ['--table', '--compare']),
    ('compare-burn', ['--burn', '--compare']), ('compare-burndown', ['--burndown', '--compare']),
    ('compare-burnup', ['--burnup', '--compare']), ('compare-burn-table', ['--burn-table', '--compare']),
])
def test_data_api_matches_cli(tmp_path, mode, flags):
    source = deepcopy(CHART_SOURCE)
    actual = deepcopy(source)
    actual['tasks'][1]['end'] = '2026-07-01'
    document = {'planned': source, 'actual': actual} if mode.startswith('compare-') else source
    before = deepcopy(document)
    source_path = tmp_path / 'chart.json'
    actual_path = tmp_path / 'actual.json'
    output = tmp_path / 'chart.png'
    source_path.write_text(json.dumps(source))
    actual_path.write_text(json.dumps(actual))
    options = {'mode': mode, 'format': 'png', 'dpi': 40,
               'valueFormat': {'value_scale': 'thousands', 'value_prefix': '$', 'value_decimals': 2}}
    args = [str(source_path), str(output), *flags]
    if mode.startswith('compare-'):
        args.append(str(actual_path))
    args += ['--dpi', '40', '--value-scale', 'thousands', '--value-prefix', '$', '--value-decimals', '2']
    if mode in {'gantt', 'compare-gantt', 'burndown', 'burnup'}:
        options.update(dateLine='2026-02-15', dateLineColor='#123abc')
        args += ['--date-line', '2026-02-15', '--date-line-color', '#123abc']
    if mode in {'table','compare-table'}:
        options['tableFilter'] = 'milestones'
        args += ['--milestones-only']
    if mode.startswith('burn') or mode.startswith('compare-burn'):
        options['burn'] = {'period':'quarter', 'group':'leaf', 'factor':'0.5'}
        args += ['--burn-period', 'quarter', '--burn-group', 'leaf', '--burn-display-factor', '0.5']
    else:
        options['renderDepth'] = 2
        args += ['--renderdepth', '2']
    assert main(args) == 0
    assert render_document(document, options) == output.read_bytes()
    assert document == before


@pytest.mark.parametrize('options', [
    {'dpi': 0}, {'dpi': 'oops'}, {'renderDepth': -1}, {'renderDepth': 1.5},
    {'mode':'wat'}, {'format':'exe'}, {'mode':'gantt','format':'csv'},
    {'tableFilter':'wat'}, {'mode':'table','dateLine':'today'},
    {'dateLine':'bad'}, {'interactive':'yes'}, {'unknown':True},
    {'valueFormat':{'value_decimals':-1}}, {'mode':'compare-gantt'},
])
def test_invalid_api_options(options):
    with pytest.raises(ValueError):
        render_document(CHART_SOURCE, options)


@pytest.mark.parametrize('mode', ['compare-gantt','compare-table'])
def test_comparison_preview_svg(mode):
    result = render_document({'planned':CHART_SOURCE,'actual':CHART_SOURCE}, {'mode':mode,'interactive':True})
    assert b'<svg' in result and b'<image' not in result
