"""Tests for update-fix-refs.py -- validated ref add/remove in edit XML."""

import importlib.util
import os
import subprocess
import sys
import tempfile

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "update-fix-refs.py")
sys.path.insert(0, SCRIPTS_DIR)

from lib.xml_doc import _build_refs_xml, _parse_refs  # noqa: E402
from lxml import etree  # noqa: E402

# Import hyphen-named module via importlib
_spec = importlib.util.spec_from_file_location("update_fix_refs", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
update_fix_refs = _mod.update_fix_refs
is_canonical = _mod.is_canonical


def _build_edit_xml(td, group_id, sections):
    """Build an edit XML file for testing.

    sections: list of dicts with keys: source, slug, path (optional),
              refs_xml (str, optional), body (str).
    """
    root = etree.Element("edit-group", id=group_id)
    summary = etree.SubElement(root, "summary")
    summary.text = "Test group"

    for sec in sections:
        attrs = {
            "source": sec.get("source", "/fake/master.xml"),
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


def _canonical_refs_xml(flat_refs):
    """Build canonical refs XML string from flat ref dicts."""
    refs_el = etree.Element("refs")
    _build_refs_xml(refs_el, flat_refs)
    return etree.tostring(refs_el, encoding="unicode", pretty_print=True).strip()


def _read_section_refs_xml(edit_path, section_path):
    """Read the <refs> element as string from an edit file for a section."""
    tree = etree.parse(edit_path)
    for sec in tree.getroot().findall("section"):
        sec_path = sec.get("path") or sec.get("slug", "")
        if sec_path == section_path:
            refs_el = sec.find("refs")
            if refs_el is not None:
                return etree.tostring(
                    refs_el, encoding="unicode", pretty_print=True,
                ).strip()
    return None


def _read_section_refs_flat(edit_path, section_path):
    """Parse refs from an edit file section to flat dicts."""
    tree = etree.parse(edit_path)
    for sec in tree.getroot().findall("section"):
        sec_path = sec.get("path") or sec.get("slug", "")
        if sec_path == section_path:
            return _parse_refs(sec.find("refs"))
    return []


# ---------------------------------------------------------------------------
# Add valid refs -- each type
# ---------------------------------------------------------------------------


class TestAddValidRefs:
    """Adding valid refs of each type succeeds and produces canonical XML."""

    def test_add_db_ref(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            snippet = (
                '<db><schema name="road_runner">'
                '<table name="data_drift_warnings"/>'
                "</schema></db>"
            )
            result = update_fix_refs(edit_path, "monitoring", add_snippet=snippet)
            assert "Added 1 ref" in result

            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert len(refs) == 1
            assert refs[0]["type"] == "db"
            assert refs[0]["schema"] == "road_runner"
            assert refs[0]["table"] == "data_drift_warnings"

    def test_add_db_ref_with_column(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            snippet = (
                '<db><schema name="road_runner">'
                '<table name="etl_runs"><column>status</column></table>'
                "</schema></db>"
            )
            result = update_fix_refs(edit_path, "monitoring", add_snippet=snippet)
            assert "Added 1 ref" in result

            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert refs[0]["column"] == "status"

    def test_add_code_function_ref(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            snippet = (
                '<code><function name="start_run" '
                'module="src/etl/tracking.py"/></code>'
            )
            result = update_fix_refs(edit_path, "monitoring", add_snippet=snippet)
            assert "Added 1 ref" in result

            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert refs[0]["type"] == "code"
            assert refs[0]["kind"] == "function"
            assert refs[0]["name"] == "start_run"
            assert refs[0]["module"] == "src/etl/tracking.py"

    def test_add_code_class_ref(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            snippet = '<code><class name="EtlRun"/></code>'
            result = update_fix_refs(edit_path, "monitoring", add_snippet=snippet)
            assert "Added 1 ref" in result

            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert refs[0]["kind"] == "class"
            assert refs[0]["name"] == "EtlRun"

    def test_add_flow_ref(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            result = update_fix_refs(
                edit_path, "monitoring",
                add_snippet="<flow>ingest-quarterly</flow>",
            )
            assert "Added 1 ref" in result

            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert refs[0] == {"type": "flow", "name": "ingest-quarterly"}

    def test_add_env_ref(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            result = update_fix_refs(
                edit_path, "monitoring",
                add_snippet="<env>WORKER_CONCURRENCY</env>",
            )
            assert "Added 1 ref" in result
            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert refs[0] == {"type": "env", "name": "WORKER_CONCURRENCY"}

    def test_add_config_ref(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            result = update_fix_refs(
                edit_path, "monitoring",
                add_snippet="<config>prefect.yaml</config>",
            )
            assert "Added 1 ref" in result
            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert refs[0] == {"type": "config", "path": "prefect.yaml"}

    def test_add_enum_ref(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            snippet = '<enum class="EtlRun" field="status"><value>completed</value></enum>'
            result = update_fix_refs(
                edit_path, "monitoring", add_snippet=snippet,
            )
            assert "Added 1 ref" in result
            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert refs[0]["type"] == "enum"
            assert refs[0]["class"] == "EtlRun"
            assert refs[0]["value"] == "completed"

    def test_add_dep_ref(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            result = update_fix_refs(
                edit_path, "monitoring",
                add_snippet="<dep>tenacity</dep>",
            )
            assert "Added 1 ref" in result
            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert refs[0] == {"type": "dep", "name": "tenacity"}

    def test_add_literal_ref(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            result = update_fix_refs(
                edit_path, "monitoring",
                add_snippet="<literal>fmp-api</literal>",
            )
            assert "Added 1 ref" in result
            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert refs[0] == {"type": "literal", "name": "fmp-api"}

    def test_add_ext_ref(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            result = update_fix_refs(
                edit_path, "monitoring",
                add_snippet="<ext>pg_dump</ext>",
            )
            assert "Added 1 ref" in result
            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert refs[0] == {"type": "ext", "name": "pg_dump"}


# ---------------------------------------------------------------------------
# Add malformed refs -- errors with hints
# ---------------------------------------------------------------------------


class TestAddMalformed:
    """Adding malformed refs produces errors with scoped format hints."""

    def test_bare_table_no_schema(self):
        """<db><table name="X"/> without schema wrapper → 0 refs → error."""
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            snippet = '<db><table name="etl_runs"/></db>'
            with pytest.raises(SystemExit):
                update_fix_refs(edit_path, "monitoring", add_snippet=snippet)

    def test_schema_only_no_table(self):
        """<db><schema name="X"/> with no tables → 0 refs → error."""
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            snippet = '<db><schema name="road_runner"/></db>'
            with pytest.raises(SystemExit):
                update_fix_refs(edit_path, "monitoring", add_snippet=snippet)

    def test_invalid_xml_syntax(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            with pytest.raises(SystemExit):
                update_fix_refs(
                    edit_path, "monitoring", add_snippet="<broken>",
                )

    def test_code_function_missing_name(self):
        """<code><function/> without name attribute → fails validation."""
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            snippet = "<code><function/></code>"
            with pytest.raises(SystemExit):
                update_fix_refs(edit_path, "monitoring", add_snippet=snippet)


# ---------------------------------------------------------------------------
# Remove refs
# ---------------------------------------------------------------------------


class TestRemoveRef:
    """Removing existing refs succeeds; non-existent fails with listing."""

    def test_remove_existing_ref(self):
        """Remove a config ref that was added canonically."""
        with tempfile.TemporaryDirectory() as td:
            # Start with a canonical config ref
            refs_xml = _canonical_refs_xml(
                [{"type": "config", "path": "prefect.yaml"}],
            )
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "deployment",
                "body": "content",
                "refs_xml": f"<refs>{refs_xml[len('<refs>'):-len('</refs>')]}</refs>"
                if "<refs>" in refs_xml else refs_xml,
            }])
            # The _canonical_refs_xml returns <refs>...</refs>, use it directly
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "deployment",
                "body": "content",
                "refs_xml": refs_xml,
            }])

            result = update_fix_refs(
                edit_path, "deployment",
                remove_snippet="<config>prefect.yaml</config>",
            )
            assert "Removed 1 ref" in result
            refs = _read_section_refs_flat(edit_path, "deployment")
            assert len(refs) == 0

    def test_remove_nonexistent_ref_errors(self):
        """Removing a ref that doesn't exist → error listing current refs."""
        with tempfile.TemporaryDirectory() as td:
            refs_xml = _canonical_refs_xml(
                [{"type": "config", "path": "prefect.yaml"}],
            )
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "deployment",
                "body": "content",
                "refs_xml": refs_xml,
            }])

            with pytest.raises(SystemExit):
                update_fix_refs(
                    edit_path, "deployment",
                    remove_snippet="<config>nonexistent.yaml</config>",
                )

    def test_remove_from_empty_refs(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "deployment",
                "body": "content",
            }])

            with pytest.raises(SystemExit):
                update_fix_refs(
                    edit_path, "deployment",
                    remove_snippet="<ext>pg_dump</ext>",
                )


# ---------------------------------------------------------------------------
# Tamper detection
# ---------------------------------------------------------------------------


class TestTamperDetection:
    """Tamper check rejects refs edited directly (non-canonical form)."""

    def test_tampered_refs_rejected(self):
        """Manually inserting non-canonical XML triggers tamper error."""
        with tempfile.TemporaryDirectory() as td:
            # Non-canonical: column as attribute instead of text child
            non_canonical_refs = (
                '<refs><db><schema name="road_runner">'
                '<table name="etl_runs" column="status"/>'
                "</schema></db></refs>"
            )
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
                "refs_xml": non_canonical_refs,
            }])

            with pytest.raises(SystemExit):
                update_fix_refs(
                    edit_path, "monitoring",
                    add_snippet="<ext>pg_dump</ext>",
                )

    def test_canonical_refs_accepted(self):
        """Refs written via the script (canonical) pass tamper check."""
        with tempfile.TemporaryDirectory() as td:
            # Start empty, add via script (which writes canonical), then add again
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            # First add
            update_fix_refs(
                edit_path, "monitoring",
                add_snippet="<ext>pg_dump</ext>",
            )

            # Second add should succeed (first was canonical)
            result = update_fix_refs(
                edit_path, "monitoring",
                add_snippet="<env>DB_HOST</env>",
            )
            assert "Added 1 ref" in result

            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert len(refs) == 2


