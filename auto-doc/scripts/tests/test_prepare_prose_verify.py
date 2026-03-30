"""Tests for prepare-prose-verify.py -- extract per-section prose+refs pairs."""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lib.xml_doc import build_xml_doc, serialize_xml_doc, update_section_refs

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
        """All 6 ref types produce readable text."""
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, [
                ("all-types", "<!-- section: all-types -->\n## All\n\nContent.", [
                    {"type": "db", "schema": "rr", "table": "runs", "column": "id"},
                    {"type": "code", "kind": "class", "name": "Run", "attr": "status"},
                    {"type": "flow", "name": "ingest-data"},
                    {"type": "env", "name": "PORT"},
                    {"type": "config", "path": "config.yaml"},
                    {"type": "enum", "class": "Status", "field": "state", "value": "ok"},
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
