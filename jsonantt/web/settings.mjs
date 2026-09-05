/** Source-backed chart settings. Defaults match the Python Style dataclass. */
import { attachDatePicker } from './datepicker.mjs';
import { formatDate } from './model.mjs';
import { STYLE_OPTIONS, parseArraySetting } from './style-options.mjs';

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function field(label, input, help) {
  const wrap = element('div', 'settings-field');
  wrap.append(element('span', '', label), input);
  if (help) wrap.append(element('small', 'settings-help', help));
  return wrap;
}
function settingInput(option, value, save) {
  const multiline = ['columns', 'palette', 'fields'].includes(option.type);
  const input = element(option.type === 'select' ? 'select' : multiline ? 'textarea' : 'input');
  input.dataset.setting = option.key;
  input.setAttribute('aria-label', option.label);
  if (option.type === 'boolean') {
    input.type = 'checkbox';
    input.checked = value ?? option.default;
  } else if (option.type === 'select') {
    const choices = [...option.choices];
    if (value != null && !choices.includes(value)) choices.push(value);
    choices.forEach(value => {
      const item = element('option', '', value || 'Default');
      item.value = value;
      input.append(item);
    });
    input.value = value ?? option.default ?? '';
  } else {
    if (!multiline) input.type = option.type === 'number' ? 'number' : 'text';
    input.value = multiline ? (value == null ? '' : JSON.stringify(value, null, 2)) : value ?? '';
    input.placeholder = option.default == null ? 'Inherit / default' : multiline ? JSON.stringify(option.default) : String(option.default);
    if (multiline) input.rows = option.type === 'columns' ? 5 : 3;
    if (option.type === 'number') {
      input.step = option.step;
      if (option.min != null) input.min = option.min;
      if (option.max != null) input.max = option.max;
    }
  }
  input.addEventListener('input', () => input.setCustomValidity(''));
  input.addEventListener('change', () => {
    try {
      input.setCustomValidity('');
      if (!input.checkValidity()) { input.reportValidity(); return; }
      const text = input.value.trim();
      let result;
      if (option.type === 'boolean') result = input.checked;
      else if (!text) result = undefined;
      else if (option.type === 'number') result = Number(text);
      else if (multiline) result = parseArraySetting(text, option.type);
      else result = text;
      if (option.key === 'fiscal_year_start' && result && !/^(0?[1-9]|1[0-2])(?:-(0?[1-9]|[12]\d|3[01]))?$/.test(result)) throw new Error('Use MM or MM-DD, such as 10-01.');
      save(result);
    } catch (error) {
      input.setCustomValidity(error.message);
      input.reportValidity();
    }
  });
  const wrap = element('span', 'setting-control');
  wrap.append(input);
  if (option.key === 'fiscal_year_start') {
    attachDatePicker(input, {format: '%m-%d', onPick: text => save(text)});
  }
  if (option.type === 'color') {
    const picker = element('input');
    picker.type = 'color';
    picker.setAttribute('aria-label', `${option.label} picker`);
    const color = value ?? option.default;
    picker.value = /^#[0-9a-f]{6}$/i.test(color || '') ? color : '#ffffff';
    picker.addEventListener('change', () => save(picker.value));
    wrap.append(picker);
  }
  const reset = element('button', 'color-clear', 'Reset');
  reset.type = 'button';
  reset.title = `Reset ${option.label} to its default`;
  reset.addEventListener('click', () => save(undefined));
  wrap.append(reset);
  return wrap;
}

export function renderChartSettings(container, doc, { onCommit, initialFocus = '' } = {}) {
  const scrollTop = container.scrollTop;
  container.replaceChildren();
  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) {
    container.append(element('p', 'settings-empty', 'Chart settings become available once the source is valid JSON.'));
    return;
  }
  // Resolve the write target on change; opening the form never mutates source.
  const style = doc.style && typeof doc.style === 'object' && !Array.isArray(doc.style) ? doc.style : {};
  container.append(element('h3', '', 'General'));
  const saveTop = (key, value) => {
    if (value === undefined) delete doc[key];
    else doc[key] = value;
    onCommit();
  };
  for (const [key, label] of [['title', 'Title'], ['dateformat', 'Date format'], ['start', 'Chart start'], ['end', 'Chart end']]) {
    const value = key === 'dateformat' ? doc.dateformat ?? doc.date_format : doc[key];
    const wrap = settingInput({key, label, type:'text', default:key === 'dateformat' ? '%Y-%m-%d' : null}, value, value => saveTop(key, value));
    if (key === 'start' || key === 'end') {
      const input = wrap.querySelector('input');
      input.placeholder = formatDate(new Date(), doc.dateformat || doc.date_format || '%Y-%m-%d');
      attachDatePicker(input, {format:doc.dateformat || doc.date_format || '%Y-%m-%d', onPick:text => saveTop(key, text)});
    }
    container.append(field(label, wrap));
  }
  let section = '';
  let tableHeading;
  for (const option of STYLE_OPTIONS) {
    if (option.section !== section) {
      section = option.section;
      const heading = element('h3', '', section);
      if (section === 'Table') tableHeading = heading;
      container.append(heading);
    }
    const save = value => {
      if (value === undefined) {
        if (doc.style && typeof doc.style === 'object') delete doc.style[option.key];
      } else {
        if (!doc.style || typeof doc.style !== 'object' || Array.isArray(doc.style)) doc.style = {};
        doc.style[option.key] = value;
      }
      onCommit();
    };
    container.append(field(option.label, settingInput(option, style[option.key], save), option.help));
  }
  if (initialFocus === 'table') tableHeading?.scrollIntoView?.({block:'start'});
  else container.scrollTop = scrollTop;
}
