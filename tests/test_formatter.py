"""Tests for the canonical jsonantt formatter shared by the CLI and studio."""
from __future__ import annotations

import json

import pytest

from jsonantt.formatter import INDENT, format_json_data, format_json_text


class TestFormatJsonText:
    def test_reindents_with_two_spaces(self):
        assert format_json_text('{"a": 1}') == '{\n  "a": 1\n}\n'

    def test_trailing_newline_is_added(self):
        assert format_json_text('{"a": 1}').endswith("\n")

    def test_is_idempotent(self):
        once = format_json_text('{"a": [1, {"b": 2}]}')
        assert format_json_text(once) == once

    def test_preserves_key_order(self):
        assert format_json_text('{"b": 1, "a": 2}') == '{\n  "b": 1,\n  "a": 2\n}\n'

    def test_non_ascii_is_not_escaped(self):
        assert "café" in format_json_text('{"name": "caf\\u00e9"}')

    def test_ensure_ascii_passthrough(self):
        assert format_json_text('{"name": "café"}') == '{\n  "name": "café"\n}\n'

    def test_empty_object(self):
        assert format_json_text("{}") == "{}\n"

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            format_json_text("{not json")

    def test_scalar_input(self):
        assert format_json_text("1") == "1\n"


class TestFormatJsonData:
    def test_matches_text_entry_point(self):
        data = {"title": "T", "tasks": [{"name": "A"}]}
        assert format_json_data(data) == format_json_text(json.dumps(data))

    def test_indent_constant(self):
        assert INDENT == 2
        data = {"a": {"b": 1}}
        assert format_json_data(data) == json.dumps(data, indent=2, ensure_ascii=False) + "\n"
