"""Tests for load-xml-context.py -- XML context loading with pre-grouped input."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "load-xml-context.py")
sys.path.insert(0, SCRIPTS_DIR)

from lib.xml_doc import build_xml_doc, serialize_xml_doc, update_section_refs  # noqa: E402

# Import hyphen-named module via importlib
_spec = importlib.util.spec_from_file_location("load_xml_context", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
build_fix_context = _mod.build_fix_context


def _build_xml(xml_dir, audience, doc_name, sections_with_refs):
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


class TestIndexResolution:
    """Finding indices are resolved correctly from grouping input."""

    def test_resolves_indices_to_findings(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                [],
            )])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "c1", "description": "Issue A"},
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "c2", "description": "Issue B"},
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "c3", "description": "Issue C"},
            ]

            grouping = {
                "groups": [
                    {
                        "group_id": "group-ab",
                        "root_cause_summary": "Issues A and B",
                        "finding_indices": [0, 1],
                    },
                    {
                        "group_id": "group-c",
                        "root_cause_summary": "Issue C",
                        "finding_indices": [2],
                    },
                ]
            }

            result = build_fix_context(grouping, findings, xml_dir)
            assert result["total_groups"] == 2
            assert result["total_findings"] == 3
            assert len(result["groups"][0]["findings"]) == 2
            assert len(result["groups"][1]["findings"]) == 1
            assert result["groups"][0]["findings"][0]["description"] == "Issue A"
            assert result["groups"][1]["findings"][0]["description"] == "Issue C"

    def test_out_of_range_indices_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            findings = [
                {"document": "OPS", "section": "s1", "audience": "devops",
                 "check": "c1", "description": "Only finding"},
            ]

            grouping = {
                "groups": [{
                    "group_id": "g1",
                    "root_cause_summary": "test",
                    "finding_indices": [0, 5, 99],
                }]
            }

            result = build_fix_context(grouping, findings, xml_dir)
            # Only index 0 is valid
            assert len(result["groups"][0]["findings"]) == 1


class TestXMLContextLoading:
    """Loading XML context for grouped findings."""

    def test_loads_section_context(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            refs = [{"type": "db", "schema": "road_runner", "table": "etl_runs"}]
            _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent about etl_runs.",
                refs,
            )])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "xml-ref-integrity", "description": "Table `etl_runs` issue"},
            ]

            grouping = {
                "groups": [{
                    "group_id": "etl-runs-issue",
                    "root_cause_summary": "etl_runs table issue",
                    "finding_indices": [0],
                }]
            }

            result = build_fix_context(grouping, findings, xml_dir)
            assert result["total_groups"] == 1
            group = result["groups"][0]
            assert len(group["affected_sections"]) == 1
            sec = group["affected_sections"][0]
            assert sec["slug"] == "monitoring"
            assert sec["audience"] == "devops"
            assert len(sec["current_refs"]) > 0

    def test_missing_xml_file(self):
        """Findings referencing non-existent XML files produce 0 sections."""
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            findings = [
                {"document": "NONEXISTENT", "section": "s1", "audience": "devops",
                 "check": "c1", "description": "some issue"},
            ]

            grouping = {
                "groups": [{
                    "group_id": "missing-doc",
                    "root_cause_summary": "test",
                    "finding_indices": [0],
                }]
            }

            result = build_fix_context(grouping, findings, xml_dir)
            assert result["total_groups"] == 1
            assert len(result["groups"][0]["affected_sections"]) == 0

    def test_multiple_sections_same_xml(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            _build_xml(xml_dir, "devops", "OPS", [
                ("monitoring", "<!-- section: monitoring -->\n## Monitoring\n\nM content.", []),
                ("deployment", "<!-- section: deployment -->\n## Deployment\n\nD content.", []),
            ])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "c1", "description": "Issue in monitoring"},
                {"document": "OPS", "section": "deployment", "audience": "devops",
                 "check": "c1", "description": "Issue in deployment"},
            ]

            grouping = {
                "groups": [{
                    "group_id": "ops-issues",
                    "root_cause_summary": "Issues across OPS sections",
                    "finding_indices": [0, 1],
                }]
            }

            result = build_fix_context(grouping, findings, xml_dir)
            assert result["total_groups"] == 1
            assert len(result["groups"][0]["affected_sections"]) == 2

    def test_deduplicates_sections(self):
        """Multiple findings pointing to same section don't duplicate it."""
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                [],
            )])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "c1", "description": "Issue A"},
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "c2", "description": "Issue B"},
            ]

            grouping = {
                "groups": [{
                    "group_id": "monitoring-issues",
                    "root_cause_summary": "Multiple issues in monitoring",
                    "finding_indices": [0, 1],
                }]
            }

            result = build_fix_context(grouping, findings, xml_dir)
            # Same section referenced by 2 findings -> only 1 affected_section
            assert len(result["groups"][0]["affected_sections"]) == 1


class TestCLI:
    """CLI invocation tests."""

    def test_basic_run(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            findings = [
                {"document": "OPS", "section": "s1", "audience": "devops",
                 "check": "c1", "description": "Issue with etl_runs"},
            ]
            findings_file = os.path.join(td, "findings.json")
            with open(findings_file, "w") as f:
                json.dump(findings, f)

            grouping = {
                "groups": [{
                    "group_id": "etl-issue",
                    "root_cause_summary": "etl_runs problem",
                    "finding_indices": [0],
                }]
            }
            grouping_file = os.path.join(td, "grouping.json")
            with open(grouping_file, "w") as f:
                json.dump(grouping, f)

            output_path = os.path.join(td, "fix-context.json")
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--grouping-file", grouping_file,
                 "--findings-file", findings_file,
                 "--xml-dir", xml_dir,
                 "--output", output_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_path) as f:
                ctx = json.load(f)
            assert ctx["total_findings"] == 1
            assert ctx["total_groups"] == 1

    def test_empty_grouping(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            findings_file = os.path.join(td, "findings.json")
            with open(findings_file, "w") as f:
                json.dump([], f)

            grouping_file = os.path.join(td, "grouping.json")
            with open(grouping_file, "w") as f:
                json.dump({"groups": []}, f)

            output_path = os.path.join(td, "fix-context.json")
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--grouping-file", grouping_file,
                 "--findings-file", findings_file,
                 "--xml-dir", xml_dir,
                 "--output", output_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_path) as f:
                ctx = json.load(f)
            assert ctx["total_groups"] == 0
