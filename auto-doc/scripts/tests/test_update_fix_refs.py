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
                '<db name="road_runner_db"><schema name="road_runner">'
                '<table name="data_drift_warnings"/>'
                "</schema></db>"
            )
            result = update_fix_refs(edit_path, "monitoring", add_snippet=snippet)
            assert "Added" in result

            refs = _read_section_refs_flat(edit_path, "monitoring")
            # db-level + schema-level + table-level = 3
            assert len(refs) == 3
            assert refs[0]["type"] == "db"
            assert refs[0]["db"] == "road_runner_db"
            assert refs[2]["table"] == "data_drift_warnings"

    def test_add_db_ref_with_column(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            snippet = (
                '<db name="road_runner_db"><schema name="road_runner">'
                '<table name="etl_runs"><column>status</column></table>'
                "</schema></db>"
            )
            result = update_fix_refs(edit_path, "monitoring", add_snippet=snippet)
            assert "Added" in result

            refs = _read_section_refs_flat(edit_path, "monitoring")
            # db + schema + table + column = 4
            assert len(refs) == 4
            assert refs[3]["column"] == "status"

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
            assert "module" not in refs[0]

    def test_add_code_class_ref_with_module(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            snippet = (
                '<code><class name="Settings" '
                'module="src/road_runner/config.py"/></code>'
            )
            result = update_fix_refs(edit_path, "monitoring", add_snippet=snippet)
            assert "Added 1 ref" in result

            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert refs[0]["kind"] == "class"
            assert refs[0]["name"] == "Settings"
            assert refs[0]["module"] == "src/road_runner/config.py"

    def test_add_code_class_ref_with_module_and_attr(self):
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
            }])

            snippet = (
                '<code><class name="Settings" module="src/config.py">'
                '<attr>fmp_api_key</attr></class></code>'
            )
            result = update_fix_refs(edit_path, "monitoring", add_snippet=snippet)
            assert "Added 1 ref" in result

            refs = _read_section_refs_flat(edit_path, "monitoring")
            assert refs[0]["kind"] == "class"
            assert refs[0]["name"] == "Settings"
            assert refs[0]["module"] == "src/config.py"
            assert refs[0]["attr"] == "fmp_api_key"

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
# Canonical no-op detection
# ---------------------------------------------------------------------------


