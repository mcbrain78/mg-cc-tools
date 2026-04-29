"""Tests for extract-edit-xml.py -- extract per-group edit XML from masters."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "extract-edit-xml.py")
sys.path.insert(0, SCRIPTS_DIR)

from lib.xml_doc import build_xml_doc, serialize_xml_doc, update_section_refs  # noqa: E402
from lxml import etree  # noqa: E402

# Import hyphen-named module via importlib
_spec = importlib.util.spec_from_file_location("extract_edit_xml", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
extract_edit_xml = _mod.extract_edit_xml


def _build_xml(xml_dir, audience, doc_name, sections_with_refs):
    """Build an XML file with populated refs.

    sections_with_refs: list of (slug, body, refs) or (slug, body, refs, children)
    where children is a list of (slug, body, refs) or (slug, body, refs, children).
    """
    def _to_section_dicts(items):
        result = []
        for item in items:
            slug, body, refs = item[0], item[1], item[2]
            children_raw = item[3] if len(item) > 3 else []
            d = {"slug": slug, "body": body}
            if children_raw:
                d["children"] = _to_section_dicts(children_raw)
            result.append(d)
        return result

    def _collect_refs(items, prefix=""):
        """Collect (path, refs) pairs from nested section specs."""
        result = []
        for item in items:
            slug, _, refs = item[0], item[1], item[2]
            children_raw = item[3] if len(item) > 3 else []
            path = f"{prefix}/{slug}" if prefix else slug
            if refs:
                result.append((path, refs))
            result.extend(_collect_refs(children_raw, path))
        return result

    sections = _to_section_dicts(sections_with_refs)
    tree = build_xml_doc(audience, "how-to", f"# {doc_name}", sections)
    for path, refs in _collect_refs(sections_with_refs):
        update_section_refs(tree, path, refs)

    doc_dir = os.path.join(xml_dir, audience) if audience != "all" else xml_dir
    os.makedirs(doc_dir, exist_ok=True)
    xml_path = os.path.join(doc_dir, f"{doc_name}.xml")
    serialize_xml_doc(tree, xml_path)
    return xml_path


class TestBasicExtraction:
    """Extract edit XML for a single group with one section."""

    def test_extracts_one_section(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            refs = [{"type": "code", "kind": "function", "name": "start_run",
                      "module": "src/etl/tracking.py"}]
            xml_path = _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                refs,
            )])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "reference-integrity",
                 "description": "Function `start_run` not mentioned in prose"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "tracking-funcs",
                    "root_cause_summary": "Tracking functions not named",
                    "finding_indices": [0],
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            root = tree.getroot()

            assert root.tag == "edit-group"
            assert root.get("id") == "tracking-funcs"

            summary = root.find("summary")
            assert summary.text == "Tracking functions not named"

            sections = root.findall("section")
            assert len(sections) == 1

            sec = sections[0]
            assert sec.get("source") == xml_path
            assert sec.get("slug") == "monitoring"
            assert sec.get("audience") == "devops"
            assert sec.get("document") == "OPS"

            # Findings are present
            finding_els = sec.findall("findings/finding")
            assert len(finding_els) == 1
            assert finding_els[0].get("check") == "reference-integrity"
            assert "start_run" in finding_els[0].text

            # Refs are preserved in native XML
            refs_el = sec.find("refs")
            assert refs_el is not None
            func_el = refs_el.find("code/function")
            assert func_el is not None
            assert func_el.get("name") == "start_run"

            # Body is in CDATA
            body_el = sec.find("body")
            assert body_el is not None
            assert "## Monitoring" in body_el.text

    def test_multiple_findings_same_section(self):
        """Multiple findings in same section → one section, multiple findings."""
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            refs = [
                {"type": "code", "kind": "function", "name": "start_run"},
                {"type": "code", "kind": "function", "name": "complete_run"},
            ]
            _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                refs,
            )])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "reference-integrity", "description": "start_run missing"},
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "reference-integrity", "description": "complete_run missing"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "tracking-funcs",
                    "root_cause_summary": "Functions not named",
                    "finding_indices": [0, 1],
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            sections = tree.getroot().findall("section")
            assert len(sections) == 1

            finding_els = sections[0].findall("findings/finding")
            assert len(finding_els) == 2


class TestMultiSection:
    """Groups spanning multiple sections and XML files."""

    def test_two_sections_same_file(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            _build_xml(xml_dir, "devops", "OPS", [
                ("monitoring", "<!-- section: monitoring -->\n## Monitoring\n\nM.", []),
                ("deployment", "<!-- section: deployment -->\n## Deployment\n\nD.", []),
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
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            sections = tree.getroot().findall("section")
            assert len(sections) == 2

    def test_two_sections_different_files(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            _build_xml(xml_dir, "devops", "OPS", [
                ("monitoring", "<!-- section: monitoring -->\n## Monitoring\n\nM.", []),
            ])
            _build_xml(xml_dir, "devops", "TROUBLESHOOT", [
                ("diagnosis", "<!-- section: diagnosis -->\n## Diagnosis\n\nD.", []),
            ])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "c1", "description": "Issue A"},
                {"document": "TROUBLESHOOT", "section": "diagnosis", "audience": "devops",
                 "check": "c1", "description": "Issue B"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "cross-doc",
                    "root_cause_summary": "Cross-doc issues",
                    "finding_indices": [0, 1],
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            sections = tree.getroot().findall("section")
            assert len(sections) == 2
            sources = {s.get("source") for s in sections}
            assert len(sources) == 2


class TestEdgeCases:
    """Edge cases: missing XML, out-of-range, empty."""

    def test_missing_xml_produces_zero_sections(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            findings = [
                {"document": "NONEXISTENT", "section": "s1", "audience": "devops",
                 "check": "c1", "description": "Issue"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "missing-doc",
                    "root_cause_summary": "test",
                    "finding_indices": [0],
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            sections = tree.getroot().findall("section")
            assert len(sections) == 0

    def test_missing_section_in_xml(self):
        """Finding references a slug that doesn't exist in the master XML."""
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            _build_xml(xml_dir, "devops", "OPS", [
                ("monitoring", "<!-- section: monitoring -->\n## M\n\nM.", []),
            ])

            findings = [
                {"document": "OPS", "section": "nonexistent-slug",
                 "audience": "devops", "check": "c1", "description": "Issue"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "bad-slug",
                    "root_cause_summary": "test",
                    "finding_indices": [0],
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            sections = tree.getroot().findall("section")
            assert len(sections) == 0

    def test_out_of_range_group_index(self):
        grouping = {"groups": [{"group_id": "g1", "finding_indices": [0]}]}
        findings = [{"check": "c1", "description": "Issue"}]
        import pytest
        with pytest.raises(ValueError, match="out of range"):
            extract_edit_xml(grouping, findings, "/tmp/fake", 5)

    def test_out_of_range_finding_indices_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## M\n\nM.",
                [],
            )])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "c1", "description": "Issue A"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "g1",
                    "root_cause_summary": "test",
                    "finding_indices": [0, 5, 99],
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            sections = tree.getroot().findall("section")
            assert len(sections) == 1
            # Only index 0 was valid → 1 finding in the section
            finding_els = sections[0].findall("findings/finding")
            assert len(finding_els) == 1

    def test_root_level_xml(self):
        """Root-level XML files (no audience subdir) resolve via 'all' key."""
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            _build_xml(xml_dir, "all", "GLOSSARY", [(
                "terms",
                "<!-- section: terms -->\n## Terms\n\nT.",
                [],
            )])

            findings = [
                {"document": "GLOSSARY", "section": "terms", "audience": "all",
                 "check": "c1", "description": "Issue"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "glossary-issue",
                    "root_cause_summary": "test",
                    "finding_indices": [0],
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            sections = tree.getroot().findall("section")
            assert len(sections) == 1


class TestRefsPreservation:
    """Refs are preserved in native XML format."""

    def test_db_refs_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            refs = [
                {"type": "db", "db": "road_runner_db", "schema": "road_runner",
                 "table": "etl_runs"},
                {"type": "db", "db": "road_runner_db", "schema": "road_runner",
                 "table": "etl_runs", "column": "status"},
            ]
            _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## M\n\nContent.",
                refs,
            )])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "c1", "description": "Issue"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "db-issue",
                    "root_cause_summary": "test",
                    "finding_indices": [0],
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            sec = tree.getroot().findall("section")[0]
            refs_el = sec.find("refs")

            # DB refs should be in native XML with name attribute
            db_el = refs_el.find("db")
            assert db_el is not None
            assert db_el.get("name") == "road_runner_db"
            schema_el = db_el.find("schema")
            assert schema_el.get("name") == "road_runner"
            tables = schema_el.findall("table")
            assert len(tables) == 1
            assert tables[0].get("name") == "etl_runs"

    def test_empty_refs(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## M\n\nContent.",
                [],
            )])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "c1", "description": "Issue"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "g1",
                    "root_cause_summary": "test",
                    "finding_indices": [0],
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            sec = tree.getroot().findall("section")[0]
            refs_el = sec.find("refs")
            assert refs_el is not None
            assert len(refs_el) == 0


