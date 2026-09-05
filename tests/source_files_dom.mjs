import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {prepareSourceFiles,wireSourceFiles} from '../jsonantt/web/source-files.mjs';
const require=createRequire(resolve(process.argv[2],'package.json'));
const {JSDOM}=require('jsdom');
const dom=new JSDOM(readFileSync(new URL('../jsonantt/web/index.html',import.meta.url),'utf8'),{url:'http://127.0.0.1:4187/'});
globalThis.document=dom.window.document;
dom.window.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
dom.window.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');this.dispatchEvent(new dom.window.Event('close'));};
const nativeFetch=globalThis.fetch;
globalThis.fetch=(url,options)=>nativeFetch(new URL(url,dom.window.location.href),options);
const q=id=>document.getElementById(id);
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(check){for(let i=0;i<1000;i++){if(check())return;await wait(10);}assert.fail(q('include-status').textContent);}
let opened=null;
wireSourceFiles({useServer:()=>true,onOpen:source=>{opened=JSON.parse(source);}});
const leaf=name=>({tasks:[{name,start:'2026-01-01',duration:'1w'}]});
const root={title:'Keep title',tasks:[{name:'Parent',filename:'nested/phase.json'}]};
const dependencies={
  'nested/phase.json':{tasks:[{filename:'work.json'},{filename:'fallback.json'}]},
  'nested/work.json':leaf('Relative first'),
  'work.json':leaf('Wrong duplicate'),
  'fallback.json':leaf('Working directory fallback'),
};
function select(id,files){Object.defineProperty(q(id),'files',{configurable:true,value:files});q(id).dispatchEvent(new dom.window.Event('change'));}
select('source-file',[{name:'composed.json',text:async()=>JSON.stringify(root)}]);
await until(()=>q('include-dialog').open);
assert.match(q('include-status').textContent,/nested\/phase.json/);
assert(q('include-confirm').disabled);
assert.equal(opened,null,'No partial import while dependencies are missing');
select('include-folder',Object.entries(dependencies).map(([path,document])=>({name:path.split('/').at(-1),webkitRelativePath:'project/'+path,text:async()=>JSON.stringify(document)})));
await until(()=>!q('include-confirm').disabled);
q('include-confirm').click();
await until(()=>opened);
assert.equal(opened.title,'Keep title');
assert.deepEqual(opened.tasks[0].tasks.map(task=>task.name),['Relative first','Working directory fallback']);
assert(!q('include-dialog').open);
assert(!JSON.stringify(opened).includes('filename'));
// A flat picker can still resolve a single nested include by its supplied name.
const flat=prepareSourceFiles(root,'composed.json',new Map([
  ['phase.json',{tasks:[{filename:'work.json'}]}],['work.json',leaf('Flat selection')],
]),new Set(['phase.json','work.json']));
assert.deepEqual(flat.missing,[]);
assert.throws(()=>prepareSourceFiles({tasks:[{filename:'a.json'}]},'main.json',new Map([
  ['a.json',{tasks:[{filename:'a.json'}]}],
])),/Circular filename/);
opened=null;
select('source-file',[{name:'composed.json',text:async()=>JSON.stringify(root)}]);
await until(()=>q('include-dialog').open);
q('include-close').click();assert.equal(opened,null);
console.log('Passed composed-file upload, folder paths, relative-first/working-directory fallback, atomic confirmation, flat selection, cycles and cancel.');
dom.window.close();
