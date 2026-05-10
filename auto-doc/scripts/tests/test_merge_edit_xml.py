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
    _build_refs_xml,
    build_xml_doc,
    parse_xml_doc,
    serialize_xml_doc,
    update_section_refs,
)
from lxml import etree  # noqa: E402

# Import hyphen-named module via importlib
_spec = importlib.util.spec_from_file_location("merge_edit_xml", SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
merge_edit_xml = _mod.merge_edit_xml


def _canonical_refs_xml(flat_refs):
    """Build canonical <refs> XML string from flat ref dicts."""
    refs_el = etree.Element("refs")
    _build_refs_xml(refs_el, flat_refs)
    return etree.tostring(refs_el, encoding="unicode", pretty_print=True).strip()


def _build_master(td, audience, doc_name, sections_with_refs):
    """Build a master XML file, return its path.

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

    doc_dir = os.path.join(td, audience) if audience != "all" else td
    os.makedirs(doc_dir, exist_ok=True)
    xml_path = os.path.join(doc_dir, f"{doc_name}.xml")
    serialize_xml_doc(tree, xml_path)
    return xml_path


def _build_edit_xml(td, group_id, sections):
    """Build an edit XML file.

    sections: list of dicts with keys: source, slug, audience, document,
              findings (list of {check, description}), refs_xml (str), body (str),
              path (str, optional -- added as attribute when present)
    """
    root = etree.Element("edit-group", id=group_id)
    summary = etree.SubElement(root, "summary")
    summary.text = "Test group"

    for sec in sections:
        attrs = {
            "source": sec["source"],
            "slug": sec["slug"],
            "audience": sec.get("audience", "devops"),
            "document": sec.get("document", "DOC"),
        }
        if "path" in sec:
            attrs["path"] = sec["path"]
        section_el = etree.SubElement(root, "section", **attrs)

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
                [{"type": "db", "db": "mydb", "schema": "wrong", "table": "etl_runs"}],
            )])

            # Edit XML has corrected refs (canonical form)
            refs_xml = _canonical_refs_xml(
                [{"type": "db", "db": "mydb", "schema": "road_runner", "table": "etl_runs"}],
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
            # db + schema + table = 3
            assert len(refs) == 3
            # The table-level ref has the corrected schema
            table_ref = [r for r in refs if r.get("table")][0]
            assert table_ref["schema"] == "road_runner"

    def test_added_ref(self):
        """Adding a new ref to a section with empty refs."""
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                [],
            )])

            refs_xml = _canonical_refs_xml([{
                "type": "code", "kind": "function", "name": "start_run",
                "module": "src/etl/tracking.py",
            }])
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
                [{"type": "db", "db": "mydb", "schema": "wrong", "table": "bad"}],
            )])

            refs_xml = _canonical_refs_xml(
                [{"type": "db", "db": "mydb", "schema": "correct", "table": "good"}],
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
            table_ref = [r for r in doc["sections"][0]["refs"] if r.get("table")][0]
            assert table_ref["table"] == "good"


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
            assert extract_spec is not None and extract_spec.loader is not None
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


class TestNestedMerge:
    """Merge edited sections into nested positions in master XML."""

    def test_merge_reads_path_attribute(self):
        """Merge uses path attribute to locate nested section in master."""
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [(
                "monitoring-alerting",
                "<!-- section: monitoring-alerting -->\n## M\n\nParent.",
                [],
                [(
                    "etl-run-logging",
                    "<!-- section: etl-run-logging -->\n### ETL\n\nOriginal child.",
                    [],
                )],
            )])

            edit_path = _build_edit_xml(td, "g1", [{
                "source": master_path,
                "slug": "etl-run-logging",
                "path": "monitoring-alerting/etl-run-logging",
                "body": "<!-- section: etl-run-logging -->\n### ETL\n\nFixed child.",
            }])

            summary = merge_edit_xml(edit_path)
            assert summary["sections_updated"] == 1
            assert master_path in summary["files_modified"]

            doc = parse_xml_doc(master_path)
            child = doc["sections"][0]["children"][0]
            assert "Fixed child" in child["body"]
            assert "Original" not in child["body"]

    def test_merge_falls_back_to_slug_when_no_path(self):
        """Backward compat: merge works with slug-only (no path attribute)."""
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [(
                "deployment",
                "<!-- section: deployment -->\n## Deployment\n\nOld.",
                [],
            )])

            # No path attribute -- just slug
            edit_path = _build_edit_xml(td, "g1", [{
                "source": master_path,
                "slug": "deployment",
                "body": "<!-- section: deployment -->\n## Deployment\n\nFixed.",
            }])

            summary = merge_edit_xml(edit_path)
            assert summary["sections_updated"] == 1

            doc = parse_xml_doc(master_path)
            assert "Fixed" in doc["sections"][0]["body"]

    def test_update_helpers_called_with_path(self):
        """update_section_body and update_section_refs receive path, not slug."""
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [(
                "monitoring-alerting",
                "<!-- section: monitoring-alerting -->\n## M\n\nParent.",
                [],
                [(
                    "etl-run-logging",
                    "<!-- section: etl-run-logging -->\n### ETL\n\nOriginal.",
                    [{"type": "code", "kind": "function", "name": "old_func"}],
                )],
            )])

            refs_xml = _canonical_refs_xml(
                [{"type": "code", "kind": "function", "name": "new_func"}],
            )
            edit_path = _build_edit_xml(td, "g1", [{
                "source": master_path,
                "slug": "etl-run-logging",
                "path": "monitoring-alerting/etl-run-logging",
                "body": "<!-- section: etl-run-logging -->\n### ETL\n\nUpdated.",
                "refs_xml": refs_xml,
            }])

            summary = merge_edit_xml(edit_path)
            assert summary["sections_updated"] == 1

            doc = parse_xml_doc(master_path)
            child = doc["sections"][0]["children"][0]
            assert "Updated" in child["body"]
            assert child["refs"][0]["name"] == "new_func"

    def test_nested_round_trip_idempotent(self):
        """Extract then merge (unedited) on nested XML is idempotent."""
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            refs = [{"type": "code", "kind": "function", "name": "log_run"}]
            master_path = _build_master(
                os.path.join(xml_dir, "devops"), "devops", "OPS", [(
                    "monitoring-alerting",
                    "<!-- section: monitoring-alerting -->\n## M\n\nParent.",
                    [],
                    [(
                        "etl-run-logging",
                        "<!-- section: etl-run-logging -->\n### ETL\n\nChild content.",
                        refs,
                    )],
                )],
            )

            original = parse_xml_doc(master_path)

            # Extract
            extract_spec = importlib.util.spec_from_file_location(
                "extract_edit_xml",
                os.path.join(SCRIPTS_DIR, "extract-edit-xml.py"),
            )
            assert extract_spec is not None and extract_spec.loader is not None
            extract_mod = importlib.util.module_from_spec(extract_spec)
            extract_spec.loader.exec_module(extract_mod)

            findings = [
                {"document": "OPS",
                 "section": "monitoring-alerting/etl-run-logging",
                 "audience": "devops",
                 "check": "c1", "description": "Issue"},
            ]
            grouping = {
                "groups": [{
                    "group_id": "g1",
                    "root_cause_summary": "test",
                    "finding_indices": [0],
                }],
            }

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
            orig_child = original["sections"][0]["children"][0]
            after_child = after["sections"][0]["children"][0]
            assert orig_child["body"] == after_child["body"]
            assert orig_child["refs"] == after_child["refs"]


class TestTamperDetection:
    """Non-canonical refs are detected and ref changes are skipped."""

    def test_tampered_refs_skipped_body_applied(self):
        """Direct ref edits (non-canonical) are ignored; body edits still merge."""
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nOriginal body.",
                [{"type": "db", "db": "mydb", "schema": "road_runner", "table": "etl_runs"}],
            )])

            # Non-canonical refs: column as attribute (parser ignores this)
            # This simulates an agent using Edit tool to insert malformed XML
            non_canonical_refs = (
                '<refs><db><schema name="road_runner">'
                '<table name="etl_runs" column="status"/>'
                '</schema></db></refs>'
            )
            edit_path = _build_edit_xml(td, "g1", [{
                "source": master_path,
                "slug": "monitoring",
                "body": "<!-- section: monitoring -->\n## Monitoring\n\nFixed body.",
                "refs_xml": non_canonical_refs,
            }])

            merge_edit_xml(edit_path)

            # Body change applied
            doc = parse_xml_doc(master_path)
            assert "Fixed body" in doc["sections"][0]["body"]

            # Refs should be UNCHANGED (tampered refs ignored)
            refs = doc["sections"][0]["refs"]
            # db + schema + table = 3 (original hierarchy)
            assert len(refs) == 3
            table_ref = [r for r in refs if r.get("table")][0]
            assert table_ref["schema"] == "road_runner"
            assert table_ref["table"] == "etl_runs"
            assert "column" not in table_ref  # original had no column

    def test_tampered_refs_warning_on_stderr(self):
        """Non-canonical refs produce a warning on stderr."""
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                [],
            )])

            non_canonical_refs = (
                '<refs><db><schema name="road_runner">'
                '<table name="etl_runs" column="status"/>'
                '</schema></db></refs>'
            )
            edit_path = _build_edit_xml(td, "g1", [{
                "source": master_path,
                "slug": "monitoring",
                "body": "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                "refs_xml": non_canonical_refs,
            }])

            result = subprocess.run(
                [sys.executable, SCRIPT, "--edit-file", edit_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "modified directly" in result.stderr
            assert "monitoring" in result.stderr

    def test_canonical_refs_still_merge(self):
        """Canonical refs (written via script or _build_refs_xml) merge normally."""
        with tempfile.TemporaryDirectory() as td:
            master_path = _build_master(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                [],
            )])

            # Canonical refs built from flat dicts via _build_refs_xml
            from lib.xml_doc import _build_refs_xml  # noqa: E402
            refs_el = etree.Element("refs")
            _build_refs_xml(refs_el, [
                {"type": "code", "kind": "function", "name": "start_run"},
            ])
            canonical_refs = etree.tostring(
                refs_el, encoding="unicode", pretty_print=True,
            )
            # Wrap for _build_edit_xml
            edit_path = _build_edit_xml(td, "g1", [{
                "source": master_path,
                "slug": "monitoring",
                "body": "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                "refs_xml": canonical_refs,
            }])

            summary = merge_edit_xml(edit_path)
            assert summary["sections_updated"] == 1

            doc = parse_xml_doc(master_path)
            refs = doc["sections"][0]["refs"]
            assert len(refs) == 1
            assert refs[0]["name"] == "start_run"
