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
_apply_suppressions = _mod._apply_suppressions
_load_suppressions = _mod._load_suppressions


def _run_script(audit_dir, output_path, suppress_file=None):
    cmd = [sys.executable, SCRIPT, "--audit-dir", audit_dir, "--output", output_path]
    if suppress_file is not None:
        cmd.extend(["--suppress-file", suppress_file])
    return subprocess.run(cmd, capture_output=True, text=True)


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


class TestSectionctlExclusion:
    """Verify .sectionctl state files are not matched by prose glob."""

    def test_sectionctl_file_excluded_from_merge(self):
        """A .sectionctl state file next to a findings file is not loaded."""
        with tempfile.TemporaryDirectory() as td:
            # Real findings file
            with open(os.path.join(td, "findings-prose-devops-OPS.json"), "w") as f:
                json.dump([
                    {"document": "OPS", "section": "monitoring", "check": "c1", "description": "real"},
                ], f)

            # Sectionctl state file (should NOT be matched)
            with open(os.path.join(td, "findings-prose-devops-OPS.json.sectionctl"), "w") as f:
                json.dump({"current_index": 3, "total": 5}, f)

            result = load_and_merge(td)
            assert len(result) == 1
            assert result[0]["description"] == "real"


class TestSlashSeparatedPaths:
    """Verify deduplication works correctly with slash-separated section paths."""

    def test_dedup_with_slash_paths(self):
        """Findings with slash-separated section paths are deduplicated correctly."""
        findings = [
            {"document": "OPS", "section": "monitoring-alerting/etl-run-logging",
             "check": "xml-ref-integrity", "description": "Table not found"},
            {"document": "OPS", "section": "monitoring-alerting/etl-run-logging",
             "check": "xml-ref-integrity", "description": "Table not found"},
        ]
        result = deduplicate(findings)
        assert len(result) == 1
        assert result[0]["section"] == "monitoring-alerting/etl-run-logging"

    def test_bare_slug_and_path_are_distinct(self):
        """Old-format (bare slug) and new-format (path) findings are treated as distinct."""
        findings = [
            {"document": "OPS", "section": "etl-run-logging",
             "check": "xml-ref-integrity", "description": "Table not found"},
            {"document": "OPS", "section": "monitoring-alerting/etl-run-logging",
             "check": "xml-ref-integrity", "description": "Table not found"},
        ]
        result = deduplicate(findings)
        assert len(result) == 2

    def test_different_paths_same_leaf_slug(self):
        """Same leaf slug under different parents are treated as distinct."""
        findings = [
            {"document": "OPS", "section": "monitoring-alerting/overview",
             "check": "xml-ref-integrity", "description": "bad ref"},
            {"document": "OPS", "section": "deployment/overview",
             "check": "xml-ref-integrity", "description": "bad ref"},
        ]
        result = deduplicate(findings)
        assert len(result) == 2

    def test_merge_with_mixed_path_formats(self):
        """load_and_merge handles mixed bare-slug and path findings from different files."""
        with tempfile.TemporaryDirectory() as td:
            # Deterministic findings with slash paths
            with open(os.path.join(td, "findings-refs.json"), "w") as f:
                json.dump([
                    {"document": "OPS", "section": "monitoring-alerting/etl-run-logging",
                     "check": "xml-ref-integrity", "description": "Table not found"},
                ], f)

            # Prose findings with slash paths
            with open(os.path.join(td, "findings-prose-devops-OPS.json"), "w") as f:
                json.dump([
                    {"document": "OPS", "section": "monitoring-alerting/etl-run-logging",
                     "check": "dangling-prose-reference", "description": "Different check"},
                    {"document": "OPS", "section": "monitoring-alerting/etl-run-logging",
                     "check": "xml-ref-integrity", "description": "Table not found"},
                ], f)

            result = load_and_merge(td)
            # Should have 2: one xml-ref-integrity (deduped) + one dangling-prose-reference
            assert len(result) == 2


