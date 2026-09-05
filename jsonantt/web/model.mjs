/**
 * Browser-side model for jsonantt JSON documents.
 *
 * This mirrors the semantics of `jsonantt/parser.py` and `jsonantt/models.py`
 * (dates, durations, `not_before` chaining, colour inheritance) so the studio
 * can preview a chart without a Python round-trip. The Python package remains
 * the source of truth for rendering images.
 */

import { validateValueFormat } from './value-format.mjs';

export const DEFAULT_PALETTE = [
  '#4472C4', '#ED7D31', '#70AD47', '#FF5757', '#9DC3E6',
  '#FFC000', '#7030A0', '#00B0F0', '#FF0066', '#00B050',
];

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];

const DURATION_RE = /^\s*(\d+)\s*(d|day|days|w|week|weeks|m|month|months|y|year|years)\s*$/i;

/** Build a UTC-anchored date from year/month/day numbers. */
export function makeDate(year, month, day) {
  return new Date(Date.UTC(year, month - 1, day));
}

/** Parse a date string using a Python-style `strftime` format. */
export function parseDate(value, format) {
  if (value instanceof Date) return value;
  const text = String(value).trim();
  const fields = { year: 1900, month: 1, day: 1 };
  let cursor = 0;
  let index = 0;
  while (index < format.length) {
    const char = format[index];
    if (char !== '%') {
      if (text[cursor] !== char) throw new Error(`date ${text} does not match format ${format}`);
      cursor += 1;
      index += 1;
      continue;
    }
    const token = format[index + 1];
    index += 2;
    if (token === '%') {
      if (text[cursor] !== '%') throw new Error(`date ${text} does not match format ${format}`);
      cursor += 1;
      continue;
    }
    if (token === 'b' || token === 'B') {
      const name = text.slice(cursor).match(/^[A-Za-z]+/);
      if (!name) throw new Error(`date ${text} does not match format ${format}`);
      const found = MONTHS.findIndex((month) => month.toLowerCase().startsWith(name[0].toLowerCase()));
      if (found < 0) throw new Error(`unknown month name ${name[0]}`);
      fields.month = found + 1;
      cursor += name[0].length;
      continue;
    }
    const digits = text.slice(cursor).match(/^\d{1,4}/);
    if (!digits) throw new Error(`date ${text} does not match format ${format}`);
    const number = Number(digits[0]);
    cursor += digits[0].length;
    if (token === 'Y') fields.year = number;
    else if (token === 'y') fields.year = number + (number < 69 ? 2000 : 1900);
    else if (token === 'm') fields.month = number;
    else if (token === 'd') fields.day = number;
    else if (token === 'j') {
      fields.month = 1;
      fields.day = number;
    } else if (!'HMS'.includes(token)) throw new Error(`unsupported date directive %${token}`);
  }
  const parsed = makeDate(fields.year, fields.month, fields.day);
  if (Number.isNaN(parsed.getTime())) throw new Error(`invalid date ${text}`);
  return parsed;
}

/** Format a date using a Python-style `strftime` format. */
export function formatDate(value, format) {
  if (!value) return '';
  const pad = (number, width = 2) => String(number).padStart(width, '0');
  return format.replace(/%([A-Za-z%])/g, (match, token) => {
    switch (token) {
      case 'Y': return String(value.getUTCFullYear());
      case 'y': return pad(value.getUTCFullYear() % 100);
      case 'm': return pad(value.getUTCMonth() + 1);
      case 'd': return pad(value.getUTCDate());
      case 'b': return MONTHS[value.getUTCMonth()].slice(0, 3);
      case 'B': return MONTHS[value.getUTCMonth()];
      case '%': return '%';
      default: return match;
    }
  });
}

function addDays(value, days) {
  return new Date(value.getTime() + days * 86400000);
}

function addMonths(value, months) {
  const total = value.getUTCMonth() + months;
  const year = value.getUTCFullYear() + Math.floor(total / 12);
  const month = ((total % 12) + 12) % 12;
  const maxDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return new Date(Date.UTC(year, month, Math.min(value.getUTCDate(), maxDay)));
}

/** Parse a duration spec into `[unit, value]` where unit is `d`, `m` or `y`. */
export function parseDuration(spec) {
  const text = String(spec).trim();
  if (/^\d+$/.test(text)) return ['d', Number(text)];
  const match = DURATION_RE.exec(text);
  if (!match) throw new Error(`Invalid duration spec '${spec}'. Use e.g. '14d', '2w', '3m', '2y'.`);
  const value = Number(match[1]);
  const unit = match[2].toLowerCase();
  if (unit.startsWith('d')) return ['d', value];
  if (unit.startsWith('w')) return ['d', value * 7];
  if (unit.startsWith('m')) return ['m', value];
  return ['y', value];
}

/** Return the date that is *spec* after *start*. */
export function applyDuration(start, spec) {
  const [unit, value] = parseDuration(spec);
  if (unit === 'd') return addDays(start, value);
  if (unit === 'm') return addMonths(start, value);
  return addMonths(start, value * 12);
}