class TestCLI:
    """CLI invocation tests."""

    def test_basic_run(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                [],
            )])

            findings_file = os.path.join(td, "findings.json")
            with open(findings_file, "w") as f:
                json.dump([
                    {"document": "OPS", "section": "monitoring", "audience": "devops",
                     "check": "c1", "description": "Issue"},
                ], f)

            grouping_file = os.path.join(td, "grouping.json")
            with open(grouping_file, "w") as f:
                json.dump({
                    "groups": [{
                        "group_id": "g1",
                        "root_cause_summary": "test",
                        "finding_indices": [0],
                    }],
                }, f)

            output = os.path.join(td, "edit.xml")
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--grouping-file", grouping_file,
                 "--group-index", "0",
                 "--findings-file", findings_file,
                 "--xml-dir", xml_dir,
                 "--output", output],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert os.path.isfile(output)

            # Parse and verify
            tree = etree.parse(output)
            sections = tree.getroot().findall("section")
            assert len(sections) == 1

    def test_empty_group(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            findings_file = os.path.join(td, "findings.json")
            with open(findings_file, "w") as f:
                json.dump([], f)

            grouping_file = os.path.join(td, "grouping.json")
            with open(grouping_file, "w") as f:
                json.dump({
                    "groups": [{
                        "group_id": "empty",
                        "root_cause_summary": "test",
                        "finding_indices": [],
                    }],
                }, f)

            output = os.path.join(td, "edit.xml")
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--grouping-file", grouping_file,
                 "--group-index", "0",
                 "--findings-file", findings_file,
                 "--xml-dir", xml_dir,
                 "--output", output],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            tree = etree.parse(output)
            sections = tree.getroot().findall("section")
            assert len(sections) == 0


