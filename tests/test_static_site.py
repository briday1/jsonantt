import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from jsonantt.browser_renderer import render_json
from jsonantt.static_site import build_site
from tests.test_burn_preview import CHART_SOURCE


def test_static_bundle_contains_current_python_sources(tmp_path):
    build_site(tmp_path)
    package = Path(__file__).resolve().parents[1] / 'jsonantt'
    with ZipFile(tmp_path / 'python/jsonantt.zip') as archive:
        for source in package.glob('*.py'):
            assert archive.read('jsonantt/' + source.name) == source.read_bytes()
    for name in ('index.html', 'preview.mjs', 'python-worker.mjs', 'python-runtime.mjs', 'python-client.mjs'):
        assert (tmp_path / name).is_file()
    manifest = json.loads((tmp_path / 'startup-previews.json').read_text())
    assert manifest['version'] in (tmp_path / 'index.html').read_text()
    assert len(manifest['version']) == 64


def test_prerendered_demos_use_the_shared_renderer(tmp_path):
    import shutil
    import matplotlib
    from tests.test_burn_preview import drawing
    if not shutil.which('node'):
        pytest.skip('Node needed to load demo data')
    with matplotlib.rc_context({'svg.hashsalt':'startup-preview-parity'}):
        build_site(tmp_path, prerender=True)
    bundle = json.loads((tmp_path / 'startup-previews.json').read_text())
    assert len(bundle['previews']) == 3
    for preview in bundle['previews']:
        assert '<svg' in preview['svg'] and 'studio-task-' in preview['svg']
        assert '<image' not in preview['svg']
        assert preview['options']['mode'] == 'gantt'
        assert json.loads(preview['source'])['tasks']
        with matplotlib.rc_context({'svg.hashsalt':'startup-preview-parity'}):
            expected = render_json(preview['source'], json.dumps({'mode':'gantt','format':'svg','interactive':True})).decode()
        assert drawing(preview['svg']) == drawing(expected)


def test_static_build_rejects_source_directory():
    with pytest.raises(ValueError, match='source tree'):
        build_site(Path(__file__).resolve().parents[1] / 'jsonantt/web')


@pytest.mark.parametrize('mode', ['gantt', 'table', 'burn', 'burndown', 'burnup', 'burn-table'])
def test_browser_entrypoint_has_interactive_svg_and_png(mode):
    source = json.dumps(CHART_SOURCE)
    svg = render_json(source, json.dumps({'mode':mode, 'format':'svg', 'interactive':True}))
    assert b'<svg' in svg and b'studio-' in svg and b'<image' not in svg
    png = render_json(source, json.dumps({'mode':mode, 'format':'png', 'dpi':40}))
    assert png.startswith(b'\x89PNG\r\n\x1a\n')


def test_browser_entrypoint_table_filter_and_invalid_export():
    source = json.dumps(CHART_SOURCE)
    csv = render_json(source, json.dumps({'mode':'table','format':'csv','tableFilter':'milestones'})).decode()
    assert 'Gate' in csv and 'Research' not in csv
    with pytest.raises(ValueError, match='CSV'):
        render_json(source, '{"mode":"gantt","format":"csv"}')


def test_app_uses_only_shared_renderer_and_tight_checkbox():
    web = Path(__file__).resolve().parents[1] / 'jsonantt/web'
    app = (web / 'app.mjs').read_text()
    assert 'renderGantt' not in app and 'renderTable' not in app and 'renderBurn(' not in app
    assert 'chart-summary' not in (web / 'index.html').read_text()
    assert '.view-options input[type="checkbox"] { width: 13px;' in (web / 'styles.css').read_text()
