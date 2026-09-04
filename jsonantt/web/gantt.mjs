/** SVG Gantt renderer used by the jsonantt studio canvas. */
import { chartRows, formatDate } from './model.mjs';

const SVG_NS = 'http://www.w3.org/2000/svg';
const DAY = 86400000;

function element(name, attributes = {}, text) {
  const node = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) => {
    if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  });
  if (text !== undefined) node.textContent = text;
  return node;
}

function addDays(value, days) {
  return new Date(value.getTime() + days * DAY);
}

function startOfMonth(value) {
  return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), 1));
}

/** Parse a fiscal-year start spec ("MM" or "MM-DD") into { month, day } (1-based month). */
export function parseFiscalYearStart(spec) {
  if (typeof spec !== 'string') return null;
  const match = /^\s*(\d{1,2})(?:-(\d{1,2}))?\s*$/.exec(spec);
  if (!match) return null;
  const month = Number(match[1]);
  const day = match[2] === undefined ? 1 : Number(match[2]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return { month, day };
}

function fiscalAnchor(year, fiscalStart) {
  const maxDay = new Date(Date.UTC(year, fiscalStart.month, 0)).getUTCDate();
  return new Date(Date.UTC(year, fiscalStart.month - 1, Math.min(fiscalStart.day, maxDay)));
}

/** Fiscal year (named after the calendar year it ends in) + its start date. */
function fiscalYearInfo(value, fiscalStart) {
  const anchor = fiscalAnchor(value.getUTCFullYear(), fiscalStart);
  if (value >= anchor) return { year: value.getUTCFullYear() + 1, anchor };
  return { year: value.getUTCFullYear(), anchor: fiscalAnchor(value.getUTCFullYear() - 1, fiscalStart) };
}

/** Fiscal quarter (1-4) + quarter start for a date. */
function fiscalQuarterInfo(value, fiscalStart) {
  const { year, anchor } = fiscalYearInfo(value, fiscalStart);
  const monthsSince = (value.getUTCFullYear() - anchor.getUTCFullYear()) * 12 + (value.getUTCMonth() - anchor.getUTCMonth());
  const quarterIndex = Math.max(0, Math.min(3, Math.floor(monthsSince / 3)));
  const monthIndex = anchor.getUTCMonth() + quarterIndex * 3;
  const start = fiscalAnchor(anchor.getUTCFullYear() + Math.floor(monthIndex / 12), { month: (monthIndex % 12) + 1, day: fiscalStart.day });
  return { year, quarter: quarterIndex + 1, start };
}

function tickDates(start, end, fiscalStart) {
  const spanDays = Math.max(1, Math.round((end - start) / DAY));
  const ticks = [];
  if (spanDays <= 45 && !fiscalStart) {
    for (let cursor = new Date(start); cursor <= end; cursor = addDays(cursor, 7)) ticks.push(new Date(cursor));
    return { ticks, format: '%d %b' };
  }
  const step = spanDays <= 400 ? 1 : (spanDays <= 1200 ? 3 : 12);
  if (fiscalStart && step === 3) {
    // Quarter ticks land on the fiscal calendar and use fiscal labels.
    let { start: cursor } = fiscalQuarterInfo(start, fiscalStart);
    while (cursor <= end) {
      if (cursor >= start) ticks.push(new Date(cursor));
      const monthIndex = cursor.getUTCMonth() + 3;
      cursor = fiscalAnchor(cursor.getUTCFullYear() + Math.floor(monthIndex / 12), { month: (monthIndex % 12) + 1, day: fiscalStart.day });
    }
    return {
      ticks,
      format: fiscalStart,
      label: (tick) => {
        const info = fiscalQuarterInfo(tick, fiscalStart);
        return `Q${info.quarter} FY${String(info.year % 100).padStart(2, '0')}`;
      },
    };
  }
  let cursor = fiscalStart && step === 12
    ? fiscalYearInfo(start, fiscalStart).anchor
    : startOfMonth(start);
  while (cursor <= end) {
    if (cursor >= start) ticks.push(new Date(cursor));
    cursor = fiscalStart && step === 12
      ? fiscalAnchor(cursor.getUTCFullYear() + 1, fiscalStart)
      : new Date(Date.UTC(cursor.getUTCFullYear(), cursor.getUTCMonth() + step, 1));
  }
  if (fiscalStart && step === 12) {
    return {
      ticks,
      format: '%Y',
      label: (tick) => `FY${String(fiscalYearInfo(tick, fiscalStart).year % 100).padStart(2, '0')}`,
    };
  }
  return { ticks, format: step === 12 ? '%Y' : '%b %Y' };
}

function labelFor(task) {
  return `${'    '.repeat(task.depth)}${task.name}`;
}

/**
 * Render *chart* as an interactive SVG Gantt chart.
 *
 * Rows carry `data-key` attributes so the studio can map clicks back to the
 * originating JSON task.
 */
export function renderGantt(chart, options = {}) {
  const { selectedKey = null, showArrows = true, todayMarker = false } = options;
  const rows = chartRows(chart, Number(chart.style.render_depth || 0));
  const rowHeight = 28;
  const barHeight = 15;
  const headerHeight = chart.title ? 74 : 48;
  const padding = 18;

  const labelWidth = Math.min(420, Math.max(150, ...rows.map((task) => labelFor(task).length * 6.6 + 24)));
  const dates = rows.flatMap((task) => [task.effectiveStart, task.effectiveEnd]).filter(Boolean);
  let domainStart = chart.start || (dates.length ? new Date(Math.min(...dates)) : new Date());
  let domainEnd = chart.end || (dates.length ? new Date(Math.max(...dates)) : addDays(domainStart, 30));
  if (domainEnd <= domainStart) domainEnd = addDays(domainStart, 1);
  const pad = Math.max(1, Math.round((domainEnd - domainStart) / DAY * 0.03));
  if (!chart.start) domainStart = addDays(domainStart, -pad);
  if (!chart.end) domainEnd = addDays(domainEnd, pad);

  const plotWidth = 780;
  const width = labelWidth + plotWidth + padding * 2;
  const height = headerHeight + Math.max(1, rows.length) * rowHeight + padding + 12;
  const scale = (value) => labelWidth + padding + ((value - domainStart) / (domainEnd - domainStart)) * plotWidth;

  const svg = element('svg', {
    xmlns: SVG_NS,
    width,
    height,
    viewBox: `0 0 ${width} ${height}`,
    class: 'gantt-svg',
    role: 'img',
  });
  svg.append(element('rect', {
    x: 0, y: 0, width, height, fill: chart.style.background || '#ffffff',
  }));

  if (chart.title) {
    svg.append(element('text', {
      x: padding, y: 30, fill: '#102a43', 'font-size': 17, 'font-weight': 700, 'font-family': 'Inter, sans-serif',
    }, chart.title));
  }

  const gridTop = headerHeight - 12;
  const gridBottom = height - padding;
  const fiscalStart = parseFiscalYearStart(chart.style.fiscal_year_start);
  const { ticks, format, label: tickLabel } = tickDates(domainStart, domainEnd, fiscalStart);
  ticks.forEach((tick) => {
    const x = scale(tick);
    svg.append(element('line', {
      x1: x, y1: gridTop, x2: x, y2: gridBottom, stroke: chart.style.grid_color || '#e0e0e0', 'stroke-width': 1,
    }));
    svg.append(element('text', {
      x, y: gridTop - 8, fill: '#627d98', 'font-size': 10, 'text-anchor': 'middle', 'font-family': 'Inter, sans-serif',
    }, tickLabel ? tickLabel(tick) : formatDate(tick, format)));
  });

  rows.forEach((task, index) => {
    const y = headerHeight + index * rowHeight;
    if (index % 2 === 1) {
      svg.append(element('rect', {
        x: padding, y, width: width - padding * 2, height: rowHeight,
        fill: chart.style.row_band_color || '#f5f5f5',
      }));
    }
  });

  if (todayMarker) {
    const today = new Date();
    const utcToday = new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()));
    if (utcToday >= domainStart && utcToday <= domainEnd) {
      svg.append(element('line', {
        x1: scale(utcToday), y1: gridTop, x2: scale(utcToday), y2: gridBottom,
        stroke: '#c00000', 'stroke-width': 1.5, 'stroke-dasharray': '4 3',
      }));
    }
  }

  const anchors = new Map();
  rows.forEach((task, index) => {
    const y = headerHeight + index * rowHeight;
    const centre = y + rowHeight / 2;
    const group = element('g', {
      class: `selectable${selectedKey === task.key ? ' selected-element' : ''}`,
      'data-key': task.key,
      'data-kind': 'task',
      tabindex: 0,
    });

    group.append(element('text', {
      x: padding + 6 + task.depth * 12,
      y: centre + 4,
      class: `row-label${selectedKey === task.key ? ' selected-label' : ''}`,
      fill: selectedKey === task.key ? '#2e6ba7' : '#243b53',
      'font-size': 11,
      'font-weight': task.depth === 0 || task.raw.bold ? 700 : 400,
      'font-family': 'Inter, sans-serif',
    }, task.name));

    if (task.milestone) {
      const markerDates = task.milestoneDates.length ? task.milestoneDates : [task.effectiveStart].filter(Boolean);
      markerDates.forEach((date) => {
        const x = scale(date);
        const size = 7;
        group.append(element('polygon', {
          class: 'hit-shape',
          points: `${x},${centre - size} ${x + size},${centre} ${x},${centre + size} ${x - size},${centre}`,
          fill: task.color || chart.style.milestone_color || '#FFD700',
          stroke: task.edgeColor || chart.style.milestone_edge_color || '#8a6d00',
          'stroke-width': 1,
        }));
      });
      if (markerDates.length && task.id) {
        anchors.set(task.id, { start: scale(markerDates[0]), end: scale(markerDates[markerDates.length - 1]), y: centre });
      }
    } else if (task.effectiveStart && task.effectiveEnd) {
      const x = scale(task.effectiveStart);
      const barWidth = Math.max(2, scale(task.effectiveEnd) - x);
      group.append(element('rect', {
        class: 'hit-shape',
        x,
        y: centre - barHeight / 2,
        width: barWidth,
        height: barHeight,
        rx: 3,
        fill: task.resolvedColor || '#4472C4',
        stroke: task.edgeColor || 'none',
        'stroke-width': task.edgeColor ? 1 : 0,
      }));
      if (task.id) anchors.set(task.id, { start: x, end: x + barWidth, y: centre });
    } else {
      group.append(element('rect', {
        class: 'hit-shape',
        x: labelWidth + padding,
        y: centre - barHeight / 2,
        width: 4,
        height: barHeight,
        fill: 'none',
        stroke: 'none',
      }));
    }

    group.append(element('rect', {
      x: padding, y, width: width - padding * 2, height: rowHeight, fill: 'transparent',
    }));
    group.append(element('title', {}, `${task.name}${task.effectiveStart ? ` · ${formatDate(task.effectiveStart, chart.dateFormat)}` : ''}`));
    svg.append(group);
  });

  if (showArrows && chart.arrows.length) {
    const defs = element('defs');
    const marker = element('marker', {
      id: 'jsonantt-arrow', viewBox: '0 0 10 10', refX: 8, refY: 5,
      markerWidth: 6, markerHeight: 6, orient: 'auto-start-reverse',
    });
    marker.append(element('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: '#888888' }));
    defs.append(marker);
    svg.append(defs);

    chart.arrows.forEach((arrow) => {
      const from = anchors.get(arrow.from);
      const to = anchors.get(arrow.to);
      if (!from || !to) return;
      const path = element('path', {
        class: `selectable${selectedKey === `arrow.${arrow.index}` ? ' selected-element' : ''}`,
        'data-key': `arrow.${arrow.index}`,
        'data-kind': 'arrow',
        d: `M ${from.end} ${from.y} C ${from.end + 26} ${from.y}, ${to.start - 26} ${to.y}, ${to.start} ${to.y}`,
        fill: 'none',
        stroke: arrow.color,
        'stroke-width': selectedKey === `arrow.${arrow.index}` ? 2.4 : 1.4,
        'marker-end': 'url(#jsonantt-arrow)',
      });
      path.append(element('title', {}, arrow.label || `${arrow.from} → ${arrow.to}`));
      svg.append(path);
    });
  }

  if (!rows.length) {
    svg.append(element('text', {
      x: width / 2, y: height / 2, fill: '#829ab1', 'font-size': 12, 'text-anchor': 'middle',
      'font-family': 'Inter, sans-serif',
    }, 'No tasks yet — add one from the New menu.'));
  }

  return svg;
}
