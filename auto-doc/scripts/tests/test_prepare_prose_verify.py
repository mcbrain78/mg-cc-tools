"""Tests for prepare-prose-verify.py -- extract per-section prose+refs pairs."""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lib.xml_doc import build_xml_doc, serialize_xml_doc, update_section_refs, walk_sections

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "prepare-prose-verify.py")


def _build_xml(td, sections_with_refs, audience="devops"):
    """Build an XML file with populated refs, return path."""
    sections = [{"slug": s, "body": b} for s, b, _ in sections_with_refs]
    tree = build_xml_doc(audience, "how-to", "# Ops Guide", sections,
                         title="Operations Guide")
    for slug, _, refs in sections_with_refs:
        if refs:
            update_section_refs(tree, slug, refs)
    xml_path = os.path.join(td, "doc.xml")
    serialize_xml_doc(tree, xml_path)
    return xml_path


class TestPrepareProsVerify:
    """prepare-prose-verify.py extracts per-section JSON files."""

    def test_basic_output(self):
        """Creates per-section JSON + manifest."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                (
                    "monitoring",
                    "<!-- section: monitoring -->\n## Monitoring\n\nThe `etl_runs` table tracks executions.",
                    [
                        {"type": "db", "db": "mydb", "schema": "road_runner", "table": "etl_runs", "column": "flow_name"},
                        {"type": "code", "kind": "function", "name": "compute_metrics",
                         "module": "src/compute.py", "param": "stale"},
                    ],
                ),
                (
                    "deployment",
                    "<!-- section: deployment -->\n## Deployment\n\nDeploy via CI.",
                    [],
                ),
            ])
            output_dir = os.path.join(td, "output")

            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, result.stderr

            # Manifest exists
            manifest_path = os.path.join(output_dir, "manifest.json")
            assert os.path.isfile(manifest_path)
            with open(manifest_path) as f:
                manifest = json.load(f)
            assert manifest["sections"] == ["monitoring", "deployment"]
            assert manifest["audience"] == "devops"

            # Per-section files exist
            mon_path = os.path.join(output_dir, "monitoring.json")
            assert os.path.isfile(mon_path)
            with open(mon_path) as f:
                mon = json.load(f)
            assert mon["slug"] == "monitoring"
            assert "etl_runs" in mon["body"]
            assert "[db] road_runner.etl_runs.flow_name" in mon["refs_as_text"]
            assert "[code:function] compute_metrics" in mon["refs_as_text"]

    def test_empty_refs_section(self):
        """Section with no refs gets '(no refs declared)' text."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("intro", "<!-- section: intro -->\n## Intro\n\nPure prose.", []),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "intro.json")) as f:
                data = json.load(f)
            assert data["refs_as_text"] == "(no refs declared)"

    def test_all_ref_types_formatted(self):
        """All 9 ref types produce readable text."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("all-types", "<!-- section: all-types -->\n## All\n\nContent.", [
                    {"type": "db", "db": "mydb", "schema": "rr", "table": "runs", "column": "id"},
                    {"type": "code", "kind": "class", "name": "Run", "attr": "status"},
                    {"type": "flow", "name": "ingest-data"},
                    {"type": "env", "name": "PORT"},
                    {"type": "config", "path": "config.yaml"},
                    {"type": "enum", "class": "Status", "field": "state", "value": "ok"},
                    {"type": "dep", "name": "tenacity"},
                    {"type": "literal", "name": "fmp-api"},
                    {"type": "ext", "name": "pg_dump"},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "all-types.json")) as f:
                data = json.load(f)

            refs = data["refs_as_text"]
            assert "[db] rr.runs.id" in refs
            assert "[code:class] Run" in refs
            assert "[flow] ingest-data" in refs
            assert "[env] PORT" in refs
            assert "[config] config.yaml" in refs
            assert "[enum] Status.state = ok" in refs
            assert "[dep] tenacity" in refs
            assert "[literal] fmp-api" in refs
            assert "[ext] pg_dump" in refs

    def test_missing_xml_exits_1(self):
        result = subprocess.run(
            [sys.executable, SCRIPT,
             "--xml-file", "/nonexistent/doc.xml",
             "--output-dir", "/tmp/out"],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_document_and_audience_in_output(self):
        """Section JSON includes document title and audience."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nText.", []),
            ], audience="end-users")
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            assert data["audience"] == "end-users"
            assert data["document"] == "doc"

    def test_function_with_module(self):
        """Code ref with module formats with 'in module' clause."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("func", "<!-- section: func -->\n## Func\n\nText.", [
                    {"type": "code", "kind": "function", "name": "do_thing",
                     "module": "src/lib/utils.py"},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "func.json")) as f:
                data = json.load(f)
            assert "in src/lib/utils.py" in data["refs_as_text"]


def _build_xml_nested(td, sections_tree, audience="devops"):
    """Build XML with nested sections (children key supported).

    sections_tree: list of dicts with keys:
        slug, body, refs (list of flat ref dicts), children (optional list of same)
    """
    def _strip_refs(sections):
        result = []
        for s in sections:
            d = {"slug": s["slug"], "body": s["body"]}
            if s.get("children"):
                d["children"] = _strip_refs(s["children"])
            result.append(d)
        return result

    sections = _strip_refs(sections_tree)
    tree = build_xml_doc(audience, "how-to", "# Ops Guide", sections,
                         title="Operations Guide")

    for path, sec in walk_sections(sections_tree):
        refs = sec.get("refs", [])
        if refs:
            update_section_refs(tree, path, refs)

    xml_path = os.path.join(td, "doc.xml")
    serialize_xml_doc(tree, xml_path)
    return xml_path


class TestNestedSections:
    """Nested section support for prepare-prose-verify.py."""

    def test_nested_creates_nested_directories(self):
        """Nested sections produce files in nested directories."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml_nested(td, [
                {
                    "slug": "monitoring-alerting",
                    "body": "<!-- section: monitoring-alerting -->\n## Monitoring & Alerting\n\nParent section.",
                    "refs": [],
                    "children": [
                        {
                            "slug": "etl-run-logging",
                            "body": "<!-- section: etl-run-logging -->\n### ETL Run Logging\n\nChild content.",
                            "refs": [{"type": "ext", "name": "systemctl"}],
                        },
                    ],
                },
            ])
            output_dir = os.path.join(td, "output")

            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, result.stderr

            # Nested directory should exist
            nested_file = os.path.join(output_dir, "monitoring-alerting", "etl-run-logging.json")
            assert os.path.isfile(nested_file), f"Expected nested file at {nested_file}"

            # Parent file should be at top level
            parent_file = os.path.join(output_dir, "monitoring-alerting.json")
            assert os.path.isfile(parent_file), f"Expected parent file at {parent_file}"

    def test_nested_section_includes_path_field(self):
        """Section JSON includes 'path' field alongside 'slug'."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml_nested(td, [
                {
                    "slug": "monitoring-alerting",
                    "body": "<!-- section: monitoring-alerting -->\n## Monitoring\n\nParent.",
                    "refs": [],
                    "children": [
                        {
                            "slug": "etl-run-logging",
                            "body": "<!-- section: etl-run-logging -->\n### ETL Logging\n\nChild.",
                            "refs": [],
                        },
                    ],
                },
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            # Child should have path field
            nested_file = os.path.join(output_dir, "monitoring-alerting", "etl-run-logging.json")
            with open(nested_file) as f:
                data = json.load(f)
            assert data["path"] == "monitoring-alerting/etl-run-logging"
            assert data["slug"] == "etl-run-logging"

            # Parent should also have path field
            parent_file = os.path.join(output_dir, "monitoring-alerting.json")
            with open(parent_file) as f:
                data = json.load(f)
            assert data["path"] == "monitoring-alerting"
            assert data["slug"] == "monitoring-alerting"

    def test_manifest_lists_paths(self):
        """Manifest 'sections' lists slash-separated paths, not bare slugs."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml_nested(td, [
                {
                    "slug": "monitoring-alerting",
                    "body": "<!-- section: monitoring-alerting -->\n## Monitoring\n\nParent.",
                    "refs": [],
                    "children": [
                        {
                            "slug": "etl-run-logging",
                            "body": "<!-- section: etl-run-logging -->\n### ETL Logging\n\nChild.",
                            "refs": [],
                        },
                    ],
                },
                {
                    "slug": "deployment",
                    "body": "<!-- section: deployment -->\n## Deployment\n\nDeploy.",
                    "refs": [],
                },
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)
            assert manifest["sections"] == [
                "monitoring-alerting",
                "monitoring-alerting/etl-run-logging",
                "deployment",
            ]

    def test_top_level_backward_compatible(self):
        """Top-level sections still produce flat files (backward compat)."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml_nested(td, [
                {
                    "slug": "monitoring",
                    "body": "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                    "refs": [],
                },
                {
                    "slug": "deployment",
                    "body": "<!-- section: deployment -->\n## Deployment\n\nDeploy.",
                    "refs": [],
                },
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            # Files at top level (no nested dirs)
            assert os.path.isfile(os.path.join(output_dir, "monitoring.json"))
            assert os.path.isfile(os.path.join(output_dir, "deployment.json"))

            manifest_path = os.path.join(output_dir, "manifest.json")
            with open(manifest_path) as f:
                manifest = json.load(f)
            assert manifest["sections"] == ["monitoring", "deployment"]


class TestEmptyRefFields:
    """Defense-in-depth: _format_single_ref returns None for empty required fields."""

    def test_db_empty_schema_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", [
                    {"type": "db", "schema": "", "table": "runs"},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            # Empty schema → ref filtered out → "(no refs declared)"
            assert data["refs_as_text"] == "(no refs declared)"

    def test_db_empty_table_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", [
                    {"type": "db", "schema": "rr", "table": ""},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            assert data["refs_as_text"] == "(no refs declared)"

    def test_code_empty_name_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", [
                    {"type": "code", "kind": "function", "name": ""},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            assert data["refs_as_text"] == "(no refs declared)"

    def test_dep_empty_name_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", [
                    {"type": "dep", "name": ""},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            assert data["refs_as_text"] == "(no refs declared)"

    def test_enum_empty_class_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", [
                    {"type": "enum", "class": "", "field": "f", "value": "v"},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            assert data["refs_as_text"] == "(no refs declared)"

    def test_valid_ref_still_formatted(self):
        """Non-empty refs still produce formatted text (regression check)."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", [
                    {"type": "dep", "name": "tenacity"},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            assert "[dep] tenacity" in data["refs_as_text"]


class TestMalformedRefsField:
    """prepare-prose-verify.py includes malformed_refs field in output."""

    def test_malformed_refs_empty_when_none(self):
        """Normal refs → malformed_refs is empty list."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", [
                    {"type": "dep", "name": "tenacity"},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            assert data["malformed_refs"] == []

    def test_malformed_refs_populated(self):
        """Section with malformed ref → malformed_refs contains the ref."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", [
                    {"type": "malformed", "original_type": "dep", "name": ""},
                    {"type": "dep", "name": "tenacity"},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            assert len(data["malformed_refs"]) == 1
            assert data["malformed_refs"][0]["type"] == "malformed"
            assert data["malformed_refs"][0]["original_type"] == "dep"

    def test_malformed_ref_formatted_with_candidate(self):
        """Malformed ref with non-empty field produces formatted text."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", [
                    {"type": "malformed", "original_type": "dep", "name": "tenacity"},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            assert "[malformed:dep] tenacity" in data["refs_as_text"]


class TestRefEntries:
    """prepare-prose-verify.py includes ref_entries with pre-computed identifiers."""

    def test_ref_entries_present(self):
        """Section JSON includes ref_entries list."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", [
                    {"type": "dep", "name": "tenacity"},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            assert "ref_entries" in data
            assert len(data["ref_entries"]) == 1
            assert data["ref_entries"][0]["display"] == "[dep] tenacity"
            assert data["ref_entries"][0]["identifier"] == "tenacity"

    def test_ref_entries_all_types(self):
        """Each ref type produces correct identifier in ref_entries."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", [
                    {"type": "db", "db": "mydb", "schema": "rr", "table": "runs", "column": "id"},
                    {"type": "code", "kind": "class", "name": "Run", "attr": "status"},
                    {"type": "code", "kind": "function", "name": "compute",
                     "param": "stale"},
                    {"type": "code", "kind": "function", "name": "do_thing"},
                    {"type": "flow", "name": "ingest-data"},
                    {"type": "env", "name": "PORT"},
                    {"type": "config", "path": "config/settings.yaml"},
                    {"type": "enum", "class": "Status", "field": "state", "value": "ok"},
                    {"type": "dep", "name": "tenacity"},
                    {"type": "literal", "name": "fmp-api"},
                    {"type": "ext", "name": "pg_dump"},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)

            entries = {e["identifier"]: e["display"] for e in data["ref_entries"]}
            assert entries["id"] == "[db] rr.runs.id"
            assert entries["status"] == "[code:class] Run (attr: status)"
            assert entries["stale"] == "[code:function] compute (param: stale)"
            assert entries["do_thing"] == "[code:function] do_thing"
            assert entries["ingest-data"] == "[flow] ingest-data"
            assert entries["PORT"] == "[env] PORT"
            assert entries["settings.yaml"] == "[config] config/settings.yaml"
            assert entries["ok"] == "[enum] Status.state = ok"
            assert entries["tenacity"] == "[dep] tenacity"
            assert entries["fmp-api"] == "[literal] fmp-api"
            assert entries["pg_dump"] == "[ext] pg_dump"

    def test_ref_entries_excludes_malformed(self):
        """Malformed refs do not appear in ref_entries."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", [
                    {"type": "malformed", "original_type": "dep", "name": "bad"},
                    {"type": "dep", "name": "good"},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            assert len(data["ref_entries"]) == 1
            assert data["ref_entries"][0]["identifier"] == "good"

    def test_ref_entries_empty_for_no_refs(self):
        """Section with no refs has empty ref_entries list."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", []),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            assert data["ref_entries"] == []

    def test_ref_entries_db_table_only(self):
        """DB ref without column uses table as identifier."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\nContent.", [
                    {"type": "db", "db": "mydb", "schema": "rr", "table": "etl_runs"},
                ]),
            ])
            output_dir = os.path.join(td, "output")

            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)
            # Table-level ref uses table as identifier
            table_entries = [e for e in data["ref_entries"]
                            if e.get("identifier") == "etl_runs"]
            assert len(table_entries) == 1


