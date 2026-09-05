/** Server-side file picker: keep full paths, never infer them from upload names. */
export function wireLocalFiles({onOpen}) {
  const q = id => document.getElementById(id);
  const dialog = q('local-file-dialog');
  let generation = 0;
  let selectFile = onOpen;
  const error = message => { q('local-file-status').textContent = message; };
  const request = async (endpoint, path) => {
    const response = await fetch(`${endpoint}?${new URLSearchParams(path ? {path} : {})}`);
    if (!response.headers.get('Content-Type')?.includes('application/json')) throw new Error('Local file access needs the updated server. Restart jsonantt serve and refresh this page.');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    return data;
  };
  const open = async path => {
    const ticket = ++generation;
    try {
      error(`Opening ${path}…`);
      const file = await request('api/project', path);
      if (ticket !== generation) return;
      selectFile(file);
      dialog.close();
    } catch (failure) { if (ticket === generation) error(failure.message); }
  };
  const browse = async path => {
    const ticket = ++generation;
    error('Loading directory…');
    try {
      const data = await request('api/files', path);
      if (ticket !== generation) return;
      q('local-file-path').value = data.path;
      const entries = [{name:'..',path:data.parent,directory:true}, ...data.entries];
      q('local-file-list').replaceChildren(...entries.map(entry => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = `${entry.name}${entry.directory ? '/' : ''}`;
        button.title = entry.path;
        if (!entry.directory) button.setAttribute('aria-pressed','false');
        button.addEventListener('click', () => {
          if (entry.directory) {browse(entry.path);return;}
          q('local-file-path').value=entry.path;
          q('local-file-list').querySelectorAll('[aria-pressed]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
          error(`Selected: ${entry.path}. Click ${q('local-file-open').textContent} to confirm.`);
        });
        if (!entry.directory) button.addEventListener('dblclick',()=>open(entry.path));
        return button;
      }));
      error(data.truncated ? 'First 1,000 entries shown. Enter a full path to open another file.' : 'Select a JSON file, or enter its full path and click Open.');
    } catch (failure) { if (ticket === generation) error(failure.message); }
  };
  const show = callback => {
    selectFile=callback || onOpen;
    q('local-file-open').textContent=callback ? 'Use this file':'Open file';
    dialog.showModal(); browse();
  };
  q('open-local-file').addEventListener('click', () => show());
  q('local-file-browse').addEventListener('click', () => browse(q('local-file-path').value));
  q('local-file-open').addEventListener('click', () => open(q('local-file-path').value));
  q('local-file-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => generation++);
  return {open:show};
}
