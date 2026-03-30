"""Tests for apply-audit-fixes.py -- apply ref + body fixes to XML."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "apply-audit-fixes.py")
sys.path.insert(0, SCRIPTS_DIR)

from lib.xml_doc import (  # noqa: E402
    build_xml_doc,
    parse_xml_doc,
    serialize_xml_doc,
    update_section_refs,
)

# Import hyphen-named module via importlib
_spec = importlib.util.spec_from_file_location("apply_audit_fixes", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
apply_fixes = _mod.apply_fixes
collect_fixes_by_file = _mod.collect_fixes_by_file


def _build_xml(td, audience, doc_name, sections_with_refs):
    """Build an XML file, return its path."""
    sections = [{"slug": s, "body": b} for s, b, _ in sections_with_refs]
    tree = build_xml_doc(audience, "how-to", f"# {doc_name}", sections)
    for slug, _, refs in sections_with_refs:
        if refs:
            update_section_refs(tree, slug, refs)

    xml_path = os.path.join(td, f"{doc_name}.xml")
    serialize_xml_doc(tree, xml_path)
    return xml_path


class TestCollectFixesByFile:
    """Group section fixes by XML file."""

    def test_groups_by_file(self):
        plan = {
            "fixes": [
                {
                    "group_id": "g1",
                    "section_fixes": [
                        {"xml_file": "/a.xml", "slug": "s1"},
                        {"xml_file": "/b.xml", "slug": "s2"},
                        {"xml_file": "/a.xml", "slug": "s3"},
                    ],
                },
            ],
        }
        by_file = collect_fixes_by_file(plan)
        assert len(by_file) == 2
        assert len(by_file["/a.xml"]) == 2
        assert len(by_file["/b.xml"]) == 1

    def test_empty_plan(self):
        by_file = collect_fixes_by_file({"fixes": []})
        assert by_file == {}


class TestApplyRefFixes:
    """Ref replacement via update_section_refs."""

    def test_replaces_refs(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                [{"type": "db", "schema": "wrong_schema", "table": "etl_runs"}],
            )])

            plan = {
                "fixes": [{
                    "group_id": "g1",
                    "section_fixes": [{
                        "xml_file": xml_path,
                        "slug": "monitoring",
                        "ref_fix": {
                            "action": "replace_all",
                            "refs": [{"type": "db", "schema": "road_runner", "table": "etl_runs"}],
                        },
                    }],
                }],
            }

            summary = apply_fixes(plan)
            assert summary["refs_fixed"] == 1
            assert xml_path in summary["files_modified"]

            # Verify the XML was updated
            doc = parse_xml_doc(xml_path)
            refs = doc["sections"][0]["refs"]
            assert len(refs) == 1
            assert refs[0]["schema"] == "road_runner"
            assert refs[0]["table"] == "etl_runs"


class TestApplyBodyFixes:
    """Body replacement via update_section_body."""

    def test_replaces_body(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nOld content.",
                [],
            )])

            new_body = "<!-- section: monitoring -->\n## Monitoring\n\nCorrected content."
            plan = {
                "fixes": [{
                    "group_id": "g1",
                    "section_fixes": [{
                        "xml_file": xml_path,
                        "slug": "monitoring",
                        "body_fix": {
                            "action": "replace",
                            "body": new_body,
                        },
                    }],
                }],
            }

            summary = apply_fixes(plan)
            assert summary["bodies_fixed"] == 1

            doc = parse_xml_doc(xml_path)
            assert "Corrected content" in doc["sections"][0]["body"]


class TestBothFixTypes:
    """Combined ref + body fixes."""

    def test_both_ref_and_body(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nWrong content.",
                [{"type": "db", "schema": "wrong", "table": "bad_table"}],
            )])

            plan = {
                "fixes": [{
                    "group_id": "g1",
                    "section_fixes": [{
                        "xml_file": xml_path,
                        "slug": "monitoring",
                        "ref_fix": {
                            "action": "replace_all",
                            "refs": [{"type": "db", "schema": "correct", "table": "good_table"}],
                        },
                        "body_fix": {
                            "action": "replace",
                            "body": "<!-- section: monitoring -->\n## Monitoring\n\nCorrect content.",
                        },
                    }],
                }],
            }

            summary = apply_fixes(plan)
            assert summary["refs_fixed"] == 1
            assert summary["bodies_fixed"] == 1
            assert summary["sections_fixed"] == 1

            doc = parse_xml_doc(xml_path)
            assert doc["sections"][0]["refs"][0]["table"] == "good_table"
            assert "Correct content" in doc["sections"][0]["body"]


class TestBatchedWrites:
    """Multiple sections in same XML file are batched."""

    def test_two_sections_one_file(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, "devops", "OPS", [
                ("monitoring", "<!-- section: monitoring -->\n## Monitoring\n\nM.", []),
                ("deployment", "<!-- section: deployment -->\n## Deployment\n\nD.", []),
            ])

            plan = {
                "fixes": [{
                    "group_id": "g1",
                    "section_fixes": [
                        {
                            "xml_file": xml_path,
                            "slug": "monitoring",
                            "body_fix": {"action": "replace", "body": "<!-- section: monitoring -->\n## Monitoring\n\nFixed M."},
                        },
                        {
                            "xml_file": xml_path,
                            "slug": "deployment",
                            "body_fix": {"action": "replace", "body": "<!-- section: deployment -->\n## Deployment\n\nFixed D."},
                        },
                    ],
                }],
            }

            summary = apply_fixes(plan)
            assert summary["sections_fixed"] == 2
            assert len(summary["files_modified"]) == 1

            doc = parse_xml_doc(xml_path)
            assert "Fixed M" in doc["sections"][0]["body"]
            assert "Fixed D" in doc["sections"][1]["body"]


class TestDryRun:
    """Dry run mode doesn't write files."""

    def test_dry_run_no_write(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nOriginal.",
                [],
            )])

            plan = {
                "fixes": [{
                    "group_id": "g1",
                    "section_fixes": [{
                        "xml_file": xml_path,
                        "slug": "monitoring",
                        "body_fix": {"action": "replace", "body": "<!-- section: monitoring -->\n## Monitoring\n\nChanged."},
                    }],
                }],
            }

            summary = apply_fixes(plan, dry_run=True)
            assert summary["bodies_fixed"] == 1
            assert xml_path in summary["files_modified"]

            # File should NOT have been modified
            doc = parse_xml_doc(xml_path)
            assert "Original" in doc["sections"][0]["body"]


