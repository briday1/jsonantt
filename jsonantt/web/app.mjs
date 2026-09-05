/**
 * jsonantt studio – a Pugflow-styled source/canvas workspace for jsonantt JSON
 * documents. The JSON source stays the single source of truth: every canvas or
 * inspector interaction rewrites the document and the views re-render from it.
 */
import { parseChart, taskAtPath, removeTaskAtPath, taskRelations, formatDate, parseDate, applyDuration } from './model.mjs';
import { availableBurnFields, numericAmount } from './burn.mjs';
import { renderChartSettings } from './settings.mjs';
import { attachDatePicker } from './datepicker.mjs';
import { formatSourceData } from './format.mjs';
import { exportChart, setExportBackend } from './export.mjs';
import { highlightJson } from './highlight.mjs';
import { DEMOS, STARTER } from './demo-charts.mjs';
import { wireInspectorDrag } from './inspector-drag.mjs';
import { createPreviewLoader } from './preview.mjs';
import { createPreviewStore } from './preview-store.mjs';
import { warmBrowserRenderer } from './python-client.mjs';

const STORAGE_SOURCE = 'jsonantt.source';
const STORAGE_THEME = 'jsonantt.theme';
const HISTORY_LIMIT = 100;

const $ = (selector) => document.querySelector(selector);

const state = {
  source: '',
  doc: null,
  chart: null,
  error: null,
  selection: null, // { kind: 'task' | 'arrow', key, path?, index? }
  canvasTab: 'gantt',
  tableFilter: 'all',
  burn: { field: 'cost', period: 'month', group: '0', factor: 1 },
  zoom: 100,
  showArrows: true,
  todayMarker: false,
  serverPreview: false,
  serverBurnPreview: false, // Older local servers may support burn views only.
  settingsFocus: 'general',
  undoStack: [],
  redoStack: [],
};

const elements = {
  source: $('#source'),
  lineNumbers: $('#line-numbers'),
  highlightLayer: $('#highlight-layer'),
  highlightCode: $('#highlight-code'),
  status: $('#status'),
  canvas: $('#canvas'),
  toast: $('#canvas-toast'),
  inspector: $('#canvas-inspector'),
  inspectorContent: $('#inspector-content'),
  taskList: $('#task-list'),
  milestoneList: $('#milestone-list'),
  arrowList: $('#arrow-list'),
  settingsDialog: $('#settings-dialog'),
  settingsContent: $('#settings-content'),
  main: document.querySelector('main'),
};

const chartPreview = createPreviewLoader({
  store: createPreviewStore(document.querySelector('meta[name="jsonantt-static-build"]')?.content),
  useBrowser: options => !(state.serverPreview || (state.serverBurnPreview && options.mode.startsWith('burn'))),
  onProgress: message => {
    const loading = elements.canvas.querySelector(':scope > .burn-empty');
    if (loading) loading.textContent = message;
    else setStatus(message);
  },
  onPending: ({mode}) => {
    elements.canvas.setAttribute('aria-busy', 'true');
    const current = elements.canvas.querySelector(':scope > svg[data-renderer="python"]');
    if (current?.dataset.previewMode !== mode) {
      const loading = document.createElement('p');
      loading.className = 'burn-empty';
      loading.setAttribute('role', 'status');
      loading.textContent = 'Rendering preview…';
      elements.canvas.replaceChildren(loading);
    }
  },
  onRender: view => {
    elements.canvas.replaceChildren(view);
    updateCanvasSelection();
    elements.canvas.setAttribute('aria-busy', 'false');
    elements.canvas.classList.remove('preview-invalid');
    delete elements.canvas.dataset.error;
    applyCanvasZoom();
    if (!state.serverPreview && !state.serverBurnPreview) {
      // Paint the cached/bundled SVG first; prepare Python without blocking it.
      setTimeout(()=>{void warmBrowserRenderer();},500);
    }
  },
  onError: message => {
    elements.canvas.setAttribute('aria-busy', 'false');
    const loading = elements.canvas.querySelector(':scope > .burn-empty');
    if (loading) loading.textContent = `Renderer preview: ${message}`;
    else {
      elements.canvas.classList.add('preview-invalid');
      elements.canvas.dataset.error = `Renderer preview: ${message}`;
    }
    setStatus(`Renderer preview: ${message}`, 'error');
  },
});

// --------------------------------------------------------------- source I/O

function setSource(text, { pushHistory = true, refreshEditor = true, preserveInspector = false } = {}) {
  if (pushHistory && text !== state.source) {
    state.undoStack.push(state.source);
    if (state.undoStack.length > HISTORY_LIMIT) state.undoStack.shift();
    state.redoStack.length = 0;
  }
  state.source = text;
  if (refreshEditor) elements.source.value = text;
  try {
    localStorage.setItem(STORAGE_SOURCE, text);
  } catch (error) {
    /* storage is optional */
  }
  renderLineNumbers();
  renderHighlight();
  compile({ preserveInspector });
}

