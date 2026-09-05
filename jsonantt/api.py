"""Data-only rendering API shared by HTTP, Python callers, and Pyodide."""
from copy import deepcopy
from datetime import date, datetime
import threading
from pathlib import Path
import tempfile

from .parser import parse_chart
from .renderer import (render_chart, render_table, render_burn_chart,
                       render_burn_table, render_compare_chart, render_compare_table)
from .value_format import validate_value_format

MODES = ('gantt', 'table', 'burn', 'burndown', 'burnup', 'burn-table', 'compare-gantt', 'compare-table',
         'compare-burn', 'compare-burndown', 'compare-burnup', 'compare-burn-table')
FORMATS = ('png', 'svg', 'csv')
TABLE_MODES = ('table', 'burn-table', 'compare-table', 'compare-burn-table')
_FILENAMES = {'png': 'chart.png', 'svg': 'chart.svg', 'csv': 'chart.csv'}
_LOCK = threading.RLock()


def _integer(value, name, minimum):
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f'{name} must be an integer >= {minimum}') from None
    if isinstance(value, bool) or str(value) != str(number) or number < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return number


def render_document(document, options=None):
    """Return PNG/SVG/CSV bytes without modifying the input.

    Comparison modes take ``{'planned': chart, 'actual': chart}`` instead of a
    single chart. See docs/api.rst for the complete options and capability matrix.
    """
    if not isinstance(document, dict):
        raise ValueError('chart JSON must be an object')
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError('render options must be an object')
    allowed = {'mode', 'format', 'dpi', 'interactive', 'renderDepth', 'tableFilter',
               'burn', 'dateLine', 'dateLineColor', 'valueFormat'}
    if set(options) - allowed:
        raise ValueError(f'unknown render options: {sorted(set(options) - allowed)}')
    mode, fmt = options.get('mode', 'gantt'), options.get('format', 'svg')
    if mode not in MODES:
        raise ValueError(f'unknown export mode: {mode}')
    if fmt not in FORMATS or (fmt == 'csv' and mode not in TABLE_MODES):
        raise ValueError('Choose PNG/SVG, or CSV for a table')
    dpi = _integer(options.get('dpi', 150), 'dpi', 1)
    depth = options.get('renderDepth')
    if depth is not None:
        depth = _integer(depth, 'render depth', 0)
    table_filter = options.get('tableFilter', 'all')
    if table_filter not in {'all', 'milestones', 'tasks'}:
        raise ValueError('unknown table filter')
    interactive = options.get('interactive', False)
    if not isinstance(interactive, bool):
        raise ValueError('interactive must be a boolean')
    compare = mode.startswith('compare-')
    source = deepcopy(document)
    if compare:
        if not all(isinstance(source.get(key), dict) for key in ('planned', 'actual')):
            raise ValueError('comparison JSON requires planned and actual chart objects')
        sources = [source['planned'], source['actual']]
    else:
        sources = [source]
    if mode.startswith('compare-burn'):
        from .compare_output import pair_outputs
        nested = dict(options, mode=mode[len('compare-'):], interactive=False)
        for label, item in zip(('Baseline', 'Current'), sources):
            item['title'] = f"{label} — {item['title']}" if item.get('title') else label
        left, right = (render_document(item, nested) for item in sources)
        return pair_outputs(left, right, fmt, dpi, parse_chart(sources[0]).style.background)
    overrides = options.get('valueFormat', {})
    value_keys = {'value_scale', 'value_prefix', 'value_suffix', 'value_decimals', 'value_fields'}
    if not isinstance(overrides, dict) or set(overrides) - value_keys:
        raise ValueError('valueFormat must contain only value_* formatting settings')
    configs = [parse_chart(item) for item in sources]
    for config in configs:
        for key, value in overrides.items():
            setattr(config.style, key, value)
        validate_value_format(config.style)
    config = configs[0]
    burn = options.get('burn', {})
    if not isinstance(burn, dict) or set(burn) - {'field', 'period', 'group', 'factor', 'display'}:
        raise ValueError('invalid burn options')
    display = {'burndown': 'remaining', 'burnup': 'cumulative'}.get(mode, burn.get('display', 'spend'))
    date_options = {}
    line = options.get('dateLine')
    if line is not None:
        if mode not in {'gantt', 'compare-gantt', 'burndown', 'burnup'} and not (mode == 'burn' and display in {'remaining', 'cumulative'}):
            raise ValueError('dateLine is only supported for Gantt, burndown, or burnup output')
        if not isinstance(line, str):
            raise ValueError('dateLine must be a date string or today')
        date_options['date_line'] = date.today() if line.strip().lower() == 'today' else datetime.strptime(line, config.date_format).date()
    if mode in {'gantt', 'compare-gantt', 'burn', 'burndown', 'burnup'}:
        date_options['date_line_color'] = options.get('dateLineColor', '#C00000')
    with _LOCK, tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / _FILENAMES[fmt])
        kwargs = {'dpi': dpi}
        if not compare:
            kwargs['interactive'] = interactive
        if mode.startswith('burn'):
            kwargs.update(field=burn.get('field', 'cost'), period=burn.get('period', 'month'),
                          group_by=burn.get('group', '0'), display_factor=burn.get('factor', 1))
            if mode == 'burn-table':
                render_burn_table(config, path, **kwargs)
            else:
                render_burn_chart(config, path, display=display, **date_options, **kwargs)
        else:
            kwargs['render_depth'] = depth
            if mode in {'table', 'compare-table'}:
                kwargs.update(milestones_only=table_filter == 'milestones', no_milestones=table_filter == 'tasks')
                render = render_compare_table if compare else render_table
            else:
                kwargs.update(date_options)
                render = render_compare_chart if compare else render_chart
            render(*configs, path, **kwargs)
        return Path(path).read_bytes()
