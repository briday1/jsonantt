/** Versioned exact-SVG cache. Never substitute a drawing for different source/options. */
export function previewKey(source, options) {
  const settings = (options.mode.startsWith('burn') || options.mode.startsWith('compare-burn'))
    ? {mode:options.mode,field:options.field ?? 'cost',period:options.period ?? 'month',group:String(options.group ?? '0'),factor:Number(options.factor ?? 1)}
    : {mode:options.mode,renderDepth:Number(options.renderDepth ?? 0),...(options.mode.endsWith('table') ? {tableFilter:options.tableFilter ?? 'all'} : {})};
  const doc = JSON.parse(source);
  // Today's marker invalidates an otherwise identical preview at midnight.
  const day = (doc.style?.today_marker || doc.planned?.style?.today_marker) ? [new Date().toDateString(),new Date().toISOString().slice(0,10)] : null;
  return JSON.stringify([doc,settings,day]);
}

export function createPreviewStore(version) {
  if (!version) return null; // Live local sources are not versioned builds.
  let database, bundled;
  const open = () => database ||= new Promise(resolve=>{
    if (!globalThis.indexedDB) return resolve(null);
    const request = indexedDB.open('jsonantt-exact-previews',1);
    request.onupgradeneeded = () => request.result.createObjectStore('previews',{keyPath:'key'});
    request.onsuccess = () => resolve(request.result);
    request.onerror = request.onblocked = () => resolve(null);
  });
  const digest = async key => {
    const bytes = await crypto.subtle.digest('SHA-256',new TextEncoder().encode(version+'\n'+key));
    return [...new Uint8Array(bytes)].map(byte=>byte.toString(16).padStart(2,'0')).join('');
  };
  const read = async key => {
    try {
      const db = await open();
      if (!db) return null;
      const hashed = await digest(key);
      return await new Promise(resolve=>{
        const request = db.transaction('previews').objectStore('previews').get(hashed);
        request.onsuccess = () => resolve(request.result?.svg || null);
        request.onerror = () => resolve(null);
      });
    } catch {return null;}
  };
  return {
    async get(key) {
      const cached = await read(key);
      if (cached) return cached;
      try {
        bundled ||= fetch(new URL('./startup-previews.json',import.meta.url),{cache:'no-cache'})
          .then(response=>response.ok ? response.json() : null).catch(()=>null);
        const data = await bundled;
        if (data?.version !== version) return null;
        return data.previews.find(item=>previewKey(item.source,item.options) === key)?.svg || null;
      } catch {return null;}
    },
    async put(key,svg) {
      if (svg.length > 2_000_000) return;
      try {
        const db = await open();
        if (!db) return;
        const hashed = await digest(key);
        const tx = db.transaction('previews','readwrite'), entries = tx.objectStore('previews');
        tx.onerror = () => {}; // Quota/private-mode failures cannot break rendering.
        entries.put({key:hashed,svg,updated:Date.now()});
        const all = entries.getAll();
        all.onsuccess = () => {
          let size = 0;
          all.result.sort((a,b)=>b.updated-a.updated).forEach((entry,index)=>{
            size += entry.svg.length;
            if (index >= 12 || size > 4_000_000) entries.delete(entry.key);
          });
        };
      } catch {/* Storage is optional. */}
    },
  };
}
