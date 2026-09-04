/**
 * Table mode renderer for the jsonantt studio.
 *
 * Mirrors the CLI's `render_table` semantics: `style.table_columns` picks the
 * columns (string field names or `{ field, title, rollup, total, total_level,
 * display_factor }` objects), the special `task`/`name`/`description` fields
 * keep their existing behaviour, numeric columns can roll up and total, and
 * `style.table_colorize` / `style.table_show_markers` drive the accent gutter.
 */
import { chartRows, formatDate } from './model.mjs';

const DEFAULT_COLUMNS = ['task', 'name', 'description'];

const DEFAULT_TITLES = {
  task: 'Task',
  name: 'Name',
  description: 'Description',
  id: 'ID',
  not_before: 'Not Before',
  effective_start: 'Effective Start',
  effective_end: 'Effective End',
  milestone_date: 'Date',
  date: 'Date',
  offset: 'Offset',
};

function defaultTitle(field) {
  return DEFAULT_TITLES[field] || field.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

/** Normalise `style.table_columns` into `{ field, title, rollup, total, totalLevel, displayFactor }` entries. */
export function resolveTableColumns(style) {
  const raw = Array.isArray(style.table_columns) && style.table_columns.length ? style.table_columns : DEFAULT_COLUMNS;
  const columns = raw.map((item) => {
    if (typeof item === 'string') {
      return { field: item.trim(), title: defaultTitle(item.trim()), rollup: null, total: false, totalLevel: null, displayFactor: 1 };
    }
    if (item && typeof item === 'object') {
      const field = String(item.field || '').trim();
      const rollup = item.rollup === true ? 'sum' : (item.rollup || null);
      return {
        field,
        title: item.title === undefined ? defaultTitle(field) : String(item.title),
        rollup: rollup === 'sum' ? 'sum' : null,
        total: Boolean(item.total),
        totalLevel: Number.isInteger(item.total_level) ? item.total_level : null,
        displayFactor: Number(item.display_factor) || 1,
      };
    }
    return null;
  }).filter((column) => column && column.field);
  return columns.length ? columns : resolveTableColumns({});
}

/** Hierarchy numbers (`1`, `1.1`, …) for each row, matching the Python renderer. */
function rowNumbers(chart) {
  const numbers = new Map();
  const visit = (tasks, prefix) => {
    tasks.forEach((task, index) => {
      const number = `${prefix}${index + 1}`;
      numbers.set(task, number);
      visit(task.children, `${number}.`);
    });
  };
  visit(chart.tasks, '');
  return numbers;
}

function rawFieldValue(task, field) {
  if (field === 'id') return task.id;
  if (field === 'not_before') return task.notBefore;
  if (field === 'effective_start') return task.effectiveStart;
  if (field === 'effective_end') return task.effectiveEnd;
  if (field === 'milestone_date' || field === 'date') {
    return task.milestoneDates.length ? task.milestoneDates[0] : null;
  }
  return task.raw ? task.raw[field] : undefined;
}

function formatCellValue(value, chart) {
  if (value === null || value === undefined) return '';
  if (value instanceof Date) return formatDate(value, chart.dateFormat);
  if (Array.isArray(value)) {
    return value.map((entry) => formatCellValue(entry, chart)).join(', ');
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return String(value);
}

function parseNumeric(value) {
  if (value === null || value === undefined || value instanceof Date || Array.isArray(value)) return null;
  if (typeof value === 'boolean') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

/** Recursively summed numeric value for *task* and *field*, or `null` when nothing numeric exists. */
function rollupSum(task, field) {
  const own = parseNumeric(rawFieldValue(task, field));
  let total = own === null ? 0 : own;
  let seen = own !== null;
  task.children.forEach((child) => {
    const childValue = rollupSum(child, field);
    if (childValue !== null) {
      total += childValue;
      seen = true;
    }
  });
  return seen ? total : null;
}

function formatNumeric(value) {
  if (!Number.isFinite(value)) return '';
  const rounded = Math.round(value * 1e6) / 1e6;
  return String(rounded);
}

function cellValue(task, column, chart) {
  const { field } = column;
  if (field === 'name') return task.name;
  if (field === 'description') return task.description;
  if (column.rollup === 'sum') {
    const total = rollupSum(task, field);
    return total === null ? '' : formatNumeric(total * column.displayFactor);
  }
  const numeric = parseNumeric(rawFieldValue(task, field));
  if (numeric !== null) return formatNumeric(numeric * column.displayFactor);
  return formatCellValue(rawFieldValue(task, field), chart);
}

/** Rows that contribute to a column footer total, mirroring the Python renderer. */
function totalCandidateRows(rows, column) {
  if (column.totalLevel !== null) return rows.filter((task) => task.depth === column.totalLevel);
  if (column.rollup === 'sum') return rows.filter((task) => task.depth === 0);
  return rows;
}

function footerTotals(rows, columns) {
  const totals = new Map();
  columns.forEach((column, index) => {
    if (!column.total) return;
    let sum = 0;
    let seen = false;
    totalCandidateRows(rows, column).forEach((task) => {
      const value = column.rollup === 'sum'
        ? rollupSum(task, column.field)
        : parseNumeric(rawFieldValue(task, column.field));
      if (value !== null) {
        sum += value;
        seen = true;
      }
    });
    if (seen) totals.set(index, formatNumeric(sum * column.displayFactor));
  });
  if (totals.size) {
    // Label the footer in the same preferred column the Python renderer uses.
    let labelIndex = 0;
    for (const preferred of ['name', 'description', 'task']) {
      const found = columns.findIndex((column) => column.field === preferred);
      if (found >= 0) {
        labelIndex = found;
        break;
      }
    }
    if (!totals.has(labelIndex)) totals.set(labelIndex, 'Total');
  }
  return totals;
}

function element(name, className, text) {
  const node = document.createElement(name);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/**
 * Render *chart* as a selectable table element.
 *
 * Rows carry `data-key`/`data-kind="task"` so the studio maps clicks back to
 * the originating JSON task, exactly like the Gantt canvas.
 */
export function renderTable(chart, options = {}) {
  const { selectedKey = null, renderDepth = 0 } = options;
  const columns = resolveTableColumns(chart.style || {});
  const rows = chartRows(chart, renderDepth);
  const colorize = chart.style.table_colorize !== false;
  const showMarkers = chart.style.table_show_markers !== false;
  const totals = footerTotals(rows, columns);
  const numbers = rowNumbers(chart);
  const numberMilestones = Boolean(chart.style.number_milestones);
  let milestoneCounter = 0;

  const wrap = element('div', 'table-wrap');
  const table = element('table', 'studio-table');

  const thead = element('thead');
  const headerRow = element('tr');
  if (colorize) headerRow.append(element('th', 'table-gutter-header', ''));
  columns.forEach((column) => headerRow.append(element('th', '', column.title)));
  thead.append(headerRow);
  table.append(thead);

  const tbody = element('tbody');
  if (!rows.length) {
    const row = element('tr', 'table-empty-row');
    const cell = element('td', 'table-empty', 'No tasks yet — add one from the New menu.');
    cell.colSpan = columns.length + (colorize ? 1 : 0);
    row.append(cell);
    tbody.append(row);
  }
  rows.forEach((task, index) => {
    const row = element('tr', `table-row selectable${selectedKey === task.key ? ' selected-row' : ''}`);
    row.dataset.key = task.key;
    row.dataset.kind = 'task';
    row.tabIndex = 0;
    if (task.milestone) row.classList.add('milestone-row');

    if (colorize) {
      const gutter = element('td', 'table-gutter');
      const color = task.milestone
        ? (task.color || chart.style.milestone_color || '#FFD700')
        : (task.resolvedColor || '#4472C4');
      if (task.milestone && showMarkers) {
        const marker = element('span', 'table-milestone-marker');
        marker.style.background = color;
        gutter.append(marker);
      } else {
        const bar = element('span', 'table-color-bar');
        bar.style.background = color;
        gutter.append(bar);
      }
      row.append(gutter);
    }

    const hierarchyNumber = numbers.get(task) || '';
    let taskCell;
    if (task.milestone && numberMilestones) {
      milestoneCounter += 1;
      taskCell = `M${milestoneCounter}`;
    } else {
      taskCell = hierarchyNumber.includes('.') ? hierarchyNumber : `${hierarchyNumber}.`;
    }
    columns.forEach((column) => {
      const cell = element('td', `cell-${column.field.replace(/[^a-z0-9_-]/gi, '')}`);
      if (column.field === 'task') {
        cell.textContent = taskCell;
      } else if (column.field === 'name') {
        cell.textContent = task.name;
        if (task.depth === 0 || task.raw.bold) cell.classList.add('cell-bold');
        if (task.depth) cell.style.paddingLeft = `${10 + task.depth * 12}px`;
      } else {
        cell.textContent = cellValue(task, column, chart);
      }
      row.append(cell);
    });
    tbody.append(row);
  });
  table.append(tbody);

  if (totals.size) {
    const tfoot = element('tfoot');
    const footerRow = element('tr', 'table-total-row');
    if (colorize) footerRow.append(element('td', 'table-gutter', ''));
    columns.forEach((column, index) => {
      footerRow.append(element('td', '', totals.get(index) || ''));
    });
    tfoot.append(footerRow);
    table.append(tfoot);
  }

  wrap.append(table);
  return wrap;
}
