"""Tests for verify-xml-refs.py -- deterministic XML ref verification.

Uses fixture XML files and mock Python source to test each ref type checker.
"""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from lib.xml_doc import build_xml_doc, serialize_xml_doc, update_section_refs

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "verify-xml-refs.py")


def _make_project(td):
    """Create a mock project with Python source files.

    Returns (project_root, xml_dir, findings_file).
    """
    project_root = os.path.join(td, "project")
    xml_dir = os.path.join(project_root, ".mg", "docs", "xml-sources")
    os.makedirs(xml_dir)

    # Create Python source files
    src_dir = os.path.join(project_root, "src", "app")
    os.makedirs(src_dir)

    # SQLAlchemy model
    with open(os.path.join(src_dir, "models.py"), "w") as f:
        f.write(
            "from sqlalchemy import Column, Integer, String\n"
            "from sqlalchemy.orm import DeclarativeBase\n\n"
            "class Base(DeclarativeBase): pass\n\n"
            "class EtlRun(Base):\n"
            "    __tablename__ = 'etl_runs'\n"
            "    __table_args__ = {'schema': 'road_runner'}\n"
            "    id = Column(Integer, primary_key=True)\n"
            "    flow_name = Column(String)\n"
            "    status = Column(String)\n"
        )

    # Functions
    with open(os.path.join(src_dir, "compute.py"), "w") as f:
        f.write(
            "def compute_finance_metrics(recompute_stale=False):\n"
            "    pass\n"
        )

    # Flow-decorated functions
    with open(os.path.join(src_dir, "flows.py"), "w") as f:
        f.write(
            "from prefect import flow\n\n"
            "@flow\n"
            "def ingest_quarterly_finance_data():\n"
            "    pass\n"
        )

    # Enum
    with open(os.path.join(src_dir, "enums.py"), "w") as f:
        f.write(
            "from enum import Enum\n\n"
            "class RunStatus(str, Enum):\n"
            "    completed = 'completed'\n"
            "    failed = 'failed'\n"
            "    running = 'running'\n"
        )

    # Settings
    with open(os.path.join(src_dir, "settings.py"), "w") as f:
        f.write(
            "class Settings:\n"
            "    WORKER_CONCURRENCY: int = 4\n"
            "    DATABASE_URL: str = ''\n"
        )

    # Config file
    config_dir = os.path.join(project_root, "config")
    os.makedirs(config_dir)
    with open(os.path.join(config_dir, "field-mapping.yaml"), "w") as f:
        f.write("mappings:\n  - field: name\n")

    # .env.example
    with open(os.path.join(project_root, ".env.example"), "w") as f:
        f.write("DATABASE_URL=postgres://...\nWORKER_CONCURRENCY=4\n")

    findings_file = os.path.join(td, "findings.json")
    with open(findings_file, "w") as f:
        json.dump([], f)

    return project_root, xml_dir, findings_file


def _build_xml_with_refs(xml_dir, audience, doc_name, sections_with_refs):
    """Build an XML file with populated refs.

    sections_with_refs: list of (slug, body, flat_refs_list)
    """
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


def _run_verify(xml_dir, project_root, findings_file, audience=None):
    cmd = [
        sys.executable, SCRIPT,
        "--xml-dir", xml_dir,
        "--project-root", project_root,
        "--findings-file", findings_file,
    ]
    if audience:
        cmd.extend(["--audience", audience])
    return subprocess.run(cmd, capture_output=True, text=True)


