"""Tests for load-audit-findings.py -- merge + deduplicate audit findings."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "load-audit-findings.py")

# Import hyphen-named module via importlib
_spec = importlib.util.spec_from_file_location("load_audit_findings", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.path.insert(0, SCRIPTS_DIR)
_spec.loader.exec_module(_mod)
deduplicate = _mod.deduplicate
load_and_merge = _mod.load_and_merge


def _run_script(audit_dir, output_path):
    return subprocess.run(
        [sys.executable, SCRIPT, "--audit-dir", audit_dir, "--output", output_path],
        capture_output=True, text=True,
    )


class TestDeduplicate:
    """Deduplication by (document, section, check, description)."""

    def test_removes_exact_duplicates(self):
        findings = [
            {"document": "OPS", "section": "monitoring", "check": "xml-ref-integrity", "description": "bad ref"},
            {"document": "OPS", "section": "monitoring", "check": "xml-ref-integrity", "description": "bad ref"},
        ]
        result = deduplicate(findings)
        assert len(result) == 1

    def test_keeps_different_sections(self):
        findings = [
            {"document": "OPS", "section": "monitoring", "check": "xml-ref-integrity", "description": "bad ref"},
            {"document": "OPS", "section": "deployment", "check": "xml-ref-integrity", "description": "bad ref"},
        ]
        result = deduplicate(findings)
        assert len(result) == 2

    def test_keeps_different_checks(self):
        findings = [
            {"document": "OPS", "section": "monitoring", "check": "xml-ref-integrity", "description": "bad ref"},
            {"document": "OPS", "section": "monitoring", "check": "data-model-fact-check", "description": "bad ref"},
        ]
        result = deduplicate(findings)
        assert len(result) == 2

    def test_preserves_order(self):
        findings = [
            {"document": "A", "section": "s1", "check": "c1", "description": "first"},
            {"document": "B", "section": "s2", "check": "c2", "description": "second"},
            {"document": "A", "section": "s1", "check": "c1", "description": "first"},
        ]
        result = deduplicate(findings)
        assert len(result) == 2
        assert result[0]["description"] == "first"
        assert result[1]["description"] == "second"

    def test_empty_input(self):
        assert deduplicate([]) == []


class TestLoadAndMerge:
    """Load from audit directory and merge deterministic + prose findings."""

    def test_merge_deterministic_and_prose(self):
        with tempfile.TemporaryDirectory() as td:
            # Deterministic findings
            with open(os.path.join(td, "findings-refs.json"), "w") as f:
                json.dump([
                    {"document": "OPS", "section": "monitoring", "check": "xml-ref-integrity",
                     "description": "Table `etl_runs` not found"},
                ], f)

            # Prose findings
            with open(os.path.join(td, "findings-prose-devops-OPS.json"), "w") as f:
                json.dump([
                    {"document": "OPS", "section": "monitoring", "check": "dangling-prose-reference",
                     "description": "Prose mentions `wrong_table`"},
                ], f)

            result = load_and_merge(td)
            assert len(result) == 2

    def test_deduplicates_across_sources(self):
        with tempfile.TemporaryDirectory() as td:
            finding = {"document": "OPS", "section": "monitoring",
                       "check": "xml-ref-integrity", "description": "same issue"}

            with open(os.path.join(td, "findings-refs.json"), "w") as f:
                json.dump([finding], f)

            with open(os.path.join(td, "findings-prose-devops-OPS.json"), "w") as f:
                json.dump([finding], f)

            result = load_and_merge(td)
            assert len(result) == 1

    def test_missing_deterministic_file(self):
        with tempfile.TemporaryDirectory() as td:
            # Only prose findings, no deterministic file
            with open(os.path.join(td, "findings-prose-devops-OPS.json"), "w") as f:
                json.dump([
                    {"document": "OPS", "section": "monitoring", "check": "c1", "description": "d1"},
                ], f)

            result = load_and_merge(td)
            assert len(result) == 1

    def test_missing_prose_files(self):
        with tempfile.TemporaryDirectory() as td:
            # Only deterministic, no prose files
            with open(os.path.join(td, "findings-refs.json"), "w") as f:
                json.dump([
                    {"document": "OPS", "section": "monitoring", "check": "c1", "description": "d1"},
                ], f)

            result = load_and_merge(td)
            assert len(result) == 1

    def test_empty_audit_dir(self):
        with tempfile.TemporaryDirectory() as td:
            result = load_and_merge(td)
            assert result == []

    def test_multiple_prose_files(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "findings-refs.json"), "w") as f:
                json.dump([], f)

            with open(os.path.join(td, "findings-prose-devops-OPS.json"), "w") as f:
                json.dump([
                    {"document": "OPS", "section": "s1", "check": "c1", "description": "d1"},
                ], f)

            with open(os.path.join(td, "findings-prose-devops-TROUBLESHOOTING.json"), "w") as f:
                json.dump([
                    {"document": "TROUBLESHOOTING", "section": "s2", "check": "c2", "description": "d2"},
                ], f)

            result = load_and_merge(td)
            assert len(result) == 2


class TestCLI:
    """CLI invocation tests."""

    def test_basic_run(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "findings-refs.json"), "w") as f:
                json.dump([
                    {"document": "OPS", "section": "s1", "check": "c1", "description": "d1"},
                ], f)

            output_path = os.path.join(td, "merged.json")
            result = _run_script(td, output_path)
            assert result.returncode == 0

            merged = json.loads(open(output_path).read())
            assert len(merged) == 1

    def test_missing_audit_dir(self):
        with tempfile.TemporaryDirectory() as td:
            output_path = os.path.join(td, "merged.json")
            result = _run_script(os.path.join(td, "nonexistent"), output_path)
            assert result.returncode == 0

            merged = json.loads(open(output_path).read())
            assert merged == []
