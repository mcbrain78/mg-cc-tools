"""Tests for add-verify-finding.py -- validate and append verify findings.

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
    "add-verify-finding.py",
)


def _valid_finding():
    """Return a valid finding dict with all 7 required fields."""
    return {
        "document": "OPERATIONS",
        "section": "deployment-pipeline",
        "audience": "devops",
        "severity": "high",
        "check": "reference-integrity",
        "description": "File path src/deploy/old-pipeline.sh referenced in section does not exist",
        "suggestion": "Update reference to src/deploy/pipeline.sh (renamed in commit abc1234)",
    }


class TestAddVerifyFindingBasic:
    """Core append and validation behavior."""

    def test_valid_finding_appends_to_empty_file(self):
        """Valid finding with all 7 required fields appends to empty findings file, creates file."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            with open(input_file, "w") as f:
                json.dump(_valid_finding(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["document"] == "OPERATIONS"
            assert data[0]["section"] == "deployment-pipeline"
            assert data[0]["check"] == "reference-integrity"

    def test_valid_finding_appends_to_existing_array(self):
        """Valid finding appends to existing findings array (3 entries -> 4 entries)."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            # Seed with 3 existing findings
            existing = [_valid_finding() for _ in range(3)]
            with open(findings_file, "w") as f:
                json.dump(existing, f)

            new_finding = _valid_finding()
            new_finding["document"] = "ARCHITECTURE"
            new_finding["section"] = "overview"
            with open(input_file, "w") as f:
                json.dump(new_finding, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(findings_file) as f:
                data = json.load(f)

            assert len(data) == 4
            assert data[3]["document"] == "ARCHITECTURE"

    def test_confirmation_message_on_stderr(self):
        """Confirmation message printed to stderr with document and check type."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            with open(input_file, "w") as f:
                json.dump(_valid_finding(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "OPERATIONS" in result.stderr
            assert "deployment-pipeline" in result.stderr
            assert "reference-integrity" in result.stderr
            assert "high" in result.stderr


class TestAddVerifyFindingRejection:
    """Invalid input rejection with .rejected files."""

    def test_missing_required_field_rejects(self):
        """Missing required field (e.g., no 'section') exits non-zero, saves .rejected file."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            finding = _valid_finding()
            del finding["section"]
            with open(input_file, "w") as f:
                json.dump(finding, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)
            with open(rejected_path) as f:
                rejected = json.load(f)
            assert "reason" in rejected
            assert "section" in rejected["reason"]

    def test_invalid_severity_rejects(self):
        """Invalid severity value (e.g., 'urgent') exits non-zero, saves .rejected file."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            finding = _valid_finding()
            finding["severity"] = "urgent"
            with open(input_file, "w") as f:
                json.dump(finding, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)
            with open(rejected_path) as f:
                rejected = json.load(f)
            assert "severity" in rejected["reason"].lower()

    def test_invalid_check_rejects(self):
        """Invalid check value (e.g., 'spelling') exits non-zero, saves .rejected file."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            finding = _valid_finding()
            finding["check"] = "spelling"
            with open(input_file, "w") as f:
                json.dump(finding, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)
            with open(rejected_path) as f:
                rejected = json.load(f)
            assert "check" in rejected["reason"].lower()

    def test_invalid_json_in_input_rejects(self):
        """Invalid JSON in --input file exits non-zero, saves .rejected file."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            input_file = os.path.join(tmp, "input.json")

            with open(input_file, "w") as f:
                f.write("{not valid json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)


class TestAddVerifyFindingCLI:
    """CLI argument validation."""

    def test_missing_input_arg_fails(self):
        """Missing --input arg exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            findings_file = os.path.join(tmp, "findings.json")
            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--findings-file", findings_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

    def test_missing_findings_file_arg_fails(self):
        """Missing --findings-file arg exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            with open(input_file, "w") as f:
                json.dump(_valid_finding(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0
