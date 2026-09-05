/** Baselines are read-only snapshots; choosing one never replaces the editor. */
import {parseChart} from './model.mjs';

export function wireComparison({isAttached, getPath, hasLocalServer, chooseCurrentFile, onChange}) {
  const q = id => document.getElementById(id);
  let baseline = null, baselineLabel = '', enabled = false, generation = 0;
  let loadingBaseline = false;
  const status = text => { q('compare-status').textContent = text; };
  const updateConfirm = () => {q('confirm-compare').disabled=loadingBaseline || !baseline;};
  const accept = (text, label) => {
    const document = JSON.parse(text);
    parseChart(document);
    baseline = document;
    baselineLabel = label;
    enabled = true;
    q('compare-enabled').checked = true;
    status(`Baseline: ${label} · compared with the current editor`);
    onChange();
  };
  q('compare-upload').addEventListener('click', () => q('compare-file').click());
  q('open-compare').addEventListener('click', () => q('compare-dialog').showModal());
  q('close-compare').addEventListener('click', () => q('compare-dialog').close());
  q('confirm-compare').addEventListener('click', () => {
    if (loadingBaseline || !baseline) return;
    onChange();
    q('compare-dialog').close();
  });
  q('compare-enabled').addEventListener('change', event => {enabled=event.target.checked; onChange();});
  q('compare-mode-toggle').addEventListener('change', event => {
    enabled=event.target.checked;
    if (enabled && !baseline) q('compare-dialog').showModal();
    onChange();
  });
  q('compare-file').addEventListener('change', async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    const ticket = ++generation;
    loadingBaseline=true; updateConfirm();
    try {
      const source = await file.text();
      if (ticket !== generation) return;
      accept(source, file.name);
      q('compare-revisions').value = '';
    } catch (error) { if (ticket === generation) status(`Could not load baseline: ${error.message}`); }
    finally {if(ticket===generation){loadingBaseline=false;updateConfirm();}}
    event.target.value = '';
  });
  const loadHistory = async () => {
    if (!hasLocalServer()) {
      status('Git history runs on the local server. Open this GUI with jsonantt serve; uploaded baseline files also work here.');
      return;
    }
    if (!isAttached()) {
      status('Choose the current file on disk to locate its Git history. Your unsaved editor will be kept.');
      chooseCurrentFile(() => loadHistory());
      return;
    }
    const ticket = ++generation;
    status('Loading this file’s Git history…');
    loadingBaseline=false; updateConfirm();
    try {
      const response = await fetch(`api/history?${new URLSearchParams({path:getPath()})}`);
      if (!response.headers.get('Content-Type')?.includes('application/json')) throw new Error('Git history needs the updated server. Restart jsonantt serve and refresh this page.');
      const data = await response.json();
      if (ticket !== generation) return;
      if (!response.ok) throw new Error(data.error);
      const list = q('compare-revisions');
      list.replaceChildren(...data.revisions.map(revision => {
        const option = document.createElement('option');
        option.value = revision.sha;
        option.textContent = `${revision.date} · ${revision.sha.slice(0, 8)} · ${revision.message}`;
        return option;
      }));
      list.selectedIndex = -1;
      list.hidden = !data.revisions.length;
      status(data.revisions.length ? `${data.file}: choose a baseline revision (latest ${data.limit} file commits).` : 'No committed versions of this file.');
    } catch (error) { if (ticket === generation) status(error.message); }
  };
  q('compare-history').addEventListener('click', loadHistory);
  q('compare-revisions').addEventListener('change', async event => {
    const sha = event.target.value;
    if (!sha) return;
    const label = event.target.selectedOptions[0].textContent;
    const ticket = ++generation;
    status('Loading baseline revision…');
    loadingBaseline=true; updateConfirm();
    try {
      const response = await fetch(`api/history?${new URLSearchParams({path:getPath(),revision:sha})}`);
      const source = await response.text();
      if (ticket !== generation) return;
      if (!response.ok) throw new Error(JSON.parse(source).error);
      accept(source, label);
    } catch (error) { if (ticket === generation) status(`Could not load revision: ${error.message}`); }
    finally {if(ticket===generation){loadingBaseline=false;updateConfirm();}}
  });
  return {
    get baseline() { return baseline; },
    get enabled() { return enabled; },
    snapshot() { return {baseline, enabled, label:baselineLabel, revisions:[...q('compare-revisions').options].map(option=>({sha:option.value,label:option.textContent})), revision:q('compare-revisions').value}; },
    restore(saved) {
      if (!saved) return;
      if (saved.baseline) parseChart(saved.baseline);
      baseline = saved.baseline || null;
      baselineLabel = saved.label || 'Restored baseline';
      enabled = saved.enabled ?? Boolean(baseline);
      status(baseline ? `Baseline: ${baselineLabel} · compared with the current editor` : 'Choose another JSON file or a Git revision as the baseline.');
      q('compare-revisions').replaceChildren(...(saved.revisions || []).map(entry=>{
        const option=document.createElement('option'); option.value=entry.sha; option.textContent=entry.label; return option;
      }));
      q('compare-revisions').hidden = !q('compare-revisions').options.length;
      q('compare-revisions').value = saved.revision || '';
    },
    sync() {
      updateConfirm();
      q('compare-current-file').textContent = `Current file: ${isAttached() ? getPath() : 'unsaved editor (locate its file with Git history…)'} `;
      q('compare-baseline-file').textContent = `Baseline: ${baseline ? baselineLabel : 'none selected'}`;
      q('compare-mode-toggle').checked = enabled;
      q('compare-enabled').checked = enabled;
      q('compare-indicator').hidden = !enabled;
      q('compare-history').disabled = false;
      q('compare-history').title = isAttached() ? `Browse Git history: ${getPath()}` : 'Locate the current file and browse its Git history';
    },
    reset() {
      generation++;
      baseline = null;
      baselineLabel = '';
      enabled = false;
      loadingBaseline = false;
      q('compare-revisions').replaceChildren();
      q('compare-revisions').hidden = true;
      status('Choose another JSON file or a Git revision as the baseline.');
    },
  };
}
