"""Compatibility entry point for the shared data-only API under Pyodide."""
import json

from .api import render_document
from .composition import compose_document


def render_json(source, options_json):
    options = json.loads(options_json)
    if options.get('action') == 'compose':
        payload = json.loads(source)
        return json.dumps(compose_document(**payload), ensure_ascii=False, indent=2).encode('utf-8')
    document = json.loads(source)
    # Uploaded documents have no OS directory. Never fall through to Pyodide's
    # internal working directory when a dependency has not been selected.
    def check_includes(value):
        if not isinstance(value, dict):
            return
        if 'filename' in value:
            raise ValueError(f"Missing included file: {value['filename']}. Open the composed JSON and select its supporting files or folder.")
        for key in ('tasks', 'children'):
            for item in value.get(key, []):
                check_includes(item)
    for chart in ([document.get('planned'), document.get('actual')] if options.get('mode', '').startswith('compare-') else [document]):
        check_includes(chart)
    return render_document(document, options)
