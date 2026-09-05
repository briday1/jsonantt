/** Drag the inspector within the visible canvas, never the scrollable chart. */
export function clampInspectorPosition(position, bounds, size, margin = 12) {
  const padX = Math.min(margin, Math.max(0, (bounds.width - size.width) / 2));
  const padY = Math.min(margin, Math.max(0, (bounds.height - size.height) / 2));
  return {
    x: Math.max(padX, Math.min(position.x, bounds.width - size.width - padX)),
    y: Math.max(padY, Math.min(position.y, bounds.height - size.height - padY)),
  };
}

export function wireInspectorDrag(panel, shell, handle) {
  let position = null;
  let drag = null;
  function currentPosition() {
    const box = panel.getBoundingClientRect(), area = shell.getBoundingClientRect();
    return { x: box.left - area.left - shell.clientLeft, y: box.top - area.top - shell.clientTop };
  }
  function move(next) {
    position = clampInspectorPosition(next, {width:shell.clientWidth, height:shell.clientHeight},
      {width:panel.offsetWidth, height:panel.offsetHeight});
    panel.style.right = 'auto';
    panel.style.left = `${position.x}px`;
    panel.style.top = `${position.y}px`;
  }
  function reclamp() {
    if (!panel.hidden && position) move(position);
  }
  handle.addEventListener('pointerdown', event => {
    if (event.button !== 0 || event.isPrimary === false) return;
    event.preventDefault();
    drag = {id:event.pointerId, x:event.clientX, y:event.clientY, origin:currentPosition()};
    handle.setPointerCapture(event.pointerId);
    handle.classList.add('dragging');
  });
  handle.addEventListener('pointermove', event => {
    if (!drag || event.pointerId !== drag.id) return;
    move({x:drag.origin.x + event.clientX - drag.x, y:drag.origin.y + event.clientY - drag.y});
  });
  const stop = event => {
    if (!drag || event.pointerId !== drag.id) return;
    drag = null;
    handle.classList.remove('dragging');
    if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
  };
  for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) handle.addEventListener(type, stop);
  handle.addEventListener('keydown', event => {
    const delta = {ArrowLeft:[-1,0], ArrowRight:[1,0], ArrowUp:[0,-1], ArrowDown:[0,1]}[event.key];
    if (!delta) return;
    event.preventDefault();
    const origin = currentPosition(), step = event.shiftKey ? 20 : 5;
    move({x:origin.x + delta[0] * step, y:origin.y + delta[1] * step});
  });
  const view = panel.ownerDocument.defaultView;
  if (view.ResizeObserver) {
    const observer = new view.ResizeObserver(reclamp);
    observer.observe(shell);
    observer.observe(panel);
  }
  view.addEventListener('resize', reclamp);
  return {reclamp};
}
