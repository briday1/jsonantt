import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(resolve(process.argv[2],'package.json'));
const {JSDOM}=require('jsdom');
const origin='http://127.0.0.1:4187/';
const dom=new JSDOM(readFileSync(new URL('../jsonantt/web/index.html',import.meta.url),'utf8'),{url:origin,pretendToBeVisual:true});
for(const key of ['window','document','localStorage','HTMLElement','HTMLLabelElement','navigator','DOMParser'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
const nativeFetch=globalThis.fetch;
globalThis.fetch=(url,options)=>nativeFetch(new URL(url,origin),options);
const q=selector=>document.querySelector(selector);
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(check,message){for(let i=0;i<1000;i++){if(check())return;await wait(10);}assert.fail(message+': '+q('#status').textContent);}
const {state}=await import('../jsonantt/web/app.mjs');
await until(()=>state.chart,'boot');
const original={dateformat:'%d/%m/%Y',tasks:[{id:'chain',name:'Gates',milestone:true,date:['01/06/2026','10/07/2026']}]};
const inputs=()=>[...document.querySelectorAll('.milestone-date-list input')];
function change(input,value){input.value=value;input.dispatchEvent(new window.Event('change'));}
async function select(mode,source=original){
  q('#source').value=JSON.stringify(source);q('#source').dispatchEvent(new window.Event('input'));
  q(`[data-canvas-tab="${mode}"]`).click();
  await until(()=>q('#canvas > svg')?.dataset.previewMode===mode && q('#canvas').getAttribute('aria-busy')!=='true','preview');
  q('#canvas [data-key="tasks.0"]').dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
}
for(const mode of ['gantt','table']) {
  await select(mode);
  assert.deepEqual(inputs().map(input=>input.value),original.tasks[0].date);
  assert.equal(q('.milestone-date-list').querySelectorAll('.date-trigger').length,2);
  assert.deepEqual(state.doc,original,'Opening properties must not rewrite source');
  // The first calendar must change only the first entry, in the source format.
  q('.milestone-date-list .date-trigger').click();
  assert.equal(q('.date-picker').parentElement,document.body,'Calendar escapes inspector clipping');
  [...document.querySelectorAll('.date-picker-day')].find(button=>button.textContent==='15').click();
  assert.deepEqual(state.doc.tasks[0].date,['15/06/2026','10/07/2026']);
  change(inputs()[1],'20/07/2026');
  change(inputs()[0],'16/06/2026');
  assert.deepEqual(state.doc.tasks[0].date,['16/06/2026','20/07/2026'],'Repeated edits use the current source, not stale objects');
  const before=state.source;
  q('[data-action="add-milestone-date"]').click();
  assert.equal(inputs().length,3);
  assert.equal(state.source,before,'A blank added row is a draft, not a source date');
  change(inputs()[2],'not a date');
  assert(!inputs()[2].checkValidity());assert.equal(state.source,before);
  change(inputs()[2],'01/08/2026');
  assert.deepEqual(state.doc.tasks[0].date,['16/06/2026','20/07/2026','01/08/2026']);
  document.querySelectorAll('.milestone-date-list li > button')[1].click();
  assert.deepEqual(state.doc.tasks[0].date,['16/06/2026','01/08/2026']);
  q('#undo-source').click();
  assert.deepEqual(state.doc.tasks[0].date,['16/06/2026','20/07/2026','01/08/2026']);
  assert.equal(inputs().length,3);
  q('#redo-source').click();assert.equal(inputs().length,2);
  q('.milestone-date-list li > button').click();
  assert.deepEqual(state.doc.tasks[0].date,['01/08/2026'],'A one-entry chain must stay an array');
  q('.milestone-date-list li > button').click();
  assert.deepEqual(state.doc.tasks[0].date,[]);
  q('[data-action="add-milestone-date"]').click();change(inputs()[0],'05/08/2026');
  assert.deepEqual(state.doc.tasks[0].date,['05/08/2026']);
  assert.equal(state.doc.tasks[0].id,'chain');
  assert.equal(state.doc.tasks[0].name,'Gates');
}
await select('gantt',{...original,tasks:[{...original.tasks[0],date:'01/06/2026'}]});
change(inputs()[0],'02/06/2026');assert.equal(state.doc.tasks[0].date,'02/06/2026');
q('[data-action="add-milestone-date"]').click();change(inputs()[1],'03/06/2026');
assert.deepEqual(state.doc.tasks[0].date,['02/06/2026','03/06/2026']);
console.log('Passed per-date milestone rows/calendars, repeated edits, add/remove, validation, undo/redo, array/scalar preservation and Gantt/Table selection.');
await until(()=>q('#canvas').getAttribute('aria-busy')!=='true','final preview');
await wait(10); // Flush queued workspace writes before disposing the test document.
dom.window.close();
