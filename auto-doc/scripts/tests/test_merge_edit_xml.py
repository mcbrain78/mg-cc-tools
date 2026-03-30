"""Tests for merge-edit-xml.py -- merge edited sections back into master XMLs."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "merge-edit-xml.py")
sys.path.insert(0, SCRIPTS_DIR)

from lib.xml_doc import (  # noqa: E402
    build_xml_doc,
    parse_xml_doc,
    serialize_xml_doc,
    update_section_refs,
)
from lxml import etree  # noqa: E402

# Import hyphen-named module via importlib
_spec = importlib.util.spec_from_file_location("merge_edit_xml", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
merge_edit_xml = _mod.merge_edit_xml


def _build_master(td, audience, doc_name, sections_with_refs):
    """Build a master XML file, return its path."""
    sections = [{"slug": s, "body": b} for s, b, _ in sections_with_refs]
    tree = build_xml_doc(audience, "how-to", f"# {doc_name}", sections)
    for slug, _, refs in sections_with_refs:
        if refs:
            update_section_refs(tree, slug, refs)

    doc_dir = os.path.join(td, audience) if audience != "all" else td
    os.makedirs(doc_dir, exist_ok=True)
    xml_path = os.path.join(doc_dir, f"{doc_name}.xml")
    serialize_xml_doc(tree, xml_path)
    return xml_path


def _build_edit_xml(td, group_id, sections):
    """Build an edit XML file.

    sections: list of dicts with keys: source, slug, audience, document,
              findings (list of {check, description}), refs_xml (str), body (str)
    """
    root = etree.Element("edit-group", id=group_id)
    summary = etree.SubElement(root, "summary")
    summary.text = "Test group"

    for sec in sections:
        section_el = etree.SubElement(
            root, "section",
            source=sec["source"],
            slug=sec["slug"],
            audience=sec.get("audience", "devops"),
            document=sec.get("document", "DOC"),
        )

        findings_el = etree.SubElement(section_el, "findings")
        for f in sec.get("findings", []):
            finding_el = etree.SubElement(
                findings_el, "finding", check=f.get("check", ""),
            )
            finding_el.text = f.get("description", "")

        # Refs — parse from XML string if provided
        if "refs_xml" in sec and sec["refs_xml"]:
            refs_el = etree.fromstring(sec["refs_xml"])
            section_el.append(refs_el)
        else:
            etree.SubElement(section_el, "refs")

        body_el = etree.SubElement(section_el, "body")
        body_el.text = etree.CDATA(sec.get("body", ""))

    tree = etree.ElementTree(root)
    edit_path = os.path.join(td, f"{group_id}.xml")
    tree.write(edit_path, xml_declaration=True, encoding="utf-8", pretty_print=True)
    return edit_path


class TestBodyMerge:
    """Body changes are written back to master XML."""

    def test_changed_body_updates_master(self):
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nOriginal content.",
                [],
            )])

            edit_path = _build_edit_xml(td, "g1", [{
                "source": master_path,
                "slug": "monitoring",
                "body": "<!-- section: monitoring -->\n## Monitoring\n\nFixed content.",
            }])

            summary = merge_edit_xml(edit_path)
            assert summary["sections_updated"] == 1
            assert master_path in summary["files_modified"]

            doc = parse_xml_doc(master_path)
            assert "Fixed content" in doc["sections"][0]["body"]
            assert "Original" not in doc["sections"][0]["body"]

    def test_unchanged_body_no_write(self):
        with tempfile.TemporaryDirectory() as td:
            body = "<!-- section: monitoring -->\n## Monitoring\n\nSame content."
            master_path = _build_master(td, "devops", "OPS", [(
                "monitoring", body, [],
            )])

            edit_path = _build_edit_xml(td, "g1", [{
                "source": master_path,
                "slug": "monitoring",
                "body": body,
            }])

            summary = merge_edit_xml(edit_path)
            assert summary["sections_updated"] == 0
            assert summary["files_modified"] == []


class TestRefsMerge:
    """Ref changes are written back to master XML."""

    def test_changed_refs_updates_master(self):
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                [{"type": "db", "schema": "wrong", "table": "etl_runs"}],
            )])

            # Edit XML has corrected refs
            refs_xml = (
                "<refs><db><schema name=\"road_runner\">"
                "<table name=\"etl_runs\"/>"
                "</schema></db></refs>"
            )
            edit_path = _build_edit_xml(td, "g1", [{
                "source": master_path,
                "slug": "monitoring",
                "body": "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                "refs_xml": refs_xml,
            }])

            summary = merge_edit_xml(edit_path)
            assert summary["sections_updated"] == 1

            doc = parse_xml_doc(master_path)
            refs = doc["sections"][0]["refs"]
            assert len(refs) == 1
            assert refs[0]["schema"] == "road_runner"

    def test_added_ref(self):
        """Adding a new ref to a section with empty refs."""
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                [],
            )])

            refs_xml = (
                '<refs><code><function name="start_run" '
                'module="src/etl/tracking.py"/></code></refs>'
            )
            edit_path = _build_edit_xml(td, "g1", [{
                "source": master_path,
                "slug": "monitoring",
                "body": "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                "refs_xml": refs_xml,
            }])

            summary = merge_edit_xml(edit_path)
            assert summary["sections_updated"] == 1

            doc = parse_xml_doc(master_path)
            refs = doc["sections"][0]["refs"]
            assert len(refs) == 1
            assert refs[0]["name"] == "start_run"


class TestBothChanges:
    """Combined body + ref changes."""

    def test_both_body_and_refs_updated(self):
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nOld text.",
                [{"type": "db", "schema": "wrong", "table": "bad"}],
            )])

            refs_xml = (
                '<refs><db><schema name="correct">'
                '<table name="good"/>'
                "</schema></db></refs>"
            )
            edit_path = _build_edit_xml(td, "g1", [{
                "source": master_path,
                "slug": "monitoring",
                "body": "<!-- section: monitoring -->\n## Monitoring\n\nNew text.",
                "refs_xml": refs_xml,
            }])

            summary = merge_edit_xml(edit_path)
            assert summary["sections_updated"] == 1
            assert len(summary["files_modified"]) == 1

            doc = parse_xml_doc(master_path)
            assert "New text" in doc["sections"][0]["body"]
            assert doc["sections"][0]["refs"][0]["table"] == "good"


class TestMultiSection:
    """Multiple sections in one edit file."""

    def test_two_sections_one_file(self):
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [
                ("monitoring", "<!-- section: monitoring -->\n## M\n\nOld M.", []),
                ("deployment", "<!-- section: deployment -->\n## D\n\nOld D.", []),
            ])

            edit_path = _build_edit_xml(td, "g1", [
                {
                    "source": master_path,
                    "slug": "monitoring",
                    "body": "<!-- section: monitoring -->\n## M\n\nFixed M.",
                },
                {
                    "source": master_path,
                    "slug": "deployment",
                    "body": "<!-- section: deployment -->\n## D\n\nFixed D.",
                },
            ])

            summary = merge_edit_xml(edit_path)
            assert summary["sections_updated"] == 2
            assert len(summary["files_modified"]) == 1

            doc = parse_xml_doc(master_path)
            assert "Fixed M" in doc["sections"][0]["body"]
            assert "Fixed D" in doc["sections"][1]["body"]

    def test_two_sections_different_files(self):
        with tempfile.TemporaryDirectory() as td:
            master1 = _build_master(td, "devops", "OPS", [(
                "monitoring", "<!-- section: monitoring -->\n## M\n\nOld.", [],
            )])
            master2 = _build_master(td, "devops", "TROUBLE", [(
                "diagnosis", "<!-- section: diagnosis -->\n## D\n\nOld.", [],
            )])

            edit_path = _build_edit_xml(td, "g1", [
                {
                    "source": master1,
                    "slug": "monitoring",
                    "body": "<!-- section: monitoring -->\n## M\n\nFixed.",
                },
                {
                    "source": master2,
                    "slug": "diagnosis",
                    "body": "<!-- section: diagnosis -->\n## D\n\nFixed.",
                },
            ])

            summary = merge_edit_xml(edit_path)
            assert summary["sections_updated"] == 2
            assert len(summary["files_modified"]) == 2

            doc1 = parse_xml_doc(master1)
            doc2 = parse_xml_doc(master2)
            assert "Fixed" in doc1["sections"][0]["body"]
            assert "Fixed" in doc2["sections"][0]["body"]


class TestErrorHandling:
    """Error handling for missing files and bad slugs."""

    def test_missing_master_file(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "source": "/nonexistent/path.xml",
                "slug": "s1",
                "body": "content",
            }])

            summary = merge_edit_xml(edit_path)
            assert len(summary["errors"]) == 1
            assert "not found" in summary["errors"][0]
            assert summary["sections_updated"] == 0

    def test_missing_slug_in_master(self):
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [(
                "monitoring", "<!-- section: monitoring -->\n## M\n\nContent.", [],
            )])

            edit_path = _build_edit_xml(td, "g1", [{
                "source": master_path,
                "slug": "nonexistent-section",
                "body": "new content",
            }])

            summary = merge_edit_xml(edit_path)
            assert len(summary["errors"]) == 1
            assert "nonexistent-section" in summary["errors"][0]


class TestRoundTrip:
    """Extract + merge with no edits leaves master unchanged."""

    def test_extract_then_merge_no_change(self):
        """Extracting and merging without edits should not modify master."""
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            refs = [{"type": "code", "kind": "function", "name": "start_run"}]
            master_path = _build_master(
                os.path.join(xml_dir, "devops"), "devops", "OPS", [(
                    "monitoring",
                    "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                    refs,
                )],
            )

            # Read original state
            original = parse_xml_doc(master_path)

            # Import extract function
            extract_spec = importlib.util.spec_from_file_location(
                "extract_edit_xml",
                os.path.join(SCRIPTS_DIR, "extract-edit-xml.py"),
            )
            extract_mod = importlib.util.module_from_spec(extract_spec)
            extract_spec.loader.exec_module(extract_mod)

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

            # Extract
            edit_tree = extract_mod.extract_edit_xml(
                grouping, findings, xml_dir, 0,
            )
            edit_path = os.path.join(td, "edit.xml")
            edit_tree.write(
                edit_path, xml_declaration=True,
                encoding="utf-8", pretty_print=True,
            )

            # Merge without editing
            summary = merge_edit_xml(edit_path)
            assert summary["sections_updated"] == 0
            assert summary["files_modified"] == []

            # Master unchanged
            after = parse_xml_doc(master_path)
            assert original["sections"][0]["body"] == after["sections"][0]["body"]
            assert original["sections"][0]["refs"] == after["sections"][0]["refs"]


class TestCLI:
    """CLI invocation tests."""

    def test_basic_run(self):
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nOld.",
                [],
            )])

            edit_path = _build_edit_xml(td, "g1", [{
                "source": master_path,
                "slug": "monitoring",
                "body": "<!-- section: monitoring -->\n## Monitoring\n\nFixed.",
            }])

            result = subprocess.run(
                [sys.executable, SCRIPT, "--edit-file", edit_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            summary = json.loads(result.stdout)
            assert summary["sections_updated"] == 1

    def test_missing_edit_file(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--edit-file", "/nonexistent/edit.xml"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0  # always exits 0
        summary = json.loads(result.stdout)
        assert len(summary["errors"]) == 1
