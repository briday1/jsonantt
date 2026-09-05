"""Compatibility entry point for the shared data-only API under Pyodide."""
import json

from .api import render_document
from .composition import compose_document


def render_json(source, options_json):
    options = json.loads(options_json)
    if options.get('action') == 'compose':
        payload = json.loads(source)
        return json.dumps(compose_document(**payload), ensure_ascii=False, indent=2).encode('utf-8')
    return render_document(json.loads(source), options)
