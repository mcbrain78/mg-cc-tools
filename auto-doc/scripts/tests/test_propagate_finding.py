"""Tests for propagate-finding.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "propagate-finding.py")


def _write_json(td, name, data):
    """Write JSON data to a temp file."""
    path = os.path.join(td, name)
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _read_json(path):
    """Read JSON from file."""
    with open(path) as f:
        return json.load(f)


def _run(entity, section, findings_file, uncleared_file,
         document="OPERATIONS", audience="devops",
         suggestion="Add ref: [dep] example", wave=None):
    """Run propagate-finding.py and return result."""
    cmd = [
        sys.executable, SCRIPT,
        "--entity", entity,
        "--section", section,
        "--findings-file", findings_file,
        "--uncleared-file", uncleared_file,
        "--document", document,
        "--audience", audience,
        "--suggestion", suggestion,
    ]
    if wave is not None:
        cmd.extend(["--wave", str(wave)])
    return subprocess.run(cmd, capture_output=True, text=True)


class TestPropagation:
    """Finding propagation to other sections."""

    def test_entity_in_three_sections(self):
        """Entity in 3 sections, flagged in 1 → propagated to 2."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "prefect", "section": "monitoring"},
                {"name": "prefect", "section": "orchestration"},
                {"name": "prefect", "section": "deployment"},
                {"name": "PORT", "section": "deployment"},
            ])
            ff = _write_json(td, "findings.json", [])

            result = _run("prefect", "monitoring", ff, uf)
            assert result.returncode == 0

            # Findings: 2 propagated findings
            findings = _read_json(ff)
            assert len(findings) == 2
            sections = {f["section"] for f in findings}
            assert sections == {"orchestration", "deployment"}
            for f in findings:
                assert f["check"] == "dangling-prose-reference"
                assert "propagated from monitoring" in f["description"]
                assert "`prefect`" in f["description"]

            # Uncleared: all prefect entries removed, PORT remains
            uncleared = _read_json(uf)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "PORT"

    def test_entity_in_one_section_only(self):
        """Entity only in 1 section → no propagation, removed from uncleared."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "prefect", "section": "monitoring"},
                {"name": "PORT", "section": "deployment"},
            ])
            ff = _write_json(td, "findings.json", [])

            result = _run("prefect", "monitoring", ff, uf)
            assert result.returncode == 0

            # No propagated findings
            findings = _read_json(ff)
            assert len(findings) == 0

            # prefect removed from uncleared
            uncleared = _read_json(uf)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "PORT"

    def test_entity_not_in_uncleared(self):
        """Entity not in uncleared → no-op."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "PORT", "section": "deployment"},
            ])
            ff = _write_json(td, "findings.json", [])

            result = _run("nonexistent", "monitoring", ff, uf)
            assert result.returncode == 0

            findings = _read_json(ff)
            assert len(findings) == 0

            uncleared = _read_json(uf)
            assert len(uncleared) == 1

    def test_multiple_entities_independent(self):
        """Propagating one entity doesn't affect another."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "prefect", "section": "monitoring"},
                {"name": "prefect", "section": "orchestration"},
                {"name": "celery", "section": "monitoring"},
                {"name": "celery", "section": "orchestration"},
            ])
            ff = _write_json(td, "findings.json", [])

            # Propagate prefect
            result = _run("prefect", "monitoring", ff, uf)
            assert result.returncode == 0

            # prefect propagated, celery untouched
            findings = _read_json(ff)
            assert len(findings) == 1
            assert findings[0]["section"] == "orchestration"
            assert "`prefect`" in findings[0]["description"]

            uncleared = _read_json(uf)
            assert len(uncleared) == 2
            assert all(e["name"] == "celery" for e in uncleared)

    def test_idempotent(self):
        """Calling twice with same entity does nothing second time."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "prefect", "section": "monitoring"},
                {"name": "prefect", "section": "orchestration"},
            ])
            ff = _write_json(td, "findings.json", [])

            # First call
            _run("prefect", "monitoring", ff, uf)
            findings_after_first = _read_json(ff)
            uncleared_after_first = _read_json(uf)

            # Second call — entity already removed from uncleared
            _run("prefect", "monitoring", ff, uf)
            findings_after_second = _read_json(ff)
            uncleared_after_second = _read_json(uf)

            assert len(findings_after_first) == 1
            assert len(findings_after_second) == 1  # no new findings
            assert uncleared_after_first == uncleared_after_second

    def test_finding_fields(self):
        """Propagated findings have correct document, audience, suggestion."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "etl_runs", "section": "monitoring"},
                {"name": "etl_runs", "section": "deployment"},
            ])
            ff = _write_json(td, "findings.json", [])

            _run("etl_runs", "monitoring", ff, uf,
                 document="OPERATIONS", audience="devops",
                 suggestion="Add ref: [db] road_runner.etl_runs")

            findings = _read_json(ff)
            assert len(findings) == 1
            f = findings[0]
            assert f["document"] == "OPERATIONS"
            assert f["audience"] == "devops"
            assert f["section"] == "deployment"
            assert f["suggestion"] == "Add ref: [db] road_runner.etl_runs"
            assert f["check"] == "dangling-prose-reference"

    def test_uncleared_shrinks_correctly(self):
        """Uncleared count matches: before - all entries for entity."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "prefect", "section": "monitoring"},
                {"name": "prefect", "section": "orchestration"},
                {"name": "prefect", "section": "deployment"},
                {"name": "PORT", "section": "deployment"},
                {"name": "HOST", "section": "deployment"},
            ])
            ff = _write_json(td, "findings.json", [])

            result = _run("prefect", "monitoring", ff, uf)
            assert result.returncode == 0
            assert "Uncleared: 5 → 2" in result.stderr

            uncleared = _read_json(uf)
            assert len(uncleared) == 2
            names = {e["name"] for e in uncleared}
            assert names == {"PORT", "HOST"}

    def test_summary_on_stderr(self):
        """Summary line printed to stderr."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "prefect", "section": "monitoring"},
                {"name": "prefect", "section": "orchestration"},
            ])
            ff = _write_json(td, "findings.json", [])

            result = _run("prefect", "monitoring", ff, uf)
            assert "Propagated: prefect" in result.stderr
            assert "1 sections" in result.stderr

    def test_missing_uncleared_file(self):
        """Non-existent uncleared file → no-op (default empty)."""
        with tempfile.TemporaryDirectory() as td:
            uf = os.path.join(td, "does-not-exist.json")
            ff = _write_json(td, "findings.json", [])

            result = _run("prefect", "monitoring", ff, uf)
            assert result.returncode == 0

            # Uncleared file is created with empty list
            uncleared = _read_json(uf)
            assert uncleared == []

    def test_existing_findings_preserved(self):
        """Pre-existing findings in the file are not lost."""
        with tempfile.TemporaryDirectory() as td:
            existing = [{
                "document": "OPERATIONS",
                "section": "monitoring",
                "audience": "devops",
                "check": "reference-integrity",
                "description": "Some prior finding",
                "suggestion": "Fix it",
                "group_id": "OPERATIONS/monitoring",
            }]
            uf = _write_json(td, "uncleared.json", [
                {"name": "prefect", "section": "monitoring"},
                {"name": "prefect", "section": "deployment"},
            ])
            ff = _write_json(td, "findings.json", existing)

            _run("prefect", "monitoring", ff, uf)

            findings = _read_json(ff)
            assert len(findings) == 2  # 1 existing + 1 propagated
            assert findings[0]["check"] == "reference-integrity"
            assert findings[1]["check"] == "dangling-prose-reference"


class TestPropagationWave:
    """Wave metadata forwarded to propagated findings."""

    def test_wave_forwarded_to_propagated_findings(self):
        """--wave N tags all propagated findings with wave=N."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "prefect", "section": "monitoring"},
                {"name": "prefect", "section": "orchestration"},
                {"name": "prefect", "section": "deployment"},
            ])
            ff = _write_json(td, "findings.json", [])

            result = _run("prefect", "monitoring", ff, uf, wave=2)
            assert result.returncode == 0

            findings = _read_json(ff)
            assert len(findings) == 2
            for f in findings:
                assert f["wave"] == 2

    def test_no_wave_means_no_wave_field(self):
        """Without --wave, propagated findings have no wave field."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "prefect", "section": "monitoring"},
                {"name": "prefect", "section": "deployment"},
            ])
            ff = _write_json(td, "findings.json", [])

            _run("prefect", "monitoring", ff, uf)

            findings = _read_json(ff)
            assert len(findings) == 1
            assert "wave" not in findings[0]