class TestApplySuppressions:
    """Filter findings against (section, check, entity) suppression tuples."""

    def test_no_suppress_file_is_noop(self):
        findings = [
            {"section": "s1", "check": "c1", "entity": "e1", "description": "d1"},
        ]
        out, n_sup, n_miss = _apply_suppressions(findings, None)
        assert out == findings
        assert n_sup == 0
        assert n_miss == 0

    def test_missing_suppress_file_is_noop(self):
        with tempfile.TemporaryDirectory() as td:
            findings = [
                {"section": "s1", "check": "c1", "entity": "e1", "description": "d1"},
            ]
            out, n_sup, n_miss = _apply_suppressions(
                findings, os.path.join(td, "does-not-exist.json"),
            )
            assert out == findings
            assert n_sup == 0
            assert n_miss == 0

    def test_matching_entry_filters(self):
        with tempfile.TemporaryDirectory() as td:
            sup_path = os.path.join(td, "suppress.json")
            with open(sup_path, "w") as f:
                json.dump([
                    {"section": "s1", "check": "c1", "entity": "e1"},
                ], f)
            findings = [
                {"section": "s1", "check": "c1", "entity": "e1", "description": "d1"},
                {"section": "s1", "check": "c1", "entity": "e2", "description": "d2"},
            ]
            out, n_sup, n_miss = _apply_suppressions(findings, sup_path)
            assert len(out) == 1
            assert out[0]["entity"] == "e2"
            assert n_sup == 1
            assert n_miss == 0

    def test_mismatched_entity_passes(self):
        with tempfile.TemporaryDirectory() as td:
            sup_path = os.path.join(td, "suppress.json")
            with open(sup_path, "w") as f:
                json.dump([
                    {"section": "s1", "check": "c1", "entity": "OTHER"},
                ], f)
            findings = [
                {"section": "s1", "check": "c1", "entity": "e1", "description": "d1"},
            ]
            out, n_sup, _ = _apply_suppressions(findings, sup_path)
            assert out == findings
            assert n_sup == 0

    def test_mismatched_section_or_check_passes(self):
        with tempfile.TemporaryDirectory() as td:
            sup_path = os.path.join(td, "suppress.json")
            with open(sup_path, "w") as f:
                json.dump([
                    {"section": "OTHER", "check": "c1", "entity": "e1"},
                    {"section": "s1", "check": "OTHER", "entity": "e1"},
                ], f)
            findings = [
                {"section": "s1", "check": "c1", "entity": "e1", "description": "d1"},
            ]
            out, n_sup, _ = _apply_suppressions(findings, sup_path)
            assert out == findings
            assert n_sup == 0

    def test_missing_entity_passes_with_warning(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            sup_path = os.path.join(td, "suppress.json")
            with open(sup_path, "w") as f:
                json.dump([
                    {"section": "s1", "check": "c1", "entity": "e1"},
                ], f)
            findings = [
                {"document": "DOC", "section": "s1", "check": "c1",
                 "description": "no entity here"},
            ]
            out, n_sup, n_miss = _apply_suppressions(findings, sup_path)
            assert out == findings
            assert n_sup == 0
            assert n_miss == 1
            err = capsys.readouterr().err
            assert "missing `entity`" in err
            assert "DOC/s1" in err

    def test_empty_entity_passes_with_warning(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            sup_path = os.path.join(td, "suppress.json")
            with open(sup_path, "w") as f:
                json.dump([
                    {"section": "s1", "check": "c1", "entity": "e1"},
                ], f)
            findings = [
                {"document": "DOC", "section": "s1", "check": "c1",
                 "entity": "", "description": "empty entity"},
            ]
            out, n_sup, n_miss = _apply_suppressions(findings, sup_path)
            assert out == findings
            assert n_miss == 1
            assert "missing `entity`" in capsys.readouterr().err

    def test_malformed_json_warns_and_passes(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            sup_path = os.path.join(td, "suppress.json")
            with open(sup_path, "w") as f:
                f.write("{ this is not valid json [")
            findings = [
                {"section": "s1", "check": "c1", "entity": "e1", "description": "d1"},
            ]
            out, n_sup, _ = _apply_suppressions(findings, sup_path)
            assert out == findings
            assert n_sup == 0
            err = capsys.readouterr().err
            assert "malformed JSON" in err

    def test_non_array_suppress_file_warns_and_passes(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            sup_path = os.path.join(td, "suppress.json")
            with open(sup_path, "w") as f:
                json.dump({"not": "an array"}, f)
            findings = [
                {"section": "s1", "check": "c1", "entity": "e1", "description": "d1"},
            ]
            out, n_sup, _ = _apply_suppressions(findings, sup_path)
            assert out == findings
            assert n_sup == 0
            assert "not a JSON array" in capsys.readouterr().err

    def test_summary_counts_when_no_suppressions(self, capsys):
        """Even with no suppress file, missing-entity findings are counted."""
        findings = [
            {"document": "DOC", "section": "s1", "check": "c1",
             "description": "no entity"},
            {"section": "s2", "check": "c2", "entity": "e2", "description": "d2"},
        ]
        out, n_sup, n_miss = _apply_suppressions(findings, None)
        assert len(out) == 2
        assert n_sup == 0
        assert n_miss == 1


class TestApplySuppressionsCLI:
    """End-to-end CLI flow with --suppress-file."""

    def test_cli_filters_suppressed(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "findings-refs.json"), "w") as f:
                json.dump([
                    {"document": "OPS", "section": "s1", "check": "c1",
                     "entity": "e1", "description": "d1"},
                    {"document": "OPS", "section": "s2", "check": "c2",
                     "entity": "e2", "description": "d2"},
                ], f)
            sup_path = os.path.join(td, "suppress.json")
            with open(sup_path, "w") as f:
                json.dump([
                    {"section": "s1", "check": "c1", "entity": "e1"},
                ], f)
            output_path = os.path.join(td, "merged.json")

            result = _run_script(td, output_path, suppress_file=sup_path)
            assert result.returncode == 0
            assert "1 suppressed" in result.stderr

            merged = json.loads(open(output_path).read())
            assert len(merged) == 1
            assert merged[0]["entity"] == "e2"

    def test_cli_no_suppress_file_passes_all(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "findings-refs.json"), "w") as f:
                json.dump([
                    {"document": "OPS", "section": "s1", "check": "c1",
                     "entity": "e1", "description": "d1"},
                ], f)
            output_path = os.path.join(td, "merged.json")

            result = _run_script(td, output_path)
            assert result.returncode == 0
            merged = json.loads(open(output_path).read())
            assert len(merged) == 1


class TestEndToEndProducerToFilter:
    """Smoke test: verify-xml-refs.py → load-audit-findings.py → filter."""

    def test_xml_ref_finding_with_entity_gets_suppressed(self):
        """An xml-ref-integrity finding produced by verify-xml-refs.py
        carries an entity that load-audit-findings.py uses to suppress it."""
        # Build the XML the same way other verify-xml-refs tests do.
        from lib.xml_doc import (
            build_xml_doc,
            serialize_xml_doc,
            update_section_refs,
        )

        verify_script = os.path.join(SCRIPTS_DIR, "verify-xml-refs.py")
        with tempfile.TemporaryDirectory() as td:
            project_root = os.path.join(td, "project")
            xml_dir = os.path.join(project_root, ".mg", "docs", "xml-sources")
            audience_dir = os.path.join(xml_dir, "developers")
            os.makedirs(audience_dir)
            with open(os.path.join(project_root, "pyproject.toml"), "w") as f:
                f.write('[project]\nname = "x"\nversion = "0"\n')

            tree = build_xml_doc(
                "developers", "how-to", "# Test",
                [{"slug": "s1",
                  "body": "<!-- section: s1 -->\n## S1\n\nContent"}],
            )
            update_section_refs(tree, "s1", [
                {"type": "dep", "name": "fake-package-xyz"},
            ])
            xml_path = os.path.join(audience_dir, "TEST.xml")
            serialize_xml_doc(tree, xml_path)

            audit_dir = os.path.join(td, "audit")
            os.makedirs(audit_dir)
            findings_refs = os.path.join(audit_dir, "findings-refs.json")
            with open(findings_refs, "w") as f:
                json.dump([], f)

            r = subprocess.run(
                [sys.executable, verify_script,
                 "--xml-dir", xml_dir,
                 "--project-root", project_root,
                 "--findings-file", findings_refs],
                capture_output=True, text=True,
            )
            assert r.returncode == 0, r.stderr

            produced = json.loads(open(findings_refs).read())
            dep_finding = next(
                (f for f in produced
                 if "fake-package-xyz" in f.get("description", "")),
                None,
            )
            assert dep_finding is not None, produced
            assert dep_finding.get("entity") == "fake-package-xyz"

            # Now suppress it via the central filter and confirm it's gone.
            sup_path = os.path.join(td, "suppress.json")
            with open(sup_path, "w") as f:
                json.dump([
                    {"section": "s1", "check": "xml-ref-integrity",
                     "entity": "fake-package-xyz"},
                ], f)
            output_path = os.path.join(td, "merged.json")
            result = _run_script(audit_dir, output_path, suppress_file=sup_path)
            assert result.returncode == 0

            merged = json.loads(open(output_path).read())
            # The dep finding should be gone; any other findings still pass.
            assert all(
                f.get("entity") != "fake-package-xyz" for f in merged
            ), merged
