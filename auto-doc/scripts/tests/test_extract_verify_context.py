"""Tests for extract-verify-context.py -- extract verify context from scan data.

Uses subprocess to invoke the script as a CLI tool, matching the
project's test pattern (no direct imports of kebab-case modules).
"""

import json
import os
import subprocess
import sys
import tempfile

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "extract-verify-context.py",
)


def _full_scan_data():
    """Return a realistic scan data dict with many fields."""
    return {
        "root_path": "/home/user/project",
        "scan_timestamp": "2026-03-25T10:00:00Z",
        "source_material_index": {
            "src/main.py": {
                "type": "module",
                "symbols": ["main", "setup", "run"],
                "description": "Main entry point",
            },
            "src/utils.py": {
                "type": "module",
                "symbols": ["helper", "format_output"],
                "description": "Utility functions",
            },
        },
        "gap_analysis": {
            "missing_for_audience": {
                "devops": ["deployment", "monitoring"],
                "end-user": ["getting-started"],
            }
        },
        "project_model": {"name": "test-project", "version": "1.0"},
        "audiences": ["developer", "devops", "end-user"],
        "large_data_blob": "x" * 10000,
    }


class TestExtractVerifyContext:
    """Core extraction behavior."""

    def test_extracts_correct_fields(self):
        """Output contains root_path, documented_sections (list), gap_analysis."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_file = os.path.join(tmp, "docs-scan.json")
            output_file = os.path.join(tmp, "context.json")

            with open(scan_file, "w") as f:
                json.dump(_full_scan_data(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-file", scan_file,
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                context = json.load(f)

            assert context["root_path"] == "/home/user/project"
            # documented_sections is a sorted list of section keys
            assert isinstance(context["documented_sections"], list)
            assert "src/main.py" in context["documented_sections"]
            assert "src/utils.py" in context["documented_sections"]
            assert "missing_for_audience" in context["gap_analysis"]
            assert context["project_model"] == {"name": "test-project", "version": "1.0"}
            # Only 4 keys in output (before --templates-dir adds optional_sections)
            assert set(context.keys()) == {"root_path", "documented_sections", "gap_analysis", "project_model"}

    def test_output_smaller_than_input(self):
        """Output file size is smaller than input file size."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_file = os.path.join(tmp, "docs-scan.json")
            output_file = os.path.join(tmp, "context.json")

            with open(scan_file, "w") as f:
                json.dump(_full_scan_data(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-file", scan_file,
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            input_size = os.path.getsize(scan_file)
            output_size = os.path.getsize(output_file)
            assert output_size < input_size

    def test_missing_optional_fields(self):
        """Scan data without gap_analysis/project_model produces empty dicts."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_file = os.path.join(tmp, "docs-scan.json")
            output_file = os.path.join(tmp, "context.json")

            scan_data = {"root_path": "/home/user/project"}
            with open(scan_file, "w") as f:
                json.dump(scan_data, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-file", scan_file,
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                context = json.load(f)

            assert context["root_path"] == "/home/user/project"
            assert context["documented_sections"] == []
            assert context["gap_analysis"] == {}
            assert context["project_model"] == {}

    def test_missing_scan_file_exits_nonzero(self):
        """Missing scan file exits non-zero with error message."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_file = os.path.join(tmp, "nonexistent.json")
            output_file = os.path.join(tmp, "context.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-file", scan_file,
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0
            assert "not found" in result.stderr


class TestExtractVerifyContextOptionalSections:
    """Optional sections via --templates-dir."""

    def test_optional_sections_included(self):
        """Templates with OPTIONAL markers produce optional_sections in output."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_file = os.path.join(tmp, "docs-scan.json")
            output_file = os.path.join(tmp, "context.json")
            templates_dir = os.path.join(tmp, "templates")
            os.makedirs(templates_dir)

            # Write scan data
            with open(scan_file, "w") as f:
                json.dump({"root_path": "/project"}, f)

            # Write template with OPTIONAL markers
            with open(os.path.join(templates_dir, "OPERATIONS.template.md"), "w") as f:
                f.write(
                    "## Deployment\n"
                    "<!-- PURPOSE: deploy -->\n\n"
                    "## Monitoring\n"
                    "<!-- OPTIONAL -- delete if not applicable -->\n\n"
                    "## Backup\n"
                    "<!-- OPTIONAL -- delete if not applicable -->\n"
                )

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-file", scan_file,
                 "--output", output_file,
                 "--templates-dir", templates_dir],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                context = json.load(f)

            assert "optional_sections" in context
            assert len(context["optional_sections"]) == 2
            slugs = {s.split("/", 1)[1] for s in context["optional_sections"]}
            assert "monitoring" in slugs
            assert "backup" in slugs

    def test_no_templates_dir_omits_field(self):
        """Without --templates-dir, output has no optional_sections key."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_file = os.path.join(tmp, "docs-scan.json")
            output_file = os.path.join(tmp, "context.json")

            with open(scan_file, "w") as f:
                json.dump({"root_path": "/project"}, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--scan-file", scan_file,
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                context = json.load(f)

            assert "optional_sections" not in context