function compile({ preserveInspector = false } = {}) {
  try {
    const doc = JSON.parse(state.source);
    state.doc = doc;
    state.chart = parseChart(doc);
    state.showArrows = state.chart.style.show_arrows !== false;
    state.todayMarker = Boolean(state.chart.style.today_marker);
    const burnFields = availableBurnFields(state.chart);
    if (burnFields.length && !burnFields.includes(state.burn.field)) {
      state.burn.field = burnFields.includes('cost') ? 'cost' : burnFields[0];
      $('#burn-field').value = state.burn.field;
    }
    state.error = null;
    setStatus(`${state.chart.flat.length} task${state.chart.flat.length === 1 ? '' : 's'} · ${state.chart.arrows.length} arrow${state.chart.arrows.length === 1 ? '' : 's'}`, 'ready');
  } catch (error) {
    state.error = error.message || String(error);
    setStatus(state.error, 'error');
  }
  renderCanvas();
  renderObjects();
  renderSettings();
  if (!preserveInspector) renderInspector();
}

function setStatus(message, kind) {
  elements.status.textContent = message;
  elements.status.className = `status ${kind || ''}`.trim();
}

function renderLineNumbers() {
  const lines = elements.source.value.split('\n').length;
  const fragment = document.createDocumentFragment();
  for (let index = 1; index <= lines; index += 1) {
    const span = document.createElement('span');
    span.textContent = String(index);
    fragment.append(span);
  }
  elements.lineNumbers.replaceChildren(fragment);
  elements.lineNumbers.style.transform = `translateY(${-elements.source.scrollTop}px)`;
}

/** Keep the syntax-highlight overlay in sync with the editor content. */
function renderHighlight() {
  if (!elements.highlightCode) return;
  elements.highlightCode.innerHTML = highlightJson(`${elements.source.value}\n`);
  syncHighlightScroll();
}

function syncHighlightScroll() {
  if (!elements.highlightLayer) return;
  elements.highlightLayer.style.transform = `translate(${-elements.source.scrollLeft}px, ${-elements.source.scrollTop}px)`;
}

/** Serialise the in-memory document back into the editor (canonical style). */
function commitDoc({ preserveInspector = false } = {}) {
  setSource(formatSourceData(state.doc), { preserveInspector });
}

// ----------------------------------------------------------------- rendering

function renderCanvas() {
  chartPreview.cancel();
  elements.canvas.setAttribute('aria-busy', 'false');
  const fields = availableBurnFields(state.chart);
  if (!fields.length && state.canvasTab.startsWith('burn')) state.canvasTab = 'gantt';
  document.querySelectorAll('[data-canvas-tab]').forEach((button) => {
    button.hidden = button.dataset.canvasTab.startsWith('burn') && !fields.length;
    const active = button.dataset.canvasTab === state.canvasTab;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  });
  const saveCsvButton = document.getElementById('save-csv');
  if (saveCsvButton) saveCsvButton.hidden = !['table', 'burn-table'].includes(state.canvasTab);
  $('#table-filter-control').hidden = state.canvasTab !== 'table';
  $('#burn-controls').hidden = !state.canvasTab.startsWith('burn');
  $('#gantt-controls').hidden = state.canvasTab !== 'gantt';
  if (!state.chart) {
    elements.canvas.classList.add('preview-invalid');
    elements.canvas.dataset.error = state.error || 'Invalid JSON';
    return;
  }
  const options = {
    selectedKey: state.selection ? state.selection.key : null,
    showArrows: state.showArrows,
    todayMarker: state.todayMarker,
    tableFilter: state.tableFilter,
  };
  const depthControl = $('#gantt-depth');
  const selectedDepth = Number(state.chart.style.render_depth || 0);
  const depths = Math.max(selectedDepth, ...state.chart.flat.map(task=>task.depth + 1), 1);
  depthControl.replaceChildren(...Array.from({length:depths + 1}, (_,depth)=>{
    const option = document.createElement('option');
    option.value = String(depth);
    option.textContent = depth === 0 ? 'All tasks' : depth === 1 ? 'Top-level tasks' : `${depth} levels`;
    return option;
  }));
  depthControl.value = String(selectedDepth);
  $('#gantt-rollup-milestones').checked = Boolean(state.chart.style.rollup_milestones);
  if (state.canvasTab.startsWith('burn')) {
    $('#burn-fields').replaceChildren(...fields.map((key) => { const option = document.createElement('option'); option.value = key; return option; }));
    const group = $('#burn-group');
    group.querySelectorAll('[data-depth]').forEach((option) => option.remove());
    const maxDepth = Math.max(0, ...state.chart.flat.map((task) => task.depth));
    for (let depth = 1; depth <= maxDepth; depth++) {
      const option = document.createElement('option'); option.value = String(depth); option.dataset.depth = 'true'; option.textContent = `Task depth ${depth}`; group.append(option);
    }
    group.value = state.burn.group;
  }
  if (!state.error) {
    const previewOptions = state.canvasTab.startsWith('burn')
      ? {mode:state.canvasTab, ...state.burn}
      : {mode:state.canvasTab, tableFilter:state.tableFilter, renderDepth:state.chart.style.render_depth};
    chartPreview.schedule(state.source, state.chart, previewOptions, options.selectedKey);
  }
  elements.canvas.classList.toggle('preview-invalid', Boolean(state.error));
  if (state.error) elements.canvas.dataset.error = state.error;
  else delete elements.canvas.dataset.error;

}