class TestImplicitNameCoverage:
    """Param/attr-scoped code refs also produce an identifier entry for the name.

    This lets clearing match prose mentions of the function/class name even
    when no bare ref exists. The extra entry has display=None so Check B
    skips it, and no path so the path resolver doesn't double-index.
    """

    def test_param_ref_emits_name_entry(self):
        """Function with param produces two ref_entries: param identifier + name identifier."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\n`compute` takes `stale`.", [
                    {"type": "code", "kind": "function", "name": "compute",
                     "module": "src/m.py", "param": "stale"},
                ]),
            ])
            output_dir = os.path.join(td, "output")
            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)

            entries = data["ref_entries"]
            param_entries = [e for e in entries if e.get("identifier") == "stale"]
            name_entries = [e for e in entries if e.get("identifier") == "compute"]

            assert len(param_entries) == 1
            assert param_entries[0]["display"] == "[code:function] compute in src/m.py (param: stale)"
            assert "path" in param_entries[0]

            assert len(name_entries) == 1
            assert name_entries[0]["display"] is None
            # No path → path resolver does not double-index
            assert "path" not in name_entries[0]

    def test_attr_ref_emits_name_entry(self):
        """Class with attr produces two ref_entries: attr identifier + name identifier."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\n`Run.status`.", [
                    {"type": "code", "kind": "class", "name": "Run", "attr": "status"},
                ]),
            ])
            output_dir = os.path.join(td, "output")
            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)

            entries = data["ref_entries"]
            attr_entries = [e for e in entries if e.get("identifier") == "status"]
            name_entries = [e for e in entries if e.get("identifier") == "Run"]

            assert len(attr_entries) == 1
            assert len(name_entries) == 1
            assert name_entries[0]["display"] is None

    def test_bare_function_no_extra_entry(self):
        """Function without param/attr produces only one ref_entry (no duplication)."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## Sec\n\n`do_thing`.", [
                    {"type": "code", "kind": "function", "name": "do_thing",
                     "module": "src/m.py"},
                ]),
            ])
            output_dir = os.path.join(td, "output")
            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_path, "--output-dir", output_dir],
                capture_output=True, text=True,
            )

            with open(os.path.join(output_dir, "sec.json")) as f:
                data = json.load(f)

            assert len(data["ref_entries"]) == 1
            assert data["ref_entries"][0]["identifier"] == "do_thing"


class TestContentHashIgnoresRefs:
    """content_hash is derived from body only, not body+refs."""

    def test_same_body_different_refs_same_hash(self):
        """Two sections with identical body but different refs produce same hash."""
        body = "<!-- section: sec -->\n## Section\n\nThe `etl_runs` table tracks jobs."

        with tempfile.TemporaryDirectory() as td:
            # Build XML with refs
            xml_with_refs = _build_xml(td, [
                ("sec", body, [
                    {"type": "db", "db": "mydb", "schema": "rr", "table": "etl_runs"},
                ]),
            ])
            out_with = os.path.join(td, "out_with")
            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_with_refs, "--output-dir", out_with],
                capture_output=True, text=True,
            )
            with open(os.path.join(out_with, "sec.json")) as f:
                hash_with_refs = json.load(f)["content_hash"]

            # Build XML without refs (same body)
            xml_no_refs = _build_xml(td, [
                ("sec", body, []),
            ])
            out_without = os.path.join(td, "out_without")
            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_no_refs, "--output-dir", out_without],
                capture_output=True, text=True,
            )
            with open(os.path.join(out_without, "sec.json")) as f:
                hash_no_refs = json.load(f)["content_hash"]

            assert hash_with_refs == hash_no_refs, (
                f"Hash should depend on body only: "
                f"with_refs={hash_with_refs}, no_refs={hash_no_refs}"
            )

    def test_different_body_different_hash(self):
        """Changing the body text produces a different hash (sanity check)."""
        with tempfile.TemporaryDirectory() as td:
            xml_a = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## A\n\nBody A.", []),
            ])
            out_a = os.path.join(td, "out_a")
            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_a, "--output-dir", out_a],
                capture_output=True, text=True,
            )
            with open(os.path.join(out_a, "sec.json")) as f:
                hash_a = json.load(f)["content_hash"]

            xml_b = _build_xml(td, [
                ("sec", "<!-- section: sec -->\n## B\n\nBody B.", []),
            ])
            out_b = os.path.join(td, "out_b")
            subprocess.run(
                [sys.executable, SCRIPT,
                 "--xml-file", xml_b, "--output-dir", out_b],
                capture_output=True, text=True,
            )
            with open(os.path.join(out_b, "sec.json")) as f:
                hash_b = json.load(f)["content_hash"]

            assert hash_a != hash_b
