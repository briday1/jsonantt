from copy import deepcopy
import json

import pytest

from jsonantt import compose_document, load_chart, parse_chart
from jsonantt.browser_renderer import render_json
from jsonantt.composition import load_composed_source


BASE = {'title':'Destination', 'dateformat':'%d/%m/%Y', 'style':{'palette':['#123456']},
        'children':[{'id':'existing','name':'Existing','start':'01/01/2026','duration':'1w'}]}
FILES = {
    'phase.json': {'title':'Ignored', 'style':{'palette':['red']}, 'arrows':[{'from':'bad','to':'bad'}],
                   'tasks':[{'filename':'nested/work.json'},{'name':'Gate','id':'gate','milestone':True,'date':['2026-02-01','2026-03-01']}]},
    'nested/work.json': {'dateformat':'%Y.%m.%d','tasks':[{'name':'Work','id':'work','start':'2026.01.08','duration':'2w','cost':100,'not_before':'existing'}]},
    'delivery.json': {'tasks':[{'name':'Delivery','id':'delivery','not_before':'work','duration':'4w'}]},
}


@pytest.mark.parametrize('wrap',[False,True])
def test_append_matches_cli_composition(tmp_path,wrap):
    for name,data in FILES.items():
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))
    expected=deepcopy(BASE)
    expected['tasks']=expected.pop('children')
    for name in ('phase.json','delivery.json'):
        expected['tasks'].append({'filename':name,**({'name':name[:-5]} if wrap else {})})
    path=tmp_path/'main.json';path.write_text(json.dumps(expected))
    before=deepcopy(BASE),deepcopy(FILES)
    result=compose_document(BASE,FILES,['phase.json','delivery.json'],wrap=wrap)
    assert parse_chart(result)==load_chart(str(path))
    assert result['title']=='Destination' and result['style']==BASE['style']
    assert 'arrows' not in result
    assert (BASE,FILES)==before
    assert 'filename' not in json.dumps(result)
    tasks=result['tasks'][1]['tasks'] if wrap else result['tasks'][1:]
    assert tasks[0]['start']=='08/01/2026'
    assert tasks[1]['date']==['01/02/2026','01/03/2026']


def test_existing_named_include_prepends_to_own_children():
    source={'tasks':[{'name':'Wrapper','filename':'part.json','children':[{'name':'Own','start':'2026-02-01','duration':'1w'}]}]}
    files={'part.json':{'tasks':[{'name':'Imported','start':'2026-01-01','duration':'1w'}]}}
    result=compose_document(source,files,[])
    assert [item['name'] for item in result['tasks'][0]['tasks']]==['Imported','Own']


@pytest.mark.parametrize('files,append,error',[
    ({'a.json':{'tasks':[{'filename':'missing.json'}]}},['a.json'],'Missing included file'),
    ({'a.json':{'tasks':[{'filename':'a.json'}]}},['a.json'],'Circular filename'),
    ({'a.json':{'tasks':[{'id':'existing','name':'Duplicate'}]}},['a.json'],'Duplicate task ID'),
])
def test_invalid_import_is_atomic(files,append,error):
    before=deepcopy(BASE)
    with pytest.raises(ValueError,match=error):compose_document(BASE,files,append)
    assert BASE==before


def test_worker_composition_adapter():
    payload={'document':BASE,'files':FILES,'append':['phase.json','delivery.json']}
    result=json.loads(render_json(json.dumps(payload),json.dumps({'action':'compose','format':'json'})))
    assert result==compose_document(**payload)


def test_local_include_search_order_and_snapshot(tmp_path, monkeypatch):
    project=tmp_path/'project';project.mkdir()
    nested=project/'nested';nested.mkdir()
    def write(path, data):path.write_text(json.dumps(data))
    leaf=lambda name:{'tasks':[{'name':name,'start':'2026-01-01','duration':'1w'}]}
    write(tmp_path/'work.json',leaf('Wrong working-directory duplicate'))
    write(nested/'work.json',leaf('Relative first'))
    write(tmp_path/'fallback.json',leaf('Working directory fallback'))
    write(nested/'phase.json',{'tasks':[{'filename':'work.json'},{'filename':'fallback.json'}]})
    path=project/'composed.json'
    write(path,{'tasks':[{'name':'Wrapper','filename':'nested/phase.json'}]})
    monkeypatch.chdir(tmp_path)
    before=path.read_text()
    snapshot=json.loads(load_composed_source(path))
    assert parse_chart(snapshot)==load_chart(str(path))
    assert [item['name'] for item in snapshot['tasks'][0]['tasks']]==['Relative first','Working directory fallback']
    assert 'filename' not in json.dumps(snapshot)
    assert path.read_text()==before


def test_virtual_include_search_order_matches_local():
    leaf=lambda name:{'tasks':[{'name':name,'start':'2026-01-01','duration':'1w'}]}
    files={'nested/phase.json':{'tasks':[{'filename':'work.json'},{'filename':'fallback.json'}]},
           'nested/work.json':leaf('Relative first'),'work.json':leaf('Wrong duplicate'),
           'fallback.json':leaf('Working directory fallback')}
    result=compose_document({'tasks':[{'filename':'nested/phase.json'}]},files,append=[],source_name='composed.json')
    assert [item['name'] for item in result['tasks']]==['Relative first','Working directory fallback']


def test_browser_missing_include_never_searches_os(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'work.json').write_text(json.dumps({'tasks':[]}))
    with pytest.raises(ValueError,match='Missing included file: work.json') as error:
        render_json(json.dumps({'tasks':[{'filename':'work.json'}]}),json.dumps({'mode':'gantt'}))
    assert str(tmp_path) not in str(error.value)


def test_local_cycles_and_missing_files(tmp_path):
    path=tmp_path/'composed.json'
    path.write_text('{"tasks":[{"filename":"composed.json"}]}')
    with pytest.raises(ValueError,match='Circular filename'):load_composed_source(path)
    path.write_text('{"tasks":[{"filename":"missing.json"}]}')
    with pytest.raises(FileNotFoundError):load_composed_source(path)
