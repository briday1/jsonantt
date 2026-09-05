from copy import deepcopy
import json

import pytest

from jsonantt import compose_document, load_chart, parse_chart
from jsonantt.browser_renderer import render_json


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
