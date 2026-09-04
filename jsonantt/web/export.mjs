/**
 * Studio image/table export.
 *
 * Exports are *always* produced by the local `jsonantt serve` backend calling
 * straight into `jsonantt.renderer` — the exact matplotlib-based code path the
 * `jsonantt` command-line tool uses. There is deliberately no client-side (DOM
 * SVG / canvas) rendering fallback for exported files: under static hosting
 * (no local server) export is unavailable and callers should direct users to
 * run `jsonantt serve` or the `jsonantt` CLI instead.
 */

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
 * @param {'gantt'|'table'|'burn'|'burn-table'} options.mode
 * @param {'png'|'svg'|'csv'} options.format
 * @param {number} [options.dpi] - Raster DPI (png only).
 * @returns {Promise<Blob>} the rendered file contents.
 */
export async function exportChart(source, { mode, format, dpi = 150 } = {}) {
  const params = new URLSearchParams({ mode, format, dpi: String(dpi) });
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
    throw new Error(message);
  }
  return response.blob();
}
