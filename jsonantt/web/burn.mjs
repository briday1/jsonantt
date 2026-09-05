/** Cost allocation metadata for editing/tooltips. All drawing lives in Python. */
import { formatDate } from './model.mjs';
import { formatValue, valueAffixes } from './value-format.mjs';

const DAY = 86400000;
export function burnDisplayForMode(mode) {
  return mode === 'burndown' ? 'remaining' : mode === 'burnup' ? 'cumulative' : 'spend';
}

/** Values at the initial boundary and after each period, already scaled. */
export function burnLineValues(values, display) {
  let value = display === 'remaining' ? values.reduce((sum, amount) => sum + amount, 0) : 0;
  const points = [value];
  for (const amount of values) {
    value += display === 'remaining' ? -amount : amount;
    points.push(value);
  }
  if (display === 'remaining' && values.length) points[points.length - 1] = 0;
  return points;
}
// Structural/styling fields are not budgets, even when they contain digits.
const TASK_FIELDS = new Set([
  'name', 'description', 'id', 'start', 'end', 'duration', 'not_before',
  'color', 'edge_color', 'milestone', 'major_milestone', 'date', 'marker',
  'marker_size', 'bold', 'filename', 'tasks', 'children',
]);

export function availableBurnFields(chart) {
  return [...new Set((chart?.flat || []).flatMap((task) => Object.keys(task.raw)
    .filter((key) => !TASK_FIELDS.has(key) && numericAmount(task.raw[key]) !== null)))];
}

export function numericAmount(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string') return null;
  const match = /^\s*([^\d+\-]*)([+\-]?(?:\d[\d,]*)(?:\.\d+)?)([^\d]*)\s*$/.exec(value);
  const number = match ? Number(match[2].replaceAll(',', '')) : NaN;
  return Number.isFinite(number) ? number : null;
}
function boundary(date, period) {
  const d = new Date(date);
  if (period === 'week') d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7);
  if (['month', 'quarter', 'year'].includes(period)) d.setUTCDate(1);
  if (period === 'quarter') d.setUTCMonth(Math.floor(d.getUTCMonth() / 3) * 3);
  if (period === 'year') d.setUTCMonth(0);
  return d;
}
function next(date, period) {
  const d = new Date(date);
  if (period === 'day' || period === 'week') d.setUTCDate(d.getUTCDate() + (period === 'day' ? 1 : 7));
  else d.setUTCMonth(d.getUTCMonth() + ({ month: 1, quarter: 3, year: 12 }[period]));
  return d;
}
function periodLabel(d, period) {
  if (period === 'quarter') return `${d.getUTCFullYear()}-Q${Math.floor(d.getUTCMonth() / 3) + 1}`;
  if (period === 'year') return String(d.getUTCFullYear());
  if (period === 'month') return formatDate(d, '%Y-%m');
  return `${period === 'week' ? 'Week of ' : ''}${formatDate(d, '%Y-%m-%d')}`;
}

