/** Runtime core, shared by the web worker and the real-WASM acceptance test. */
export const PYODIDE_VERSION = '314.0.6';
export const PYODIDE_INDEX = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

export async function loadPythonRenderer({loadPyodide, sourceArchive, indexURL=PYODIDE_INDEX, onProgress=()=>{}}) {
  onProgress('Loading Python, matplotlib and fonts (first use)…');
  // Download packages during interpreter startup instead of afterwards.
  const [python,archive] = await Promise.all([
    loadPyodide({indexURL, packages:['matplotlib'], stdout:()=>{}, stderr:()=>{}}),
    sourceArchive,
  ]);
  onProgress('Loading the shared chart renderer…');
  python.unpackArchive(archive, 'zip', {extractDir:'/home/pyodide'});
  const module = python.pyimport('jsonantt.browser_renderer');
  return {
    render(source, options) {
      const result = module.render_json(source, JSON.stringify(options));
      try { return result.toJs().slice(); }
      finally { result.destroy(); }
    },
  };
}
