"""Small data-only entry point for the same renderer running under Pyodide."""
import json
from pathlib import Path
import tempfile

from .parser import parse_chart
from .renderer import render_chart, render_table, render_burn_chart, render_burn_table


def render_json(source, options_json):
    options = json.loads(options_json)
    mode = options.get('mode', 'gantt')
    fmt = options.get('format', 'svg')
    if mode not in {'gantt', 'table', 'burn', 'burndown', 'burnup', 'burn-table'}:
        raise ValueError(f'unknown export mode: {mode}')
    if fmt not in {'svg', 'png', 'csv'} or (fmt == 'csv' and mode not in {'table', 'burn-table'}):
        raise ValueError('Choose PNG/SVG, or CSV for a table')
    config = parse_chart(json.loads(source))
    kwargs = {'dpi': int(options.get('dpi', 150)), 'interactive': bool(options.get('interactive', False))}
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / f'chart.{fmt}')
        if mode.startswith('burn'):
            burn = options.get('burn', {})
            kwargs.update(field=burn.get('field', 'cost'), period=burn.get('period', 'month'),
                          group_by=burn.get('group', '0'), display_factor=burn.get('factor', 1))
            if mode == 'burn-table':
                render_burn_table(config, path, **kwargs)
            else:
                kwargs['display'] = {'burndown': 'remaining', 'burnup': 'cumulative'}.get(mode, burn.get('display', 'spend'))
                render_burn_chart(config, path, **kwargs)
        else:
            kwargs['render_depth'] = options.get('renderDepth')
            if mode == 'table':
                table_filter = options.get('tableFilter', 'all')
                if table_filter not in {'all', 'milestones', 'tasks'}:
                    raise ValueError('unknown table filter')
                render_table(config, path, milestones_only=table_filter == 'milestones',
                             no_milestones=table_filter == 'tasks', **kwargs)
            else:
                render_chart(config, path, **kwargs)
        return Path(path).read_bytes()
