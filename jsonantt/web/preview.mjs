/** Interactive, renderer-authored SVG. Never an <img>, screenshot, or canvas bitmap. */
import { buildBurn, burnValueFormatter, burnDisplayForMode, burnLineValues } from './burn.mjs';
import { formatDate } from './model.mjs';
import { renderInBrowser } from './python-client.mjs';
import { previewKey } from './preview-store.mjs';

export function interactiveChartSvg(text, chart, options, selectedKey = null) {
  const parsed = new DOMParser().parseFromString(text, 'image/svg+xml');
  if (parsed.querySelector('parsererror') || parsed.documentElement.localName !== 'svg') throw new Error('The preview server returned invalid SVG.');
  const svg = document.importNode(parsed.documentElement, true);
  svg.querySelectorAll('script, foreignObject').forEach(node=>node.remove());
  for (const node of [svg, ...svg.querySelectorAll('*')]) {
    for (const attribute of [...node.attributes]) {
      if (/^on/i.test(attribute.name) || (attribute.localName === 'href' && !attribute.value.startsWith('#'))) node.removeAttributeNode(attribute);
    }
  }
  const [, , width, height] = svg.getAttribute('viewBox').split(/\s+/).map(Number);
  svg.setAttribute('width', width * 4 / 3);
  svg.setAttribute('height', height * 4 / 3);
  svg.dataset.renderer = 'python';
  svg.dataset.previewMode = options.mode;
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `${chart.title || options.mode} — interactive CLI renderer preview`);
  const title = (node, text) => {
    const label = document.createElementNS('http://www.w3.org/2000/svg','title');
    label.textContent = text;
    node.append(label);
  };
  const selectable = (node, key, kind, label) => {
    node.dataset.key = key;
    node.dataset.kind = kind;
    node.classList.add('selectable');
    if (key === selectedKey) node.classList.add('selected-element');
    node.setAttribute('tabindex', '0');
    node.setAttribute('role', 'button');
    node.setAttribute('aria-label', label);
  };
  if (!options.mode.startsWith('burn')) {
    const tasks = new Map();
    const visit = (items, prefix='') => items.forEach((task,index)=>{
      const number = `${prefix}${index+1}`;
      tasks.set(number,task);
      visit(task.children,`${number}.`);
    });
    visit(chart.tasks);
    svg.querySelectorAll('[id^="studio-task-"], [id^="studio-arrow-"]').forEach(node=>{
      const [, kind, identifier] = /^studio-(task|arrow)-(.+?)--/.exec(node.id) || [];
      if (kind === 'task') {
        const task = tasks.get(identifier);
        if (!task) return;
        const dates = [task.effectiveStart,task.effectiveEnd].filter(Boolean).map(date=>formatDate(date,chart.dateFormat));
        const label = [task.name, task.id, dates.join(' → '), task.description].filter(Boolean).join(' · ');
        selectable(node,task.key,'task',label);
        title(node,label);
      } else if (kind === 'arrow') {
        const arrow = chart.arrows.find(item=>item.index === Number(identifier));
        if (!arrow) return;
        const label = [arrow.label,`${arrow.from} → ${arrow.to}`].filter(Boolean).join(' · ');
        selectable(node,`arrow.${arrow.index}`,'arrow',label);
        title(node,label);
      }
    });
    return svg;
  }
  const burn = buildBurn(chart, options);
  const series = new Map(burn.series.map(item=>[item.number || 'total',item]));
  const number = burnValueFormatter(chart, burn.field, burn.factor);
  svg.querySelectorAll('[id^="studio-series-"]').forEach(node=>{
    const match = /^studio-series-(.+?)--(.+)$/.exec(node.id);
    const item = match && series.get(match[1]);
    if (!item) return;
    if (item.task) {
      selectable(node,item.task.key,'task',item.name);
    }
    let label = item.name;
    if (match[2] === 'budget') label += ` · Budget ${number(item.budget)}`;
    const bar = /^bar-(\d+)$/.exec(match[2]);
    if (bar) label += ` · ${burn.periods[Number(bar[1])].label} · ${number(item.values[Number(bar[1])])}`;
    const cell = /^cell-(\d+)/.exec(match[2]);
    if (cell && Number(cell[1]) > 1) {
      const index = Number(cell[1]) - 2;
      label += ` · ${burn.periods[index].label} · ${number(item.values[index])}`;
    }
    title(node,label);
    if (match[2] === 'line') {
      const points = burnLineValues(item.values, burnDisplayForMode(options.mode));
      node.querySelectorAll('use').forEach((point,index)=>{
        if (index < points.length) title(point, `${item.name} · ${index ? burn.periods[index-1].label : 'Start'} · ${number(points[index])}`);
      });
    }
  });
  return svg;
}

export function createPreviewLoader({onRender, onError, onPending = () => {}, onProgress = () => {}, useBrowser = () => false, store = null}) {
  let timer, controller, generation = 0;
  let previousSource;
  const cache = new Map();
  return {
    cancel() { clearTimeout(timer); controller?.abort(); generation++; },
    schedule(source, chart, options, selectedKey) {
      this.cancel();
      const ticket = generation;
      const key = previewKey(source,options);
      const editing = previousSource !== undefined && previousSource !== source;
      previousSource = source;
      const render = text => {if (ticket === generation) onRender(interactiveChartSvg(text,chart,options,selectedKey));};
      if (cache.has(key)) { render(cache.get(key)); return; }
      onPending(options);
      timer = setTimeout(async()=>{
        controller = new AbortController();
        try {
          if (store && useBrowser(options)) {
            const saved = await store.get(key);
            if (ticket !== generation) return;
            if (saved) {
              try {
                render(saved);
                cache.set(key,saved);
                if (cache.size > 6) cache.delete(cache.keys().next().value);
                void store.put(key,saved);
                return;
              } catch {/* Regenerate corrupt cached SVG. */}
            }
          }
          let text;
          if (useBrowser(options)) {
            const blob = await renderInBrowser(source, {mode:options.mode,format:'svg',interactive:true,
              renderDepth:options.renderDepth,tableFilter:options.tableFilter,burn:options},
            {signal:controller.signal,onProgress:message=>{if (ticket === generation) onProgress(message);}});
            text = await blob.text();
          } else {
          const params = new URLSearchParams({mode:options.mode});
          if (options.mode.startsWith('burn')) {
            params.set('burn_field',options.field ?? 'cost');
            params.set('burn_period',options.period ?? 'month');
            params.set('burn_group',options.group ?? '0');
            params.set('burn_factor',options.factor ?? 1);
          } else {
            if (options.renderDepth !== undefined) params.set('render_depth',options.renderDepth);
            if (options.mode === 'table') params.set('table_filter',options.tableFilter ?? 'all');
          }
          const response = await fetch(`/api/preview?${params}`, {method:'POST',headers:{'Content-Type':'application/json'},body:source,signal:controller.signal});
          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Renderer preview failed.');
          }
          text = await response.text();
          }
          if (ticket !== generation) return;
          cache.set(key,text);
          if (cache.size > 6) cache.delete(cache.keys().next().value);
          render(text);
          if (store && useBrowser(options)) void store.put(key,text);
        } catch (error) {
          if (error.name !== 'AbortError' && ticket === generation) onError(error.message);
        }
      },editing ? 150 : 0);
    },
  };
}
