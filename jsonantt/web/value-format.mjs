/** Display-only values. Existing multipliers are applied before this formatter. */
export const VALUE_SCALES = {units:[1,''], thousands:[1000,'K'], millions:[1e6,'M'], billions:[1e9,'B']};
export function valueFormatActive(style, field) {
  if (['task','id','name','description','start','end','date','effective_start','effective_end','milestone_date','duration','not_before','offset','marker_size'].includes(field)) return false;
  const fields = style.value_fields ?? ['cost'];
  return (!fields.length || fields.includes(field)) && (style.value_prefix != null || style.value_suffix != null
    || (style.value_scale ?? 'units') !== 'units' || style.value_decimals != null);
}
export function validateValueFormat(style) {
  if (!Object.hasOwn(VALUE_SCALES, style.value_scale ?? 'units')) throw new Error('Value scale must be units, thousands, millions, or billions.');
  if (style.value_decimals != null && (!Number.isInteger(style.value_decimals) || style.value_decimals < 0 || style.value_decimals > 8)) throw new Error('Value decimals must be an integer from 0 to 8.');
  if (style.value_fields !== undefined && (!Array.isArray(style.value_fields) || style.value_fields.some(field=>typeof field !== 'string' || !field.trim()))) throw new Error('Value fields must be a list of field names.');
  for (const key of ['value_prefix','value_suffix']) if (style[key] != null && typeof style[key] !== 'string') throw new Error(`${key} must be a string.`);
}
export function valueAffixes(value) {
  if (typeof value !== 'string') return {};
  const match = /^\s*([^\d+\-.]*)([+\-]?(?:\d[\d,]*)(?:\.\d+)?)\s*([^\d]*)\s*$/.exec(value);
  return match ? {prefix:match[1].trim(), suffix:match[3].trim()} : {};
}
export function chartValueAffixes(chart, field) {
  for (const task of chart.flat) {
    const spec = valueAffixes(task.raw[field]);
    if (spec.prefix || spec.suffix) return spec;
  }
  return {};
}
export function formatValue(amount, style, field, spec = {}) {
  if (!valueFormatActive(style, field)) return null;
  const [divisor, unit] = VALUE_SCALES[style.value_scale ?? 'units'];
  const places = style.value_decimals ?? 2;
  const value = amount / divisor;
  const number = Math.abs(value).toLocaleString('en-US', {minimumFractionDigits:style.value_decimals ?? 0, maximumFractionDigits:places, roundingMode:'halfEven'});
  const prefix = style.value_prefix ?? spec.prefix ?? '';
  const suffix = style.value_suffix ?? spec.suffix ?? '';
  return `${value < 0 && Number(number.replaceAll(',','')) !== 0 ? '-' : ''}${prefix}${number}${unit}${suffix ? ` ${suffix}` : ''}`;
}
export function valueUnitLabel(style, field, spec = {}) {
  if (!valueFormatActive(style, field)) return '';
  return [style.value_prefix ?? spec.prefix, (style.value_scale && style.value_scale !== 'units') ? style.value_scale : '', style.value_suffix ?? spec.suffix].filter(Boolean).join(' ');
}
