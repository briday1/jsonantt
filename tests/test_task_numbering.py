import csv
from io import StringIO
import json

import pytest

from jsonantt import parse_chart, render_document
from jsonantt.api import MODES
from jsonantt.renderer import _flatten


SOURCE = {'tasks': [
    {'id': 'parent', 'name': 'Parent', 'tasks': [
        {'id': 'work', 'name': 'Work', 'start': '2026-01-01', 'duration': '1w', 'cost': 100},
        {'id': 'gate', 'name': 'Gate', 'milestone': True, 'date': '2026-01-08'},
    ]},
    {'id': 'next', 'name': 'Next', 'not_before': 'work', 'duration': '1w', 'cost': 200},
], 'arrows': [{'from': 'work', 'to': 'gate'}]}


@pytest.mark.parametrize('start', [0, 1, 5, 42])
def test_hierarchy_keeps_ids_dates_and_colors(start):
    original = parse_chart(SOURCE)
    source = {**SOURCE, 'style': {'task_number_start': start}}
    chart = parse_chart(source)
    rows = _flatten(chart.tasks, chart.style)
    assert [row.number for row in rows] == [str(start), f'{start}.1', f'{start}.2', str(start + 1)]
    assert [row.color for row in rows] == [row.color for row in _flatten(original.tasks, original.style)]
    assert chart.tasks == original.tasks and chart.arrows == original.arrows


@pytest.mark.parametrize('invalid', [-1, 1.5, True, '5', None])
def test_invalid_number_start(invalid):
    with pytest.raises(ValueError, match='task_number_start'):
        parse_chart({**SOURCE, 'style': {'task_number_start': invalid}})


@pytest.mark.parametrize('mode', MODES)
def test_start_number_in_every_output(mode):
    source = {**SOURCE, 'style': {'task_number_start': 5}}
    document = {'planned': source, 'actual': source} if mode.startswith('compare-') else source
    options = {'mode': mode, 'format': 'svg', 'burn': {'group': '0'}}
    svg = render_document(document, options).decode()
    assert '5.' in svg and '6.' in svg
    if mode.endswith('table'):
        text = render_document(document, {**options, 'format': 'csv'}).decode()
        assert '5.' in text and '6.' in text


@pytest.mark.parametrize('mode', ['gantt', 'table', 'burn', 'burndown', 'burnup', 'burn-table'])
def test_default_unchanged_and_interactive_png_parity(mode):
    options = {'mode': mode, 'format': 'png', 'dpi': 30}
    assert render_document(SOURCE, options) == render_document({**SOURCE, 'style': {'task_number_start': 1}}, options)
    numbered = {**SOURCE, 'style': {'task_number_start': 5}}
    assert render_document(numbered, options) == render_document(numbered, {**options, 'interactive': True})


def test_rollups_filters_and_milestone_numbering():
    source = {**SOURCE, 'style': {'task_number_start': 5, 'rollup_milestones': True}}
    svg = render_document(source, {'mode': 'gantt', 'format': 'svg', 'interactive': True, 'renderDepth': 1}).decode()
    assert 'studio-task-5.2--rolled' in svg
    rows = list(csv.reader(StringIO(render_document(source, {'mode': 'table', 'format': 'csv', 'tableFilter': 'milestones'}).decode())))
    assert rows[1][0] == '5.2'
    source['style']['number_milestones'] = True
    assert 'M1' in render_document(source, {'mode': 'table', 'format': 'csv', 'tableFilter': 'milestones'}).decode()


def test_cli_uses_source_numbering(tmp_path):
    from jsonantt.cli import main
    source = {**SOURCE, 'style': {'task_number_start': 5}}
    path = tmp_path / 'input.json'
    path.write_text(json.dumps(source))
    output = tmp_path / 'table.csv'
    main([str(path), str(output), '--table'])
    assert output.read_bytes() == render_document(source, {'mode': 'table', 'format': 'csv'})


@pytest.mark.parametrize('start,prefix', [(1, 'M'), (10, 'G'), (0, ''), (7, 'Gate ')])
def test_independent_milestone_numbers_and_prefix(start, prefix):
    source = {**SOURCE, 'style': {'task_number_start': 42, 'number_milestones': True,
                                'milestone_number_start': start, 'milestone_prefix': prefix}}
    source['tasks'] = SOURCE['tasks'] + [{'name': 'Last gate', 'milestone': True, 'date': '2026-01-20'}]
    chart = parse_chart(source)
    rows = _flatten(chart.tasks, chart.style)
    assert [row.milestone_label for row in rows if row.task.milestone] == [f'{prefix}{start}', f'{prefix}{start+1}']
    assert rows[0].number == '42'
    for mode in ('gantt', 'table', 'compare-gantt', 'compare-table'):
        document = {'planned': source, 'actual': source} if mode.startswith('compare-') else source
        svg = render_document(document, {'mode': mode, 'format': 'svg', 'interactive': True}).decode()
        assert f'<!-- {prefix}{start} -->' in svg
        if mode.endswith('table'):
            text = render_document(document, {'mode': mode, 'format': 'csv', 'tableFilter': 'milestones'}).decode()
            assert list(csv.reader(StringIO(text)))[1][0] == f'{prefix}{start}'
    chart.style.rollup_milestones = True
    rolled = _flatten(chart.tasks, chart.style, max_depth=1)
    assert rolled[0].rolled_milestones[0].label == f'{prefix}{start}'


@pytest.mark.parametrize('key,value', [('milestone_number_start', -1), ('milestone_number_start', 2.5),
                                      ('milestone_number_start', True), ('milestone_number_start', '5'),
                                      ('milestone_prefix', None), ('milestone_prefix', 5)])
def test_invalid_milestone_numbering(key, value):
    with pytest.raises(ValueError, match=key):
        parse_chart({**SOURCE, 'style': {key: value}})


def test_milestone_defaults_keep_identical_png():
    source = {**SOURCE, 'style': {'number_milestones': True}}
    explicit = {**source, 'style': {**source['style'], 'milestone_number_start': 1, 'milestone_prefix': 'M'}}
    for mode in ('gantt', 'table'):
        options = {'mode': mode, 'format': 'png', 'dpi': 30}
        assert render_document(source, options) == render_document(explicit, options)
