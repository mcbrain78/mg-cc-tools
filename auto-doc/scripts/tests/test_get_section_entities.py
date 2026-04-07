"""Tests for get-section-entities.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "get-section-entities.py")


def _write_uncleared(td, entries):
    """Write uncleared entries to a temp file."""
    path = os.path.join(td, "uncleared.json")
    with open(path, "w") as f:
        json.dump(entries, f)
    return path


def _run(uncleared_file, section):
    """Run get-section-entities.py and return parsed stdout."""
    result = subprocess.run(
        [sys.executable, SCRIPT,
         "--uncleared-file", uncleared_file,
         "--section", section],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


class TestGetSectionEntities:
    """get-section-entities returns filtered entity names."""

    def test_section_with_entities(self):
        """Section present in uncleared → returns its entity names."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_uncleared(td, [
                {"name": "etl_runs", "section": "monitoring"},
                {"name": "flow_name", "section": "monitoring"},
                {"name": "PORT", "section": "deployment"},
            ])
            result = _run(uf, "monitoring")
            assert result["count"] == 2
            assert set(result["entities"]) == {"etl_runs", "flow_name"}

    def test_section_with_no_entities(self):
        """Section not in uncleared → returns count 0."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_uncleared(td, [
                {"name": "etl_runs", "section": "monitoring"},
            ])
            result = _run(uf, "deployment")
            assert result["count"] == 0
            assert result["entities"] == []

    def test_empty_uncleared_file(self):
        """Empty uncleared file → returns count 0."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_uncleared(td, [])
            result = _run(uf, "monitoring")
            assert result["count"] == 0
            assert result["entities"] == []

    def test_missing_uncleared_file(self):
        """Non-existent uncleared file → returns count 0 (default empty)."""
        with tempfile.TemporaryDirectory() as td:
            uf = os.path.join(td, "does-not-exist.json")
            result = _run(uf, "monitoring")
            assert result["count"] == 0
            assert result["entities"] == []

    def test_only_requested_section_returned(self):
        """Multiple sections → only the requested one is returned."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_uncleared(td, [
                {"name": "etl_runs", "section": "monitoring"},
                {"name": "PORT", "section": "deployment"},
                {"name": "HOST", "section": "deployment"},
                {"name": "prefect", "section": "orchestration"},
            ])
            result = _run(uf, "deployment")
            assert result["count"] == 2
            assert set(result["entities"]) == {"PORT", "HOST"}

    def test_nested_section_path(self):
        """Nested section paths (with /) work correctly."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_uncleared(td, [
                {"name": "etl_runs", "section": "etl/monitoring"},
                {"name": "flow_name", "section": "etl/monitoring"},
                {"name": "PORT", "section": "etl/deployment"},
            ])
            result = _run(uf, "etl/monitoring")
            assert result["count"] == 2
            assert set(result["entities"]) == {"etl_runs", "flow_name"}
