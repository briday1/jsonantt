/**
 * Canonical jsonantt JSON formatting for the studio.
 *
 * When served by `jsonantt serve`, formatting runs through the `/api/format`
 * endpoint, which uses the exact same Python implementation as the CLI
 * (`jsonantt fmt`), so studio output is byte-for-byte identical to the CLI.
 * Under static hosting (no local server) a local serializer with the same
 * rules — 2-space indent, UTF-8 as-is, single trailing newline — is used.
 */

/** True when the local `jsonantt serve` backend is reachable. */
export async function serverFormattingAvailable() {
  try {
    const response = await fetch('healthz');
    return response.ok;
  } catch (error) {
    return false;
  }
}

/**
 * Format *text* as canonical jsonantt JSON.
 *
 * Returns `{ text, usedServer }`. Throws an `Error` when the text is not
 * valid JSON (the server's validation message is surfaced when available).
 */
export async function formatSourceText(text, { server = true } = {}) {
  if (server) {
    const response = await fetch('/api/format', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: text,
    });
    if (!response.ok) {
      let message = `format failed (${response.status})`;
      try {
        const payload = await response.json();
        if (payload && payload.error) message = payload.error;
      } catch (error) {
        /* keep the generic message */
      }
      throw new Error(message);
    }
    return { text: await response.text(), usedServer: true };
  }
  return { text: formatSourceLocal(text), usedServer: false };
}

/** Local fallback implementing the same canonical rules as the Python formatter. */
export function formatSourceLocal(text) {
  return formatSourceData(JSON.parse(text));
}

/** Canonical serialisation of an already-parsed document (same rules as the Python formatter). */
export function formatSourceData(data) {
  return `${JSON.stringify(data, null, 2)}\n`;
}