/** Lighten a hex colour towards white by *pct* percent. */
export function lighten(color, pct) {
  const hex = normaliseHex(color);
  if (!hex) return color;
  const amount = Math.max(0, Math.min(100, pct)) / 100;
  const channels = [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16));
  // Python round() uses ties-to-even, including at 50% lightening.
  const mixed = channels.map((channel) => {
    const value = channel + (255 - channel) * amount;
    const floor = Math.floor(value);
    return value - floor === 0.5 ? floor + (floor % 2) : Math.round(value);
  });
  return `#${mixed.map((channel) => channel.toString(16).padStart(2, '0')).join('')}`;
}

function normaliseHex(color) {
  if (typeof color !== 'string') return null;
  const text = color.trim();
  if (/^#[0-9a-f]{6}$/i.test(text)) return text;
  if (/^#[0-9a-f]{3}$/i.test(text)) {
    return `#${text.slice(1).split('').map((char) => char + char).join('')}`;
  }
  return null;
}

function nestedItems(data) {
  const items = [];
  if (Array.isArray(data.tasks)) items.push(...data.tasks.map((item, index) => ({ item, key: 'tasks', index })));
  if (Array.isArray(data.children)) items.push(...data.children.map((item, index) => ({ item, key: 'children', index })));
  return items;
}

function parseTask(entry, dateFormat, depth, path) {
  const raw = typeof entry === 'string' ? { name: entry } : (entry || {});
  const majorMilestone = Boolean(raw.major_milestone);
  const milestone = Boolean(raw.milestone) || majorMilestone;
  const task = {
    raw,
    path,
    depth,
    name: raw.name === undefined ? (typeof entry === 'string' ? entry : 'Unnamed') : String(raw.name),
    description: raw.description === undefined ? '' : String(raw.description),
    id: raw.id === undefined ? null : String(raw.id),
    color: raw.color || null,
    edgeColor: raw.edge_color || null,
    milestone,
    majorMilestone,
    notBefore: raw.not_before === undefined ? null : String(raw.not_before),
    durationSpec: raw.duration === undefined || raw.duration === null ? null : String(raw.duration),
    start: raw.start === undefined ? null : parseDate(raw.start, dateFormat),
    end: raw.end === undefined ? null : parseDate(raw.end, dateFormat),
    milestoneDates: [],
    children: [],
    resolvedColor: null,
    included: Boolean(raw.filename),
  };

  if (task.start && task.durationSpec && !task.end) {
    task.end = applyDuration(task.start, task.durationSpec);
    task.durationSpec = null;
  }

  if (milestone) {
    if (raw.date !== undefined) {
      const values = Array.isArray(raw.date) ? raw.date : [raw.date];
      task.milestoneDates = values.map((value) => parseDate(value, dateFormat));
    } else if (task.start) task.milestoneDates = [task.start];
    else if (task.end) task.milestoneDates = [task.end];
  }

  task.children = nestedItems(raw).map(({ item, key, index }) => (
    parseTask(item, dateFormat, depth + 1, [...path, key, index])
  ));
  return task;
}

/** Recursively resolve the earliest start of a task (children included). */
export function effectiveStart(task) {
  if (task.milestone) {
    if (task.milestoneDates.length) {
      return task.milestoneDates.reduce((min, date) => (date < min ? date : min));
    }
    return task.start;
  }
  if (task.start) return task.start;
  const candidates = task.children.map(effectiveStart).filter(Boolean);
  return candidates.length ? candidates.reduce((min, date) => (date < min ? date : min)) : null;
}

/** Recursively resolve the latest end of a task (children included). */
export function effectiveEnd(task) {
  if (task.milestone) {
    if (task.milestoneDates.length) {
      return task.milestoneDates.reduce((max, date) => (date > max ? date : max));
    }
    return task.start;
  }
  if (task.end) return task.end;
  const candidates = task.children.map(effectiveEnd).filter(Boolean);
  return candidates.length ? candidates.reduce((max, date) => (date > max ? date : max)) : null;
}

function walk(tasks, visit, parent = null) {
  tasks.forEach((task) => {
    visit(task, parent);
    walk(task.children, visit, task);
  });
}

function resolveNotBefore(all, byId) {
  for (let pass = 0; pass <= all.length; pass += 1) {
    let changed = false;
    all.forEach((task) => {
      if (!task.notBefore || task.start) return;
      const reference = byId.get(task.notBefore);
      if (!reference) throw new Error(`not_before references unknown id: '${task.notBefore}'`);
      const referenceEnd = effectiveEnd(reference);
      if (!referenceEnd) return;
      task.start = referenceEnd;
      if (task.milestone && !task.milestoneDates.length) task.milestoneDates = [task.start];
      if (task.durationSpec) {
        task.end = applyDuration(task.start, task.durationSpec);
        task.durationSpec = null;
      }
      changed = true;
    });
    if (!changed) break;
  }
  const unresolved = all.find((task) => task.notBefore && !task.start);
  if (unresolved) {
    throw new Error(`Could not resolve not_before='${unresolved.notBefore}' for task '${unresolved.name}'.`);
  }
}

function assignColors(tasks, style) {
  const palette = Array.isArray(style.colors) && style.colors.length ? style.colors : DEFAULT_PALETTE;
  const lightenPct = Number(style.subtask_lightening_pct || 0);
  let index = 0;
  tasks.forEach((task) => {
    const base = task.color || palette[index++ % palette.length];
    task.resolvedColor = base;
    inheritColor(task.children, base, lightenPct);
  });
}

function inheritColor(children, parentColor, lightenPct) {
  children.forEach((child) => {
    const base = child.color || (lightenPct ? lighten(parentColor, lightenPct) : parentColor);
    child.resolvedColor = base;
    inheritColor(child.children, base, lightenPct);
  });
}

/**
 * Parse a raw jsonantt document into a renderable chart model.
 *
 * Throws an `Error` with a human readable message when the document is invalid.
 */
export function parseChart(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error('The document must be a JSON object');
  }
  const dateFormat = data.dateformat || data.date_format || '%Y-%m-%d';
  const style = (data.style && typeof data.style === 'object') ? data.style : {};
  for (const key of ['task_number_start','milestone_number_start']) {
    if (Object.hasOwn(style,key) && (!Number.isSafeInteger(style[key]) || style[key] < 0)) {
      throw new Error(`style.${key} must be a non-negative integer`);
    }
  }
  if (Object.hasOwn(style,'milestone_prefix') && typeof style.milestone_prefix !== 'string') {
    throw new Error('style.milestone_prefix must be a string (use "" for no prefix)');
  }
  validateValueFormat(style);
  const tasks = nestedItems(data).map(({ item, key, index }) => parseTask(item, dateFormat, 0, [key, index]));

  const flat = [];
  const byId = new Map();
  const parents = new Map();
  walk(tasks, (task, parent) => {
    flat.push(task);
    parents.set(task, parent);
    if (task.id) byId.set(task.id, task);
  });
  resolveNotBefore(flat, byId);
  assignColors(tasks, style);

  const arrows = Array.isArray(data.arrows) ? data.arrows.map((arrow, index) => ({
    raw: arrow,
    index,
    from: arrow.from,
    to: arrow.to,
    color: arrow.color || '#888888',
    label: arrow.label || null,
  })) : [];

  flat.forEach((task) => {
    task.effectiveStart = effectiveStart(task);
    task.effectiveEnd = effectiveEnd(task);
    task.key = task.path.join('.');
    task.parent = parents.get(task) || null;
  });

  return {
    raw: data,
    title: data.title || '',
    dateFormat,
    style,
    start: data.start === undefined ? null : parseDate(data.start, dateFormat),
    end: data.end === undefined ? null : parseDate(data.end, dateFormat),
    tasks,
    flat,
    byId,
    arrows,
  };
}

