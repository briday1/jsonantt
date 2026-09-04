/**
 * Chart settings editor for the jsonantt studio.
 *
 * Renders the global document fields (`title`, `dateformat`, chart `start` /
 * `end`) and the `style` block as a form. Every change mutates the source
 * document via the `onCommit` callback, so edits persist through the same
 * JSON source-of-truth flow as every other studio edit.
 */
import { attachDatePicker } from './datepicker.mjs';
import { formatDate } from './model.mjs';

const TIME_SCALE_OPTIONS = [
  { value: '', label: 'Auto (calendar)' },
  { value: 'day', label: 'Days' },
  { value: 'week', label: 'Weeks' },
  { value: 'month', label: 'Months' },
  { value: 'quarter', label: 'Quarters (Q1, Q2, …)' },
  { value: 'year', label: 'Years' },
];

function clearNode(node) {
  node.replaceChildren();
}

function field(labelText, input, help) {
  const label = document.createElement('label');
  label.className = 'settings-field';
  const span = document.createElement('span');
  span.textContent = labelText;
  label.append(span, input);
  if (help) {
    const hint = document.createElement('small');
    hint.className = 'settings-help';
    hint.textContent = help;
    label.append(hint);
  }
  return label;
}

function section(title) {
  const heading = document.createElement('h3');
  heading.textContent = title;
  return heading;
}

function textSetting(doc, key, value, onCommit, { placeholder = '', help = '' } = {}) {
  const input = document.createElement('input');
  input.type = 'text';
  input.value = value === undefined || value === null ? '' : String(value);
  input.placeholder = placeholder;
  input.addEventListener('change', () => {
    if (input.value.trim() === '') delete doc[key];
    else doc[key] = input.value;
    onCommit();
  });
  return { input, help };
}

function numberSetting(style, key, value, onCommit, { step = 'any', placeholder = '' } = {}) {
  const input = document.createElement('input');
  input.type = 'number';
  input.step = step;
  input.value = value === undefined || value === null ? '' : String(value);
  input.placeholder = placeholder;
  input.addEventListener('change', () => {
    if (input.value.trim() === '' || Number.isNaN(Number(input.value))) delete style[key];
    else style[key] = Number(input.value);
    onCommit();
  });
  return input;
}

function colorSetting(style, key, value, onCommit) {
  const wrap = document.createElement('span');
  wrap.className = 'color-setting';
  const input = document.createElement('input');
  input.type = 'color';
  input.value = /^#[0-9a-f]{6}$/i.test(value || '') ? value : '#ffffff';
  const clear = document.createElement('button');
  clear.type = 'button';
  clear.className = 'color-clear';
  clear.textContent = value === undefined ? 'Default' : 'Reset';
  clear.title = 'Use the default value';
  input.addEventListener('change', () => {
    style[key] = input.value;
    onCommit();
  });
  clear.addEventListener('click', () => {
    delete style[key];
    onCommit();
  });
  wrap.append(input, clear);
  return wrap;
}

function boolSetting(style, key, value, onCommit) {
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.checked = Boolean(value);
  input.addEventListener('change', () => {
    if (input.checked) style[key] = true;
    else delete style[key];
    onCommit();
  });
  return input;
}

function dateSetting(doc, key, value, dateFormat, onCommit, { help = '' } = {}) {
  const input = document.createElement('input');
  input.type = 'text';
  input.value = value === undefined || value === null ? '' : String(value);
  input.placeholder = formatDate(new Date(), dateFormat || '%Y-%m-%d');
  input.addEventListener('change', () => {
    if (input.value.trim() === '') delete doc[key];
    else doc[key] = input.value.trim();
    onCommit();
  });
  attachDatePicker(input, {
    format: dateFormat || '%Y-%m-%d',
    onPick: (text) => {
      input.value = text;
      doc[key] = text;
      onCommit();
    },
  });
  return { input, help };
}

function timeScaleSetting(style, key, value, onCommit) {
  const select = document.createElement('select');
  TIME_SCALE_OPTIONS.forEach((option) => {
    const node = document.createElement('option');
    node.value = option.value;
    node.textContent = option.label;
    select.append(node);
  });
  select.value = value || '';
  select.addEventListener('change', () => {
    if (select.value === '') delete style[key];
    else style[key] = select.value;
    onCommit();
  });
  return select;
}

