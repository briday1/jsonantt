/** Two-state toggle, initialized from the OS unless the user has overridden it. */
export function wireThemeControl(control) {
  const media=window.matchMedia?.('(prefers-color-scheme: dark)');
  let preference='system';
  try {
    const saved=localStorage.getItem('jsonantt.theme');
    if (['system','light','dark'].includes(saved)) preference=saved;
  } catch { /* Theme storage is optional. */ }
  const apply=()=>{
    const theme=preference==='system' ? (media?.matches ? 'dark':'light') : preference;
    document.documentElement.dataset.theme=theme;
    document.documentElement.dataset.themePreference=preference;
    control.setAttribute('aria-checked',String(theme==='dark'));
    control.title=`Switch to ${theme==='dark'?'light':'dark'} mode`;
    const label=control.querySelector('[data-theme-label]');
    if(label)label.textContent=theme==='dark'?'Dark':'Light';
  };
  control.addEventListener('click',()=>{
    preference=document.documentElement.dataset.theme==='dark'?'light':'dark';
    apply();
    try {localStorage.setItem('jsonantt.theme',preference);} catch { /* Storage is optional. */ }
  });
  const changed=()=>{if(preference==='system')apply();};
  if(media?.addEventListener)media.addEventListener('change',changed);
  else media?.addListener?.(changed);
  apply();
}