function treeItem({ key, title, subtitle, color, selected }) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `tree-item${selected ? ' selected' : ''}`;
  button.dataset.key = key;
  button.setAttribute('role', 'listitem');
  const swatch = document.createElement('span');
  swatch.className = 'tree-swatch';
  swatch.style.background = color || 'transparent';
  const copy = document.createElement('span');
  copy.className = 'tree-copy';
  const strong = document.createElement('strong');
  strong.textContent = title;
  const small = document.createElement('small');
  small.textContent = subtitle;
  copy.append(strong, small);
  button.append(swatch, copy);
  return button;
}

function renderObjects() {
  if (!state.chart) return;
  const chart = state.chart;
  const selectedKey = state.selection ? state.selection.key : null;

  const tasks = document.createDocumentFragment();
  chart.flat.forEach((task) => {
    const start = task.effectiveStart ? formatDate(task.effectiveStart, chart.dateFormat) : '—';
    const end = task.effectiveEnd ? formatDate(task.effectiveEnd, chart.dateFormat) : '—';
    const item = treeItem({
      key: task.key,
      title: `${'· '.repeat(task.depth)}${task.name}`,
      subtitle: task.milestone ? `milestone · ${start}` : `${start} → ${end}`,
      color: task.milestone ? (task.color || '#FFD700') : task.resolvedColor,
      selected: selectedKey === task.key,
    });
    item.dataset.kind = 'task';
    tasks.append(item);
  });
  elements.taskList.replaceChildren(tasks);
  $('#task-count').textContent = String(chart.flat.length);
  if (!chart.flat.length) elements.taskList.append(emptyNote('No tasks yet'));

  const milestones = chart.flat.filter((task) => task.milestone);
  const milestoneFragment = document.createDocumentFragment();
  milestones.forEach((task) => {
    const item = treeItem({
      key: task.key,
      title: task.name,
      subtitle: task.milestoneDates.map((date) => formatDate(date, chart.dateFormat)).join(', ') || '—',
      color: task.color || '#FFD700',
      selected: selectedKey === task.key,
    });
    item.dataset.kind = 'task';
    milestoneFragment.append(item);
  });
  elements.milestoneList.replaceChildren(milestoneFragment);
  $('#milestone-count').textContent = String(milestones.length);
  if (!milestones.length) elements.milestoneList.append(emptyNote('No milestones'));

  const arrowFragment = document.createDocumentFragment();
  chart.arrows.forEach((arrow) => {
    const key = `arrow.${arrow.index}`;
    const item = treeItem({
      key,
      title: arrow.label || `${arrow.from} → ${arrow.to}`,
      subtitle: `${arrow.from} → ${arrow.to}`,
      color: arrow.color,
      selected: selectedKey === key,
    });
    item.dataset.kind = 'arrow';
    arrowFragment.append(item);
  });
  elements.arrowList.replaceChildren(arrowFragment);
  $('#arrow-count').textContent = String(chart.arrows.length);
  if (!chart.arrows.length) elements.arrowList.append(emptyNote('No arrows'));
}

function emptyNote(text) {
  const note = document.createElement('p');
  note.className = 'layers-empty';
  note.textContent = text;
  return note;
}

// ------------------------------------------------------------ chart settings

/** Re-render the chart settings form from the current document. */
function renderSettings() {
  if (!elements.settingsContent || !elements.settingsDialog) return;
  renderChartSettings(elements.settingsContent, state.doc, {
    initialFocus: state.settingsFocus,
    onCommit: () => commitDoc({ preserveInspector: true }),
  });
  state.settingsFocus = 'general';
}

// ---------------------------------------------------------------- selection

function updateCanvasSelection() {
  elements.canvas.querySelectorAll('[data-key]').forEach(node=>{
    node.classList.toggle('selected-element',node.dataset.key === state.selection?.key);
  });
}

function selectKey(key, kind) {
  if (!key) {
    state.selection = null;
  } else if (kind === 'arrow') {
    state.selection = { kind: 'arrow', key, index: Number(key.split('.')[1]) };
  } else {
    const task = state.chart ? state.chart.flat.find((entry) => entry.key === key) : null;
    state.selection = task ? { kind: 'task', key, path: task.path } : null;
  }
  updateCanvasSelection();
  renderObjects();
  renderInspector();
}

function selectedTask() {
  if (!state.selection || state.selection.kind !== 'task' || !state.chart) return null;
  return state.chart.flat.find((task) => task.key === state.selection.key) || null;
}

// ---------------------------------------------------------------- inspector

function field(labelText, inputElement, help) {
  // Composite controls (e.g. a date input + calendar trigger wrapper) must not
  // live inside a <label>, or clicks on the trigger would refocus the input.
  const container = inputElement instanceof HTMLLabelElement || !inputElement.classList.contains('date-field')
    ? document.createElement('label')
    : document.createElement('div');
  if (container.tagName === 'DIV') container.className = 'inspector-field';
  const span = document.createElement('span');
  span.textContent = labelText;
  container.append(span, inputElement);
  if (help) {
    const hint = document.createElement('small');
    hint.className = 'inspector-help';
    hint.textContent = help;
    container.append(hint);
  }
  return container;
}

