"""Tests for list-optional-sections.py -- parse templates for OPTIONAL markers.

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
    "list-optional-sections.py",
)


class TestListOptionalSections:
    """Core parsing behavior."""

    def test_parses_optional_markers(self):
        """Template with OPTIONAL markers produces correct section keys."""
        with tempfile.TemporaryDirectory() as tmp:
            template = os.path.join(tmp, "OPERATIONS.template.md")
            with open(template, "w") as f:
                f.write(
                    "# Operations\n\n"
                    "## Deployment Pipeline\n"
                    "<!-- PURPOSE: how to deploy -->\n\n"
                    "## Monitoring Setup\n"
                    "<!-- OPTIONAL -- delete if not applicable -->\n\n"
                    "## Backup Plan\n"
                    "<!-- OPTIONAL -- delete if not applicable -->\n"
                )

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--templates-dir", tmp],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            sections = json.loads(result.stdout)
            assert "OPERATIONS/monitoring-setup" in sections
            assert "OPERATIONS/backup-plan" in sections
            # Non-optional section should NOT appear
            assert all("deployment-pipeline" not in s for s in sections)

    def test_non_optional_excluded(self):
        """Template without OPTIONAL markers produces empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            template = os.path.join(tmp, "ARCHITECTURE.template.md")
            with open(template, "w") as f:
                f.write(
                    "# Architecture\n\n"
                    "## System Overview\n"
                    "<!-- PURPOSE: system design overview -->\n\n"
                    "## Data Model\n"
                    "<!-- PURPOSE: data model description -->\n"
                )

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--templates-dir", tmp],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            sections = json.loads(result.stdout)
            assert sections == []

    def test_multiple_templates(self):
        """Multiple templates produce merged results."""
        with tempfile.TemporaryDirectory() as tmp:
            # Template 1
            t1 = os.path.join(tmp, "OPERATIONS.template.md")
            with open(t1, "w") as f:
                f.write(
                    "## Monitoring\n"
                    "<!-- OPTIONAL -- delete if not applicable -->\n"
                )

            # Template 2 in subdirectory
            subdir = os.path.join(tmp, "developers")
            os.makedirs(subdir)
            t2 = os.path.join(subdir, "ARCHITECTURE.template.md")
            with open(t2, "w") as f:
                f.write(
                    "## Security Model\n"
                    "<!-- OPTIONAL -- delete if not applicable -->\n"
                )

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--templates-dir", tmp],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            sections = json.loads(result.stdout)
            assert len(sections) == 2
            doc_names = {s.split("/")[0] for s in sections}
            assert "OPERATIONS" in doc_names
            assert "ARCHITECTURE" in doc_names

    def test_missing_templates_dir_exits_nonzero(self):
        """Non-existent templates dir exits non-zero."""
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH,
             "--templates-dir", "/nonexistent/path"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "not found" in result.stderr

    def test_real_templates(self):
        """Smoke test against the actual project templates."""
        templates_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "references", "templates",
        )
        if not os.path.isdir(templates_dir):
            return  # skip if not in source tree

        result = subprocess.run(
            [sys.executable, SCRIPT_PATH,
             "--templates-dir", templates_dir],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

        sections = json.loads(result.stdout)
        # We know from grep that there are 26+ OPTIONAL markers
        assert len(sections) >= 20
        # Spot-check known optional sections
        slugs = {s.split("/", 1)[1] for s in sections}
        assert "monitoring-alerting" in slugs
