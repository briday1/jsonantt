// DOM acceptance tests against the real local renderer. Pyodide itself is tested in pyodide_runtime.mjs.
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
const require = createRequire(process.argv[2] ? resolve(process.argv[2],'package.json') : import.meta.url);
const {JSDOM} = require('jsdom');
const origin = process.env.JSONANTT_TEST_SERVER_URL || 'http://127.0.0.1:4187/';
const dom = new JSDOM(readFileSync(new URL('../jsonantt/web/index.html',import.meta.url),'utf8'),{url:origin+'?demo=1',pretendToBeVisual:true});
for (const key of ['window','document','localStorage','HTMLElement','HTMLLabelElement','navigator','DOMParser']) Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
const nativeFetch = globalThis.fetch;
const localFetch = (url,options)=>nativeFetch(new URL(url,origin),options);
globalThis.fetch = localFetch;
const {state} = await import('../jsonantt/web/app.mjs');
const {STYLE_OPTIONS} = await import('../jsonantt/web/style-options.mjs');
const {setExportBackend} = await import('../jsonantt/web/export.mjs');
const q = selector=>document.querySelector(selector);
const pause = ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(check,message) {
  for (let i=0;i<1500;i++) {if (check()) return; await pause(10);}
  assert.fail(message);
}
await until(()=>state.chart,'App did not boot: start jsonantt serve on port 4187');
assert.equal(q('#format-source'), null, 'Format JSON toolbar button was removed');
assert(q('#undo-source') && q('#redo-source'));
assert.equal(q('.new-menu #add-subtask'),null);
assert.equal(q('.new-menu #add-arrow'),null);
async function preview() {
  await until(()=>q('#canvas > svg')?.dataset.previewMode===state.canvasTab && q('#canvas').getAttribute('aria-busy')!=='true','Exact preview did not arrive: '+q('#status').textContent);
  assert.equal(q('#canvas img, #canvas canvas, #canvas .studio-table'),null);
  return q('#canvas > svg');
}
function load(doc) {q('#source').value=JSON.stringify(doc);q('#source').dispatchEvent(new window.Event('input'));}
function change(key,value) {
  const control=q('[data-setting="'+key+'"]');
  if (typeof value==='boolean') control.checked=value; else control.value=String(value);
  control.dispatchEvent(new window.Event('change'));
}
function pick(mode) {q('[data-canvas-tab="'+mode+'"]').click();}
const base={title:'Test project',tasks:[{name:'Parent',tasks:[
  {id:'work',name:'Work',start:'2026-01-01',end:'2026-05-01',cost:100},
  {id:'gate',name:'Gate',milestone:true,date:'2026-05-01'},
  {name:'Major',major_milestone:true,date:'2026-04-01'},
]}],arrows:[{from:'work',to:'gate',color:'#123456'}]};
load(base);
assert.equal(state.doc.style,undefined);
for (const option of STYLE_OPTIONS) {
  load(base);
  const value=option.type==='boolean' ? !option.default
    : option.type==='number' ? (option.key==='label_fraction' ? .4 : option.key==='bar_height' ? .7 : 1)
    : option.type==='color' ? '#123456' : option.type==='palette' ? '["#123456","#654321"]'
    : option.type==='columns' ? '["name",{"field":"cost","total":true}]'
    : option.key==='fiscal_year_start' ? '10-15' : option.type==='select' ? option.choices.filter(Boolean).at(-1) : 'o';
  change(option.key,value);
  assert(Object.hasOwn(state.doc.style||{},option.key),option.key+' first edit');
  q('[data-setting="'+option.key+'"]').closest('.setting-control').querySelector('button.color-clear').click();
  assert(!Object.hasOwn(state.doc.style,option.key),option.key+' reset');
}
console.log('Passed all '+STYLE_OPTIONS.length+' settings first edit/reset.');
load(base);
q('#burn-period').value='quarter';q('#burn-period').dispatchEvent(new window.Event('change'));
for (const mode of ['gantt','table','burn','burndown','burnup','burn-table']) {
  pick(mode);
  const svg=await preview();
  const target=svg.querySelector('[data-key]');
  assert(target,mode+' selection targets');
  target.dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
  assert.equal(state.selection.key,target.dataset.key);
  assert.equal(q('#canvas > svg'),svg,'Selection must not rebuild the SVG');
  await preview();
  assert(q('#canvas .selected-element'));
  assert.equal(q('#canvas-inspector').hidden,false);
}
console.log('Passed all six exact SVG views and selection.');

