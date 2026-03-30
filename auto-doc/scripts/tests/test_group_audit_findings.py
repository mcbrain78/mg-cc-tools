"""Tests for group-audit-findings.py -- root cause grouping + XML context."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "group-audit-findings.py")
sys.path.insert(0, SCRIPTS_DIR)

from lib.xml_doc import build_xml_doc, serialize_xml_doc, update_section_refs  # noqa: E402

# Import hyphen-named module via importlib
_spec = importlib.util.spec_from_file_location("group_audit_findings", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
build_groups = _mod.build_groups
extract_entities = _mod.extract_entities
group_findings = _mod.group_findings
make_group_id = _mod.make_group_id
summarize_group = _mod.summarize_group


class TestExtractEntities:
    """Entity extraction from finding descriptions."""

    def test_backtick_entities(self):
        desc = "Column `flow_name` not found on table `etl_runs`"
        ents = extract_entities(desc)
        assert "flow_name" in ents
        assert "etl_runs" in ents

    def test_camelcase_entities(self):
        desc = "Class EtlRun not found in any Python file"
        ents = extract_entities(desc)
        assert "EtlRun" in ents

    def test_no_entities(self):
        desc = "Some generic description with no code entities"
        ents = extract_entities(desc)
        assert len(ents) == 0

    def test_skips_long_phrases(self):
        desc = "`this is a very long phrase that should not be treated as an entity name because it has spaces`"
        ents = extract_entities(desc)
        # Should skip because of spaces
        assert len(ents) == 0

    def test_mixed_entities(self):
        desc = "`compute_finance_metrics` in ComputeService not found"
        ents = extract_entities(desc)
        assert "compute_finance_metrics" in ents
        assert "ComputeService" in ents


class TestGroupFindings:
    """Grouping logic: shared entities, identical descriptions, singletons."""

    def test_shared_entity_groups_together(self):
        findings = [
            {"description": "Column `flow_name` not found on table `etl_runs`", "section": "s1"},
            {"description": "Table `etl_runs` schema mismatch", "section": "s2"},
        ]
        groups = group_findings(findings)
        # Both mention etl_runs → same group
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_different_entities_separate_groups(self):
        findings = [
            {"description": "Table `etl_runs` not found", "section": "s1"},
            {"description": "Function `compute_metrics` not found", "section": "s2"},
        ]
        groups = group_findings(findings)
        assert len(groups) == 2

    def test_identical_descriptions_no_entities_grouped(self):
        findings = [
            {"description": "some generic issue", "section": "s1"},
            {"description": "some generic issue", "section": "s2"},
        ]
        groups = group_findings(findings)
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_singleton_groups(self):
        findings = [
            {"description": "unique issue A", "section": "s1"},
            {"description": "unique issue B", "section": "s2"},
        ]
        groups = group_findings(findings)
        assert len(groups) == 2

    def test_empty_findings(self):
        groups = group_findings([])
        assert groups == []

    def test_transitive_grouping(self):
        """A shares entity with B, B shares entity with C → all in one group."""
        findings = [
            {"description": "Problem with `etl_runs` in `road_runner`", "section": "s1"},
            {"description": "Schema `road_runner` has wrong table", "section": "s2"},
            {"description": "Issue with `etl_runs` column", "section": "s3"},
        ]
        groups = group_findings(findings)
        # All three share entities transitively
        assert len(groups) == 1
        assert len(groups[0]) == 3


class TestGroupIdAndSummary:
    """Group ID generation and summary."""

    def test_group_id_uses_entity(self):
        group = [
            {"description": "Table `etl_runs` not found", "check": "xml-ref-integrity"},
        ]
        gid = make_group_id(group)
        assert "etl_runs" in gid

    def test_summary_includes_counts(self):
        group = [
            {"description": "Issue with `etl_runs`", "document": "OPS", "section": "s1"},
            {"description": "Issue with `etl_runs`", "document": "OPS", "section": "s2"},
        ]
        summary = summarize_group(group)
        assert "2 finding(s)" in summary
        assert "etl_runs" in summary


class TestXMLContextLoading:
    """Loading XML context for grouped findings."""

    def _build_xml(self, xml_dir, audience, doc_name, sections_with_refs):
        """Build an XML file with populated refs."""
        sections = [{"slug": s, "body": b} for s, b, _ in sections_with_refs]
        tree = build_xml_doc(audience, "how-to", f"# {doc_name}", sections)
        for slug, _, refs in sections_with_refs:
            if refs:
                update_section_refs(tree, slug, refs)

        doc_dir = os.path.join(xml_dir, audience) if audience != "all" else xml_dir
        os.makedirs(doc_dir, exist_ok=True)
        xml_path = os.path.join(doc_dir, f"{doc_name}.xml")
        serialize_xml_doc(tree, xml_path)
        return xml_path

    def test_loads_section_context(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            refs = [{"type": "db", "schema": "road_runner", "table": "etl_runs"}]
            self._build_xml(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent about etl_runs.",
                refs,
            )])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "xml-ref-integrity", "description": "Table `etl_runs` issue"},
            ]

            result = build_groups(findings, xml_dir)
            assert result["total_groups"] == 1
            group = result["groups"][0]
            assert len(group["affected_sections"]) == 1
            sec = group["affected_sections"][0]
            assert sec["slug"] == "monitoring"
            assert sec["audience"] == "devops"
            assert len(sec["current_refs"]) > 0
            assert "monitoring" in sec["current_body"].lower() or "etl_runs" in sec["current_body"]

    def test_missing_xml_file(self):
        """Findings referencing non-existent XML files are skipped gracefully."""
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            findings = [
                {"document": "NONEXISTENT", "section": "s1", "audience": "devops",
                 "check": "c1", "description": "some issue"},
            ]

            result = build_groups(findings, xml_dir)
            assert result["total_groups"] == 1
            # Group exists but has no affected sections
            assert len(result["groups"][0]["affected_sections"]) == 0

    def test_multiple_sections_same_xml(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            self._build_xml(xml_dir, "devops", "OPS", [
                ("monitoring", "<!-- section: monitoring -->\n## Monitoring\n\nM content.", []),
                ("deployment", "<!-- section: deployment -->\n## Deployment\n\nD content.", []),
            ])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "c1", "description": "Issue with `shared_entity`"},
                {"document": "OPS", "section": "deployment", "audience": "devops",
                 "check": "c1", "description": "Issue with `shared_entity`"},
            ]

            result = build_groups(findings, xml_dir)
            assert result["total_groups"] == 1
            assert len(result["groups"][0]["affected_sections"]) == 2


class TestCLI:
    """CLI invocation tests."""

    def test_basic_run(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            findings_file = os.path.join(td, "findings.json")
            with open(findings_file, "w") as f:
                json.dump([
                    {"document": "OPS", "section": "s1", "audience": "devops",
                     "check": "c1", "description": "Issue with `etl_runs`"},
                ], f)

            output_path = os.path.join(td, "grouped.json")
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--findings-file", findings_file,
                 "--xml-dir", xml_dir,
                 "--output", output_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            grouped = json.loads(open(output_path).read())
            assert grouped["total_findings"] == 1
            assert grouped["total_groups"] == 1

    def test_empty_findings(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            findings_file = os.path.join(td, "findings.json")
            with open(findings_file, "w") as f:
                json.dump([], f)

            output_path = os.path.join(td, "grouped.json")
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--findings-file", findings_file,
                 "--xml-dir", xml_dir,
                 "--output", output_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            grouped = json.loads(open(output_path).read())
            assert grouped["total_groups"] == 0
