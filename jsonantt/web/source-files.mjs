/** Resolve uploaded includes in a virtual directory, never an OS/Pyodide path. */
import {renderInBrowser} from './python-client.mjs';

export function normalizeFilePath(path) {
  const parts=[];
  for (const part of path.replaceAll('\\','/').split('/')) {
    if (part==='..' && parts.length && parts.at(-1)!=='..') parts.pop();
    else if (part && part!=='.') parts.push(part);
  }
  return parts.join('/');
}

export function prepareSourceFiles(source, sourceName, supplied, flatNames=new Set()) {
  const files={}, missing=new Set();
  const expand=(data, owner, seen)=>{
    const copy=structuredClone(data);
    const visit=item=>{
      if (!item || typeof item!=='object') return;
      if (typeof item.filename==='string') {
        const reference=normalizeFilePath(item.filename.startsWith('/') ? item.filename : owner.slice(0,owner.lastIndexOf('/')+1)+item.filename);
        // Individual file pickers expose basenames only; folder picks preserve paths.
        const flatName=normalizeFilePath(item.filename).split('/').at(-1);
        const workingPath=normalizeFilePath(item.filename);
        const key=supplied.has(reference) ? reference : supplied.has(workingPath) ? workingPath : flatNames.has(flatName) ? flatName : null;
        if (!key) missing.add(reference);
        else {
          if (seen.has(key)) throw new Error(`Circular filename reference: ${key}`);
          files[key]=expand(supplied.get(key),key,new Set([...seen,key]));
          // compose_document resolves from each owner's directory.
          item.filename='/'+key;
        }
      }
      for (const child of [...(item.tasks || []),...(item.children || [])]) visit(child);
    };
    for (const item of [...(copy.tasks || []),...(copy.children || [])]) visit(item);
    return copy;
  };
  const document=expand(source,sourceName,new Set([sourceName]));
  return {document,files:Object.fromEntries(Object.entries(files).map(([name,data])=>['/'+name,data])),missing:[...missing]};
}

export function wireSourceFiles({useServer,onOpen}) {
  const q=id=>document.getElementById(id);
  const dialog=q('include-dialog');
  let root, rootName, supplied=new Map(), flatNames=new Set(), generation=0;
  const status=text=>{q('include-status').textContent=text;};
  const inspect=()=>{
    const prepared=prepareSourceFiles(root,rootName,supplied,flatNames);
    q('include-confirm').disabled=prepared.missing.length>0;
    status(prepared.missing.length ? `Select these files (or the folder containing ${rootName}): ${prepared.missing.join(', ')}` : 'All referenced files are available. Open composed chart to confirm.');
    return prepared;
  };
  q('source-file').addEventListener('change',async event=>{
    const file=event.target.files?.[0];
    if (!file) return;
    const ticket=++generation;
    try {
      const source=await file.text();
      if(ticket!==generation)return;
      let document;
      try {document=JSON.parse(source);} catch {onOpen(source);return;}
      if(!document || typeof document!=='object' || Array.isArray(document)){onOpen(source);return;}
      root=document;rootName=file.name;supplied=new Map();flatNames=new Set();
      const prepared=prepareSourceFiles(root,rootName,supplied);
      if(!prepared.missing.length){onOpen(source);return;}
      dialog.showModal();inspect();
    } catch(error) {dialog.showModal();status(error.message);}
    finally {event.target.value='';}
  });
  const stage=async event=>{
    const ticket=++generation;
    q('include-confirm').disabled=true;
    try {
      const additions=await Promise.all([...event.target.files].filter(file=>file.name.toLowerCase().endsWith('.json')).map(async file=>{
        // webkitRelativePath includes the selected directory name; its contents
        // form the virtual root alongside the already selected source file.
        const name=normalizeFilePath(file.webkitRelativePath ? file.webkitRelativePath.split('/').slice(1).join('/') : file.name);
        return [name,JSON.parse(await file.text()),!file.webkitRelativePath];
      }));
      if(ticket!==generation)return;
      supplied=new Map([...supplied,...additions]);
      for(const [name,,flat] of additions) {if(flat)flatNames.add(name);else flatNames.delete(name);}
      const roots=[...supplied].filter(([name,data])=>name.split('/').at(-1)===rootName.split('/').at(-1) && JSON.stringify(data)===JSON.stringify(root));
      if(roots.length===1)rootName=roots[0][0];
      inspect();
    } catch(error){if(ticket===generation)status(error.message);}
    finally {event.target.value='';}
  };
  q('include-files').addEventListener('change',stage);
  q('include-folder').addEventListener('change',stage);
  q('include-pick').addEventListener('click',()=>q('include-files').click());
  q('include-folder-pick').addEventListener('click',()=>q('include-folder').click());
  q('include-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>generation++);
  q('include-confirm').addEventListener('click',async()=>{
    const ticket=++generation;
    q('include-confirm').disabled=true;
    try {
      const {document,files,missing}=prepareSourceFiles(root,rootName,supplied,flatNames);
      if(missing.length)throw new Error(`Missing included files: ${missing.join(', ')}`);
      const payload={document,files,append:[],source_name:rootName};
      status('Opening composed chart…');
      let source;
      if(useServer()) {
        const response=await fetch('api/compose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        source=await response.text();
        if(!response.ok)throw new Error(JSON.parse(source).error);
      } else {
        source=await (await renderInBrowser(JSON.stringify(payload),{action:'compose',format:'json'},{onProgress:status})).text();
      }
      if(ticket!==generation)return;
      onOpen(source);dialog.close();
    } catch(error){if(ticket===generation){status(error.message);q('include-confirm').disabled=false;}}
  });
}
