import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(resolve(process.argv[2],'package.json'));
const {JSDOM}=require('jsdom');
const html=readFileSync(new URL('../jsonantt/web/index.html',import.meta.url),'utf8');
const draft={title:'Unsaved current',tasks:[{name:'Work',start:'2026-01-01',duration:'4w',cost:50}]};
const baseline={...draft,title:'Previous version'};
let storage, dom;
async function mount(id,url='http://localhost/?project=1') {
  dom=new JSDOM(html,{url,pretendToBeVisual:true});
  assert(dom.window.document.querySelector('main').classList.contains('layers-collapsed'),'Objects collapsed before boot');
  assert.equal(dom.window.document.querySelector('#toggle-layers').getAttribute('aria-expanded'),'false');
  for(const key of ['window','document','localStorage','HTMLElement','HTMLLabelElement','navigator','DOMParser']) Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
  if(storage)localStorage.setItem('jsonantt.workspace.v1',storage);
  globalThis.fetch=async(url,options)=>{
    if(String(url)==='healthz') return new Response(JSON.stringify({status:'ok',capabilities:['chart-preview','local-files'],project_path:'/repo/plan.json'}));
    assert(!String(url).includes('__project'),'A recovered draft must take precedence over disk');
    if(String(url).includes('/api/preview')) {
      const body=JSON.parse(options.body);
      assert.equal(body.planned.title,'Previous version');
      assert.equal(body.actual.title,'Unsaved current');
      return new Response('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="white"/></svg>');
    }
    throw new Error('Unexpected fetch '+url);
  };
  const {state}=await import(`../jsonantt/web/app.mjs?workspaceTest=${id}`);
  for(let i=0;i<100 && !state.source;i++)await new Promise(resolve=>setTimeout(resolve,5));
  return state;
}
storage=JSON.stringify({version:1,source:JSON.stringify(draft),launchPath:'/repo/plan.json',projectPath:'/repo/other.json',projectAttached:true,
  canvasTab:'table',tableFilter:'milestones',zoom:125,burn:{period:'quarter',group:'leaf',field:'cost',factor:1},
  comparison:{baseline,enabled:true,label:'Old revision',revisions:[{sha:'123',label:'2026-01-01 · 123 · Initial'}],revision:'123'},
  undoStack:['old text'],redoStack:[],sourceCollapsed:true,layersCollapsed:true});
let state=await mount(1);
assert.equal(state.source,JSON.stringify(draft));
assert.equal(state.canvasTab,'table');
assert.equal(document.querySelector('#compare-mode-toggle').checked,true);
assert.equal(state.projectPath,'/repo/other.json');
assert.equal(state.zoom,125);
assert.equal(state.tableFilter,'milestones');
assert.equal(document.querySelector('#compare-revisions').value,'123');
assert(document.querySelector('main').classList.contains('source-collapsed'));
assert(document.querySelector('main').classList.contains('layers-collapsed'));
assert.equal(document.querySelector('#compare-history').disabled,false);
await new Promise(resolve=>setTimeout(resolve,30));
const source=document.querySelector('#source');
source.value='{ invalid but unsaved';
source.dispatchEvent(new window.Event('input',{bubbles:true}));
window.dispatchEvent(new window.Event('pagehide'));
storage=localStorage.getItem('jsonantt.workspace.v1');
assert.equal(JSON.parse(storage).source,source.value);
storage=JSON.stringify({...JSON.parse(storage),layersCollapsed:false});
await new Promise(resolve=>setTimeout(resolve,0)); // Flush the old document's queued saves before swapping test globals.
dom.window.close();
state=await mount(2,'http://localhost/');
assert.equal(state.source,'{ invalid but unsaved');
assert(!document.querySelector('main').classList.contains('layers-collapsed'),'Explicit saved expansion overrides the default');
assert.equal(document.querySelector('#toggle-layers').getAttribute('aria-label'),'Hide objects panel');
assert(state.error);
assert.equal(state.canvasTab,'table');
assert.equal(state.projectPath,'/repo/other.json');
assert.equal(state.undoStack.at(-1),JSON.stringify(draft));
assert(document.querySelector('#compare-status').textContent.includes('Old revision'));
console.log('Passed refresh/revisit restoration: unsaved/invalid source, file identity, baseline, revision, view, filters, zoom, panels and undo history.');
dom.window.close();