/** Return the visible rows of a chart, honouring the render depth limit. */
export function chartRows(chart, renderDepth = 0) {
  const rows = [];
  const collect = (tasks) => {
    tasks.forEach((task) => {
      if (renderDepth && task.depth >= renderDepth) return;
      rows.push(task);
      collect(task.children);
    });
  };
  collect(chart.tasks);
  return rows;
}

/**
 * Describe how *task* is wired to the rest of the chart.
 *
 * `upstream` holds everything the task depends on (its `not_before` reference,
 * incoming dependency arrows and its parent task), while `downstream` holds
 * everything that depends on it (tasks chained off its id, outgoing arrows and
 * its own subtasks).
 */
export function taskRelations(chart, task) {
  const upstream = [];
  const downstream = [];
  const add = (list, related, via) => {
    if (!related || related === task) return;
    if (list.some((entry) => entry.task === related && entry.via === via)) return;
    list.push({ task: related, via });
  };

  if (task.notBefore) add(upstream, chart.byId.get(task.notBefore), 'not_before');
  if (task.parent) add(upstream, task.parent, 'parent');
  task.children.forEach((child) => add(downstream, child, 'subtask'));

  chart.flat.forEach((other) => {
    if (task.id && other.notBefore === task.id) add(downstream, other, 'not_before');
  });

  chart.arrows.forEach((arrow) => {
    if (task.id && arrow.to === task.id) add(upstream, chart.byId.get(arrow.from), 'arrow');
    if (task.id && arrow.from === task.id) add(downstream, chart.byId.get(arrow.to), 'arrow');
  });

  return { upstream, downstream };
}

/** Resolve a task by its `path` key within a raw document. */
export function taskAtPath(data, path) {
  let node = data;
  for (let index = 0; index < path.length; index += 2) {
    const bucket = node[path[index]];
    if (!Array.isArray(bucket)) return null;
    node = bucket[path[index + 1]];
    if (node === undefined) return null;
  }
  return node;
}

/** Remove the task addressed by *path* from a raw document. */
export function removeTaskAtPath(data, path) {
  const parentPath = path.slice(0, -2);
  let node = data;
  for (let index = 0; index < parentPath.length; index += 2) {
    node = node[parentPath[index]][parentPath[index + 1]];
  }
  const bucket = node[path[path.length - 2]];
  if (!Array.isArray(bucket)) return false;
  bucket.splice(path[path.length - 1], 1);
  return true;
}