class TestCanonicalNoOpRejected:
    """Add operations that don't change canonical form must exit non-zero.

    Motivating case: bare `<function name="X" module="M"/>` alongside existing
    `<function name="X" module="M"><param>P</param></function>` — both share
    the same (kind, name, module) key in _build_code_xml, so the bare entry
    is absorbed into the existing element during rebuild and lost.
    """

    def test_bare_function_with_module_collides_with_param_scoped(self, capsys):
        with tempfile.TemporaryDirectory() as td:
            # Pre-populate with a param-scoped function ref
            refs_xml = _canonical_refs_xml([
                {"type": "code", "kind": "function", "name": "X",
                 "module": "src/mod.py", "param": "tickers"},
            ])
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
                "refs_xml": refs_xml,
            }])

            # Try to add a bare function ref with the same (name, module)
            with pytest.raises(SystemExit):
                update_fix_refs(
                    edit_path, "monitoring",
                    add_snippet=(
                        '<code><function name="X" module="src/mod.py"/>'
                        "</code>"
                    ),
                )

            captured = capsys.readouterr()
            assert "no-op" in captured.err.lower()
            assert "typed-refs-format" in captured.err

            # The file on disk should be unchanged — no partial write
            refs_after = _read_section_refs_flat(edit_path, "monitoring")
            assert len(refs_after) == 1
            assert refs_after[0].get("param") == "tickers"

    def test_bare_function_without_module_succeeds_alongside_param_scoped(self):
        """Bare-no-module refs differ in key (name,'') and survive canonicalization."""
        with tempfile.TemporaryDirectory() as td:
            refs_xml = _canonical_refs_xml([
                {"type": "code", "kind": "function", "name": "X",
                 "module": "src/mod.py", "param": "tickers"},
            ])
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
                "refs_xml": refs_xml,
            }])

            result = update_fix_refs(
                edit_path, "monitoring",
                add_snippet='<code><function name="X"/></code>',
            )
            assert "Added 1 ref" in result

            refs_after = _read_section_refs_flat(edit_path, "monitoring")
            assert len(refs_after) == 2

    def test_duplicate_simple_ref_succeeds(self):
        """Adding a duplicate ext ref is NOT a canonical no-op.

        _build_refs_xml does not dedupe simple types (flow/env/dep/literal/ext),
        so the second add produces a second element — the canonical form does
        change, and the no-op guard does not fire.
        """
        with tempfile.TemporaryDirectory() as td:
            refs_xml = _canonical_refs_xml([
                {"type": "ext", "name": "pg_dump"},
            ])
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "content",
                "refs_xml": refs_xml,
            }])

            # Adding the same ext ref produces two <ext>pg_dump</ext> elements
            # (no dedup in _build_refs_xml for simple types), so this actually
            # does change the canonical form — refs_after has 2 entries.
            # Sanity check: confirm this is NOT rejected, to distinguish from
            # the code-ref case above.
            result = update_fix_refs(
                edit_path, "monitoring",
                add_snippet="<ext>pg_dump</ext>",
            )
            assert "Added 1 ref" in result
            refs_after = _read_section_refs_flat(edit_path, "monitoring")
            assert len(refs_after) == 2


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

    def test_parsed_from_disk_refs_pass_tamper_check(self):
        """Canonical refs written to disk, re-parsed, pass tamper check.

        Simulates what extract-edit-xml.py does: copy refs from master XML
        (which was serialized with pretty_print) into an edit XML. The
        re-parsed refs have whitespace text/tail from the original file.
        The tamper check must tolerate this parsed whitespace.
        """
        with tempfile.TemporaryDirectory() as td:
            # Build canonical refs XML and write to a file
            refs_xml = _canonical_refs_xml([
                {"type": "db", "db": "road_runner_db", "schema": "road_runner",
                 "table": "etl_runs", "column": "status"},
                {"type": "code", "kind": "function", "name": "start_run",
                 "module": "src/tracking.py"},
                {"type": "ext", "name": "pg_tables"},
            ])

            # Write an edit XML with these refs, then re-parse from disk
            # (simulating extract → write → read cycle)
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "health-checks",
                "path": "health-checks/service-health-checks",
                "body": "content",
                "refs_xml": refs_xml,
            }])

            # The re-parsed file should pass the tamper check
            result = update_fix_refs(
                edit_path, "health-checks/service-health-checks",
                add_snippet="<ext>pg_indexes</ext>",
            )
            assert "Added 1 ref" in result

            refs = _read_section_refs_flat(
                edit_path, "health-checks/service-health-checks",
            )
            # 4 db (db + schema + table + column) + 1 code + 2 ext = 7
            assert len(refs) == 7


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
                '<db name="road_runner_db"><schema name="road_runner">'
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


# ---------------------------------------------------------------------------
# CDATA preservation (Bug 2)
# ---------------------------------------------------------------------------


class TestCDATAPreservation:
    """Verify that update-fix-refs.py preserves CDATA blocks."""

    def test_cdata_preserved_after_add(self):
        """Adding a ref must not strip CDATA wrapping from <body>."""
        with tempfile.TemporaryDirectory() as td:
            edit_path = _build_edit_xml(td, "g1", [{
                "slug": "monitoring",
                "body": "Some **markdown** with `code`",
            }])

            # Verify CDATA exists before
            with open(edit_path) as f:
                raw_before = f.read()
            assert "CDATA" in raw_before

            update_fix_refs(
                edit_path, "monitoring",
                add_snippet="<ext>pg_dump</ext>",
            )

            # Verify CDATA still present after write-back
            with open(edit_path) as f:
                raw_after = f.read()
            assert "<![CDATA[" in raw_after
