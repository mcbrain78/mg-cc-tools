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


class TestContextualFlag:
    """Contextual non-ref classification."""

    def test_contextual_flag_sets_field(self):
        """--contextual adds contextual: true to the not-entities entry."""
        with tempfile.TemporaryDirectory() as td:
            nf = _write_json(td, "not-entities.json", [])
            pf = _write_json(td, "protected-entities.json", [])

            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--entity", "status",
                 "--target", "not-entities",
                 "--reason", "Contextual: used as plain English",
                 "--contextual",
                 "--not-entities-file", nf,
                 "--protected-entities-file", pf],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            not_entities = _read_json(nf)
            assert len(not_entities) == 1
            assert not_entities[0]["name"] == "status"
            assert not_entities[0]["contextual"] is True
            assert not_entities[0]["reason"] == "Contextual: used as plain English"

    def test_no_contextual_flag_no_field(self):
        """Without --contextual, entry has no contextual field."""
        with tempfile.TemporaryDirectory() as td:
            nf = _write_json(td, "not-entities.json", [])
            pf = _write_json(td, "protected-entities.json", [])

            result = _run("bash", "not-entities", "Generic shell", nf, pf)
            assert result.returncode == 0

            not_entities = _read_json(nf)
            assert "contextual" not in not_entities[0]

    def test_contextual_on_protected_ignored(self):
        """--contextual with protected-entities target → no contextual field."""
        with tempfile.TemporaryDirectory() as td:
            nf = _write_json(td, "not-entities.json", [])
            pf = _write_json(td, "protected-entities.json", [])

            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--entity", "compute_hash",
                 "--target", "protected-entities",
                 "--reason", "Project function",
                 "--contextual",
                 "--not-entities-file", nf,
                 "--protected-entities-file", pf],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            protected = _read_json(pf)
            assert len(protected) == 1
            assert "contextual" not in protected[0]


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


class TestProtectedFindingEmission:
    """Auto-emit a dangling-prose-reference finding when newly protected."""

    def test_protected_no_finding_args_no_findings(self):
        """Without finding args, protected classification leaves findings alone."""
        with tempfile.TemporaryDirectory() as td:
            nf = _write_json(td, "not-entities.json", [])
            pf = _write_json(td, "protected-entities.json", [])
            ff = os.path.join(td, "findings.json")

            result = _run(
                "compute_hash", "protected-entities",
                "Project function", nf, pf,
            )
            assert result.returncode == 0
            # findings file should not be created since no --findings-file passed
            assert not os.path.exists(ff)

    def test_protected_with_findings_writes_one_per_section(self):
        """Full finding args → one dangling-prose-reference per section."""
        with tempfile.TemporaryDirectory() as td:
            nf = _write_json(td, "not-entities.json", [])
            pf = _write_json(td, "protected-entities.json", [])
            ff = _write_json(td, "findings.json", [])

            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--entity", "compute_hash",
                 "--target", "protected-entities",
                 "--reason", "Project function name",
                 "--not-entities-file", nf,
                 "--protected-entities-file", pf,
                 "--findings-file", ff,
                 "--sections", "system-concepts", "technical-terms",
                 "--audience", "end-users",
                 "--document", "GLOSSARY"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            findings = _read_json(ff)
            assert len(findings) == 2
            for finding in findings:
                assert finding["check"] == "dangling-prose-reference"
                assert finding["audience"] == "end-users"
                assert finding["document"] == "GLOSSARY"
                assert finding["wave"] == 0
                assert "compute_hash" in finding["description"]
                assert "Project function name" in finding["description"]
            # One finding per section
            sections_in_findings = sorted(f["section"] for f in findings)
            assert sections_in_findings == ["system-concepts", "technical-terms"]

    def test_not_entities_ignores_finding_args(self):
        """--target not-entities + finding args → no findings file."""
        with tempfile.TemporaryDirectory() as td:
            nf = _write_json(td, "not-entities.json", [])
            pf = _write_json(td, "protected-entities.json", [])
            ff = _write_json(td, "findings.json", [])

            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--entity", "bash",
                 "--target", "not-entities",
                 "--reason", "Generic shell",
                 "--not-entities-file", nf,
                 "--protected-entities-file", pf,
                 "--findings-file", ff,
                 "--sections", "section-a",
                 "--audience", "end-users",
                 "--document", "GLOSSARY"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            findings = _read_json(ff)
            assert findings == []  # untouched

    def test_finding_suppressed_when_in_suppress_file(self):
        """Suppressed entity for one section is skipped; others still file."""
        with tempfile.TemporaryDirectory() as td:
            nf = _write_json(td, "not-entities.json", [])
            pf = _write_json(td, "protected-entities.json", [])
            ff = _write_json(td, "findings.json", [])
            sf = _write_json(td, "suppressed.json", [
                {
                    "section": "system-concepts",
                    "check": "dangling-prose-reference",
                    "entity": "compute_hash",
                },
            ])

            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--entity", "compute_hash",
                 "--target", "protected-entities",
                 "--reason", "Project function",
                 "--not-entities-file", nf,
                 "--protected-entities-file", pf,
                 "--findings-file", ff,
                 "--sections", "system-concepts", "technical-terms",
                 "--audience", "end-users",
                 "--document", "GLOSSARY",
                 "--suppress-file", sf],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            findings = _read_json(ff)
            # system-concepts is suppressed; technical-terms still fires
            assert len(findings) == 1
            assert findings[0]["section"] == "technical-terms"

    def test_duplicate_classify_does_not_duplicate_findings(self):
        """Second classify call dedups classification AND skips finding emission."""
        with tempfile.TemporaryDirectory() as td:
            nf = _write_json(td, "not-entities.json", [])
            pf = _write_json(td, "protected-entities.json", [])
            ff = _write_json(td, "findings.json", [])

            # First classify → 1 finding
            subprocess.run(
                [sys.executable, SCRIPT,
                 "--entity", "compute_hash",
                 "--target", "protected-entities",
                 "--reason", "Project function",
                 "--not-entities-file", nf,
                 "--protected-entities-file", pf,
                 "--findings-file", ff,
                 "--sections", "system-concepts",
                 "--audience", "end-users",
                 "--document", "GLOSSARY"],
                capture_output=True, text=True,
            )
            assert len(_read_json(ff)) == 1

            # Second classify with same entity → dedup, no additional finding
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--entity", "compute_hash",
                 "--target", "protected-entities",
                 "--reason", "Project function",
                 "--not-entities-file", nf,
                 "--protected-entities-file", pf,
                 "--findings-file", ff,
                 "--sections", "system-concepts",
                 "--audience", "end-users",
                 "--document", "GLOSSARY"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "Already classified" in result.stderr
            # Still 1 finding — second call hit the dedup path
            assert len(_read_json(ff)) == 1
