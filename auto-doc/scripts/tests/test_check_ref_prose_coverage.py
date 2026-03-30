"""Tests for check-ref-prose-coverage.py -- deterministic ref-in-prose checking."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "check-ref-prose-coverage.py")
sys.path.insert(0, SCRIPTS_DIR)

from lib.xml_doc import build_xml_doc, serialize_xml_doc, update_section_refs  # noqa: E402

# Import hyphen-named module via importlib
_spec = importlib.util.spec_from_file_location("check_ref_prose_coverage", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
check_section_coverage = _mod.check_section_coverage
check_xml_file = _mod.check_xml_file


def _build_xml(td, sections_with_refs, audience="devops", doc_name="OPS"):
    """Build an XML file with populated refs, return path."""
    sections = [{"slug": s, "body": b} for s, b, _ in sections_with_refs]
    tree = build_xml_doc(audience, "how-to", f"# {doc_name}", sections,
                         title=f"{doc_name} Guide")
    for slug, _, refs in sections_with_refs:
        if refs:
            update_section_refs(tree, slug, refs)
    xml_path = os.path.join(td, f"{doc_name}.xml")
    serialize_xml_doc(tree, xml_path)
    return xml_path


class TestCheckSectionCoverage:
    """Unit tests for the check_section_coverage function."""

    def test_ref_mentioned_in_body_no_finding(self):
        section = {
            "slug": "monitoring",
            "body": "The `etl_runs` table tracks pipeline executions.",
            "refs": [{"type": "db", "schema": "road_runner", "table": "etl_runs"}],
        }
        findings = check_section_coverage(section, "OPS", "devops", 3)
        assert len(findings) == 0

    def test_ref_not_mentioned_produces_finding(self):
        section = {
            "slug": "monitoring",
            "body": "This section describes the monitoring setup.",
            "refs": [{"type": "code", "kind": "function", "name": "start_run"}],
        }
        findings = check_section_coverage(section, "OPS", "devops", 3)
        assert len(findings) == 1
        assert findings[0]["check"] == "reference-integrity"
        assert "start_run" in findings[0]["description"]

    def test_short_names_skipped(self):
        """Ref names shorter than min_name_length are skipped."""
        section = {
            "slug": "overview",
            "body": "The system has an internal ID field.",
            "refs": [{"type": "db", "schema": "s", "table": "t", "column": "id"}],
        }
        # "id" is 2 chars, below min_name_length=3
        findings = check_section_coverage(section, "OPS", "devops", 3)
        # Should not flag "id" (too short) but "t" is also short
        assert all("column `id`" not in f["description"] for f in findings)

    def test_multiple_refs_mixed(self):
        """Some refs mentioned, some not."""
        section = {
            "slug": "config",
            "body": "Set FMP_API_KEY in your .env file.",
            "refs": [
                {"type": "env", "name": "FMP_API_KEY"},
                {"type": "env", "name": "FINRA_API_KEY"},
            ],
        }
        findings = check_section_coverage(section, "OPS", "devops", 3)
        assert len(findings) == 1
        assert "FINRA_API_KEY" in findings[0]["description"]

    def test_no_refs_no_findings(self):
        section = {
            "slug": "intro",
            "body": "Pure prose section.",
            "refs": [],
        }
        findings = check_section_coverage(section, "OPS", "devops", 3)
        assert len(findings) == 0

    def test_empty_body_no_findings(self):
        section = {
            "slug": "empty",
            "body": "",
            "refs": [{"type": "code", "kind": "function", "name": "something"}],
        }
        findings = check_section_coverage(section, "OPS", "devops", 3)
        assert len(findings) == 0

    def test_config_ref_matches_basename(self):
        """Config ref matches if basename appears in body."""
        section = {
            "slug": "config",
            "body": "Edit field-mapping.yaml to configure field mappings.",
            "refs": [{"type": "config", "path": "config/field-mapping.yaml"}],
        }
        findings = check_section_coverage(section, "OPS", "devops", 3)
        assert len(findings) == 0

    def test_config_ref_matches_full_path(self):
        """Config ref matches if full path appears in body."""
        section = {
            "slug": "config",
            "body": "The file at config/field-mapping.yaml controls mappings.",
            "refs": [{"type": "config", "path": "config/field-mapping.yaml"}],
        }
        findings = check_section_coverage(section, "OPS", "devops", 3)
        assert len(findings) == 0

    def test_enum_ref_checks_class_name(self):
        section = {
            "slug": "types",
            "body": "The Status enum defines allowed states.",
            "refs": [{"type": "enum", "class": "Status", "field": "state", "value": "ok"}],
        }
        findings = check_section_coverage(section, "OPS", "devops", 3)
        assert len(findings) == 0

    def test_flow_ref_not_mentioned(self):
        section = {
            "slug": "flows",
            "body": "The pipeline runs on a schedule.",
            "refs": [{"type": "flow", "name": "ingest-data"}],
        }
        findings = check_section_coverage(section, "OPS", "devops", 3)
        assert len(findings) == 1
        assert "ingest-data" in findings[0]["description"]

    def test_db_table_mentioned_column_not(self):
        """Table name present but column name absent — only column flagged."""
        section = {
            "slug": "data",
            "body": "Query the etl_runs table for run history.",
            "refs": [
                {"type": "db", "schema": "rr", "table": "etl_runs",
                 "column": "tickers_count"},
            ],
        }
        findings = check_section_coverage(section, "OPS", "devops", 3)
        # etl_runs is mentioned, tickers_count is not
        assert len(findings) == 1
        assert "tickers_count" in findings[0]["description"]

    def test_duplicate_table_from_multiple_columns(self):
        """Same table from multiple column refs should only check once."""
        section = {
            "slug": "data",
            "body": "This section covers the data model.",
            "refs": [
                {"type": "db", "schema": "rr", "table": "etl_runs", "column": "col_a"},
                {"type": "db", "schema": "rr", "table": "etl_runs", "column": "col_b"},
            ],
        }
        findings = check_section_coverage(section, "OPS", "devops", 3)
        # etl_runs should be flagged once, col_a and col_b once each = 3
        table_findings = [f for f in findings if "etl_runs" in f["description"]]
        assert len(table_findings) == 1


class TestCheckXmlFile:
    """Integration tests using actual XML files."""

    def test_finds_uncovered_ref(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                (
                    "monitoring",
                    "<!-- section: monitoring -->\n## Monitoring\n\nThe system is monitored.",
                    [{"type": "code", "kind": "function", "name": "check_health"}],
                ),
            ])

            findings = check_xml_file(xml_path, 3)
            assert len(findings) == 1
            assert findings[0]["document"] == "OPS"
            assert findings[0]["section"] == "monitoring"
            assert "check_health" in findings[0]["description"]

    def test_all_refs_covered(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                (
                    "monitoring",
                    "<!-- section: monitoring -->\n## Monitoring\n\nCall check_health to verify.",
                    [{"type": "code", "kind": "function", "name": "check_health"}],
                ),
            ])

            findings = check_xml_file(xml_path, 3)
            assert len(findings) == 0


class TestCLI:
    """CLI invocation tests."""

    def test_basic_run(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources", "devops")
            os.makedirs(xml_dir)

            _build_xml(xml_dir, [
                (
                    "monitoring",
                    "<!-- section: monitoring -->\n## Monitoring\n\nSystem is monitored.",
                    [{"type": "code", "kind": "function", "name": "check_health"}],
                ),
            ], doc_name="OPS")

            findings_file = os.path.join(td, "findings.json")
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-dir", os.path.join(td, "xml-sources"),
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                findings = json.load(f)
            assert len(findings) == 1
            assert findings[0]["check"] == "reference-integrity"

    def test_appends_to_existing(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources", "devops")
            os.makedirs(xml_dir)

            _build_xml(xml_dir, [
                (
                    "sec",
                    "<!-- section: sec -->\n## Sec\n\nText.",
                    [{"type": "env", "name": "MISSING_VAR"}],
                ),
            ], doc_name="OPS")

            findings_file = os.path.join(td, "findings.json")
            # Pre-existing finding
            with open(findings_file, "w") as f:
                json.dump([{"check": "xml-ref-integrity", "description": "existing"}], f)

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-dir", os.path.join(td, "xml-sources"),
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )

            with open(findings_file) as f:
                findings = json.load(f)
            # 1 existing + 1 new
            assert len(findings) == 2

    def test_audience_filter(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            devops_dir = os.path.join(xml_dir, "devops")
            users_dir = os.path.join(xml_dir, "end-users")
            os.makedirs(devops_dir)
            os.makedirs(users_dir)

            _build_xml(devops_dir, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nText.",
                 [{"type": "env", "name": "DEVOPS_VAR"}]),
            ], audience="devops", doc_name="OPS")

            _build_xml(users_dir, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nText.",
                 [{"type": "env", "name": "USER_VAR"}]),
            ], audience="end-users", doc_name="GUIDE")

            findings_file = os.path.join(td, "findings.json")
            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-dir", xml_dir,
                 "--findings-file", findings_file,
                 "--audience", "devops"],
                capture_output=True, text=True,
            )

            with open(findings_file) as f:
                findings = json.load(f)
            # Only devops findings
            assert all(f["audience"] == "devops" for f in findings)

    def test_empty_xml_dir(self):
        with tempfile.TemporaryDirectory() as td:
            xml_dir = os.path.join(td, "xml-sources")
            os.makedirs(xml_dir)

            findings_file = os.path.join(td, "findings.json")
            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-dir", xml_dir,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