function fiscalStartSetting(style, value, onCommit) {
  const select = document.createElement('select');
  const auto = document.createElement('option');
  auto.value = '';
  auto.textContent = 'Calendar year (January)';
  select.append(auto);
  const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'];
  monthNames.forEach((name, index) => {
    const option = document.createElement('option');
    option.value = `${String(index + 1).padStart(2, '0')}-01`;
    option.textContent = `Fiscal year starts ${name} 1`;
    select.append(option);
  });
  const current = typeof value === 'string' ? value : '';
  select.value = current;
  if (select.value !== current) {
    // Preserve non-standard (day-aligned) specs as a manual option.
    const custom = document.createElement('option');
    custom.value = current;
    custom.textContent = `Custom (${current})`;
    select.append(custom);
    select.value = current;
  }
  select.addEventListener('change', () => {
    if (select.value === '') delete style.fiscal_year_start;
    else style.fiscal_year_start = select.value;
    onCommit();
  });
  return select;
}

function columnsSetting(style, onCommit) {
  const input = document.createElement('input');
  input.type = 'text';
  const current = Array.isArray(style.table_columns) ? style.table_columns : [];
  input.value = current.map((entry) => (typeof entry === 'string' ? entry : JSON.stringify(entry))).join(', ');
  input.placeholder = 'task, name, description';
  input.addEventListener('change', () => {
    const parts = input.value.split(',').map((part) => part.trim()).filter(Boolean);
    if (!parts.length) {
      delete style.table_columns;
      onCommit();
      return;
    }
    style.table_columns = parts.map((part) => {
      if (part.startsWith('{')) {
        try {
          return JSON.parse(part);
        } catch (error) {
          return part;
        }
      }
      return part;
    });
    onCommit();
  });
  return input;
}

/**
 * Render the chart settings form into *container*.
 *
 * `doc` is the parsed source document; `onCommit(doc)` must persist it (the
 * studio re-serialises the JSON source and re-renders). `initialFocus` may be
 * `'general'` or `'table'` to deep-link a settings section.
 */
