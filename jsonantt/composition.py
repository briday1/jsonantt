"""Materialize CLI-style task-file composition into portable, editable JSON."""
from copy import deepcopy
import posixpath

from .parser import _nested_task_items, _parse_date, parse_chart


def compose_document(document, files, append=None, wrap=False, source_name=None):
    """Append task trees from a virtual filename→JSON map, in the given order.

    Only task trees are imported. Filename-only includes inline their tasks;
    named includes prepend imported tasks to their children, matching the CLI.
    Dates are converted from each file's format into the destination format.
    Imported filenames become editable snapshots; no disk files are read/written.
    """
    if not isinstance(document, dict) or not isinstance(files, dict):
        raise ValueError('document and files must be JSON objects')
    if not isinstance(wrap, bool):
        raise ValueError('wrap must be a boolean')
    if append is None:
        append = list(files)
    if not isinstance(append, list) or not all(isinstance(name, str) for name in append):
        raise ValueError('append must be a list of filenames in append order')
    normalized = {}
    for name, value in files.items():
        key = posixpath.normpath(name.replace('\\', '/'))
        if key in normalized:
            raise ValueError(f'Duplicate filename: {name}')
        if not isinstance(value, dict):
            raise ValueError(f'{name}: expected a chart JSON object')
        normalized[key] = value
    output = deepcopy(document)
    target_format = output.get('dateformat', output.get('date_format', '%Y-%m-%d'))

    def load(name, owner, seen):
        key = posixpath.normpath(posixpath.join(posixpath.dirname(owner or ''), name.replace('\\', '/')))
        if key in seen:
            raise ValueError(f'Circular filename reference: {key}')
        if key not in normalized:
            raise ValueError(f'Missing included file: {key}. Select that JSON file too (or load its folder).')
        data = normalized[key]
        return tasks(_nested_task_items(data), data.get('dateformat', data.get('date_format', '%Y-%m-%d')), key, seen | {key})

    def tasks(items, date_format, owner, seen):
        result = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Task entries must be JSON objects')
            included = load(item['filename'], owner, seen) if 'filename' in item else []
            if set(item) == {'filename'}:
                result.extend(included)
                continue
            task = deepcopy(item)
            for key in ('start', 'end', 'date'):
                if key in task:
                    values = task[key] if isinstance(task[key], list) else [task[key]]
                    converted = [_parse_date(value, date_format).strftime(target_format) for value in values]
                    task[key] = converted if isinstance(task[key], list) else converted[0]
            children = included + tasks(_nested_task_items(item), date_format, owner, seen)
            task.pop('filename', None)
            task.pop('children', None)
            task.pop('tasks', None)
            if children or 'tasks' in item or 'children' in item or 'filename' in item:
                task['tasks'] = children
            result.append(task)
        return result

    source_name = posixpath.normpath(source_name) if source_name else None
    combined = tasks(_nested_task_items(output), target_format, source_name, {source_name} if source_name else set())
    for name in append:
        imported = load(name, None, set())
        if wrap:
            combined.append({'name': posixpath.splitext(posixpath.basename(name))[0], 'tasks': imported})
        else:
            combined.extend(imported)
    output.pop('children', None)
    output['tasks'] = combined
    # Duplicate IDs would otherwise silently retarget arrows/dependencies.
    identifiers = set()
    def check_ids(items):
        for item in items:
            identifier = item.get('id')
            if identifier:
                if identifier in identifiers:
                    raise ValueError(f'Duplicate task ID: {identifier}. Rename it before appending.')
                identifiers.add(identifier)
            check_ids(item.get('tasks', []))
    check_ids(combined)
    parse_chart(output)
    return output