# ---------------------------------------------------------------------------
# Canonical round-trip
# ---------------------------------------------------------------------------


class TestCanonicalRoundTrip:
    """Refs added via script survive _parse_refs comparison in merge."""

    def test_add_then_parse_matches(self):
        """After adding via script, _parse_refs on result matches expected."""
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            # Add a db ref with column
            snippet = (
                '<db><schema name="road_runner">'
                '<table name="etl_runs"><column>flow_name</column></table>'
                "</schema></db>"
            )
            update_fix_refs(edit_path, "monitoring", add_snippet=snippet)

            # Parse the written refs
            refs = _read_section_refs_flat(edit_path, "monitoring")

            # Now build canonical XML from those parsed refs and compare
            expected_el = etree.Element("refs")
            _build_refs_xml(expected_el, refs)
            expected_xml = etree.tostring(
                expected_el, encoding="unicode", pretty_print=True,
            ).strip()

            actual_xml = _read_section_refs_xml(edit_path, "monitoring")
            assert actual_xml == expected_xml


# ---------------------------------------------------------------------------
# Section lookup
# ---------------------------------------------------------------------------


class TestSectionLookup:
    """Section lookup uses path attribute, falls back to slug."""

    def test_path_attribute_used(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "etl-run-logging",
                "path": "monitoring-alerting/etl-run-logging",
                "body": "content",
            }])

            result = update_fix_refs(
                edit_path, "monitoring-alerting/etl-run-logging",
                add_snippet="<ext>pg_dump</ext>",
            )
            assert "Added 1 ref" in result

    def test_slug_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "deployment",
                "body": "content",
            }])

            result = update_fix_refs(
                edit_path, "deployment",
                add_snippet="<ext>pg_dump</ext>",
            )
            assert "Added 1 ref" in result

    def test_missing_section_errors(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "deployment",
                "body": "content",
            }])

            with pytest.raises(SystemExit):
                update_fix_refs(
                    edit_path, "nonexistent",
                    add_snippet="<ext>pg_dump</ext>",
                )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    """CLI invocation tests."""

    def test_add_via_cli(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            result = subprocess.run(
                [
                    sys.executable, SCRIPT,
                    "--edit-file", edit_path,
                    "--section", "monitoring",
                    "--add", "<ext>pg_dump</ext>",
                ],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "Added 1 ref" in result.stdout

    def test_remove_via_cli(self):
        with tempfile.TemporaryDirectory() as td:
            refs_xml = _canonical_refs_xml(
                [{"type": "ext", "name": "pg_dump"}],
            )
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
                "refs_xml": refs_xml,
            }])

            result = subprocess.run(
                [
                    sys.executable, SCRIPT,
                    "--edit-file", edit_path,
                    "--section", "monitoring",
                    "--remove", "<ext>pg_dump</ext>",
                ],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "Removed 1 ref" in result.stdout

    def test_malformed_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            result = subprocess.run(
                [
                    sys.executable, SCRIPT,
                    "--edit-file", edit_path,
                    "--section", "monitoring",
                    "--add", '<db><table name="x"/></db>',
                ],
                capture_output=True, text=True,
            )
            assert result.returncode != 0
            assert "0 refs" in result.stderr
