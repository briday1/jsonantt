import json
import subprocess
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from jsonantt.history import file_history, revision_source
from jsonantt.server import create_server


@pytest.fixture
def tracked_file(tmp_path):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], stderr=subprocess.PIPE).decode().strip()
    git('init')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.invalid')
    source = {'tasks':[{'name':'Old', 'start':'2026-01-01', 'duration':'4w'}]}
    old = tmp_path / 'old name.json'
    old.write_text(json.dumps(source))
    git('add', '--', old.name)
    git('commit', '-m', 'Initial budget')
    first = git('rev-parse', 'HEAD')
    path = tmp_path / 'current [plan].json'
    git('mv', old.name, path.name)
    git('commit', '-m', 'Rename plan')
    source['tasks'][0]['name'] = 'Current'
    path.write_text(json.dumps(source))
    git('add', '--', path.name)
    git('commit', '-m', 'Revise budget')
    path.write_text('{"unsaved_on_disk":true}')
    return path, first, git('status', '--porcelain')


def test_history_follows_renames_without_touching_worktree(tracked_file):
    path, first, before = tracked_file
    _, entries = file_history(path)
    assert [entry['message'] for entry in entries] == ['Revise budget','Rename plan','Initial budget']
    assert entries[-1]['sha'] == first and entries[-1]['path'] == 'old name.json'
    assert json.loads(revision_source(path, first))['tasks'][0]['name'] == 'Old'
    after = subprocess.check_output(['git','-C',str(path.parent),'status','--porcelain']).decode().strip()
    assert after == before
    assert path.read_text() == '{"unsaved_on_disk":true}'
    with pytest.raises(ValueError):
        revision_source(path, 'HEAD:../../other')


def test_full_path_http_history_without_startup_file(tracked_file):
    from urllib.parse import urlencode
    path, first, _ = tracked_file
    httpd = create_server('127.0.0.1',0,quiet=True)
    worker = threading.Thread(target=httpd.serve_forever,daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{httpd.server_address[1]}'
    try:
        with urlopen(base+'/api/history?'+urlencode({'path':str(path)})) as response:
            entries=json.load(response)['revisions']
        assert entries[-1]['sha']==first
        with urlopen(base+'/api/history?'+urlencode({'path':str(path),'revision':first})) as response:
            assert json.load(response)['tasks'][0]['name']=='Old'
        with urlopen(base+'/api/files?'+urlencode({'path':str(path.parent)})) as response:
            assert any(item['path']==str(path) for item in json.load(response)['entries'])
        path.write_text(revision_source(path,first))
        with urlopen(base+'/api/project?'+urlencode({'path':str(path)})) as response:
            assert json.load(response)['path']==str(path)
        with pytest.raises(HTTPError):
            urlopen(base+'/api/project?'+urlencode({'path':str(path.parent / '.git/config')}))
    finally:
        httpd.shutdown(); httpd.server_close(); worker.join(timeout=5)
