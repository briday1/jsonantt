"""Canonical JSON formatting for jsonantt documents.

This module is the single formatting implementation shared by the command line
(``jsonantt fmt``) and the studio (via the ``/api/format`` endpoint in
:mod:`jsonantt.server`), so studio output is byte-for-byte identical to CLI
output.
"""
from __future__ import annotations

import json
from typing import Any

INDENT = 2


def format_json_text(text: str) -> str:
    """Parse *text* as JSON and return it in canonical jsonantt style.

    Raises :class:`ValueError` when the text is not valid JSON.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    return format_json_data(data)


def format_json_data(data: Any) -> str:
    """Serialise *data* in canonical jsonantt style (2-space indent, trailing newline)."""
    return json.dumps(data, indent=INDENT, ensure_ascii=False) + "\n"