function textInput(value, onChange, { type = 'text', placeholder = '' } = {}) {
  const input = document.createElement('input');
  input.type = type;
  input.value = value === null || value === undefined ? '' : String(value);
  input.placeholder = placeholder;
  input.addEventListener('input', () => onChange(input.value, input));
  return input;
}

function dateInput(value, onChange, dateFormat, { placeholder = '' } = {}) {
  const input = textInput(value, onChange, { placeholder });
  const wrapper = attachDatePicker(input, { format: dateFormat, onPick: (text) => { input.value = text; onChange(text, input); } });
  return wrapper || input;
}

function updateRaw(raw, key, value) {
  if (value === '' || value === null || value === undefined || value === false) delete raw[key];
  else raw[key] = value;
  commitDoc({ preserveInspector: true });
}

function renderInspector() {
  const container = elements.inspectorContent;
  if (!state.selection || !state.chart) {
    elements.inspector.hidden = true;
    container.replaceChildren();
    return;
  }
  elements.inspector.hidden = false;
  const fragment = document.createDocumentFragment();

  if (state.selection.kind === 'arrow') {
    const arrow = state.chart.arrows[state.selection.index];
    if (!arrow) {
      elements.inspector.hidden = true;
      return;
    }
    const raw = arrow.raw;
    fragment.append(field('From (task id)', textInput(raw.from, (value) => updateRaw(raw, 'from', value))));
    fragment.append(field('To (task id)', textInput(raw.to, (value) => updateRaw(raw, 'to', value))));
    fragment.append(field('Label', textInput(raw.label, (value) => updateRaw(raw, 'label', value))));
    fragment.append(field('Colour', textInput(raw.color || '#888888', (value) => updateRaw(raw, 'color', value), { type: 'color' })));
    const endpoints = document.createElement('div');
    endpoints.className = 'inspector-relations';
    endpoints.append(relationGroup('Upstream endpoint', [state.chart.byId.get(arrow.from)].filter(Boolean).map((related) => ({ task: related, via: 'arrow' })), 'Unknown "from" id.'));
    endpoints.append(relationGroup('Downstream endpoint', [state.chart.byId.get(arrow.to)].filter(Boolean).map((related) => ({ task: related, via: 'arrow' })), 'Unknown "to" id.'));
    fragment.append(endpoints);
    container.replaceChildren(fragment);
    return;
  }

  const task = selectedTask();
  if (!task) {
    elements.inspector.hidden = true;
    return;
  }
  const raw = task.raw;
  const dateFormat = state.chart.dateFormat;

  fragment.append(field('Name', textInput(raw.name || '', (value) => updateRaw(raw, 'name', value))));
  const addSubtask = document.createElement('button');
  addSubtask.id = 'inspector-add-subtask';
  addSubtask.type = 'button';
  addSubtask.textContent = 'Add subtask';
  addSubtask.addEventListener('click', () => addTask({ asChild: true }));
  fragment.append(addSubtask);
  fragment.append(field('ID', textInput(raw.id, (value) => updateRaw(raw, 'id', value)), 'Used by arrows and not_before'));

  const cost = textInput(raw.cost, (value, input) => {
    const trimmed = value.trim();
    const plain = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(trimmed);
    const amount = plain ? Number(trimmed) : trimmed;
    if (trimmed && numericAmount(amount) === null) {
      input.setCustomValidity('Enter a numeric amount, optionally with a currency prefix or unit suffix.');
      return;
    }
    input.setCustomValidity('');
    updateRaw(taskAtPath(state.doc, task.path), 'cost', amount);
  }, {placeholder:'e.g. 125000 or $125,000'});
  cost.dataset.field = 'cost';
  fragment.append(field('Cost', cost, 'Source amount before display scaling. Blank removes the cost.'));

  let startControl;
  let endControl;
  let durationControl;
  const controlInput = (control) => control.matches('input') ? control : control.querySelector('input');
  const validDate = (value) => {
    try { return value ? parseDate(value, dateFormat) : null; } catch (error) { return null; }
  };
  const commitSynchronized = () => commitDoc({ preserveInspector: true });
  const setRaw = (key, value) => {
    if (value === '' || value === null || value === undefined) delete raw[key];
    else raw[key] = value;
  };
  const effectiveStartText = raw.start || (task.effectiveStart ? formatDate(task.effectiveStart, dateFormat) : '');
  const effectiveEndText = raw.end || (task.effectiveEnd ? formatDate(task.effectiveEnd, dateFormat) : '');

  startControl = dateInput(effectiveStartText, (value) => {
    setRaw('start', value);
    const start = validDate(value);
    if (start && raw.duration) {
      try {
        raw.end = formatDate(applyDuration(start, raw.duration), dateFormat);
        controlInput(endControl).value = raw.end;
      } catch (error) { /* retain the typed duration until it becomes valid */ }
    } else if (start && raw.end) {
      const end = validDate(raw.end);
      if (end && end >= start) {
        raw.duration = `${Math.round((end - start) / 86400000)}d`;
        controlInput(durationControl).value = raw.duration;
      }
    }
    commitSynchronized();
  }, dateFormat, { placeholder: formatDate(new Date(), dateFormat) });
  endControl = dateInput(effectiveEndText, (value) => {
    setRaw('end', value);
    const start = validDate(raw.start || effectiveStartText);
    const end = validDate(value);
    if (start && end && end >= start) {
      raw.duration = `${Math.round((end - start) / 86400000)}d`;
      controlInput(durationControl).value = raw.duration;
    }
    commitSynchronized();
  }, dateFormat);
  durationControl = textInput(raw.duration, (value) => {
    setRaw('duration', value);
    const start = validDate(raw.start || effectiveStartText);
    if (start && value) {
      try {
        raw.end = formatDate(applyDuration(start, value), dateFormat);
        controlInput(endControl).value = raw.end;
      } catch (error) { /* retain partial input while typing */ }
    }
    commitSynchronized();
  }, { placeholder: '6w' });

  const grid = document.createElement('div');
  grid.className = 'inspector-grid';
  grid.append(
    field('Start', startControl),
    field('End', endControl),
  );
  fragment.append(grid);

  const grid2 = document.createElement('div');
  grid2.className = 'inspector-grid';
  grid2.append(
    field('Duration', durationControl),
  );
  fragment.append(grid2);

  const notBefore = document.createElement('select');
  const noDependency = document.createElement('option');
  noDependency.value = '';
  noDependency.textContent = 'None';
  notBefore.append(noDependency);
  state.chart.flat.forEach((candidate) => {
    if (!candidate.id || candidate.key === task.key) return;
    const option = document.createElement('option');
    option.value = candidate.id;
    option.textContent = `${candidate.id} — ${candidate.name}`;
    notBefore.append(option);
  });
  // Keep an existing source reference visible even if it is unresolved.
  if (raw.not_before && ![...notBefore.options].some((option) => option.value === raw.not_before)) {
    const option = document.createElement('option');
    option.value = raw.not_before;
    option.textContent = `${raw.not_before} — unavailable`;
    notBefore.append(option);
  }
  notBefore.value = raw.not_before || '';
  notBefore.addEventListener('change', () => {
    updateRaw(taskAtPath(state.doc, task.path), 'not_before', notBefore.value);
    renderInspector();
  });
  fragment.append(field('Not before', notBefore, 'Choose a task by ID and name; only its ID is saved.'));

  fragment.append(field('Colour', textInput(raw.color || task.resolvedColor || '#4472C4', (value) => updateRaw(raw, 'color', value), { type: 'color' })));

  const milestoneToggle = document.createElement('label');
  milestoneToggle.className = 'inspector-switch';
  const milestoneInput = document.createElement('input');
  milestoneInput.type = 'checkbox';
  milestoneInput.checked = Boolean(raw.milestone || raw.major_milestone);
  milestoneInput.addEventListener('change', () => {
    updateRaw(raw, 'milestone', milestoneInput.checked);
    renderInspector();
  });
  const milestoneLabel = document.createElement('span');
  milestoneLabel.textContent = 'Milestone';
  milestoneToggle.append(milestoneInput, milestoneLabel);
  fragment.append(milestoneToggle);

  const majorToggle = document.createElement('label');
  majorToggle.className = 'inspector-switch';
  const majorInput = document.createElement('input');
  majorInput.type = 'checkbox';
  majorInput.checked = Boolean(raw.major_milestone);
  majorInput.addEventListener('change', () => {
    updateRaw(raw, 'major_milestone', majorInput.checked);
    renderInspector();
  });
  const majorLabel = document.createElement('span');
  majorLabel.textContent = 'Major milestone';
  majorToggle.append(majorInput, majorLabel);
  fragment.append(majorToggle);

  if (raw.milestone || raw.major_milestone) {
    const commitDates = (value) => {
      const parts = value.split(',').map((part) => part.trim()).filter(Boolean);
      if (!parts.length) updateRaw(raw, 'date', '');
      else updateRaw(raw, 'date', parts.length === 1 ? parts[0] : parts);
    };
    fragment.append(field('Milestone date(s)', dateInput(
      Array.isArray(raw.date) ? raw.date.join(', ') : raw.date,
      commitDates,
      dateFormat,
    ), 'Comma separated for milestone chains; the calendar edits the last date'));
  }

  const description = document.createElement('textarea');
  description.rows = 3;
  description.value = raw.description || '';
  description.addEventListener('input', () => updateRaw(raw, 'description', description.value));
  fragment.append(field('Description', description));

  fragment.append(relationsSection(task));

  container.replaceChildren(fragment);
}

