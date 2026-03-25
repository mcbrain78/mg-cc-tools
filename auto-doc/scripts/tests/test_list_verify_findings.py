"""Tests for list-verify-findings.py -- filter and query verify findings.

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
    "list-verify-findings.py",
)


def _sample_findings():
    """Return a list of diverse findings for filter testing."""
    return [
        {
            "document": "OPERATIONS",
            "section": "deployment-pipeline",
            "audience": "devops",
            "severity": "critical",
            "check": "reference-integrity",
            "description": "Broken file reference in deployment section",
            "suggestion": "Update path to current location",
        },
        {
            "document": "OPERATIONS",
            "section": "monitoring-setup",
            "audience": "devops",
            "severity": "high",
            "check": "completeness",
            "description": "Missing monitoring configuration details",
            "suggestion": "Add Prometheus config example",
        },
        {
            "document": "ARCHITECTURE",
            "section": "overview",
            "audience": "developers",
            "severity": "medium",
            "check": "diataxis",
            "description": "Section mixes tutorial and reference styles",
            "suggestion": "Split into separate sections",
        },
        {
            "document": "ARCHITECTURE",
            "section": "data-model",
            "audience": "developers",
            "severity": "low",
            "check": "cross-doc",
            "description": "Redundant explanation also in OPERATIONS",
            "suggestion": "Cross-reference instead of duplicating",
        },
        {
            "document": "GETTING_STARTED",
            "section": "installation",
            "audience": "developers",
            "severity": "info",
            "check": "example-validity",
            "description": "Example uses deprecated flag",
            "suggestion": "Update to current CLI syntax",
        },
    ]


class TestListVerifyFindingsSummary:
    """Summary mode behavior."""

    def test_summary_mode_counts_by_severity_and_document(self):
        """--summary mode produces counts by severity and document with total."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            output_file = os.path.join(tmp, "output.json")

            with open(findings_file, "w") as f:
                json.dump(_sample_findings(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--summary",
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                summary = json.load(f)

            assert summary["total"] == 5
            assert summary["by_severity"]["critical"] == 1
            assert summary["by_severity"]["high"] == 1
            assert summary["by_severity"]["medium"] == 1
            assert summary["by_severity"]["low"] == 1
            assert summary["by_severity"]["info"] == 1
            assert summary["by_document"]["OPERATIONS"] == 2
            assert summary["by_document"]["ARCHITECTURE"] == 2
            assert summary["by_document"]["GETTING_STARTED"] == 1

    def test_missing_findings_file_summary_produces_zero_counts(self):
        """Missing findings file with --summary produces zero-count summary."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "nonexistent.json")
            output_file = os.path.join(tmp, "output.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--summary",
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                summary = json.load(f)

            assert summary["total"] == 0
            assert summary["by_severity"] == {}
            assert summary["by_document"] == {}


class TestListVerifyFindingsFilter:
    """Filtering behavior."""

    def test_filter_by_document(self):
        """--document OPERATIONS filters to only OPERATIONS findings."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            output_file = os.path.join(tmp, "output.json")

            with open(findings_file, "w") as f:
                json.dump(_sample_findings(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--document", "OPERATIONS",
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                data = json.load(f)

            assert len(data) == 2
            assert all(f["document"] == "OPERATIONS" for f in data)

    def test_filter_by_audience(self):
        """--audience devops filters to only devops findings."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            output_file = os.path.join(tmp, "output.json")

            with open(findings_file, "w") as f:
                json.dump(_sample_findings(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--audience", "devops",
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                data = json.load(f)

            assert len(data) == 2
            assert all(f["audience"] == "devops" for f in data)

    def test_filter_combined_document_and_audience(self):
        """--document + --audience combined filter works."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            output_file = os.path.join(tmp, "output.json")

            with open(findings_file, "w") as f:
                json.dump(_sample_findings(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--document", "ARCHITECTURE",
                 "--audience", "developers",
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                data = json.load(f)

            assert len(data) == 2
            assert all(f["document"] == "ARCHITECTURE" for f in data)
            assert all(f["audience"] == "developers" for f in data)

    def test_severity_high_returns_high_and_critical(self):
        """--severity high returns high AND critical (not just high)."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            output_file = os.path.join(tmp, "output.json")

            with open(findings_file, "w") as f:
                json.dump(_sample_findings(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--severity", "high",
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                data = json.load(f)

            severities = {f["severity"] for f in data}
            assert severities == {"critical", "high"}
            assert len(data) == 2

    def test_severity_medium_returns_medium_high_critical(self):
        """--severity medium returns medium, high, and critical."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            output_file = os.path.join(tmp, "output.json")

            with open(findings_file, "w") as f:
                json.dump(_sample_findings(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--severity", "medium",
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                data = json.load(f)

            severities = {f["severity"] for f in data}
            assert severities == {"critical", "high", "medium"}
            assert len(data) == 3

    def test_empty_findings_file_produces_empty_results(self):
        """Empty findings file produces empty results (not error)."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            output_file = os.path.join(tmp, "output.json")

            with open(findings_file, "w") as f:
                json.dump([], f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--document", "OPERATIONS",
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                data = json.load(f)

            assert data == []


class TestListVerifyFindingsClean:
    """--clean mode behavior."""

    def test_clean_removes_all_verify_artifacts(self):
        """--clean removes all verify artifacts that exist."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create the docs dir structure with all verify artifacts
            scan_logs = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_logs)

            artifacts = [
                os.path.join(tmp, "docs-verify-findings.json"),
                os.path.join(tmp, "docs-verify-report.md"),
                os.path.join(scan_logs, "verify-refs-broken.json"),
                os.path.join(scan_logs, "verify-refs-symbols.json"),
                os.path.join(scan_logs, "verify-refs.json"),
                os.path.join(tmp, "docs-verify-findings-mechanical.json"),
                os.path.join(tmp, "docs-verify-findings-editorial.json"),
            ]
            for path in artifacts:
                with open(path, "w") as f:
                    f.write("{}")

            findings_file = os.path.join(tmp, "docs-verify-findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--clean",
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            # All artifacts should be gone
            for path in artifacts:
                assert not os.path.exists(path), f"Expected removed: {path}"

            # Stderr should mention each removed file
            for path in artifacts:
                assert path in result.stderr

    def test_clean_succeeds_when_no_artifacts_exist(self):
        """--clean exits 0 when no verify artifacts exist (no error)."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "docs-verify-findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--clean",
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

    def test_clean_only_removes_verify_artifacts(self):
        """--clean does not remove other files in the directory."""
        with tempfile.TemporaryDirectory() as tmp:
            scan_logs = os.path.join(tmp, "scan-logs")
            os.makedirs(scan_logs)

            # Create a verify artifact
            verify_file = os.path.join(tmp, "docs-verify-findings.json")
            with open(verify_file, "w") as f:
                f.write("[]")

            # Create non-verify files that should be preserved
            other_files = [
                os.path.join(tmp, "docs-scan.json"),
                os.path.join(tmp, ".docs.config.json"),
                os.path.join(scan_logs, "other-scan-log.json"),
            ]
            for path in other_files:
                with open(path, "w") as f:
                    f.write("{}")

            findings_file = os.path.join(tmp, "docs-verify-findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--clean",
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            # Verify artifact should be gone
            assert not os.path.exists(verify_file)

            # Other files should still exist
            for path in other_files:
                assert os.path.exists(path), f"Expected preserved: {path}"


class TestListVerifyFindingsCLI:
    """CLI argument validation."""

    def test_missing_output_arg_fails(self):
        """Missing --output arg exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            with open(findings_file, "w") as f:
                json.dump([], f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--summary"],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

    def test_missing_findings_file_arg_fails(self):
        """Missing --findings-file arg exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            output_file = os.path.join(tmp, "output.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--summary",
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0


class TestListVerifyFindingsInit:
    """--init mode behavior."""

    def test_init_creates_empty_findings_file(self):
        """--init creates file with [], verify contents."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--init",
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)
            assert data == []

    def test_init_overwrites_existing_file(self):
        """--init resets existing file with data to []."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")

            # Seed with existing data
            with open(findings_file, "w") as f:
                json.dump([{"document": "OLD", "severity": "high"}], f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--init",
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)
            assert data == []


class TestListVerifyFindingsMerge:
    """--merge-from behavior."""

    def test_merge_from_combines_two_files(self):
        """Two findings files merged into one with all findings."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            merge_a = os.path.join(tmp, "mechanical.json")
            merge_b = os.path.join(tmp, "editorial.json")
            output_file = os.path.join(tmp, "output.json")

            # Empty main findings file
            with open(findings_file, "w") as f:
                json.dump([], f)

            # Two findings in mechanical
            with open(merge_a, "w") as f:
                json.dump([
                    _sample_findings()[0],
                    _sample_findings()[1],
                ], f)

            # Three findings in editorial
            with open(merge_b, "w") as f:
                json.dump([
                    _sample_findings()[2],
                    _sample_findings()[3],
                    _sample_findings()[4],
                ], f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--merge-from", merge_a,
                 "--merge-from", merge_b,
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                data = json.load(f)
            assert len(data) == 5

    def test_merge_from_skips_missing_file(self):
        """Missing merge-from file is silently skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            merge_a = os.path.join(tmp, "mechanical.json")
            merge_b = os.path.join(tmp, "nonexistent.json")
            output_file = os.path.join(tmp, "output.json")

            with open(findings_file, "w") as f:
                json.dump([], f)

            with open(merge_a, "w") as f:
                json.dump([_sample_findings()[0], _sample_findings()[1]], f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--merge-from", merge_a,
                 "--merge-from", merge_b,
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                data = json.load(f)
            assert len(data) == 2

    def test_merge_from_with_output(self):
        """Merged findings are available to --output."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            merge_a = os.path.join(tmp, "mechanical.json")
            output_file = os.path.join(tmp, "output.json")

            with open(findings_file, "w") as f:
                json.dump([], f)

            with open(merge_a, "w") as f:
                json.dump([_sample_findings()[0]], f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file,
                 "--merge-from", merge_a,
                 "--summary",
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                summary = json.load(f)
            assert summary["total"] == 1
