/** Stage multiple task files, then append atomically through the shared parser. */
import {renderInBrowser} from './python-client.mjs';

export function wireAppend({getSource, useServer, sourceName, onAppend}) {
  const q=id=>document.getElementById(id);
  let files=[], generation=0, busy=false;
  const message=text=>{q('append-status').textContent=text;};
  const normalize=path=>{
    const parts=[];
    for(const part of path.replaceAll('\\','/').split('/')) {
      if(part==='..')parts.pop(); else if(part && part!=='.')parts.push(part);
    }
    return parts.join('/');
  };
  const render=()=>{
    q('append-list').replaceChildren(...files.map((file,index)=>{
      const row=document.createElement('div');row.className='append-file';
      const label=document.createElement('label');
      const checked=document.createElement('input');checked.type='checkbox';checked.checked=file.selected;
      checked.disabled=busy;
      checked.addEventListener('change',()=>{file.selected=checked.checked;render();});
      const name=document.createElement('span');name.textContent=file.name;
      label.append(checked,name);row.append(label);
      for(const [text,delta] of [['↑',-1],['↓',1]]) {
        const button=document.createElement('button');button.type='button';button.textContent=text;
        button.setAttribute('aria-label',`Move ${file.name} ${delta<0?'up':'down'}`);
        button.disabled=index+delta<0 || index+delta>=files.length || busy;
        button.addEventListener('click',()=>{[files[index],files[index+delta]]=[files[index+delta],files[index]];render();});
        row.append(button);
      }
      return row;
    }));
    q('confirm-append').disabled=busy || !files.some(file=>file.selected);
    for(const id of ['append-pick','append-folder-pick','append-placement'])q(id).disabled=busy;
  };
  const stage=async event=>{
    const ticket=++generation;
    busy=true;render();
    try {
      const loaded=await Promise.all([...event.target.files].filter(file=>file.name.toLowerCase().endsWith('.json')).map(async file=>{
        const document=JSON.parse(await file.text());
        if(!document || typeof document!=='object' || Array.isArray(document))throw new Error(`${file.name}: expected a JSON object`);
        return {name:normalize(file.webkitRelativePath || file.name),document,selected:true};
      }));
      if(ticket!==generation)return;
      const names=new Set(files.map(file=>file.name));
      for(const file of loaded) {
        if(names.has(file.name))throw new Error(`${file.name} is already loaded. Clear the list before replacing it.`);
        names.add(file.name);
      }
      files.push(...loaded);
      // Dependency files are available for resolution but aren't also appended twice.
      const dependencies=new Set();
      const visit=(value,owner)=>{
        if(!value || typeof value!=='object')return;
        if(typeof value.filename==='string') dependencies.add(normalize(owner.slice(0,owner.lastIndexOf('/')+1)+value.filename));
        Object.values(value).forEach(child=>visit(child,owner));
      };
      files.forEach(file=>visit(file.document,file.name));
      files.forEach(file=>{if(dependencies.has(file.name))file.selected=false;});
      message('Checked files append in the order shown. Unchecked files remain available for filename includes. Imported styles/titles/arrows are not merged.');
      render();
    } catch(error){if(ticket===generation)message(error.message);}
    finally {if(ticket===generation){busy=false;render();}}
    event.target.value='';
  };
  q('open-append').addEventListener('click',()=>{
    q('append-dialog').showModal();render();
    message('Append task trees to the current document. Imported files become editable snapshots, not live file links.');
  });
  q('append-pick').addEventListener('click',()=>q('append-files').click());
  q('append-folder-pick').addEventListener('click',()=>q('append-folder').click());
  q('append-files').addEventListener('change',stage);
  q('append-folder').addEventListener('change',stage);
  q('append-clear').addEventListener('click',()=>{generation++;files=[];busy=false;render();message('File list cleared.');});
  q('close-append').addEventListener('click',()=>q('append-dialog').close());
  q('append-dialog').addEventListener('close',()=>{generation++;busy=false;});
  q('confirm-append').addEventListener('click',async()=>{
    const original=getSource(), ticket=++generation;
    busy=true;render();message('Appending task files…');
    try {
      const payload={document:JSON.parse(original),files:Object.fromEntries(files.map(file=>[file.name,file.document])),
        append:files.filter(file=>file.selected).map(file=>file.name),wrap:q('append-placement').value==='wrapped',source_name:sourceName()};
      let source;
      if(useServer()) {
        const response=await fetch('api/compose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        if(!response.headers.get('Content-Type')?.includes('application/json'))throw new Error('Restart jsonantt serve to enable the composition API.');
        source=await response.text();
        if(!response.ok)throw new Error(JSON.parse(source).error);
      } else {
        const blob=await renderInBrowser(JSON.stringify(payload),{action:'compose',format:'json'},{onProgress:message});
        source=await blob.text();
      }
      if(ticket!==generation)return;
      if(getSource()!==original)throw new Error('The editor changed while files were loading. Review it and click Append again.');
      onAppend(source);
      files=[];
      q('append-dialog').close();
    } catch(error){if(ticket===generation)message(`Could not append: ${error.message}`);}
    finally {if(ticket===generation){busy=false;render();}}
  });
}
