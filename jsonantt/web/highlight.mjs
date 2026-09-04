/**
 * Dependency-free JSON syntax highlighting for the studio source editor.
 *
 * A `<pre>` overlay renders the highlighted tokens behind the (transparent)
 * textarea; the app keeps the two scroll positions in sync. Highlighting is
 * purely visual — editing, selection, undo/redo and error reporting are
 * untouched.
 */

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };

/** HTML-escape *text*. */
export function escapeHtml(text) {
  return text.replace(/[&<>"]/g, (char) => ESCAPES[char]);
}

const TOKEN_RE = /("(?:\\.|[^"\\\n])*"(?:[ \t]*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

/** Render JSON *text* as highlighted HTML (suitable for `innerHTML`). */
export function highlightJson(text) {
  let html = '';
  let cursor = 0;
  for (const match of text.matchAll(TOKEN_RE)) {
    const token = match[0];
    html += escapeHtml(text.slice(cursor, match.index));
    if (token.startsWith('"')) {
      const isKey = /[ \t]*:$/.test(token);
      if (isKey) {
        const split = token.search(/[ \t]*:$/);
        html += `<span class="tok-key">${escapeHtml(token.slice(0, split))}</span>${escapeHtml(token.slice(split))}`;
      } else {
        html += `<span class="tok-string">${escapeHtml(token)}</span>`;
      }
    } else if (token === 'true' || token === 'false' || token === 'null') {
      html += `<span class="tok-literal">${escapeHtml(token)}</span>`;
    } else {
      html += `<span class="tok-number">${escapeHtml(token)}</span>`;
    }
    cursor = match.index + token.length;
  }
  return html + escapeHtml(text.slice(cursor));
}
