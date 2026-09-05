/**
 * Studio image/table export.
 *
 * Exports always use jsonantt.renderer, either through the local server or
 * through Pyodide in a worker on static hosts. No DOM screenshot renderer.
 */

import { burnDisplayForMode } from './burn.mjs';
import { renderInBrowser } from './python-client.mjs';

let backend = 'server';
export function setExportBackend(value) { backend = value; }

/** True when the local `jsonantt serve` backend is reachable. */
export async function serverExportAvailable() {
  try {
    const response = await fetch('healthz');
    return response.ok;
  } catch (error) {
    return false;
  }
}

/**
 * Export the chart described by JSON *source* text via the CLI's
 * matplotlib renderer, running on the `jsonantt serve` backend.
 *
 * @param {string} source - Raw JSON chart document text.
 * @param {Object} options
 * @param {'gantt'|'table'|'burn'|'burndown'|'burnup'|'burn-table'} options.mode
 * @param {'png'|'svg'|'csv'} options.format
 * @param {number} [options.dpi] - Raster DPI (png only).
 * @returns {Promise<Blob>} the rendered file contents.
 */
export async function exportChart(source, { mode, format, dpi = 150, tableFilter = 'all', renderDepth = 0, burn = {} } = {}) {
  if (backend === 'browser') return renderInBrowser(source, {mode,format,dpi,tableFilter,renderDepth,burn});
  const params = new URLSearchParams({ mode, format, dpi: String(dpi) });
  if (mode === 'table' || mode === 'gantt') params.set('render_depth', String(renderDepth));
  if (mode === 'table') params.set('table_filter', tableFilter);
  if (mode?.startsWith('burn')) {
    params.set('burn_field', burn.field ?? 'cost');
    params.set('burn_period', burn.period ?? 'month');
    params.set('burn_group', burn.group ?? '0');
    params.set('burn_factor', String(burn.factor ?? 1));
    params.set('burn_display', mode === 'burn' ? (burn.display ?? 'spend') : burnDisplayForMode(mode));
  }
  const response = await fetch(`/api/export?${params.toString()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: source,
  });
  if (!response.ok) {
    let message = `export failed (${response.status})`;
    try {
      const payload = await response.json();
      if (payload && payload.error) message = payload.error;
    } catch (error) {
      /* keep the generic message */
    }
    if (message.includes('unknown export mode')) message += '. Restart jsonantt serve from the updated installation and refresh the page.';
    throw new Error(message);
  }
  if (mode === 'table' && tableFilter !== 'all'
      && response.headers.get('X-Jsonantt-Table-Filter') !== tableFilter) {
    throw new Error('The server did not confirm the selected table rows. Restart jsonantt serve from the updated installation, then refresh the page and export again.');
  }
  const blob = await response.blob();
  if (!blob.size || blob.type.includes('text/html')) throw new Error('The server did not return an exported file. Run the updated jsonantt serve server and try again.');
  return blob;
}
