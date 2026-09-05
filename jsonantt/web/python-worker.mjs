/** All Python drawing stays off the UI thread, including PNG/CSV export. */
import {loadPythonRenderer, PYODIDE_INDEX} from './python-runtime.mjs';

let runtime, queue = Promise.resolve();
const cancelled = new Set();
const requests = new Set();
async function renderer(id) {
  if (!runtime) runtime = (async()=>{
    const sourceArchive = fetch(new URL('./python/jsonantt.zip', import.meta.url), {cache:'no-cache'}).then(response=>{
      if (!response.ok) throw new Error('Python renderer bundle is missing. Build the static site with python -m jsonantt.static_site.');
      return response.arrayBuffer();
    });
    const loadPyodide = async options => (await import(`${PYODIDE_INDEX}pyodide.mjs`)).loadPyodide(options);
    return loadPythonRenderer({loadPyodide, sourceArchive,
      onProgress:message=>self.postMessage({id, progress:message})});
  })().catch(error=>{runtime=null; throw error;});
  return runtime;
}
self.onmessage = ({data}) => {
  if (data.cancel) {if (requests.has(data.id)) cancelled.add(data.id); return;}
  const {id,source,options} = data;
  requests.add(id);
  queue = queue.then(async()=>{
    try {
      if (cancelled.has(id)) return;
      const engine = await renderer(id);
      // Let pending cancel/new-source messages run before starting CPU work.
      await new Promise(resolve=>setTimeout(resolve,0));
      if (cancelled.has(id)) return;
      const bytes = options.warmup ? new Uint8Array() : engine.render(source,options);
      self.postMessage({id,bytes},[bytes.buffer]);
    } catch (error) {
      self.postMessage({id,error:error.message});
    } finally {cancelled.delete(id); requests.delete(id);}
  });
};
