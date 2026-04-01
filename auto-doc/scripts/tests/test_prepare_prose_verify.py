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
                        {"type": "db", "schema": "road_runner", "table": "etl_runs", "column": "flow_name"},
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
                    {"type": "db", "schema": "rr", "table": "runs", "column": "id"},
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