const RELATION_LABELS = {
  not_before: 'depends on date',
  arrow: 'dependency arrow',
  parent: 'parent task',
  subtask: 'subtask',
};

/** Build the upstream/downstream relationship view for a selected task. */
function relationsSection(task) {
  const { upstream, downstream } = taskRelations(state.chart, task);
  const details = document.createElement('details');
  details.className = 'inspector-relations';
  details.open = true;
  const summary = document.createElement('summary');
  summary.textContent = `Relationships (${upstream.length + downstream.length})`;
  details.append(summary);

  details.append(relationGroup('Depends on (upstream)', upstream, 'Nothing upstream of this entry.'));
  details.append(relationGroup('Feeds into (downstream)', downstream, 'Nothing depends on this entry.'));
  return details;
}

function relationGroup(title, entries, emptyText) {
  const group = document.createElement('div');
  group.className = 'relation-group';
  const heading = document.createElement('strong');
  heading.textContent = title;
  group.append(heading);
  if (!entries.length) {
    const note = document.createElement('p');
    note.className = 'inspector-empty';
    note.textContent = emptyText;
    group.append(note);
    return group;
  }
  entries.forEach(({ task: related, via }) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'relation-chip';
    const name = document.createElement('span');
    name.textContent = related.name;
    const badge = document.createElement('small');
    badge.textContent = RELATION_LABELS[via] || via;
    button.append(name, badge);
    button.addEventListener('click', () => selectKey(related.key, 'task'));
    group.append(button);
  });
  return group;
}

