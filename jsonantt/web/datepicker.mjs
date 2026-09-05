/**
 * Minimal dependency-free calendar popup used by the inspector date fields.
 *
 * `attachDatePicker(input, { format, onPick })` adds a subtle calendar trigger next
 * to *input*; picking a day writes it back in the chart's own date format via
 * the `onPick` callback (the input keeps manual typing untouched).
 */
import { formatDate, parseDate } from './model.mjs';

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];

let openPopup = null;
let openTrigger = null;

function closeOpenPopup() {
  if (openPopup) {
    openPopup.remove();
    openPopup = null;
    openTrigger?.setAttribute('aria-expanded', 'false');
    if (openTrigger?.isConnected) openTrigger.focus();
    openTrigger = null;
  }
}

function utcDate(year, month, day) {
  return new Date(Date.UTC(year, month, day));
}

function buildCalendar({ format, initial, onPick }) {
  const today = new Date();
  let viewYear = (initial || today).getUTCFullYear();
  let viewMonth = (initial || today).getUTCMonth();

  const popup = document.createElement('div');
  popup.className = 'date-picker';
  popup.setAttribute('role', 'dialog');
  popup.setAttribute('aria-label', 'Choose a date');

  const render = () => {
    popup.replaceChildren();
    const header = document.createElement('div');
    header.className = 'date-picker-header';

    const prev = document.createElement('button');
    prev.type = 'button';
    prev.textContent = '‹';
    prev.setAttribute('aria-label', 'Previous month');
    prev.addEventListener('click', () => {
      viewMonth -= 1;
      if (viewMonth < 0) { viewMonth = 11; viewYear -= 1; }
      render();
    });

    const next = document.createElement('button');
    next.type = 'button';
    next.textContent = '›';
    next.setAttribute('aria-label', 'Next month');
    next.addEventListener('click', () => {
      viewMonth += 1;
      if (viewMonth > 11) { viewMonth = 0; viewYear += 1; }
      render();
    });

    const title = document.createElement('strong');
    title.textContent = formatDate(utcDate(viewYear, viewMonth, 1), '%B %Y');

    header.append(prev, title, next);
    popup.append(header);

    const grid = document.createElement('div');
    grid.className = 'date-picker-grid';
    WEEKDAYS.forEach((day) => {
      const label = document.createElement('span');
      label.className = 'date-picker-weekday';
      label.textContent = day;
      grid.append(label);
    });

    const first = utcDate(viewYear, viewMonth, 1);
    const leadingBlanks = (first.getUTCDay() + 6) % 7; // weeks start Monday
    for (let index = 0; index < leadingBlanks; index += 1) {
      grid.append(document.createElement('span'));
    }
    const daysInMonth = new Date(Date.UTC(viewYear, viewMonth + 1, 0)).getUTCDate();
    for (let day = 1; day <= daysInMonth; day += 1) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'date-picker-day';
      button.textContent = String(day);
      const isSelected = initial
        && initial.getUTCFullYear() === viewYear
        && initial.getUTCMonth() === viewMonth
        && initial.getUTCDate() === day;
      if (isSelected) button.classList.add('selected');
      const isToday = today.getUTCFullYear() === viewYear
        && today.getUTCMonth() === viewMonth
        && today.getUTCDate() === day;
      if (isToday) button.classList.add('today');
      button.addEventListener('click', () => {
        onPick(formatDate(utcDate(viewYear, viewMonth, day), format));
        closeOpenPopup();
      });
      grid.append(button);
    }
    popup.append(grid);

    const footer = document.createElement('div');
    footer.className = 'date-picker-footer';
    const todayButton = document.createElement('button');
    todayButton.type = 'button';
    todayButton.textContent = 'Today';
    todayButton.addEventListener('click', () => {
      onPick(formatDate(utcDate(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()), format));
      closeOpenPopup();
    });
    footer.append(todayButton);
    popup.append(footer);
  };

  render();
  return popup;
}

/**
 * Attach a calendar trigger to *input*. `format` is the chart's date format;
 * `onPick(text)` is called with the picked date in that format.
 */
