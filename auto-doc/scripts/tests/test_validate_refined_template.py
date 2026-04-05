"""Tests for validate-refined-template.py."""

import json
import os
import subprocess
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import importlib.util

# Load the script as a module (filename has hyphens)
_script_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "validate-refined-template.py"
)
_spec = importlib.util.spec_from_file_location("validate_refined_template", _script_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
validate = _mod.validate

SCRIPT_PATH = _script_path


# -- Valid template fixture ----------------------------------------------------

VALID_TEMPLATE = textwrap.dedent("""\
    <!-- DIATAXIS: how-to -->
    <!-- AUDIENCE: devops -->
    <!-- REFINED: 2026-04-01, scan: 2026-03-30 -->

    # Operations Guide

    ## Deployment
    <purpose>Covers the deployment process for the application</purpose>
    <evidence>uv sync, 2 Alembic chains, 3 systemd services</evidence>

    ### Prerequisites
    <purpose>Lists what must be in place before deploying</purpose>
    <evidence>Python 3.12, PostgreSQL 16, systemd</evidence>
    <example>
    | Dependency | Version | Notes |
    | ... | ... | ... |
    </example>

    ### Service Units
    <purpose>Describes systemd service configuration</purpose>
    <evidence>3 services: web, worker, scheduler</evidence>
    <example>
    - **...**: ...
    </example>

    #### Web Service
    <purpose>Configuration for the web-facing service</purpose>
    <evidence>Gunicorn with 4 workers, port 8000</evidence>

    ## Monitoring
    <purpose>Covers observability and alerting</purpose>
    <evidence>Prometheus metrics, Grafana dashboards</evidence>

    ### Metrics
    <purpose>Application metrics collection</purpose>
    <evidence>15 custom Prometheus counters</evidence>
""")


class TestValidTemplate:
    """A fully valid template should pass with no errors."""

    def test_valid_template_passes(self):
        result = validate(VALID_TEMPLATE)
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["headings"] == 6

    def test_valid_template_no_evidence_warning_on_h2(self):
        """## without <evidence> is a warning, not an error."""
        tmpl = textwrap.dedent("""\
            ## Overview
            <purpose>High-level overview</purpose>

            ### Details
            <purpose>Specific details</purpose>
            <evidence>3 components found</evidence>
        """)
        result = validate(tmpl)
        assert result["valid"] is True
        assert len(result["warnings"]) == 1
        assert "## Overview" in result["warnings"][0]
        assert "recommended" in result["warnings"][0]


class TestMissingPurpose:
    """Missing <purpose> on any heading is an error."""

    def test_missing_purpose_on_h2(self):
        tmpl = textwrap.dedent("""\
            ## Deployment
            <evidence>Some evidence</evidence>

            ### Steps
            <purpose>Deployment steps</purpose>
            <evidence>5 steps total</evidence>
        """)
        result = validate(tmpl)
        assert result["valid"] is False
        assert any("## Deployment" in e and "missing <purpose>" in e for e in result["errors"])

    def test_missing_purpose_on_h3(self):
        tmpl = textwrap.dedent("""\
            ## Deployment
            <purpose>Deployment process</purpose>
            <evidence>uv sync</evidence>

            ### Steps
            <evidence>5 steps total</evidence>
        """)
        result = validate(tmpl)
        assert result["valid"] is False
        assert any("### Steps" in e and "missing <purpose>" in e for e in result["errors"])

    def test_missing_purpose_on_h4(self):
        tmpl = textwrap.dedent("""\
            ## Deployment
            <purpose>Deployment process</purpose>
            <evidence>uv sync</evidence>

            ### Services
            <purpose>Service configuration</purpose>
            <evidence>3 services</evidence>

            #### Web
            <evidence>Port 8000</evidence>
        """)
        result = validate(tmpl)
        assert result["valid"] is False
        assert any("#### Web" in e and "missing <purpose>" in e for e in result["errors"])


class TestMissingEvidence:
    """Missing <evidence> on ### or #### is an error."""

    def test_missing_evidence_on_h3(self):
        tmpl = textwrap.dedent("""\
            ## Deployment
            <purpose>Deployment process</purpose>
            <evidence>uv sync</evidence>

            ### Steps
            <purpose>Deployment steps</purpose>
        """)
        result = validate(tmpl)
        assert result["valid"] is False
        assert any("### Steps" in e and "missing <evidence>" in e for e in result["errors"])

    def test_missing_evidence_on_h4(self):
        tmpl = textwrap.dedent("""\
            ## Deployment
            <purpose>Deployment process</purpose>
            <evidence>uv sync</evidence>

            ### Services
            <purpose>Service units</purpose>
            <evidence>3 services</evidence>

            #### Worker
            <purpose>Background job processor</purpose>
        """)
        result = validate(tmpl)
        assert result["valid"] is False
        assert any("#### Worker" in e and "missing <evidence>" in e for e in result["errors"])

    def test_h2_without_evidence_is_warning_not_error(self):
        tmpl = textwrap.dedent("""\
            ## Overview
            <purpose>High-level overview</purpose>
        """)
        result = validate(tmpl)
        assert result["valid"] is True
        assert len(result["warnings"]) == 1
        assert "## Overview" in result["warnings"][0]


class TestDocsMetaPlaceholder:
    """Generation-time docs-meta comments must not survive into refined templates."""

    def test_docs_meta_placeholder(self):
        tmpl = textwrap.dedent("""\
            <!-- DIATAXIS: reference -->
            <!-- AUDIENCE: agents -->
            <!-- REFINED: 2026-04-01, scan: 2026-03-30 -->
            <!-- docs-meta: last-updated: {date}, sources: [{source_files}] -->

            ## Overview
            <purpose>High-level overview</purpose>
            <evidence>3 components</evidence>
        """)
        result = validate(tmpl)
        assert result["valid"] is False
        assert any("docs-meta placeholder" in e for e in result["errors"])


class TestOptionalMarker:
    """Unresolved OPTIONAL markers are errors."""

    def test_optional_marker_inline(self):
        tmpl = textwrap.dedent("""\
            ## Deployment
            <purpose>Deployment process</purpose>
            <evidence>uv sync</evidence>
            <!-- OPTIONAL -- delete if not applicable -->
        """)
        result = validate(tmpl)
        assert result["valid"] is False
        assert any("OPTIONAL marker" in e for e in result["errors"])

    def test_optional_marker_after_heading(self):
        tmpl = textwrap.dedent("""\
            ## Backup & Recovery
            <!-- OPTIONAL -- delete if not applicable -->
            <purpose>Backup procedures</purpose>
            <evidence>pg_dump scripts</evidence>
        """)
        result = validate(tmpl)
        assert result["valid"] is False
        assert any("OPTIONAL marker" in e for e in result["errors"])


class TestHeadingInsideExample:
    """Heading lines inside <example> blocks are errors."""

    def test_h2_inside_example(self):
        tmpl = textwrap.dedent("""\
            ## Deployment
            <purpose>Deployment process</purpose>
            <evidence>uv sync</evidence>

            ### Steps
            <purpose>Step-by-step guide</purpose>
            <evidence>5 steps</evidence>
            <example>
            ## Wrong Heading Inside Example
            Some content
            </example>
        """)
        result = validate(tmpl)
        assert result["valid"] is False
        assert any("inside <example>" in e for e in result["errors"])

    def test_h3_inside_example(self):
        tmpl = textwrap.dedent("""\
            ## Deployment
            <purpose>Deployment process</purpose>
            <evidence>uv sync</evidence>

            ### Steps
            <purpose>Step-by-step guide</purpose>
            <evidence>5 steps</evidence>
            <example>
            ### Sub-heading in example
            </example>
        """)
        result = validate(tmpl)
        assert result["valid"] is False
        assert any("inside <example>" in e for e in result["errors"])


class TestSanityChecks:
    """Edge cases and sanity checks."""

    def test_no_headings_at_all(self):
        result = validate("Just some text without any headings.")
        assert result["valid"] is False
        assert any("No ## headings" in e for e in result["errors"])
        assert result["headings"] == 0

    def test_heading_in_html_comment_ignored(self):
        """Headings inside HTML comments are not counted as real headings."""
        tmpl = textwrap.dedent("""\
            ## Real Section
            <purpose>This is real</purpose>
            <evidence>Real evidence</evidence>

            <!--
            ## Commented Out Section
            This should not be detected as a heading
            -->
        """)
        result = validate(tmpl)
        assert result["valid"] is True
        assert result["headings"] == 1

    def test_multiple_errors_reported(self):
        tmpl = textwrap.dedent("""\
            ## Section A
            <!-- no purpose, no evidence -->

            ### Child A
            <!-- no purpose, no evidence -->
        """)
        result = validate(tmpl)
        assert result["valid"] is False
        assert len(result["errors"]) >= 3  # missing purpose on h2, missing purpose+evidence on h3


class TestCLI:
    """Test the CLI interface via subprocess."""

    def test_valid_file_exits_zero(self, tmp_path):
        template_file = tmp_path / "VALID.template.md"
        template_file.write_text(VALID_TEMPLATE)
        proc = subprocess.run(
            [sys.executable, SCRIPT_PATH, "--template", str(template_file)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["valid"] is True

    def test_invalid_file_exits_one(self, tmp_path):
        template_file = tmp_path / "BAD.template.md"
        template_file.write_text("## No Tags\nJust text.\n")
        proc = subprocess.run(
            [sys.executable, SCRIPT_PATH, "--template", str(template_file)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 1
        data = json.loads(proc.stdout)
        assert data["valid"] is False

    def test_missing_file_exits_one(self, tmp_path):
        proc = subprocess.run(
            [sys.executable, SCRIPT_PATH, "--template", str(tmp_path / "nonexistent.md")],
            capture_output=True, text=True,
        )
        assert proc.returncode == 1
        data = json.loads(proc.stdout)
        assert data["valid"] is False
        assert any("not found" in e for e in data["errors"])
