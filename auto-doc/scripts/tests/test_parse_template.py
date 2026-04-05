"""Tests for parse-template.py -- deterministic template pre-parser.

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
    "parse-template.py",
)

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "references",
    "templates",
)


def _run(template_content, document="TEST_DOC", extra_args=None):
    """Write template to temp file, run parse-template.py, return parsed output."""
    with tempfile.TemporaryDirectory() as tmp:
        template_path = os.path.join(tmp, f"{document}.template.md")
        output_path = os.path.join(tmp, "output.json")

        with open(template_path, "w") as f:
            f.write(template_content)

        cmd = [
            sys.executable, SCRIPT_PATH,
            "--template", template_path,
            "--document", document,
            "--output", output_path,
        ]
        if extra_args:
            cmd.extend(extra_args)

        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, f"stderr: {result.stderr}"

        with open(output_path) as f:
            return json.load(f), result.stderr


class TestParseTemplateBasic:
    """Core parsing behavior."""

    def test_extracts_h2_sections(self):
        template = "# Title\n\n## Overview\nSome content.\n\n## Details\nMore.\n"
        data, _ = _run(template)
        assert data["document"] == "TEST_DOC"
        assert len(data["sections"]) == 2
        assert data["sections"][0]["heading"] == "Overview"
        assert data["sections"][0]["slug"] == "overview"
        assert data["sections"][0]["level"] == 2
        assert data["sections"][1]["heading"] == "Details"
        assert data["sections"][1]["slug"] == "details"

    def test_extracts_h3_sections(self):
        template = "# Title\n\n## Parent\nContent.\n\n### Child\nMore.\n"
        data, _ = _run(template)
        assert len(data["sections"]) == 2
        assert data["sections"][1]["level"] == 3
        assert data["sections"][1]["slug"] == "child"

    def test_valid_slugs_list(self):
        template = "# T\n\n## Foo\n\n## Bar Baz\n"
        data, _ = _run(template)
        assert data["valid_slugs"] == ["foo", "bar-baz"]

    def test_slug_with_slash(self):
        """Slash in heading becomes hyphen in slug."""
        template = "# T\n\n## Async/Concurrency Patterns\nContent.\n"
        data, _ = _run(template)
        assert data["sections"][0]["slug"] == "async-concurrency-patterns"

    def test_slug_strips_special_chars(self):
        template = "# T\n\n## What's New?\nContent.\n"
        data, _ = _run(template)
        assert data["sections"][0]["slug"] == "whats-new"


class TestParseTemplateDirectives:
    """Directive extraction (SYNTHESIZED, BOUNDARY, OPTIONAL, PURPOSE)."""

    def test_synthesized_from(self):
        template = (
            "# T\n\n"
            "## Overview\n"
            "<!-- SYNTHESIZED: project_model.components, project_model.user_interfaces -->\n"
            "Content.\n"
        )
        data, _ = _run(template)
        assert data["sections"][0]["synthesized_from"] == [
            "project_model.components",
            "project_model.user_interfaces",
        ]

    def test_no_synthesized_from(self):
        template = "# T\n\n## Overview\nContent.\n"
        data, _ = _run(template)
        assert data["sections"][0]["synthesized_from"] is None

    def test_boundary(self):
        template = (
            "# T\n\n"
            "## Getting Started\n"
            "<!-- BOUNDARY: Infrastructure setup belongs in devops/OPERATIONS.md -->\n"
            "Content.\n"
        )
        data, _ = _run(template)
        assert "Infrastructure setup" in data["sections"][0]["boundary"]

    def test_optional_inline(self):
        template = "# T\n\n## Troubleshooting <!-- OPTIONAL -->\nContent.\n"
        data, _ = _run(template)
        assert data["sections"][0]["optional"] is True
        # Heading text should not include the OPTIONAL comment
        assert data["sections"][0]["heading"] == "Troubleshooting"

    def test_optional_next_line(self):
        template = "# T\n\n## Troubleshooting\n<!-- OPTIONAL -- delete if not applicable -->\nContent.\n"
        data, _ = _run(template)
        assert data["sections"][0]["optional"] is True

    def test_not_optional_by_default(self):
        template = "# T\n\n## Required Section\nContent.\n"
        data, _ = _run(template)
        assert data["sections"][0]["optional"] is False

    def test_purpose_single_line(self):
        template = (
            "# T\n\n"
            "## Overview\n"
            "<!-- PURPOSE: Introduce what this guide covers. -->\n"
            "Content.\n"
        )
        data, _ = _run(template)
        assert data["sections"][0]["purpose"] == "Introduce what this guide covers."

    def test_purpose_multiline(self):
        template = (
            "# T\n\n"
            "## Overview\n"
            "<!-- PURPOSE: Introduce what this guide covers\n"
            "     and what the reader will gain from it. -->\n"
            "Content.\n"
        )
        data, _ = _run(template)
        purpose = data["sections"][0]["purpose"]
        assert "Introduce" in purpose
        assert "reader will gain" in purpose

    def test_no_purpose(self):
        template = "# T\n\n## Overview\nContent.\n"
        data, _ = _run(template)
        assert data["sections"][0]["purpose"] is None


class TestParseTemplateSynthesizedValidation:
    """Validation warnings for invalid synthesized_from paths."""

    def test_invalid_field_warns(self):
        template = (
            "# T\n\n"
            "## Overview\n"
            "<!-- SYNTHESIZED: project_model.nonexistent -->\n"
        )
        _, stderr = _run(template)
        assert "unknown project_model field" in stderr

    def test_invalid_prefix_warns(self):
        template = (
            "# T\n\n"
            "## Overview\n"
            "<!-- SYNTHESIZED: bad_prefix.components -->\n"
        )
        _, stderr = _run(template)
        assert "invalid synthesized_from path" in stderr

    def test_valid_fields_no_warning(self):
        template = (
            "# T\n\n"
            "## Overview\n"
            "<!-- SYNTHESIZED: project_model.components, project_model.tech_stack -->\n"
        )
        _, stderr = _run(template)
        assert "Warning" not in stderr


class TestParseTemplateRealTemplates:
    """Smoke tests against actual project templates."""

    def test_user_guide_template(self):
        template_path = os.path.join(
            TEMPLATES_DIR, "end-users", "USER_GUIDE.template.md"
        )
        if not os.path.isfile(template_path):
            return  # skip if templates not present

        with tempfile.TemporaryDirectory() as tmp:
            output_path = os.path.join(tmp, "output.json")
            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--template", template_path,
                 "--document", "USER_GUIDE",
                 "--output", output_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"stderr: {result.stderr}"

            with open(output_path) as f:
                data = json.load(f)

            # USER_GUIDE has synthesized sections (Overview, Key Concepts, Workflows)
            synth_sections = [s for s in data["sections"] if s["synthesized_from"]]
            assert len(synth_sections) == 3

            # Total sections should include all ## and ### headings
            assert len(data["sections"]) >= 9

    def test_overview_template(self):
        template_path = os.path.join(TEMPLATES_DIR, "OVERVIEW.template.md")
        if not os.path.isfile(template_path):
            return

        with tempfile.TemporaryDirectory() as tmp:
            output_path = os.path.join(tmp, "output.json")
            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--template", template_path,
                 "--document", "OVERVIEW",
                 "--output", output_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_path) as f:
                data = json.load(f)

            # OVERVIEW has no synthesized sections
            synth_sections = [s for s in data["sections"] if s["synthesized_from"]]
            assert len(synth_sections) == 0

    def test_conventions_template_slash_slug(self):
        template_path = os.path.join(
            TEMPLATES_DIR, "agents", "CONVENTIONS.template.md"
        )
        if not os.path.isfile(template_path):
            return

        with tempfile.TemporaryDirectory() as tmp:
            output_path = os.path.join(tmp, "output.json")
            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--template", template_path,
                 "--document", "CONVENTIONS",
                 "--output", output_path],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_path) as f:
                data = json.load(f)

            slugs = data["valid_slugs"]
            assert "async-concurrency-patterns" in slugs
            # Verify no malformed slug like "asyncconcurrency-patterns"
            assert "asyncconcurrency-patterns" not in slugs


class TestParseTemplateCLI:
    """CLI argument validation."""

    def test_missing_template_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--template", os.path.join(tmp, "nonexistent.md"),
                 "--document", "TEST",
                 "--output", os.path.join(tmp, "out.json")],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

    def test_stderr_summary(self):
        template = "# T\n\n## A\n\n## B\n"
        _, stderr = _run(template)
        assert "2 sections" in stderr
