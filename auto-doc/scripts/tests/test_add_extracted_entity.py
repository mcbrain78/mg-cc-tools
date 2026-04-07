"""Tests for add-extracted-entity.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "add-extracted-entity.py")


def _run(entities_file, name, section):
    """Run add-extracted-entity.py and return the subprocess result."""
    return subprocess.run(
        [sys.executable, SCRIPT,
         "--entities-file", entities_file,
         "--name", name,
         "--section", section],
        capture_output=True, text=True,
    )


class TestAddExtractedEntity:
    """add-extracted-entity.py appends entities with dedup."""

    def test_creates_new_file(self):
        """Creates entities file with one entity."""
        with tempfile.TemporaryDirectory() as td:
            ef = os.path.join(td, "entities.json")
            result = _run(ef, "etl_runs", "monitoring")
            assert result.returncode == 0
            assert "Added" in result.stderr

            with open(ef) as f:
                entities = json.load(f)
            assert len(entities) == 1
            assert entities[0] == {"name": "etl_runs", "section": "monitoring"}

    def test_appends_to_existing(self):
        """Appends to an existing entities list."""
        with tempfile.TemporaryDirectory() as td:
            ef = os.path.join(td, "entities.json")
            _run(ef, "etl_runs", "monitoring")
            _run(ef, "flow_name", "monitoring")

            with open(ef) as f:
                entities = json.load(f)
            assert len(entities) == 2
            assert entities[1]["name"] == "flow_name"

    def test_dedup_by_name_section(self):
        """Same (name, section) pair is not added twice."""
        with tempfile.TemporaryDirectory() as td:
            ef = os.path.join(td, "entities.json")
            _run(ef, "etl_runs", "monitoring")
            result = _run(ef, "etl_runs", "monitoring")
            assert "Skipped" in result.stderr

            with open(ef) as f:
                entities = json.load(f)
            assert len(entities) == 1

    def test_same_name_different_section(self):
        """Same name in different sections both kept."""
        with tempfile.TemporaryDirectory() as td:
            ef = os.path.join(td, "entities.json")
            _run(ef, "status", "monitoring")
            _run(ef, "status", "deployment")

            with open(ef) as f:
                entities = json.load(f)
            assert len(entities) == 2

    def test_missing_name_exits_nonzero(self):
        """Missing --name exits with error."""
        with tempfile.TemporaryDirectory() as td:
            ef = os.path.join(td, "entities.json")
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--entities-file", ef,
                 "--section", "monitoring"],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

    def test_missing_section_exits_nonzero(self):
        """Missing --section exits with error."""
        with tempfile.TemporaryDirectory() as td:
            ef = os.path.join(td, "entities.json")
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--entities-file", ef,
                 "--name", "etl_runs"],
                capture_output=True, text=True,
            )
            assert result.returncode != 0