export function renderChartSettings(container, doc, { onCommit, initialFocus = '' } = {}) {
  clearNode(container);
  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) {
    const note = document.createElement('p');
    note.className = 'settings-empty';
    note.textContent = 'Chart settings become available once the source is valid JSON.';
    container.append(note);
    return;
  }
  if (!doc.style || typeof doc.style !== 'object' || Array.isArray(doc.style)) doc.style = null;
  const ensureStyle = () => {
    if (!doc.style) doc.style = {};
    return doc.style;
  };
  const style = doc.style || {};
  const commit = onCommit;
  const dateFormat = doc.dateformat || doc.date_format || '%Y-%m-%d';
  const fragment = document.createDocumentFragment();

  // ---- general -----------------------------------------------------------
  fragment.append(section('General'));
  const titleSetting = textSetting(doc, 'title', doc.title, commit, { placeholder: 'Chart title' });
  fragment.append(field('Title', titleSetting.input));
  const formatSetting = textSetting(doc, 'dateformat', doc.dateformat, commit, {
    placeholder: '%Y-%m-%d',
    help: 'strptime format used for every date in the document',
  });
  fragment.append(field('Date format', formatSetting.input, formatSetting.help));
  const startSetting = dateSetting(doc, 'start', doc.start, dateFormat, commit, { help: 'Force the chart x-axis start' });
  const endSetting = dateSetting(doc, 'end', doc.end, dateFormat, commit, { help: 'Force the chart x-axis end' });
  const rangeGrid = document.createElement('div');
  rangeGrid.className = 'settings-grid';
  rangeGrid.append(field('Chart start', startSetting.input, startSetting.help), field('Chart end', endSetting.input, endSetting.help));
  fragment.append(rangeGrid);

  // ---- time scale --------------------------------------------------------
  fragment.append(section('Time scale'));
  fragment.append(field(
    'Major ticks',
    timeScaleSetting(style, 'major_tick', style.major_tick, () => { ensureStyle(); commit(); }),
    'Largest labelled divisions on the chart axis',
  ));
  fragment.append(field(
    'Minor ticks',
    timeScaleSetting(style, 'minor_tick', style.minor_tick, () => { ensureStyle(); commit(); }),
    'Finer gridline divisions (dotted)',
  ));
  fragment.append(field(
    'Fiscal calendar',
    fiscalStartSetting(style, style.fiscal_year_start, () => { ensureStyle(); commit(); }),
    'Switch year/quarter ticks to fiscal labels (FY26, Q1 FY26, …) referenced from this start date',
  ));
  const position = document.createElement('select');
  [['', 'Auto (top)'], ['top', 'Top'], ['bottom', 'Bottom'], ['both', 'Both']].forEach(([value, label]) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    position.append(option);
  });
  position.value = style.tick_position || '';
  position.addEventListener('change', () => {
    ensureStyle();
    if (position.value === '') delete doc.style.tick_position;
    else doc.style.tick_position = position.value;
    commit();
  });
  fragment.append(field('Tick labels', position, 'Where the axis labels are drawn'));

  // ---- table -------------------------------------------------------------
  const tableHeading = section('Table');
  fragment.append(tableHeading);
  fragment.append(field(
    'Columns',
    columnsSetting(style, () => { ensureStyle(); commit(); }),
    'Comma-separated fields, e.g. task, name, assignee, { "field": "cost", "total": true }',
  ));
  const colorize = boolSetting(style, 'table_colorize', style.table_colorize, () => { ensureStyle(); commit(); });
  fragment.append(field('Colour gutter', colorize, 'Task-coloured accent bar per row (default on)'));
  const markers = boolSetting(style, 'table_show_markers', style.table_show_markers, () => { ensureStyle(); commit(); });
  fragment.append(field('Milestone markers', markers, 'Diamond markers on milestone rows (default on)'));

  // ---- appearance ----------------------------------------------------------
  fragment.append(section('Appearance'));
  const appearanceGrid = document.createElement('div');
  appearanceGrid.className = 'settings-grid';
  appearanceGrid.append(
    field('Background', colorSetting(style, 'background', style.background, () => { ensureStyle(); commit(); })),
    field('Grid colour', colorSetting(style, 'grid_color', style.grid_color, () => { ensureStyle(); commit(); })),
    field('Row band', colorSetting(style, 'row_band_color', style.row_band_color, () => { ensureStyle(); commit(); })),
    field('Milestone', colorSetting(style, 'milestone_color', style.milestone_color, () => { ensureStyle(); commit(); })),
  );
  fragment.append(appearanceGrid);
  const sizingGrid = document.createElement('div');
  sizingGrid.className = 'settings-grid';
  sizingGrid.append(
    field('Row height (in)', numberSetting(style, 'row_height', style.row_height, () => { ensureStyle(); commit(); }, { placeholder: '0.3' })),
    field('Font size (pt)', numberSetting(style, 'font_size', style.font_size, () => { ensureStyle(); commit(); }, { placeholder: '12' })),
    field('Render depth', numberSetting(style, 'render_depth', style.render_depth, () => { ensureStyle(); commit(); }, { step: '1', placeholder: '0 = all' })),
    field('Lighten subtasks %', numberSetting(style, 'subtask_lightening_pct', style.subtask_lightening_pct, () => { ensureStyle(); commit(); }, { placeholder: '0' })),
  );
  fragment.append(sizingGrid);
  const bold = boolSetting(style, 'bold_tasks', style.bold_tasks, () => { ensureStyle(); commit(); });
  fragment.append(field('Bold top-level tasks', bold, 'Default on'));
  const numberTasks = boolSetting(style, 'number_tasks', style.number_tasks, () => { ensureStyle(); commit(); });
  fragment.append(field('Number task labels', numberTasks, 'Prefix labels with 1, 1.1, … (default on)'));

  container.append(fragment);

  if (initialFocus === 'table' && tableHeading.scrollIntoView) {
    tableHeading.scrollIntoView({ block: 'start' });
  }
}