load({...base,style:{task_number_start:5}});
for (const mode of ['gantt','table','burn','burndown','burnup','burn-table']) {
  pick(mode);
  const svg=await preview();
  const target=svg.querySelector('[data-key="tasks.0.tasks.0"]') || svg.querySelector('[data-key="tasks.0"]');
  assert(target,mode+' offset numbering lost its selection target');
  assert(svg.querySelector('[id^="studio-task-5"], [id^="studio-series-5"]'));
  target.dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
  assert.equal(state.selection.key,target.dataset.key);
}
pick('gantt');
change('number_milestones',true);
change('milestone_number_start',10);
change('milestone_prefix','G');
assert.equal(state.doc.style.milestone_prefix,'G');
assert((await preview()).outerHTML.includes('G10'));
change('milestone_prefix','');
assert.equal(state.doc.style.milestone_prefix,'','Empty prefix must not reset to M');
assert.equal(q('[data-setting="milestone_prefix"]').placeholder,'No prefix');
assert(!(await preview()).outerHTML.includes('G10'));
q('[data-setting="milestone_prefix"]').closest('.setting-control').querySelector('button.color-clear').click();
assert(!Object.hasOwn(state.doc.style,'milestone_prefix'));
assert.equal(q('[data-setting="milestone_prefix"]').value,'M');
assert((await preview()).outerHTML.includes('M10'));
console.log('Passed offset numbering and selection in all six views, independent milestone numbering, empty prefix and reset.');

for (const mode of ['gantt','table']) {
  for (const bucket of ['tasks','children']) {
    load({tasks:[{name:'Parent',[bucket]:[{name:'Existing',start:'2026-01-01',duration:'4w'}]}]});
    pick(mode);
    (await preview()).querySelector('[data-key="tasks.0"]').dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
    q('#inspector-add-subtask').click();
    assert.equal(state.doc.tasks.length,1);
    assert.equal(state.doc.tasks[0][bucket].length,2);
    assert.equal(state.selection.key,`tasks.0.${bucket}.1`);
    assert.equal(state.canvasTab,mode);
    assert.equal(q('#inspector-content input').value,'New task');
    q('#undo-source').click();
    assert.equal(state.doc.tasks[0][bucket].length,1);
    q('#redo-source').click();
    assert.equal(state.doc.tasks[0][bucket].length,2);
    await preview();
  }
}
console.log('Passed contextual subtask creation, child selection, undo/redo and both child schemas in Gantt/table.');

const year=new Date().getFullYear();
load({style:{today_marker:true},tasks:[{name:'Current work',start:`${year}-01-01`,end:`${year+1}-01-01`,cost:100}]});
for (const mode of ['burndown','burnup']) {
  pick(mode);
  assert((await preview()).querySelector('#chart-date-marker'),mode+' today marker');
  change('today_marker',false);
  assert.equal((await preview()).querySelector('#chart-date-marker'),null);
  change('today_marker',true);
}
console.log('Passed burndown/burnup today-marker settings.');
load(base);

