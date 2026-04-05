"""Tests for lib/heading_map.py -- slugify_heading and read_heading_map."""

import json
import os
import tempfile

import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lib.heading_map import read_heading_map, slugify_heading


class TestSlugifyHeading:
    """Canonical slugify_heading tests."""

    def test_simple(self):
        assert slugify_heading("Infrastructure Overview") == "infrastructure-overview"

    def test_strips_non_alnum(self):
        assert slugify_heading("What's New?") == "whats-new"

    def test_collapses_whitespace(self):
        assert slugify_heading("  Multiple   Spaces  ") == "multiple-spaces"

    def test_strips_leading_trailing_hyphens(self):
        assert slugify_heading("-test-") == "test"

    def test_preserves_existing_hyphens(self):
        assert slugify_heading("pre-existing") == "pre-existing"

    def test_slash_becomes_hyphen(self):
        assert slugify_heading("Async/Concurrency Patterns") == "async-concurrency-patterns"

    def test_collapses_consecutive_hyphens(self):
        assert slugify_heading("Do / Don't Rules") == "do-dont-rules"

    def test_empty_string(self):
        assert slugify_heading("") == ""


class TestReadHeadingMap:
    """Tests for read_heading_map."""

    def test_missing_file_returns_empty(self):
        result = read_heading_map("/nonexistent/path/state.json")
        assert result == {}

    def test_valid_state_file(self):
        state = {
            "queue": [
                {"type": "orient", "section": "overview"},
                {
                    "type": "write",
                    "heading_path": "overview",
                    "level": 2,
                    "title": "Overview",
                    "heading_line": "## Overview",
                    "purpose": "...",
                    "example": "...",
                },
                {
                    "type": "write",
                    "heading_path": "overview/details",
                    "level": 3,
                    "title": "Details",
                    "heading_line": "### Details",
                    "purpose": "...",
                    "example": "...",
                },
                {"done": True, "headings_processed": 2},
            ],
            "index": 0,
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(state, f)
            path = f.name
        try:
            result = read_heading_map(path)
            assert "overview" in result
            assert result["overview"] == {"title": "Overview", "level": 2}
            assert "overview/details" in result
            assert result["overview/details"] == {"title": "Details", "level": 3}
        finally:
            os.unlink(path)

    def test_filters_non_write_entries(self):
        state = {
            "queue": [
                {"type": "orient", "section": "setup"},
                {
                    "type": "write",
                    "heading_path": "setup",
                    "level": 2,
                    "title": "Setup",
                },
                {"done": True, "headings_processed": 1},
            ],
            "index": 0,
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(state, f)
            path = f.name
        try:
            result = read_heading_map(path)
            assert len(result) == 1
            assert "setup" in result
        finally:
            os.unlink(path)

    def test_empty_queue(self):
        state = {"queue": [], "index": 0}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(state, f)
            path = f.name
        try:
            result = read_heading_map(path)
            assert result == {}
        finally:
            os.unlink(path)
