/**
 * Minimal dependency-free calendar popup used by the inspector date fields.
 *
 * `attachDatePicker(input, { format, onPick })` adds a 📅 trigger button next
 * to *input*; picking a day writes it back in the chart's own date format via
 * the `onPick` callback (the input keeps manual typing untouched).
 */
import { formatDate, parseDate } from './model.mjs';

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];

let openPopup = null;

function closeOpenPopup() {
  if (openPopup) {
    openPopup.remove();
    openPopup = null;
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
export function attachDatePicker(input, { format, onPick }) {
  const wrapper = document.createElement('span');
  wrapper.className = 'date-field';
  input.replaceWith(wrapper);
  wrapper.append(input);

  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'date-trigger';
  trigger.setAttribute('aria-label', 'Pick a date');
  trigger.title = 'Pick a date';
  trigger.textContent = '📅';
  wrapper.append(trigger);

  trigger.addEventListener('click', (event) => {
    event.stopPropagation();
    if (openPopup) {
      closeOpenPopup();
      return;
    }
    let initial = null;
    try {
      if (input.value.trim()) initial = parseDate(input.value, format);
    } catch (error) {
      initial = null;
    }
    const popup = buildCalendar({ format, initial, onPick });
    wrapper.append(popup);
    openPopup = popup;
  });
}

if (typeof document !== 'undefined') {
  document.addEventListener('click', (event) => {
    if (openPopup && !openPopup.contains(event.target)) closeOpenPopup();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && openPopup) {
      event.stopPropagation();
      closeOpenPopup();
    }
  });
}
