/** SVG structure graph renderer (task hierarchy + dependency arrows). */
import { formatDate } from './model.mjs';

const SVG_NS = 'http://www.w3.org/2000/svg';

function element(name, attributes = {}, text) {
  const node = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) => {
    if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  });
  if (text !== undefined) node.textContent = text;
  return node;
}

function truncate(text, max) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/**
 * Render the same chart model as a node/edge graph: parent/child links are
 * drawn as solid connectors and `arrows` entries as dashed dependencies.
 */
export function renderGraph(chart, options = {}) {
  const { selectedKey = null } = options;
  const nodeWidth = 176;
  const nodeHeight = 42;
  const gapX = 62;
  const gapY = 16;
  const padding = 26;

  const placed = [];
  let row = 0;
  const place = (tasks) => {
    tasks.forEach((task) => {
      placed.push({ task, row: row += 1 });
      place(task.children);
    });
  };
  place(chart.tasks);

  const maxDepth = placed.reduce((max, entry) => Math.max(max, entry.task.depth), 0);
  const width = padding * 2 + (maxDepth + 1) * nodeWidth + maxDepth * gapX;
  const height = padding * 2 + Math.max(1, placed.length) * (nodeHeight + gapY);

  const svg = element('svg', {
    xmlns: SVG_NS, width, height, viewBox: `0 0 ${width} ${height}`, class: 'graph-svg', role: 'img',
  });
  svg.append(element('rect', { x: 0, y: 0, width, height, fill: chart.style.background || '#ffffff' }));

  const defs = element('defs');
  const marker = element('marker', {
    id: 'jsonantt-graph-arrow', viewBox: '0 0 10 10', refX: 9, refY: 5,
    markerWidth: 6, markerHeight: 6, orient: 'auto-start-reverse',
  });
  marker.append(element('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: '#627d98' }));
  defs.append(marker);
  svg.append(defs);

  const boxes = new Map();
  placed.forEach((entry, index) => {
    const x = padding + entry.task.depth * (nodeWidth + gapX);
    const y = padding + index * (nodeHeight + gapY);
    boxes.set(entry.task.key, { x, y, width: nodeWidth, height: nodeHeight, task: entry.task });
  });

  // parent → child connectors
  placed.forEach(({ task }) => {
    if (!task.parent) return;
    const from = boxes.get(task.parent.key);
    const to = boxes.get(task.key);
    if (!from || !to) return;
    const startX = from.x + 18;
    const startY = from.y + from.height;
    svg.append(element('path', {
      d: `M ${startX} ${startY} V ${to.y + to.height / 2} H ${to.x}`,
      fill: 'none',
      stroke: '#cbd8e4',
      'stroke-width': 1.4,
    }));
  });

  // dependency arrows
  chart.arrows.forEach((arrow) => {
    const fromTask = chart.byId.get(arrow.from);
    const toTask = chart.byId.get(arrow.to);
    if (!fromTask || !toTask) return;
    const from = boxes.get(fromTask.key);
    const to = boxes.get(toTask.key);
    if (!from || !to) return;
    const key = `arrow.${arrow.index}`;
    const path = element('path', {
      class: `selectable${selectedKey === key ? ' selected-element' : ''}`,
      'data-key': key,
      'data-kind': 'arrow',
      d: `M ${from.x + from.width} ${from.y + from.height / 2} C ${from.x + from.width + 40} ${from.y + from.height / 2}, ${to.x - 40} ${to.y + to.height / 2}, ${to.x} ${to.y + to.height / 2}`,
      fill: 'none',
      stroke: arrow.color,
      'stroke-dasharray': '5 4',
      'stroke-width': selectedKey === key ? 2.4 : 1.5,
      'marker-end': 'url(#jsonantt-graph-arrow)',
    });
    path.append(element('title', {}, arrow.label || `${arrow.from} → ${arrow.to}`));
    svg.append(path);
  });

  boxes.forEach(({ x, y, task }) => {
    const selected = selectedKey === task.key;
    const group = element('g', {
      class: `selectable${selected ? ' selected-element' : ''}`,
      'data-key': task.key,
      'data-kind': 'task',
      tabindex: 0,
    });
    group.append(element('rect', {
      class: 'hit-shape',
      x, y, width: nodeWidth, height: nodeHeight, rx: 8,
      fill: '#ffffff',
      stroke: selected ? '#2e6ba7' : '#cbd8e4',
      'stroke-width': selected ? 2 : 1,
    }));
    group.append(element('rect', {
      x, y, width: 6, height: nodeHeight, rx: 3,
      fill: task.milestone ? (task.color || chart.style.milestone_color || '#FFD700') : (task.resolvedColor || '#4472C4'),
    }));
    group.append(element('text', {
      x: x + 16, y: y + 18, fill: '#102a43', 'font-size': 11, 'font-weight': 650, 'font-family': 'Inter, sans-serif',
    }, truncate(task.name, 22)));
    const start = task.effectiveStart ? formatDate(task.effectiveStart, chart.dateFormat) : '—';
    const end = task.effectiveEnd ? formatDate(task.effectiveEnd, chart.dateFormat) : '—';
    group.append(element('text', {
      x: x + 16, y: y + 32, fill: '#829ab1', 'font-size': 9, 'font-family': 'Consolas, monospace',
    }, task.milestone ? `milestone · ${start}` : `${start} → ${end}`));
    group.append(element('title', {}, task.id ? `${task.name} (#${task.id})` : task.name));
    svg.append(group);
  });

  if (!placed.length) {
    svg.append(element('text', {
      x: width / 2, y: height / 2, fill: '#829ab1', 'font-size': 12, 'text-anchor': 'middle',
      'font-family': 'Inter, sans-serif',
    }, 'No tasks yet — add one from the New menu.'));
  }

  return svg;
}
