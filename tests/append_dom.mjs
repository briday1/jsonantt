import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(resolve(process.argv[2],'package.json'));
const {JSDOM}=require('jsdom');
const origin='http://127.0.0.1:4187/';
const dom=new JSDOM(readFileSync(new URL('../jsonantt/web/index.html',import.meta.url),'utf8'),{url:origin,pretendToBeVisual:true});
for(const key of ['window','document','localStorage','HTMLElement','HTMLLabelElement','navigator','DOMParser'])Object.defineProperty(globalThis,key,{value:dom.window[key],configurable:true});
dom.window.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
dom.window.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');this.dispatchEvent(new window.Event('close'));};
const nativeFetch=globalThis.fetch;
globalThis.fetch=(url,options)=>nativeFetch(new URL(url,origin),options);
const q=selector=>document.querySelector(selector);
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(check,message){for(let i=0;i<1000;i++){if(check())return;await wait(10);}assert.fail(message+': '+q('#append-status').textContent);}
const {state}=await import('../jsonantt/web/app.mjs');
await until(()=>state.chart,'boot');
const original=JSON.stringify({title:'Main',dateformat:'%d/%m/%Y',style:{background:'#ffffff'},tasks:[{id:'existing',name:'Existing',start:'01/01/2026',duration:'1w'}]});
q('#source').value=original;q('#source').dispatchEvent(new window.Event('input'));
const files=[
  {name:'phase.json',document:{title:'Do not import',style:{background:'red'},tasks:[{filename:'work.json'}]}},
  {name:'work.json',document:{tasks:[{id:'work',name:'Work',start:'2026-02-01',duration:'2w',cost:100}]}},
  {name:'delivery.json',document:{tasks:[{id:'delivery',name:'Delivery',not_before:'work',duration:'1w'}]}},
];
q('#open-append').click();
Object.defineProperty(q('#append-files'),'files',{configurable:true,value:files.map(file=>({name:file.name,text:async()=>JSON.stringify(file.document)}))});
q('#append-files').dispatchEvent(new window.Event('change'));
await until(()=>q('#append-list').children.length===3,'file staging');
assert.deepEqual([...q('#append-list').querySelectorAll('input')].map(input=>input.checked),[true,false,true]);
q('#append-placement').value='wrapped';
q('#confirm-append').click();
await until(()=>!q('#append-dialog').open,'append confirmation');
assert.equal(state.doc.title,'Main');assert.equal(state.doc.style.background,'#ffffff');
assert.deepEqual(state.doc.tasks.map(task=>task.name),['Existing','phase','delivery']);
assert.equal(state.doc.tasks[1].tasks[0].start,'01/02/2026');
assert.equal(state.doc.tasks[1].tasks[0].cost,100);
assert.equal(state.doc.tasks[2].tasks[0].not_before,'work');
assert(!state.source.includes('filename'));
q('#undo-source').click();assert.equal(state.source,original);
q('#redo-source').click();assert.equal(state.doc.tasks.length,3);
const composed=state.source;
q('#open-append').click();
Object.defineProperty(q('#append-files'),'files',{configurable:true,value:[{name:'duplicate.json',text:async()=>JSON.stringify({tasks:[{id:'existing',name:'Oops'}]})}]});
q('#append-files').dispatchEvent(new window.Event('change'));
await until(()=>q('#append-list').children.length===1,'duplicate staging');
q('#confirm-append').click();
await until(()=>q('#append-status').textContent.includes('Duplicate task ID'),'atomic error');
assert.equal(state.source,composed);assert(q('#append-dialog').open);
console.log('Passed multi-file composition, include dependency selection, wrapper placement, date conversion, preserved source/style, atomic undo/redo and duplicate rejection.');
dom.window.close();
