/** Complete Style controls; defaults are checked against Python in tests. */
import { DEFAULT_PALETTE } from './model.mjs';
const n = (key, label, value, section, help, min = 0, max, step = 'any') => ({ key, label, default: value, section, help, type: 'number', min, max, step });
const b = (key, label, value, section, help) => ({ key, label, default: value, section, help, type: 'boolean' });
const c = (key, label, value, section, help) => ({ key, label, default: value, section, help, type: 'color' });
const t = (key, label, value, section, help) => ({ key, label, default: value, section, help, type: 'text' });
const s = (key, label, value, section, choices, help) => ({ key, label, default: value, section, choices, help, type: 'select' });
const ticks = ['', 'day', 'week', 'month', 'quarter', 'year'];
const markers = ['D', 'd', 'o', '.', ',', 's', '^', 'v', '<', '>', 'p', '*', 'h', 'H', '8', '+', 'x', 'P', 'X', '|', '_', '1', '2', '3', '4', 'None'];
export const STYLE_OPTIONS = [
  t('value_prefix', 'Value prefix / currency symbol', null, 'Value display', 'Optional, e.g. $. Applies to the selected numeric fields in graphs and tables.'),
  s('value_scale', 'Display values in', 'units', 'Value display', ['units','thousands','millions','billions'], 'Display only: 1,250,000 becomes 1.25M in millions. Raw amounts do not change.'),
  t('value_suffix', 'Value suffix / unit annotation', null, 'Value display', 'Optional, e.g. USD. For numbers already stored in thousands, keep scale at units and use suffix "thousand".'),
  n('value_decimals', 'Decimal places', null, 'Value display', 'Blank uses up to two decimals when formatting is enabled; otherwise retains existing formatting.', 0, 8, '1'),
  {key:'value_fields', label:'Fields to format', default:['cost'], section:'Value display', type:'fields', help:'Comma-separated names or JSON array, e.g. cost, budget. Default: cost. [] applies to all numeric amount fields.'},
  n('subtask_lightening_pct', 'Lighten inherited child colours (%)', 0, 'Colours', 'Lighten each child from its immediate parent. Explicit task colours override inheritance.', 0, 100),
  { key: 'colors', label: 'Task colour palette', default: DEFAULT_PALETTE, section: 'Colours', type: 'palette', help: 'Ordered colours for tasks without an explicit or inherited colour.' },
  c('background', 'Chart background', '#FFFFFF', 'Colours', 'All views.'),
  c('row_band_color', 'Alternating row colour', '#F5F5F5', 'Colours', 'Gantt timeline and table rows.'),
  c('grid_color', 'Grid colour', '#E0E0E0', 'Colours', 'All views.'),
  n('width', 'Chart width (inches)', 14, 'Layout', 'All views; burn output can grow to fit its periods.', 0.1),
  n('font_size', 'Font size (points)', 12, 'Layout', 'All views.', 1),
  n('row_height', 'Row height (inches)', 0.3, 'Layout', 'Gantt only. Tables size rows to fit their text.', 0.01),
  n('bar_height', 'Bar height (fraction of row)', 0.5, 'Layout', 'Gantt only.', 0, 1),
  n('indent_size', 'Hierarchy indentation (spaces)', 3, 'Layout', 'Gantt labels.', 0, undefined, '1'),
  n('label_fraction', 'Minimum label panel width (fraction)', 0, 'Layout', 'Gantt: 0 fits the labels automatically. The renderer expands to fit text and caps the panel at 60% of the chart.', 0, 0.6),
  n('render_depth', 'Visible task depth', 0, 'Layout', 'Gantt and Table. 0 shows all levels; 1 shows top-level tasks.', 0, undefined, '1'),
  b('bold_tasks', 'Bold top-level tasks', true, 'Labels and display', 'Gantt and Table. Individual bold overrides still apply.'),
  b('number_tasks', 'Number task labels', true, 'Labels and display', 'Gantt prefixes. The Table Task column is configured through Columns.'),
  b('show_arrows', 'Show dependency arrows', true, 'Labels and display', 'Gantt preview and exports; keeps arrow definitions in the source.'),
  b('today_marker', "Show today's date", false, 'Labels and display', 'Gantt preview and exports. Visible only when today is in the chart range.'),
  s('major_tick', 'Major ticks', null, 'Time axis', ticks, 'Gantt: blank uses years.'),
  s('minor_tick', 'Minor ticks', null, 'Time axis', ticks, 'Gantt: blank uses quarters.'),
  t('fiscal_year_start', 'Fiscal year start', null, 'Time axis', 'Gantt: MM or MM-DD, e.g. 10-01. Blank uses calendar years.'),
  s('tick_position', 'Tick label position', 'top', 'Time axis', ['top', 'bottom', 'both'], 'Gantt only.'),
  n('major_grid_width', 'Major grid width (points)', 2, 'Time axis', 'Gantt only.'),
  n('minor_grid_width', 'Minor grid width (points)', 1.5, 'Time axis', 'Gantt only.'),
  b('number_milestones', 'Number milestones (M1, M2, …)', false, 'Milestones', 'Gantt and Table labels and markers.'),
  c('milestone_color', 'Milestone fill', '#FFD700', 'Milestones', 'Gantt and Table.'),
  c('milestone_edge_color', 'Milestone outline', null, 'Milestones', 'Blank means no outline.'),
  s('milestone_marker', 'Milestone symbol', 'D', 'Milestones', markers, 'D diamond, o circle, s square, ^ triangle, * star; standard Matplotlib markers.'),
  n('milestone_size', 'Milestone size (points)', 14, 'Milestones', 'Gantt; Table uses the CLI’s scaled size.'),
  c('major_milestone_color', 'Major milestone fill', null, 'Major milestones', 'Blank inherits the ordinary milestone setting.'),
  c('major_milestone_edge_color', 'Major milestone outline', null, 'Major milestones', 'Blank inherits the ordinary milestone setting.'),
  s('major_milestone_marker', 'Major milestone symbol', null, 'Major milestones', ['', ...markers], 'Blank inherits the ordinary milestone setting.'),
  n('major_milestone_size', 'Major milestone size (points)', null, 'Major milestones', 'Blank inherits the ordinary milestone setting.'),
  b('rollup_milestones', 'Show hidden milestones on parent bars', false, 'Milestone rollup', 'Gantt: requires a limited Visible task depth.'),
  b('rollup_major_milestones_only', 'Roll up major milestones only', false, 'Milestone rollup', 'Used when milestone rollup is enabled.'),
  { key: 'table_columns', label: 'Columns', default: [], section: 'Table', type: 'columns', help: 'Comma-separated field names, or a JSON array of names and objects with field, title, rollup, total, total_level, display_factor.' },
  b('table_colorize', 'Show colour gutter', true, 'Table', 'Task-coloured bars or milestone markers.'),
  b('table_show_markers', 'Show milestone markers', true, 'Table', 'Used when the colour gutter is enabled.'),
];

export function parseArraySetting(text, kind) {
  if (!text.trim()) return [];
  const result = text.trim().startsWith('[') ? JSON.parse(text)
    : kind === 'columns' && text.includes('{') ? JSON.parse(`[${text}]`)
    : text.split(',').map(value => value.trim()).filter(Boolean);
  if (!Array.isArray(result)) throw new Error('Enter an array.');
  if (['palette','fields'].includes(kind) && result.some(value => typeof value !== 'string' || !value.trim())) throw new Error('Enter non-empty strings.');
  if (kind === 'columns' && result.some(value => typeof value !== 'string' && !(value && typeof value.field === 'string'))) throw new Error('Each column needs a field name.');
  return result;
}
