// Run with the directory containing an npm-installed, pinned Pyodide package.
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {loadPythonRenderer} from '../jsonantt/web/python-runtime.mjs';
const require = createRequire(resolve(process.argv[2],'package.json'));
const {loadPyodide} = require('pyodide');
const sourceArchive = new Uint8Array(readFileSync(resolve(process.argv[2],'site/python/jsonantt.zip')));
const engine = await loadPythonRenderer({loadPyodide,sourceArchive,
  indexURL:resolve(process.argv[2],'node_modules/pyodide')+'/',onProgress:console.log});
const source = JSON.stringify({title:'WASM chart',style:{value_prefix:'$',value_scale:'millions',number_milestones:true},tasks:[
  {name:'Parent',tasks:[{name:'Work',id:'work',start:'2026-01-01',end:'2026-04-01',cost:1250000},
    {name:'Gate',id:'gate',milestone:true,date:'2026-04-01'}]},
],arrows:[{from:'work',to:'gate',color:'#123456'}]});
for (const mode of ['gantt','table','burn','burndown','burnup','burn-table']) {
  const options = {mode,burn:{period:'quarter',group:'leaf'}};
  const svg = new TextDecoder().decode(engine.render(source,{...options,format:'svg',interactive:true}));
  assert(svg.includes('<svg'),mode);
  assert(svg.includes('studio-'),mode+' has no interaction targets');
  assert(!svg.includes('<image'),mode+' must be vector');
  if (mode==='gantt') assert(svg.includes('studio-arrow-0--'));
  const png = engine.render(source,{...options,format:'png',dpi:40});
  assert.deepEqual([...png.slice(0,8)],[137,80,78,71,13,10,26,10]);
  assert.deepEqual(png,engine.render(source,{...options,format:'png',dpi:40,interactive:true}));
  console.log(`Passed WASM ${mode}: interactive SVG and identical PNG drawing.`);
}
const csv = new TextDecoder().decode(engine.render(source,{mode:'table',format:'csv',tableFilter:'milestones'}));
assert(csv.includes('Gate') && !csv.includes('Work'));
assert.throws(()=>engine.render(source,{mode:'gantt',format:'csv'}),/CSV/);
const rolled = new TextDecoder().decode(engine.render(JSON.stringify({...JSON.parse(source),style:{render_depth:1,rollup_milestones:true}}),{mode:'gantt',format:'svg',interactive:true}));
assert(rolled.includes('studio-task-1.2--rolled-'));
console.log('Passed WASM filtering, validation, and rolled-up milestone targeting.');
const year=new Date().getFullYear();
const current=JSON.stringify({style:{today_marker:true},tasks:[
  {name:'Current work',start:`${year}-01-01`,end:`${year+1}-01-01`,cost:100},
]});
for (const mode of ['burndown','burnup']) {
  for (const interactive of [false,true]) {
    const svg=new TextDecoder().decode(engine.render(current,{mode,format:'svg',interactive}));
    assert(svg.includes('chart-date-marker') && svg.includes('Today'));
  }
}
console.log('Passed WASM burndown/burnup today markers in preview and export.');
const comparison=JSON.stringify({planned:JSON.parse(source),actual:JSON.parse(source)});
for(const mode of ['gantt','table','burn','burndown','burnup','burn-table']) {
  const options={mode:`compare-${mode}`,format:'svg',interactive:true};
  const svg=new TextDecoder().decode(engine.render(comparison,options));
  assert(svg.includes('<svg') && !svg.includes('<image'),mode+' comparison must remain vector');
  const png=engine.render(comparison,{...options,format:'png',dpi:40});
  assert.deepEqual([...png.slice(0,8)],[137,80,78,71,13,10,26,10]);
  if(mode.endsWith('table')) assert(new TextDecoder().decode(engine.render(comparison,{...options,format:'csv'})).includes('Parent'));
}
console.log('Passed WASM all six comparison modes: SVG, PNG and table CSV exports.');
const composition={document:{title:'Main',tasks:[]},files:{'phase.json':{tasks:[{filename:'work.json'}]},'work.json':{tasks:[{name:'Imported',start:'2026-01-01',duration:'1w'}]}},append:['phase.json'],wrap:true};
const composed=JSON.parse(new TextDecoder().decode(engine.render(JSON.stringify(composition),{action:'compose',format:'json'})));
assert.equal(composed.tasks[0].name,'phase');
assert.equal(composed.tasks[0].tasks[0].name,'Imported');
assert(!JSON.stringify(composed).includes('filename'));
console.log('Passed WASM portable multi-file composition through the shared Python parser.');
