"""Tests for write-scan-output.py -- validate and write scan agent output.

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
    "write-scan-output.py",
)


def _valid_scan_output():
    """Return valid scan output with correct key format."""
    return {
        "source_material_index": {
            "ARCHITECTURE/overview": {
                "title": "Architecture Overview",
                "sources": ["src/main.py"],
            },
            "ARCHITECTURE/data-model": {
                "title": "Data Model",
                "sources": ["src/models.py"],
            },
        },
        "gap_analysis": {
            "covered": ["overview", "data-model"],
            "gaps": ["deployment"],
        },
    }


class TestWriteScanOutputBasic:
    """Core write and validation behavior."""

    def test_valid_scan_output_writes_atomically(self):
        """Valid scan output with correct key format writes atomically to --output path."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            with open(input_file, "w") as f:
                json.dump(_valid_scan_output(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                data = json.load(f)

            assert "source_material_index" in data
            assert "gap_analysis" in data
            assert len(data["source_material_index"]) == 2

    def test_extra_fields_preserved_in_output(self):
        """Valid keys with extra fields (e.g., staleness_report) are preserved in output."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            scan_output = _valid_scan_output()
            scan_output["staleness_report"] = {"stale_sections": []}
            scan_output["note_classifications"] = []

            with open(input_file, "w") as f:
                json.dump(scan_output, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(output_file) as f:
                data = json.load(f)

            assert "staleness_report" in data
            assert "note_classifications" in data
            assert data["staleness_report"] == {"stale_sections": []}

    def test_parent_directories_created(self):
        """Parent directories for --output are created if they don't exist."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "nested", "dir", "output.json")

            with open(input_file, "w") as f:
                json.dump(_valid_scan_output(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert os.path.exists(output_file)

    def test_confirmation_message_on_stderr(self):
        """Confirmation message printed to stderr with audience and entry count."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            with open(input_file, "w") as f:
                json.dump(_valid_scan_output(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "developers" in result.stderr
            assert "2" in result.stderr  # 2 source material entries


class TestWriteScanOutputRejection:
    """Invalid input rejection with .rejected files."""

    def test_missing_source_material_index_rejects(self):
        """Missing source_material_index field exits non-zero, saves .rejected file."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            scan_output = {"gap_analysis": {"covered": [], "gaps": []}}
            with open(input_file, "w") as f:
                json.dump(scan_output, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers"],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)
            with open(rejected_path) as f:
                rejected = json.load(f)
            assert "source_material_index" in rejected["reason"]

    def test_missing_gap_analysis_rejects(self):
        """Missing gap_analysis field exits non-zero, saves .rejected file."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            scan_output = {
                "source_material_index": {
                    "ARCHITECTURE/overview": {"title": "Overview"},
                },
            }
            with open(input_file, "w") as f:
                json.dump(scan_output, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers"],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)
            with open(rejected_path) as f:
                rejected = json.load(f)
            assert "gap_analysis" in rejected["reason"]

    def test_invalid_key_format_lowercase_doc_rejects(self):
        """Invalid key format (e.g., 'architecture/overview' lowercase doc name) exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            scan_output = {
                "source_material_index": {
                    "architecture/overview": {"title": "Overview"},
                },
                "gap_analysis": {"covered": [], "gaps": []},
            }
            with open(input_file, "w") as f:
                json.dump(scan_output, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers"],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)

    def test_invalid_key_format_no_section_slug_rejects(self):
        """Invalid key format (e.g., 'ARCHITECTURE' no section slug) exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            scan_output = {
                "source_material_index": {
                    "ARCHITECTURE": {"title": "Overview"},
                },
                "gap_analysis": {"covered": [], "gaps": []},
            }
            with open(input_file, "w") as f:
                json.dump(scan_output, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers"],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)


class TestWriteScanOutputCLI:
    """CLI argument validation."""

    def test_missing_input_arg_fails(self):
        """Missing --input arg exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            output_file = os.path.join(tmp, "output.json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--output", output_file,
                 "--audience", "developers"],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

    def test_missing_output_arg_fails(self):
        """Missing --output arg exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            with open(input_file, "w") as f:
                json.dump(_valid_scan_output(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--audience", "developers"],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

    def test_missing_audience_arg_fails(self):
        """Missing --audience arg exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            with open(input_file, "w") as f:
                json.dump(_valid_scan_output(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0