class TestNestedExtraction:
    """Extract edit XML for nested sections using path-based navigation."""

    def test_nested_section_has_path_attribute(self):
        """Extraction of a nested section produces edit XML with path attribute."""
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            refs = [{"type": "code", "kind": "function", "name": "log_run"}]
            _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring-alerting",
                "<!-- section: monitoring-alerting -->\n## Monitoring & Alerting\n\nOverview.",
                [],
                [(
                    "etl-run-logging",
                    "<!-- section: etl-run-logging -->\n### ETL Run Logging\n\nLogs all runs.",
                    refs,
                )],
            )])

            findings = [
                {"document": "OPS",
                 "section": "monitoring-alerting/etl-run-logging",
                 "audience": "devops",
                 "check": "reference-integrity",
                 "description": "Function log_run not mentioned"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "nested-funcs",
                    "root_cause_summary": "Nested section issue",
                    "finding_indices": [0],
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            sections = tree.getroot().findall("section")
            assert len(sections) == 1

            sec = sections[0]
            assert sec.get("path") == "monitoring-alerting/etl-run-logging"
            assert sec.get("slug") == "etl-run-logging"

    def test_path_attribute_contains_full_path(self):
        """Path attribute is the full slash-separated path."""
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring-alerting",
                "<!-- section: monitoring-alerting -->\n## M\n\nM.",
                [],
                [(
                    "etl-run-logging",
                    "<!-- section: etl-run-logging -->\n### ETL\n\nE.",
                    [],
                    [(
                        "artifact-format",
                        "<!-- section: artifact-format -->\n#### Artifact Format\n\nA.",
                        [],
                    )],
                )],
            )])

            findings = [
                {"document": "OPS",
                 "section": "monitoring-alerting/etl-run-logging/artifact-format",
                 "audience": "devops",
                 "check": "c1", "description": "Issue"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "deep-nested",
                    "root_cause_summary": "test",
                    "finding_indices": [0],
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            sections = tree.getroot().findall("section")
            assert len(sections) == 1
            assert sections[0].get("path") == "monitoring-alerting/etl-run-logging/artifact-format"
            assert sections[0].get("slug") == "artifact-format"

    def test_sections_map_groups_by_path(self):
        """Findings group by (xml_path, path) not (xml_path, slug)."""
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring-alerting",
                "<!-- section: monitoring-alerting -->\n## M\n\nM.",
                [],
                [(
                    "etl-run-logging",
                    "<!-- section: etl-run-logging -->\n### ETL\n\nE.",
                    [],
                )],
            )])

            # Two findings targeting the same nested path
            findings = [
                {"document": "OPS",
                 "section": "monitoring-alerting/etl-run-logging",
                 "audience": "devops",
                 "check": "c1", "description": "Issue A"},
                {"document": "OPS",
                 "section": "monitoring-alerting/etl-run-logging",
                 "audience": "devops",
                 "check": "c2", "description": "Issue B"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "grouped",
                    "root_cause_summary": "test",
                    "finding_indices": [0, 1],
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            sections = tree.getroot().findall("section")
            # Both findings grouped into one section
            assert len(sections) == 1
            finding_els = sections[0].findall("findings/finding")
            assert len(finding_els) == 2

    def test_top_level_section_gets_path_attribute(self):
        """Top-level sections also get a path attribute (bare slug as path)."""
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            _build_xml(xml_dir, "devops", "OPS", [(
                "deployment",
                "<!-- section: deployment -->\n## Deployment\n\nD.",
                [],
            )])

            findings = [
                {"document": "OPS", "section": "deployment",
                 "audience": "devops", "check": "c1", "description": "Issue"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "top-level",
                    "root_cause_summary": "test",
                    "finding_indices": [0],
                }],
            }

            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            sec = tree.getroot().findall("section")[0]
            # Top-level: path equals slug
            assert sec.get("path") == "deployment"
            assert sec.get("slug") == "deployment"


class TestEntityAttribute:
    """The <finding> element carries the entity attribute so the audit-fixer
    agent can extract the suppression key directly without parsing the
    description (which may contain multiple backticked tokens).
    """

    def test_entity_attribute_present_when_set(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                [],
            )])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "xml-ref-integrity",
                 "description": "Attribute `provider` not found on class `RateLimitError`",
                 "entity": "provider"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "g1",
                    "root_cause_summary": "test",
                    "finding_indices": [0],
                }],
            }
            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            finding_el = tree.getroot().findall("section/findings/finding")[0]
            assert finding_el.get("entity") == "provider"
            assert finding_el.get("check") == "xml-ref-integrity"

    def test_entity_attribute_empty_when_missing(self):
        """Findings without entity render as <finding entity=""> rather
        than crashing — the orchestrator's load-audit-findings pass warns
        on missing-entity findings; extract-edit-xml just preserves them."""
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            _build_xml(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                [],
            )])

            findings = [
                {"document": "OPS", "section": "monitoring", "audience": "devops",
                 "check": "diataxis", "description": "Mixed content"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "g1",
                    "root_cause_summary": "test",
                    "finding_indices": [0],
                }],
            }
            tree = extract_edit_xml(grouping, findings, xml_dir, 0)
            finding_el = tree.getroot().findall("section/findings/finding")[0]
            assert finding_el.get("entity") == ""