class TestErrorHandling:
    """Error handling for missing files and bad slugs."""

    def test_missing_xml_file(self):
        plan = {
            "fixes": [{
                "group_id": "g1",
                "section_fixes": [{
                    "xml_file": "/nonexistent/path.xml",
                    "slug": "s1",
                    "body_fix": {"action": "replace", "body": "new"},
                }],
            }],
        }

        summary = apply_fixes(plan)
        assert len(summary["errors"]) == 1
        assert "not found" in summary["errors"][0]

    def test_missing_slug(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                [],
            )])

            plan = {
                "fixes": [{
                    "group_id": "g1",
                    "section_fixes": [{
                        "xml_file": xml_path,
                        "slug": "nonexistent-section",
                        "body_fix": {"action": "replace", "body": "new"},
                    }],
                }],
            }

            summary = apply_fixes(plan)
            assert len(summary["errors"]) == 1
            assert "nonexistent-section" in summary["errors"][0]


class TestCLI:
    """CLI invocation tests."""

    def test_basic_run(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nContent.",
                [],
            )])

            plan_path = os.path.join(td, "fix-plan.json")
            with open(plan_path, "w") as f:
                json.dump({
                    "fixes": [{
                        "group_id": "g1",
                        "section_fixes": [{
                            "xml_file": xml_path,
                            "slug": "monitoring",
                            "body_fix": {"action": "replace", "body": "<!-- section: monitoring -->\n## Monitoring\n\nFixed."},
                        }],
                    }],
                }, f)

            result = subprocess.run(
                [sys.executable, SCRIPT, "--fix-plan", plan_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            summary = json.loads(result.stdout)
            assert summary["sections_fixed"] == 1

    def test_dry_run_flag(self):
        with tempfile.TemporaryDirectory() as td:
            xml_path = _build_xml(td, "devops", "OPS", [(
                "monitoring",
                "<!-- section: monitoring -->\n## Monitoring\n\nOriginal.",
                [],
            )])

            plan_path = os.path.join(td, "fix-plan.json")
            with open(plan_path, "w") as f:
                json.dump({
                    "fixes": [{
                        "group_id": "g1",
                        "section_fixes": [{
                            "xml_file": xml_path,
                            "slug": "monitoring",
                            "body_fix": {"action": "replace", "body": "<!-- section: monitoring -->\n## Monitoring\n\nChanged."},
                        }],
                    }],
                }, f)

            result = subprocess.run(
                [sys.executable, SCRIPT, "--fix-plan", plan_path, "--dry-run"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "dry-run" in result.stderr.lower()

            # File untouched
            doc = parse_xml_doc(xml_path)
            assert "Original" in doc["sections"][0]["body"]

    def test_missing_plan_file(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--fix-plan", "/nonexistent/plan.json"],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
