/** Best-effort local recovery, including invalid/unsaved source text. */
const KEY = 'jsonantt.workspace.v1';
export function readWorkspace() {
  try {
    const value = JSON.parse(localStorage.getItem(KEY));
    return value?.version === 1 && typeof value.source === 'string' ? value : null;
  } catch { return null; }
}
export function saveWorkspace(value) {
  try {
    localStorage.setItem(KEY, JSON.stringify({...value,version:1}));
    return true;
  } catch {
    // Preserve the draft and baseline ahead of optional undo history on quota errors.
    try {
      localStorage.setItem(KEY, JSON.stringify({...value,undoStack:[],redoStack:[],version:1}));
      return true;
    } catch { return false; }
  }
}
