/** Per-date milestone editing; the source remains a date string or date array. */
import {attachDatePicker} from './datepicker.mjs';
import {parseDate,formatDate} from './model.mjs';

export function milestoneDateList({getValue,format,onChange}) {
  const container=document.createElement('div');container.className='milestone-dates';
  const list=document.createElement('ol');list.className='milestone-date-list';
  list.setAttribute('aria-label','Milestone dates');
  const initial=getValue();
  const entries=(Array.isArray(initial) ? initial : initial == null ? [] : [initial]).map(value=>({value}));
  const add=document.createElement('button');add.type='button';add.textContent='Add date';add.dataset.action='add-milestone-date';
  const save=()=>{
    const dates=entries.filter(entry=>entry.value != null).map(entry=>entry.value);
    // Keep an existing array an array, even after removing all but one date.
    onChange(Array.isArray(getValue()) || dates.length>1 ? dates : dates[0]);
  };
  const render=()=>{
    list.replaceChildren(...entries.map((entry,index)=>{
      const row=document.createElement('li');
      const order=document.createElement('span');order.textContent=String(index+1);order.setAttribute('aria-hidden','true');
      const input=document.createElement('input');input.type='text';input.value=entry.value ?? '';
      input.setAttribute('aria-label',`Milestone date ${index+1}`);
      input.placeholder=formatDate(new Date(),format);
      const commit=text=>{
        try {
          if(!text.trim())throw new Error('Choose a date, or use Remove to delete this entry.');
          parseDate(text.trim(),format);
          input.setCustomValidity('');entry.value=text.trim();save();
        } catch(error){input.setCustomValidity(error.message);input.reportValidity();}
      };
      input.addEventListener('input',()=>input.setCustomValidity(''));
      input.addEventListener('change',()=>commit(input.value));
      const calendar=attachDatePicker(input,{format,onPick:text=>{if(input.isConnected)commit(text);}});
      const remove=document.createElement('button');remove.type='button';remove.textContent='×';
      remove.className='danger';remove.setAttribute('aria-label',`Remove milestone date ${index+1}`);
      remove.title=`Remove date ${index+1}`;
      remove.addEventListener('click',()=>{
        entries.splice(index,1);
        if(entry.value != null)save();
        render();
        (list.querySelectorAll('input')[Math.min(index,entries.length-1)] || add).focus();
      });
      row.append(order,calendar,remove);return row;
    }));
  };
  add.addEventListener('click',()=>{
    entries.push({value:null});render();list.querySelector('li:last-child input').focus();
  });
  container.append(list,add);render();return container;
}
