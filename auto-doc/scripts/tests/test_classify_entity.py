"""Tests for classify-entity.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "classify-entity.py")


def _write_json(td, name, data):
    path = os.path.join(td, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _run(entity, target, reason, not_entities_file, protected_entities_file):
    return subprocess.run(
        [sys.executable, SCRIPT,
         "--entity", entity,
         "--target", target,
         "--reason", reason,
         "--not-entities-file", not_entities_file,
         "--protected-entities-file", protected_entities_file],
        capture_output=True, text=True,
    )


class TestClassifyToNotEntities:
    """Classification to the not-entities list."""

    def test_classify_to_not_entities(self):
        """Entity classified to not-entities with reason."""
        with tempfile.TemporaryDirectory() as td:
            nf = _write_json(td, "not-entities.json", [])
            pf = _write_json(td, "protected-entities.json", [])

            result = _run("bash", "not-entities", "Generic shell name", nf, pf)
            assert result.returncode == 0

            not_entities = _read_json(nf)
            assert len(not_entities) == 1
            assert not_entities[0]["name"] == "bash"
            assert not_entities[0]["reason"] == "Generic shell name"

            # Protected list unchanged
            protected = _read_json(pf)
            assert len(protected) == 0


class TestClassifyToProtectedEntities:
    """Classification to the protected-entities list."""

    def test_classify_to_protected_entities(self):
        """Entity classified to protected-entities with reason."""
        with tempfile.TemporaryDirectory() as td:
            nf = _write_json(td, "not-entities.json", [])
            pf = _write_json(td, "protected-entities.json", [])

            result = _run(
                "compute_hash", "protected-entities",
                "Project function name", nf, pf,
            )
            assert result.returncode == 0

            protected = _read_json(pf)
            assert len(protected) == 1
            assert protected[0]["name"] == "compute_hash"
            assert protected[0]["reason"] == "Project function name"

            # Not-entities list unchanged
            not_entities = _read_json(nf)
            assert len(not_entities) == 0


class TestDedup:
    """Deduplication behavior."""

    def test_dedup_classification(self):
        """Classifying same entity twice does not duplicate."""
        with tempfile.TemporaryDirectory() as td:
            nf = _write_json(td, "not-entities.json", [
                {"name": "bash", "reason": "Generic shell"},
            ])
            pf = _write_json(td, "protected-entities.json", [])

            result = _run("bash", "not-entities", "Shell name", nf, pf)
            assert result.returncode == 0
            assert "Already classified" in result.stderr

            not_entities = _read_json(nf)
            assert len(not_entities) == 1
            assert not_entities[0]["reason"] == "Generic shell"  # original preserved


class TestInvalidTarget:
    """Invalid target argument."""

    def test_invalid_target(self):
        """Invalid target name → argparse error."""
        with tempfile.TemporaryDirectory() as td:
            nf = _write_json(td, "not-entities.json", [])
            pf = _write_json(td, "protected-entities.json", [])

            result = _run("bash", "invalid-target", "reason", nf, pf)
            assert result.returncode != 0


class TestConflictWarning:
    """Conflict detection when entity is in the other list."""

    def test_conflict_warning(self):
        """Entity in other list → warning on stderr."""
        with tempfile.TemporaryDirectory() as td:
            nf = _write_json(td, "not-entities.json", [
                {"name": "bash", "reason": "Generic shell"},
            ])
            pf = _write_json(td, "protected-entities.json", [])

            # Try to classify bash as protected when it's already in not-entities
            result = _run(
                "bash", "protected-entities",
                "Actually a project script", nf, pf,
            )
            assert result.returncode == 0
            assert "WARNING: bash already exists in not-entities" in result.stderr

            # Entity still gets added to target
            protected = _read_json(pf)
            assert len(protected) == 1
            assert protected[0]["name"] == "bash"


class TestMissingFiles:
    """Missing file handling."""

    def test_missing_files_created(self):
        """Non-existent target files → created with the entity."""
        with tempfile.TemporaryDirectory() as td:
            nf = os.path.join(td, "not-entities.json")
            pf = os.path.join(td, "protected-entities.json")

            result = _run("bash", "not-entities", "Generic shell", nf, pf)
            assert result.returncode == 0

            not_entities = _read_json(nf)
            assert len(not_entities) == 1
            assert not_entities[0]["name"] == "bash"