// ------------------------------------------------------------------ actions

function toast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add('show');
  window.setTimeout(() => elements.toast.classList.remove('show'), 1600);
}

function addTask({ asChild = false, milestone = false } = {}) {
  if (!state.doc) return;
  const parentTask = asChild ? selectedTask() : null;
  if (asChild && !parentTask) return;
  const parentRaw = parentTask ? parentTask.raw : state.doc;
  const bucketKey = Array.isArray(parentRaw.children) && !Array.isArray(parentRaw.tasks) ? 'children' : 'tasks';
  if (!Array.isArray(parentRaw[bucketKey])) parentRaw[bucketKey] = [];
  const today = new Date();
  const iso = formatDate(new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())), state.chart ? state.chart.dateFormat : '%Y-%m-%d');
  const entry = milestone
    ? { name: 'New milestone', milestone: true, date: iso }
    : { name: 'New task', start: iso, duration: '4w' };
  const createdPath = [...(parentTask?.path || []), bucketKey, parentRaw[bucketKey].length];
  parentRaw[bucketKey].push(entry);
  commitDoc();
  const created = state.chart?.flat.find((task) => task.key === createdPath.join('.'));
  if (created) selectKey(created.key, 'task');
  toast(milestone ? 'Milestone added' : asChild ? 'Subtask added' : 'Task added');
}

function deleteSelection() {
  if (!state.selection || !state.doc) return;
  if (state.selection.kind === 'arrow') {
    if (Array.isArray(state.doc.arrows)) state.doc.arrows.splice(state.selection.index, 1);
  } else if (state.selection.path) {
    removeTaskAtPath(state.doc, state.selection.path);
  }
  state.selection = null;
  commitDoc();
  toast('Deleted');
}

function download(filename, content, type) {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.append(link);
  link.click();
  setTimeout(() => {
    link.remove();
    URL.revokeObjectURL(url);
  }, 1000);
}

/**
 * Export through the shared Python renderer, locally or in the Pyodide worker.
 */
async function exportCanvas(format, { dpi } = {}) {
  if (!state.source) return false;
  const source = state.source;
  const options = canvasExportOptions();
  const { mode } = options;
  try {
    const blob = await exportChart(source, { ...options, format, dpi });
    download(`${mode}.${format}`, blob, blob.type);
    toast(`${format.toUpperCase()} exported via CLI renderer`);
    return true;
  } catch (error) {
    setStatus(`Export: ${error.message}`, 'error');
    return false;
  }
}

function canvasExportOptions() {
  return {
    mode: state.canvasTab,
    tableFilter: state.tableFilter,
    renderDepth: Number(state.chart?.style.render_depth || 0),
    burn: { ...state.burn },
  };
}

async function copyExportedSvg() {
  if (!state.source) return;
  const source = state.source;
  const options = canvasExportOptions();
  const { mode } = options;
  try {
    const blob = await exportChart(source, { ...options, format: 'svg' });
    const text = await blob.text();
    try {
      await navigator.clipboard.writeText(text);
      toast('SVG copied (CLI renderer)');
    } catch (error) {
      download(`${mode}.svg`, blob, blob.type);
    }
  } catch (error) {
    setStatus(`Export: ${error.message}`, 'error');
  }
}

/** Open the chart settings dialog (optionally focused on a section). */
function openSettings(focus = 'general') {
  if (!elements.settingsDialog) return;
  state.settingsFocus = focus;
  renderSettings();
  elements.settingsDialog.showModal();
}

// -------------------------------------------------------------------- wiring

function wireEditor() {
  elements.source.addEventListener('input', () => {
    setSource(elements.source.value, { refreshEditor: false });
  });
  elements.source.addEventListener('scroll', () => {
    renderLineNumbers();
    syncHighlightScroll();
  });
}