export function buildBurn(chart, { field = 'cost', period = 'month', group = '0', factor = 1 } = {}) {
  if (!['day', 'week', 'month', 'quarter', 'year'].includes(period)) throw new Error('Choose a valid reporting period.');
  if (!['total', 'leaf'].includes(String(group)) && !/^\d+$/.test(String(group))) throw new Error('Choose a valid grouping.');
  if (!Number.isFinite(Number(factor))) throw new Error('Display multiplier must be a finite number.');
  const sources = chart.flat.filter((task) => numericAmount(task.raw[field]) !== null).map((task) => {
    let start = task.effectiveStart || task.effectiveEnd;
    if (!start) throw new Error(`${task.name} has ${field} but no dates for allocation.`);
    let end = task.effectiveEnd;
    if (task.milestone || !end || end <= start) end = new Date(+start + DAY);
    return { task, start, end, amount: numericAmount(task.raw[field]) };
  });
  if (!sources.length) throw new Error(`No numeric ${field} values. Add costs to tasks or open ?demo=3.`);
  const start = boundary(chart.start || new Date(Math.min(...sources.map((s) => +s.start))), period);
  const last = chart.end || new Date(Math.max(...sources.map((s) => +s.end)));
  let end = boundary(last, period);
  if (end < last || end <= start) end = next(end, period);
  const periods = [];
  for (let cursor = start; cursor < end; cursor = next(cursor, period)) {
    if (periods.length >= 5000) throw new Error('Too many periods; choose a coarser reporting period.');
    periods.push({ start: cursor, end: next(cursor, period), label: periodLabel(cursor, period) });
  }
  const numbers = new Map();
  const visit = (tasks, prefix = '') => tasks.forEach((task, index) => {
    const number = `${prefix}${index + 1}`;
    numbers.set(task, number);
    visit(task.children, `${number}.`);
  });
  visit(chart.tasks);
  const series = new Map();
  for (const source of sources) {
    let task = source.task;
    if (group !== 'leaf' && group !== 'total') {
      while (task.parent && task.depth > Number(group)) task = task.parent;
    }
    const key = group === 'total' ? '__total__' : task.key;
    if (!series.has(key)) series.set(key, {
      key, task: group === 'total' ? null : task, name: group === 'total' ? 'Total' : task.name,
      number: group === 'total' ? '' : numbers.get(task),
      color: task.resolvedColor, values: periods.map(() => 0), budget: 0,
    });
    const item = series.get(key);
    item.budget += source.amount * Number(factor);
    periods.forEach((bucket, index) => {
      const overlap = Math.max(0, Math.min(+source.end, +bucket.end) - Math.max(+source.start, +bucket.start));
      item.values[index] += source.amount * overlap / (source.end - source.start) * Number(factor);
    });
  }
  return { periods, series: [...series.values()], field, period, factor:Number(factor),
    totals: periods.map((_, i) => [...series.values()].reduce((sum, s) => sum + s.values[i], 0)) };
}
/** Preserve the CLI's source-derived currency, precision, and separator rules. */
export function burnValueFormatter(chart, field, factor = 1) {
  const amounts = chart.flat.map(task=>task.raw[field]).filter(value=>numericAmount(value) !== null);
  const specs = amounts.map(value=>({prefix:'',suffix:'',...valueAffixes(value)}));
  if (specs.some(spec=>spec.prefix !== specs[0].prefix || spec.suffix !== specs[0].suffix)) throw new Error(`Cannot mix incompatible numeric formats in burn field '${field}'`);
  const spec = specs[0] || {};
  const places = Math.max(0, ...amounts.map(value=>{
    const match = String(value).replaceAll(',','').match(/[+-]?\d+(?:\.(\d+))?(?:e([+-]?\d+))?/i);
    return match ? Math.max(0, (match[1]?.length || 0) - Number(match[2] || 0)) : 0;
  }));
  const factorMatch = String(Math.abs(factor)).match(/(?:\.(\d+))?(?:e([+-]?\d+))?$/i);
  const scalePlaces = Math.max(0, (factorMatch?.[1]?.length || 0) - Number(factorMatch?.[2] || 0));
  const grouping = amounts.some(value=>typeof value === 'string' && value.includes(','));
  return value => {
    const formatted = formatValue(value, chart.style, field, spec);
    if (formatted !== null) return formatted;
    const text = Math.abs(value).toLocaleString('en-US', {useGrouping:grouping, minimumFractionDigits:Math.min(20,places), maximumFractionDigits:Math.min(20,places+scalePlaces), roundingMode:'halfEven'});
    const sign = value < 0 && Number(text.replaceAll(',','')) !== 0 ? '-' : '';
    return `${sign}${spec.prefix || ''}${spec.prefix?.endsWith(':') ? ' ' : ''}${text}${spec.suffix ? ` ${spec.suffix}` : ''}`;
  };
}