class TestDbRefs:
    """Database ref verification against SQLAlchemy models."""

    def test_valid_table_and_column(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent",
                [{"type": "db", "schema": "road_runner", "table": "etl_runs", "column": "flow_name"}],
            )])

            result = _run_verify(xml_dir, project_root, findings_file)
            assert result.returncode == 0

            findings = json.loads(open(findings_file).read())
            assert len(findings) == 0

    def test_wrong_column(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent",
                [{"type": "db", "schema": "road_runner", "table": "etl_runs", "column": "nonexistent_col"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 1
            assert "nonexistent_col" in findings[0]["description"]

    def test_wrong_table(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent",
                [{"type": "db", "schema": "road_runner", "table": "nonexistent_table"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 1
            assert "nonexistent_table" in findings[0]["description"]


class TestCodeRefs:
    """Code ref verification against AST symbols."""

    def test_valid_function_with_param(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "compute",
                "<!-- section: compute -->\n## Compute\n\nContent",
                [{"type": "code", "kind": "function", "name": "compute_finance_metrics",
                  "module": "src/app/compute.py", "param": "recompute_stale"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 0

    def test_wrong_param(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "compute",
                "<!-- section: compute -->\n## Compute\n\nContent",
                [{"type": "code", "kind": "function", "name": "compute_finance_metrics",
                  "module": "src/app/compute.py", "param": "nonexistent_param"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 1
            assert "nonexistent_param" in findings[0]["description"]

    def test_class_attr(self):
        """Class attr ref verified by scanning (module not on <class> XML element)."""
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "models",
                "<!-- section: models -->\n## Models\n\nContent",
                [{"type": "code", "kind": "class", "name": "EtlRun", "attr": "flow_name"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 0

    def test_wrong_class_attr(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "models",
                "<!-- section: models -->\n## Models\n\nContent",
                [{"type": "code", "kind": "class", "name": "EtlRun", "attr": "bogus_attr"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 1
            assert "bogus_attr" in findings[0]["description"]

    def test_function_without_module_found_by_scan(self):
        """Function ref without module is found by scanning all .py files."""
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "compute",
                "<!-- section: compute -->\n## Compute\n\nContent",
                [{"type": "code", "kind": "function", "name": "compute_finance_metrics"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 0


class TestFlowRefs:
    """Flow ref verification against @flow decorators."""

    def test_valid_flow_hyphenated(self):
        """Flow name with hyphens matches function name with underscores."""
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "flows",
                "<!-- section: flows -->\n## Flows\n\nContent",
                [{"type": "flow", "name": "ingest-quarterly-finance-data"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 0

    def test_missing_flow(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "flows",
                "<!-- section: flows -->\n## Flows\n\nContent",
                [{"type": "flow", "name": "nonexistent-flow"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 1
            assert "nonexistent-flow" in findings[0]["description"]


class TestEnvRefs:
    """Env var verification against Settings classes and .env files."""

    def test_valid_env_from_dotenv(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "config",
                "<!-- section: config -->\n## Config\n\nContent",
                [{"type": "env", "name": "WORKER_CONCURRENCY"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 0

    def test_missing_env(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "config",
                "<!-- section: config -->\n## Config\n\nContent",
                [{"type": "env", "name": "TOTALLY_NONEXISTENT_VAR"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 1
            assert "TOTALLY_NONEXISTENT_VAR" in findings[0]["description"]


class TestConfigRefs:
    """Config file path verification against filesystem."""

    def test_valid_config(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "config",
                "<!-- section: config -->\n## Config\n\nContent",
                [{"type": "config", "path": "config/field-mapping.yaml"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 0

    def test_missing_config(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "config",
                "<!-- section: config -->\n## Config\n\nContent",
                [{"type": "config", "path": "config/nonexistent.yaml"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 1
            assert "nonexistent.yaml" in findings[0]["description"]


class TestEnumRefs:
    """Enum value verification against enum class definitions."""

    def test_valid_enum_value(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "status",
                "<!-- section: status -->\n## Status\n\nContent",
                [{"type": "enum", "class": "RunStatus", "field": "status", "value": "completed"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 0

    def test_wrong_enum_value(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "status",
                "<!-- section: status -->\n## Status\n\nContent",
                [{"type": "enum", "class": "RunStatus", "field": "status", "value": "bogus_value"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 1
            assert "bogus_value" in findings[0]["description"]


class TestMixedRefs:
    """Multiple ref types in one document, multiple findings."""

    def test_mix_of_valid_and_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "overview",
                "<!-- section: overview -->\n## Overview\n\nContent",
                [
                    {"type": "db", "schema": "road_runner", "table": "etl_runs", "column": "flow_name"},  # valid
                    {"type": "db", "schema": "road_runner", "table": "etl_runs", "column": "wrong_col"},  # invalid
                    {"type": "code", "kind": "function", "name": "compute_finance_metrics"},              # valid
                    {"type": "config", "path": "config/nonexistent.yaml"},                                 # invalid
                ],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 2
            descriptions = [f["description"] for f in findings]
            assert any("wrong_col" in d for d in descriptions)
            assert any("nonexistent.yaml" in d for d in descriptions)


class TestEdgeCases:
    """Edge cases: no xml dir, audience filter, empty refs."""

    def test_no_xml_dir_exits_0(self):
        """Missing xml-sources dir exits 0 gracefully."""
        with tempfile.TemporaryDirectory() as td:
            findings_file = os.path.join(td, "findings.json")
            with open(findings_file, "w") as f:
                json.dump([], f)

            result = _run_verify(
                os.path.join(td, "nonexistent"),
                td, findings_file,
            )
            assert result.returncode == 0

    def test_audience_filter(self):
        """Audience filter skips non-matching XML files."""
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            # Create a devops doc with a bad ref
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "bad",
                "<!-- section: bad -->\n## Bad\n\nContent",
                [{"type": "config", "path": "nonexistent.yaml"}],
            )])
            # Filter to end-users — should skip devops
            result = _run_verify(xml_dir, project_root, findings_file, audience="end-users")
            assert result.returncode == 0
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 0

    def test_section_with_no_refs(self):
        """Sections with empty refs produce no findings."""
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "intro",
                "<!-- section: intro -->\n## Intro\n\nPure prose.",
                [],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 0

    def test_findings_appended_to_existing(self):
        """New findings are appended to existing findings file."""
        with tempfile.TemporaryDirectory() as td:
            project_root, xml_dir, findings_file = _make_project(td)
            # Pre-populate with an existing finding
            with open(findings_file, "w") as f:
                json.dump([{"existing": True}], f)

            _build_xml_with_refs(xml_dir, "devops", "OPS", [(
                "bad",
                "<!-- section: bad -->\n## Bad\n\nContent",
                [{"type": "config", "path": "nonexistent.yaml"}],
            )])

            _run_verify(xml_dir, project_root, findings_file)
            findings = json.loads(open(findings_file).read())
            assert len(findings) == 2
            assert findings[0] == {"existing": True}