function wireCanvas() {
  $('#gantt-depth').addEventListener('change', event => {
    state.doc.style ||= {};
    state.doc.style.render_depth = Number(event.target.value);
    commitDoc({preserveInspector:true});
  });
  $('#gantt-rollup-milestones').addEventListener('change', event => {
    state.doc.style ||= {};
    state.doc.style.rollup_milestones = event.target.checked;
    commitDoc({preserveInspector:true});
  });
  $('#table-filter').addEventListener('change', (event) => {
    state.tableFilter = event.target.value;
    renderCanvas();
  });
  for (const [id, key] of [['burn-field', 'field'], ['burn-period', 'period'], ['burn-group', 'group'], ['burn-factor', 'factor']]) {
    $(`#${id}`).addEventListener('change', (event) => {
      state.burn[key] = key === 'factor' ? (event.target.value === '' ? NaN : Number(event.target.value)) : event.target.value;
      renderCanvas();
    });
  }
  document.querySelectorAll('[data-canvas-tab]').forEach((button) => {
    button.addEventListener('click', () => {
      state.canvasTab = button.dataset.canvasTab;
      document.querySelectorAll('[data-canvas-tab]').forEach((other) => {
        const active = other === button;
        other.classList.toggle('active', active);
        other.setAttribute('aria-selected', String(active));
      });
      renderCanvas();
    });
  });

  elements.canvas.addEventListener('click', (event) => {
    const target = event.target.closest('.selectable');
    if (!target) {
      selectKey(null);
      return;
    }
    selectKey(target.dataset.key, target.dataset.kind);
  });

  elements.canvas.addEventListener('dblclick', (event) => {
    if (state.canvasTab === 'table' && event.target.closest('.studio-table, svg[data-preview-mode="table"]')) {
      openSettings('table');
    }
  });

  elements.canvas.addEventListener('keydown', (event) => {
    const target = event.target.closest('.selectable');
    if (target && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      selectKey(target.dataset.key, target.dataset.kind);
    }
  });

  [elements.taskList, elements.milestoneList, elements.arrowList].forEach((list) => {
    list.addEventListener('click', (event) => {
      const item = event.target.closest('.tree-item');
      if (item) selectKey(item.dataset.key, item.dataset.kind);
    });
  });

  $('#close-inspector').addEventListener('click', () => selectKey(null));
  $('#delete-selection').addEventListener('click', deleteSelection);
}

function applyCanvasZoom() {
  const view = elements.canvas.querySelector('svg, .table-wrap');
  if (view) {
    view.style.transform = 'none';
    view.style.zoom = String(state.zoom / 100);
  }
}

function setZoom(value) {
  state.zoom = Math.max(25, Math.min(400, Math.round(value)));
  const select = $('#canvas-zoom');
  let option = [...select.options].find((entry) => Number(entry.value) === state.zoom);
  if (!option) {
    option = select.querySelector('option[data-custom]') || document.createElement('option');
    option.dataset.custom = 'true';
    option.value = String(state.zoom);
    option.textContent = `${state.zoom}%`;
    if (!option.parentElement) select.append(option);
  }
  select.value = String(state.zoom);
  applyCanvasZoom();
}

function wireZoom() {
  $('#zoom-in').addEventListener('click', () => setZoom(state.zoom + 25));
  $('#zoom-out').addEventListener('click', () => setZoom(state.zoom - 25));
  $('#canvas-zoom').addEventListener('change', (event) => setZoom(Number(event.target.value)));
  $('#zoom-fit').addEventListener('click', () => {
    const svg = elements.canvas.querySelector('svg');
    const table = elements.canvas.querySelector('.table-wrap');
    if (!svg && !table) return;
    const available = elements.canvas.clientWidth - 44;
    const intrinsicWidth = svg ? Number(svg.getAttribute('width')) : Number.parseFloat(table.style.width);
    if (intrinsicWidth) setZoom((available / intrinsicWidth) * 100);
  });
  document.querySelector('.canvas-shell').addEventListener('wheel', (event) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    setZoom(state.zoom + (event.deltaY < 0 ? 10 : -10));
  }, { passive: false });
}

function wirePanels() {
  wireInspectorDrag(elements.inspector, $('.canvas-shell'), $('.inspector-drag-handle'));
  const main = elements.main;
  const toggleSource = $('#toggle-source');
  toggleSource.addEventListener('click', () => {
    const collapsed = main.classList.toggle('source-collapsed');
    toggleSource.setAttribute('aria-expanded', String(!collapsed));
    toggleSource.querySelector('.toggle-arrow').textContent = collapsed ? '›' : '‹';
  });
  const toggleLayers = $('#toggle-layers');
  toggleLayers.addEventListener('click', () => {
    const collapsed = main.classList.toggle('layers-collapsed');
    toggleLayers.setAttribute('aria-expanded', String(!collapsed));
    toggleLayers.querySelector('.toggle-arrow').textContent = collapsed ? '‹' : '›';
  });

  const drag = (handle, property, compute, bodyClass) => {
    handle.addEventListener('pointerdown', (event) => {
      handle.setPointerCapture(event.pointerId);
      document.body.classList.add(bodyClass);
      const move = (moveEvent) => {
        main.style.setProperty(property, `${compute(moveEvent)}px`);
      };
      const stop = (upEvent) => {
        handle.releasePointerCapture(upEvent.pointerId);
        document.body.classList.remove(bodyClass);
        handle.removeEventListener('pointermove', move);
        handle.removeEventListener('pointerup', stop);
      };
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', stop);
    });
  };
  drag($('#panel-resizer'), '--panel-width', (event) => Math.max(280, Math.min(760, event.clientX)), 'resizing-panel');
  drag($('#graph-panel-resizer'), '--layers-open-width', (event) => Math.max(180, Math.min(520, window.innerWidth - event.clientX)), 'resizing-graphs');
}

