"""Tests for dismiss-entity.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "dismiss-entity.py")


def _write_json(td, name, data):
    path = os.path.join(td, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _run(entity, section, uncleared_file, not_entities_file):
    return subprocess.run(
        [sys.executable, SCRIPT,
         "--entity", entity,
         "--section", section,
         "--uncleared-file", uncleared_file,
         "--not-entities-file", not_entities_file],
        capture_output=True, text=True,
    )


class TestDismiss:
    """Entity removal from uncleared and addition to not-entities."""

    def test_entity_removed_from_all_sections(self):
        """Entity in multiple sections → all removed from uncleared."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
                {"name": "bash", "section": "deployment"},
                {"name": "bash", "section": "orchestration"},
                {"name": "PORT", "section": "deployment"},
            ])
            nf = _write_json(td, "not-entities.json", [])

            result = _run("bash", "monitoring", uf, nf)
            assert result.returncode == 0

            uncleared = _read_json(uf)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "PORT"

    def test_entity_added_to_not_entities(self):
        """Dismissed entity appended to not-entities list."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            nf = _write_json(td, "not-entities.json", [])

            _run("bash", "monitoring", uf, nf)

            not_entities = _read_json(nf)
            assert len(not_entities) == 1
            assert not_entities[0]["name"] == "bash"
            assert not_entities[0]["dismissed_in"] == "monitoring"

    def test_dedup_not_entities(self):
        """Dismissing same entity twice does not duplicate in not-entities."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            nf = _write_json(td, "not-entities.json", [
                {"name": "bash", "dismissed_in": "deployment"},
            ])

            _run("bash", "monitoring", uf, nf)

            not_entities = _read_json(nf)
            assert len(not_entities) == 1
            assert not_entities[0]["dismissed_in"] == "deployment"  # original preserved

    def test_entity_not_in_uncleared(self):
        """Entity not in uncleared → no-op on uncleared, still added to not-entities."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "PORT", "section": "deployment"},
            ])
            nf = _write_json(td, "not-entities.json", [])

            result = _run("nonexistent", "monitoring", uf, nf)
            assert result.returncode == 0

            uncleared = _read_json(uf)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "PORT"

            not_entities = _read_json(nf)
            assert len(not_entities) == 1
            assert not_entities[0]["name"] == "nonexistent"

    def test_empty_uncleared(self):
        """Empty uncleared file → no-op on uncleared."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [])
            nf = _write_json(td, "not-entities.json", [])

            result = _run("bash", "monitoring", uf, nf)
            assert result.returncode == 0

            uncleared = _read_json(uf)
            assert uncleared == []

    def test_missing_not_entities_file(self):
        """Non-existent not-entities file → created with the entity."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            nf = os.path.join(td, "not-entities.json")
            # not-entities file does not exist

            result = _run("bash", "monitoring", uf, nf)
            assert result.returncode == 0

            not_entities = _read_json(nf)
            assert len(not_entities) == 1
            assert not_entities[0]["name"] == "bash"

    def test_missing_uncleared_file(self):
        """Non-existent uncleared file → defaults to empty, created."""
        with tempfile.TemporaryDirectory() as td:
            uf = os.path.join(td, "uncleared.json")
            nf = _write_json(td, "not-entities.json", [])

            result = _run("bash", "monitoring", uf, nf)
            assert result.returncode == 0

            uncleared = _read_json(uf)
            assert uncleared == []

    def test_summary_on_stderr(self):
        """Summary line printed to stderr."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
                {"name": "bash", "section": "deployment"},
                {"name": "PORT", "section": "deployment"},
            ])
            nf = _write_json(td, "not-entities.json", [])

            result = _run("bash", "monitoring", uf, nf)
            assert "Dismissed: bash" in result.stderr
            assert "3 → 1" in result.stderr

    def test_dedup_with_plain_string_entries(self):
        """Not-entities list with plain string entries (legacy format) deduped correctly."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            nf = _write_json(td, "not-entities.json", ["bash"])

            _run("bash", "monitoring", uf, nf)

            not_entities = _read_json(nf)
            assert len(not_entities) == 1
            assert not_entities[0] == "bash"  # original preserved, not duplicated
