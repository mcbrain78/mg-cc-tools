"""Shared fixtures for the auto-doc test suite.

Extracted from per-file helpers to eliminate scaffolding duplication.
"""

import json
import os
import subprocess
import sys

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, SCRIPTS_DIR)

from lib.xml_doc import build_xml_doc, serialize_xml_doc, update_section_refs


@pytest.fixture
def tmp_xml_path(tmp_path):
    return str(tmp_path / "doc.xml")


@pytest.fixture
def findings_file(tmp_path):
    path = str(tmp_path / "findings.json")
    with open(path, "w") as f:
        json.dump([], f)
    return path


@pytest.fixture
def input_file_factory(tmp_path):
    counter = [0]

    def _make(payload, name=None):
        if name is None:
            counter[0] += 1
            name = f"input_{counter[0]}.json"
        path = str(tmp_path / name)
        with open(path, "w") as f:
            json.dump(payload, f)
        return path

    return _make


@pytest.fixture
def mock_project(tmp_path):
    """Project with SQLAlchemy models, flows, enums, env, config.

    Returns (project_root, xml_dir, findings_file). xml_dir lives inside project_root.
    """
    project_root = str(tmp_path / "project")
    xml_dir = os.path.join(project_root, ".mg", "docs", "xml-sources")
    os.makedirs(xml_dir)

    src_dir = os.path.join(project_root, "src", "app")
    os.makedirs(src_dir)

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

    with open(os.path.join(src_dir, "compute.py"), "w") as f:
        f.write(
            "def compute_finance_metrics(recompute_stale=False):\n"
            "    pass\n"
        )

    with open(os.path.join(src_dir, "flows.py"), "w") as f:
        f.write(
            "from prefect import flow\n\n"
            "@flow\n"
            "def ingest_quarterly_finance_data():\n"
            "    pass\n"
        )

    with open(os.path.join(src_dir, "enums.py"), "w") as f:
        f.write(
            "from enum import Enum\n\n"
            "class RunStatus(str, Enum):\n"
            "    completed = 'completed'\n"
            "    failed = 'failed'\n"
            "    running = 'running'\n"
        )

    with open(os.path.join(src_dir, "types.py"), "w") as f:
        f.write(
            "from typing import Literal\n\n"
            "DriftSeverity = Literal['critical', 'warning', 'info']\n"
        )

    with open(os.path.join(src_dir, "settings.py"), "w") as f:
        f.write(
            "class Settings:\n"
            "    WORKER_CONCURRENCY: int = 4\n"
            "    DATABASE_URL: str = ''\n"
        )

    config_dir = os.path.join(project_root, "config")
    os.makedirs(config_dir)
    with open(os.path.join(config_dir, "field-mapping.yaml"), "w") as f:
        f.write("mappings:\n  - field: name\n")

    with open(os.path.join(project_root, ".env.example"), "w") as f:
        f.write("DATABASE_URL=postgres://...\nWORKER_CONCURRENCY=4\n")

    findings = str(tmp_path / "findings.json")
    with open(findings, "w") as f:
        json.dump([], f)

    return project_root, xml_dir, findings


@pytest.fixture
def xml_doc_factory():
    """Build XML doc with refs, write to xml_dir, return path.

    sections_with_refs: list of (slug, body, flat_refs_list).
    """
    def _make(xml_dir, audience, doc_name, sections_with_refs):
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

    return _make


@pytest.fixture
def run_script():
    def _run(script_name, *args, **kwargs):
        cmd = [sys.executable, os.path.join(SCRIPTS_DIR, script_name), *args]
        return subprocess.run(cmd, capture_output=True, text=True, **kwargs)

    return _run
