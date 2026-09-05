/** Published package metadata is optional and never gates studio startup. */
const CACHE_KEY = 'jsonantt.pypi-version.v1';
const MAX_AGE = 60 * 60 * 1000;
const ENDPOINT = 'https://pypi.org/pypi/jsonantt/json';
const validVersion = value => typeof value === 'string' && /^\d[\w.!+\-]{0,79}$/.test(value);

export function wirePublishedVersion(menu, label) {
  let cached = null, pending = false;
  try {
    const value = JSON.parse(localStorage.getItem(CACHE_KEY));
    if (validVersion(value?.version) && Number.isFinite(value.checkedAt)) cached = value;
  } catch { /* Offline/storage-restricted browsers still work. */ }
  const show = (value, detail) => {
    label.textContent = value;
    label.title = detail;
  };
  show(cached?.version || '—', cached ? 'Last checked published PyPI version' : 'Checked when this menu opens');
  const refresh = async () => {
    if (!menu.open || pending) return;
    const age = cached ? Date.now() - cached.checkedAt : Infinity;
    if (age >= 0 && age < MAX_AGE) return;
    pending = true;
    if (!cached) show('Checking…', 'Looking up the published PyPI version');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(ENDPOINT, {signal: controller.signal, credentials: 'omit', referrerPolicy: 'no-referrer'});
      if (!response.ok) throw new Error('PyPI unavailable');
      const version = (await response.json()).info?.version;
      if (!validVersion(version)) throw new Error('Invalid PyPI version');
      cached = {version, checkedAt: Date.now()};
      show(version, 'Latest published PyPI release (not necessarily the running build)');
      try { localStorage.setItem(CACHE_KEY, JSON.stringify(cached)); } catch { /* Caching is optional. */ }
    } catch {
      show(cached?.version || 'Unavailable', cached ? 'Cached PyPI version; could not check for updates' : 'Could not reach PyPI; the studio works offline');
    } finally {
      clearTimeout(timeout);
      pending = false;
    }
  };
  menu.addEventListener('toggle', refresh);
  void refresh();
}