pick('gantt');await preview();
q('#canvas [id^="studio-arrow-0--"]').dispatchEvent(new window.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
assert.equal(state.selection.kind,'arrow');
assert.equal(q('#inspector-add-subtask'),null,'Arrow properties must not offer subtasks');
const arrowColor=q('#inspector-content input[type="color"]');
arrowColor.value='#abcdef';arrowColor.dispatchEvent(new window.Event('input'));
await preview();
assert.equal(state.doc.arrows[0].color,'#abcdef');
for (const path of q('#canvas').querySelectorAll('[id^="studio-arrow-0--"] path')) assert(path.getAttribute('style').includes('#abcdef'));

const work=()=>q('#canvas [id^="studio-task-1.1--"]');
work().dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
const cost=q('[data-field="cost"]');
assert.equal(cost.value,'100');
for (const [value,expected] of [['0',0],['250000',250000],['$1,250.50','$1,250.50']]) {
  cost.value=value;cost.dispatchEvent(new window.Event('input'));
  assert.equal(state.doc.tasks[0].tasks[0].cost,expected);
}
cost.value='bad';cost.dispatchEvent(new window.Event('input'));
assert.equal(cost.checkValidity(),false);
assert.equal(state.doc.tasks[0].tasks[0].cost,'$1,250.50');
cost.value='';cost.dispatchEvent(new window.Event('input'));
assert(!Object.hasOwn(state.doc.tasks[0].tasks[0],'cost'));
assert([...document.querySelectorAll('[data-canvas-tab^="burn"]')].every(tab=>tab.hidden));
cost.value='1250000';cost.dispatchEvent(new window.Event('input'));
assert.equal(q('[data-canvas-tab="burn"]').hidden,false);
change('value_prefix','$');change('value_scale','millions');change('value_decimals',2);
assert.equal(q('[data-field="cost"]').value,'1250000','Properties must show raw cost, not scaled display');
console.log('Passed arrow head/body colour, keyboard selection, raw cost editing/validation/removal and no-cost hiding.');

q('#gantt-depth').value='1';q('#gantt-depth').dispatchEvent(new window.Event('change'));
q('#gantt-rollup-milestones').checked=true;q('#gantt-rollup-milestones').dispatchEvent(new window.Event('change'));
await preview();
assert.equal(state.doc.style.render_depth,1);
assert.equal(q('[data-setting="render_depth"]').value,'1');
assert.equal(state.doc.style.rollup_milestones,true);
assert.equal(q('#canvas [id^="studio-task-1.1--"]'),null);
q('#canvas [id^="studio-task-1.2--rolled-"]').dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
assert.equal(state.selection.key,state.chart.flat.find(task=>task.name==='Gate').key);
await preview();
q('#gantt-rollup-milestones').checked=false;q('#gantt-rollup-milestones').dispatchEvent(new window.Event('change'));
await preview();
assert.equal(q('#canvas [id*="--rolled-"]'),null);
change('render_depth',0);
assert.equal(q('#gantt-depth').value,'0');
console.log('Passed Gantt rollup controls, source/settings sync, and descendant milestone selection.');

pick('table');
for (const filter of ['all','milestones','tasks']) {
  q('#table-filter').value=filter;q('#table-filter').dispatchEvent(new window.Event('change'));
  await preview();
  assert.equal(Boolean(q('#canvas [id^="studio-task-1.1--"]')),filter!=='milestones');
  assert.equal(Boolean(q('#canvas [id^="studio-task-1.2--"]')),filter!=='tasks');
}
q('#settings-dialog').showModal=()=>{q('#settings-dialog').open=true;};
q('#canvas > svg').dispatchEvent(new window.MouseEvent('dblclick',{bubbles:true}));
assert.equal(q('#settings-dialog').open,true);
q('#settings-dialog').open=false;
q('#zoom-in').click();assert.equal(q('#canvas > svg').style.zoom,String(state.zoom/100));
q('#zoom-fit').click();
console.log('Passed table filters, double-click settings and zoom/fit.');

const existing=await preview();
load({...base,title:'Pending new title'});
assert.equal(q('#canvas > svg'),existing,'Do not replace an exact SVG while an update is pending');
assert.equal(q('#canvas .studio-table, #canvas .burn-empty'),null);
await preview();
const updated=q('#canvas > svg');
pick('gantt');pick('table');
assert.equal(q('#canvas .burn-empty'),null,'Cached view must render immediately');
assert(q('#canvas > svg'));
globalThis.fetch=async()=>new Response(JSON.stringify({error:'Test rendering failure'}),{status:400});
load({...base,title:'Fail'});
await until(()=>q('#canvas').getAttribute('aria-busy')==='false','Failure never completed');
assert.equal(q('#canvas > svg').textContent,updated.textContent);
assert(q('#canvas').dataset.error.includes('Test rendering failure'));
globalThis.fetch=localFetch;
load(base);await preview();

const downloads=[];
dom.window.HTMLAnchorElement.prototype.click=function(){downloads.push(nativeFetch(this.href).then(async response=>new Uint8Array(await response.arrayBuffer())));};
const dialog=q('#export-dialog');
dialog.showModal=()=>{dialog.open=true;};dialog.close=()=>{dialog.open=false;};
async function exportPng() {
  q('#export-chart').click();q('#export-format').value='png';q('#export-dpi').value='96';q('#confirm-export').click();
  await until(()=>!q('#confirm-export').disabled,'Export never completed');
  assert.equal(q('#export-error').hidden,true,q('#export-error').textContent);
  assert.equal(dialog.open,false);
}
for (const mode of ['gantt','table','burn','burndown','burnup','burn-table']) {pick(mode);await preview();await exportPng();}
for (const bytes of await Promise.all(downloads)) assert.deepEqual([...bytes.slice(0,8)],[137,80,78,71,13,10,26,10]);
assert.equal(downloads.length,6);
console.log('Passed no-flash updates/cached views/errors and all six PNG download buttons.');

// Exercise browser transport without an HTTP preview route. Real WASM is separately tested.
const workerRequests=[];
let workerCount=0;
globalThis.Worker=class {
  constructor(url,options){assert(url.href.endsWith('/python-worker.mjs'));assert.equal(options.type,'module');workerCount++;}
  postMessage(data) {
    if(data.cancel)return;
    workerRequests.push(data);
    const o=data.options,b=o.burn||{};
    const params=new URLSearchParams({mode:o.mode,format:o.format,dpi:o.dpi||150,table_filter:o.tableFilter||'all',
      render_depth:o.renderDepth||0,burn_field:b.field||'cost',burn_period:b.period||'month',burn_group:b.group||'0',burn_factor:b.factor??1});
    localFetch('/api/'+(o.interactive?'preview':'export')+'?'+params,{method:'POST',body:data.source})
      .then(async response=>response.ok ? {id:data.id,bytes:new Uint8Array(await response.arrayBuffer())} : {id:data.id,error:(await response.json()).error})
      .then(data=>this.onmessage({data}));
  }
};
state.serverPreview=false;state.serverBurnPreview=false;setExportBackend('browser');
globalThis.fetch=async()=>{throw new Error('Static hosting must not call local API routes');};
load({...base,title:'Static WASM transport'});pick('gantt');await preview();
await exportPng();
assert.equal(workerCount,1);
assert(workerRequests.some(r=>r.options.interactive));
assert(workerRequests.some(r=>r.options.format==='png' && r.options.dpi===96));
assert(workerRequests.every(r=>typeof r.source==='string' && !('python' in r)));
console.log('Passed hosted worker preview/export transport with no local API calls.');

const {createPreviewLoader}=await import('../jsonantt/web/preview.mjs');
const sample='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200"><text>LABEL</text></svg>';
const frames=[],errors=[];
let resolveOld;
const loader=createPreviewLoader({onRender:svg=>frames.push(svg.textContent),onError:message=>errors.push(message)});
globalThis.fetch=()=>new Promise(resolve=>{resolveOld=resolve;});
loader.schedule(JSON.stringify({...base,title:'old'}),state.chart,{mode:'gantt'},null);
await pause(200);assert(resolveOld);
globalThis.fetch=async()=>new Response(sample.replace('LABEL','new'));
loader.schedule(JSON.stringify({...base,title:'new'}),state.chart,{mode:'gantt'},null);
await pause(200);
resolveOld(new Response(sample.replace('LABEL','obsolete')));
await pause(20);
assert.deepEqual(frames,['new']);assert.deepEqual(errors,[]);
loader.cancel();
assert.equal(q('#chart-summary'),null);
console.log('Passed stale in-flight response rejection and removed date summary.');
