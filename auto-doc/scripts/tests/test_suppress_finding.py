"""Tests for suppress-finding.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "suppress-finding.py")


def _write_json(td, name, data):
    path = os.path.join(td, name)
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _run(suppress_file, section, check, entity):
    return subprocess.run(
        [sys.executable, SCRIPT,
         "--suppress-file", suppress_file,
         "--section", section,
         "--check", check,
         "--entity", entity],
        capture_output=True, text=True,
    )


class TestSuppressBasic:
    """Core suppress functionality."""

    def test_adds_entry_to_empty_file(self):
        """Suppress adds entry to empty suppress file."""
        with tempfile.TemporaryDirectory() as td:
            sf = _write_json(td, "suppressed.json", [])

            result = _run(sf, "monitoring/alerting", "dangling-prose-reference", "Failed")
            assert result.returncode == 0
            assert "Suppressed:" in result.stderr

            entries = _read_json(sf)
            assert len(entries) == 1
            assert entries[0]["section"] == "monitoring/alerting"
            assert entries[0]["check"] == "dangling-prose-reference"
            assert entries[0]["entity"] == "Failed"

    def test_appends_to_existing(self):
        """Suppress appends to existing entries."""
        with tempfile.TemporaryDirectory() as td:
            sf = _write_json(td, "suppressed.json", [
                {"section": "s1", "check": "c1", "entity": "e1"},
            ])

            result = _run(sf, "s2", "c2", "e2")
            assert result.returncode == 0

            entries = _read_json(sf)
            assert len(entries) == 2

    def test_creates_missing_file(self):
        """Suppress creates file if it doesn't exist."""
        with tempfile.TemporaryDirectory() as td:
            sf = os.path.join(td, "suppressed.json")

            result = _run(sf, "sec", "check", "ent")
            assert result.returncode == 0

            entries = _read_json(sf)
            assert len(entries) == 1


class TestSuppressDedup:
    """Deduplication behavior."""

    def test_dedup_exact_match(self):
        """Duplicate suppress entry is skipped."""
        with tempfile.TemporaryDirectory() as td:
            sf = _write_json(td, "suppressed.json", [
                {"section": "s1", "check": "dangling-prose-reference", "entity": "Failed"},
            ])

            result = _run(sf, "s1", "dangling-prose-reference", "Failed")
            assert result.returncode == 0
            assert "Already suppressed" in result.stderr

            entries = _read_json(sf)
            assert len(entries) == 1

    def test_different_section_not_dedup(self):
        """Same check+entity but different section is not a duplicate."""
        with tempfile.TemporaryDirectory() as td:
            sf = _write_json(td, "suppressed.json", [
                {"section": "s1", "check": "c1", "entity": "e1"},
            ])

            result = _run(sf, "s2", "c1", "e1")
            assert result.returncode == 0
            assert "Already suppressed" not in result.stderr

            entries = _read_json(sf)
            assert len(entries) == 2