export function attachDatePicker(input, { format, onPick, multiple = false }) {
  wireGlobalListeners(input);
  if (!input.parentNode) {
    // Not mounted yet: wrap now and let the caller append the wrapper instead.
    const wrapper = document.createElement('span');
    wrapper.className = 'date-field';
    wrapper.append(input);
    buildTrigger(wrapper, input, { format, onPick, multiple });
    return wrapper;
  }
  buildTrigger(wrapInline(input), input, { format, onPick, multiple });
  return null;
}

function wrapInline(input) {
  const wrapper = document.createElement('span');
  wrapper.className = 'date-field';
  input.replaceWith(wrapper);
  wrapper.append(input);
  return wrapper;
}

function buildTrigger(wrapper, input, { format, onPick, multiple }) {
  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'date-trigger';
  trigger.setAttribute('aria-label', 'Pick a date');
  trigger.setAttribute('aria-haspopup', 'dialog');
  trigger.setAttribute('aria-expanded', 'false');
  trigger.title = 'Pick a date';
  trigger.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5.5" width="17" height="15" rx="2"></rect><path d="M8 3v5M16 3v5M3.5 10h17"></path></svg>';
  wrapper.append(trigger);

  trigger.addEventListener('click', (event) => {
    event.stopPropagation();
    if (openPopup) {
      const sameTrigger = openTrigger === trigger;
      closeOpenPopup();
      if (sameTrigger) return;
    }
    let initial = null;
    try {
      let text = multiple ? input.value.split(',').at(-1).trim() : input.value.trim();
      if (format === '%m-%d' && /^\d{1,2}$/.test(text)) text += '-01';
      if (text) initial = parseDate(text, format);
      if (initial && !/%[Yy]/.test(format)) initial.setUTCFullYear(new Date().getFullYear());
    } catch (error) {
      initial = null;
    }
    const popup = buildCalendar({ format, initial, onPick: text => {
      if (multiple) {
        const parts = input.value.split(',');
        parts[parts.length - 1] = text;
        text = parts.map(part=>part.trim()).filter(Boolean).join(', ');
      }
      input.value = text;
      onPick(text);
    }});
    // Keep clicks inside the calendar from reaching the dismissal listener.
    popup.addEventListener('click', (clickEvent) => clickEvent.stopPropagation());
    // The dialog keeps the calendar in its focus scope; a popover raises it
    // above modal content and scrolling/clipping containers in the top layer.
    (input.closest('dialog[open]') || document.body).append(popup);
    if (typeof popup.showPopover === 'function') {
      popup.setAttribute('popover', 'manual');
      popup.showPopover();
    }
    const triggerBox = trigger.getBoundingClientRect();
    const popupBox = popup.getBoundingClientRect();
    const gap = 4;
    const viewportPad = 8;
    let left = triggerBox.right - popupBox.width;
    left = Math.max(viewportPad, Math.min(left, window.innerWidth - popupBox.width - viewportPad));
    let top = triggerBox.bottom + gap;
    if (top + popupBox.height > window.innerHeight - viewportPad) {
      top = triggerBox.top - popupBox.height - gap;
    }
    top = Math.max(viewportPad, Math.min(top, window.innerHeight - popupBox.height - viewportPad));
    popup.style.left = `${left}px`;
    popup.style.top = `${top}px`;
    openPopup = popup;
    openTrigger = trigger;
    trigger.setAttribute('aria-expanded', 'true');
    popup.querySelector('.date-picker-day.selected, .date-picker-day.today, .date-picker-day')?.focus();
  });
}

// Dismissal listeners are attached per-document the first time a picker is
// wired, so the module works regardless of when/where it was imported.
const wiredDocuments = new WeakSet();

function wireGlobalListeners(input) {
  const doc = input.ownerDocument;
  if (!doc || wiredDocuments.has(doc)) return;
  wiredDocuments.add(doc);
  doc.addEventListener('click', (event) => {
    if (openPopup && !openPopup.contains(event.target)) closeOpenPopup();
  });
  doc.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && openPopup) {
      event.preventDefault();
      event.stopPropagation();
      closeOpenPopup();
    }
  }, true);
  doc.addEventListener('close', () => { if (openPopup) closeOpenPopup(); }, true);
}
