/** Lazy singleton worker; source data stays inside the browser on static hosts. */
let worker, sequence = 0;
const pending = new Map();
const MIME = {svg:'image/svg+xml',png:'image/png',csv:'text/csv'};
let warming;
export function warmBrowserRenderer() {
  warming ||= renderInBrowser('',{warmup:true}).catch(()=>{warming=null;});
  return warming;
}

export function renderInBrowser(source, options, {signal,onProgress=()=>{}}={}) {
  if (signal?.aborted) return Promise.reject(new DOMException('Cancelled','AbortError'));
  if (typeof Worker === 'undefined') return Promise.reject(new Error('This browser cannot run the Python renderer. Use a browser with WebAssembly/workers, or jsonantt serve.'));
  if (!worker) {
    worker = new Worker(new URL('./python-worker.mjs',import.meta.url),{type:'module'});
    worker.onmessage = ({data}) => {
      const request = pending.get(data.id);
      if (!request) return;
      if (data.progress) {request.onProgress(data.progress); return;}
      request.cleanup();
      if (data.error) request.reject(new Error(data.error));
      else request.resolve(new Blob([data.bytes],{type:MIME[request.format]}));
    };
    worker.onerror = () => {
      const error = new Error('Could not load the Python renderer. Check network/CDN access and WebAssembly support, or use jsonantt serve.');
      for (const request of [...pending.values()]) {request.cleanup(); request.reject(error);}
      worker.terminate();
      worker = null;
    };
  }
  return new Promise((resolve,reject)=>{
    const id = ++sequence;
    const cleanup = () => {pending.delete(id); signal?.removeEventListener('abort',abort);};
    const abort = () => {worker?.postMessage({id,cancel:true}); cleanup(); reject(new DOMException('Cancelled','AbortError'));};
    pending.set(id,{resolve,reject,cleanup,onProgress,format:options.format || 'svg'});
    signal?.addEventListener('abort',abort,{once:true});
    worker.postMessage({id,source,options});
  });
}