function wireToolbar() {
  $('#new-chart').addEventListener('click', () => {
    setSource(JSON.stringify({ title: 'New chart', dateformat: '%Y-%m-%d', tasks: [] }, null, 2));
    selectKey(null);
  });
  $('#load-source').addEventListener('click', () => $('#source-file').click());
  $('#source-file').addEventListener('change', async (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    setSource(await file.text());
    selectKey(null);
    event.target.value = '';
  });
  $('#save-source').addEventListener('click', () => download('chart.json', state.source, 'application/json'));
  $('#export-chart').addEventListener('click', () => {
    $('#export-error').hidden = true;
    const viewName = { gantt: 'Gantt', table: 'Table', burn: 'Burn', burndown: 'Burndown', burnup: 'Burnup', 'burn-table': 'Burn table' }[state.canvasTab];
    $('#export-view-name').textContent = state.canvasTab === 'table'
      ? `${viewName} — ${$('#table-filter').selectedOptions[0].textContent}` : viewName;
    $('#export-dialog').showModal();
  });
  $('#export-format').addEventListener('change', (event) => {
    $('#export-dpi-field').hidden = event.target.value !== 'png';
  });
  $('#confirm-export').addEventListener('click', async () => {
    const button = $('#confirm-export');
    const format = $('#export-format').value;
    const dpi = Number($('#export-dpi').value);
    button.disabled = true;
    button.textContent = 'Exporting…';
    const error = $('#export-error');
    error.hidden = true;
    try {
      const exported = await exportCanvas(format, { dpi });
      if (exported) $('#export-dialog').close();
      else {
        error.textContent = elements.status.textContent || 'Export failed. Check that jsonantt serve is running.';
        error.hidden = false;
      }
    } catch (failure) {
      error.textContent = `Export failed: ${failure.message}`;
      error.hidden = false;
    } finally {
      button.disabled = false;
      button.textContent = 'Export';
    }
  });
  $('#save-csv').addEventListener('click', () => exportCanvas('csv'));
  $('#add-task').addEventListener('click', () => addTask());
  $('#add-milestone').addEventListener('click', () => addTask({ milestone: true }));
  $('#chart-settings').addEventListener('click', () => openSettings('general'));
  $('#close-settings').addEventListener('click', () => elements.settingsDialog.close());
  $('#undo-source').addEventListener('click', undo);
  $('#redo-source').addEventListener('click', redo);
  document.addEventListener('click', (event) => {
    if (event.target.closest('#settings-dialog')) return;
    document.querySelectorAll('details.toolbar-menu[open]').forEach((menu) => {
      if (!menu.contains(event.target)) menu.removeAttribute('open');
    });
  });
}

function undo() {
  if (!state.undoStack.length) return;
  state.redoStack.push(state.source);
  const previous = state.undoStack.pop();
  setSource(previous, { pushHistory: false });
}

function redo() {
  if (!state.redoStack.length) return;
  state.undoStack.push(state.source);
  setSource(state.redoStack.pop(), { pushHistory: false });
}

function wireTheme() {
  const button = $('#theme');
  const value = $('#theme-value');
  const apply = (theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    value.textContent = theme ? theme : 'System';
  };
  let stored = null;
  try {
    stored = localStorage.getItem(STORAGE_THEME);
  } catch (error) {
    /* storage is optional */
  }
  apply(stored);
  button.addEventListener('click', () => {
    const current = document.documentElement.dataset.theme;
    const next = current === 'dark' ? 'light' : 'dark';
    apply(next);
    try {
      localStorage.setItem(STORAGE_THEME, next);
    } catch (error) {
      /* storage is optional */
    }
  });
}

function wireKeyboard() {
  document.addEventListener('keydown', (event) => {
    const typing = ['INPUT', 'TEXTAREA'].includes(event.target.tagName);
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && !typing) {
      event.preventDefault();
      if (event.shiftKey) redo();
      else undo();
    }
    if (event.key === 'Escape') selectKey(null);
    if ((event.key === 'Delete' || event.key === 'Backspace') && !typing && state.selection) {
      event.preventDefault();
      deleteSelection();
    }
  });
}

async function loadInitialSource() {
  const params = new URLSearchParams(window.location.search);
  if (params.get('project') === '1') {
    try {
      const response = await fetch('__project.json');
      if (response.ok) return await response.text();
    } catch (error) {
      /* fall through to stored/starter source */
    }
  }
  const demo = DEMOS[params.get('demo')];
  if (demo) return JSON.stringify(demo, null, 2);
  try {
    const stored = localStorage.getItem(STORAGE_SOURCE);
    if (stored) return stored;
  } catch (error) {
    /* storage is optional */
  }
  return JSON.stringify(STARTER, null, 2);
}

async function boot() {
  wireEditor();
  wireCanvas();
  wireZoom();
  wirePanels();
  wireToolbar();
  wireTheme();
  wireKeyboard();
  setExportBackend('browser');
  const staticBuild = document.querySelector('meta[name="jsonantt-static-build"]')?.content;
  try {
    const response = staticBuild ? null : await fetch('healthz');
    if (response?.ok) {
      const payload = await response.json();
      if (payload.status === 'ok') setExportBackend('server');
      state.serverPreview = payload.capabilities?.includes('chart-preview') === true;
      state.serverBurnPreview = payload.capabilities?.includes('burn-preview') === true;
      if (payload.version) $('#app-version').textContent = payload.version;
    }
  } catch (error) {
    $('#app-version').textContent = 'web';
  }
  setSource(await loadInitialSource(), { pushHistory: false });
}

boot();

export { state, parseDate };
