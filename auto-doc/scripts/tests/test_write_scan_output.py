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


def _make_sections_file(tmp_dir, document, sections):
    """Create a parsed template JSON file for content validation tests."""
    path = os.path.join(tmp_dir, f"template-{document}.json")
    data = {
        "document": document,
        "sections": sections,
        "valid_slugs": [s["slug"] for s in sections],
    }
    with open(path, "w") as f:
        json.dump(data, f)
    return path


class TestWriteScanOutputContentValidation:
    """Content validation against parsed template sections."""

    def test_valid_slugs_pass(self):
        """Entries with slugs matching template sections pass validation."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            sections_file = _make_sections_file(tmp, "ARCHITECTURE", [
                {"heading": "Overview", "slug": "overview", "level": 2,
                 "synthesized_from": None, "boundary": None, "optional": False, "purpose": None},
                {"heading": "Data Model", "slug": "data-model", "level": 2,
                 "synthesized_from": None, "boundary": None, "optional": False, "purpose": None},
            ])

            with open(input_file, "w") as f:
                json.dump(_valid_scan_output(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers",
                 "--sections-file", sections_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

    def test_invalid_slug_rejects(self):
        """Entry with slug not in template sections is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            sections_file = _make_sections_file(tmp, "ARCHITECTURE", [
                {"heading": "Overview", "slug": "overview", "level": 2,
                 "synthesized_from": None, "boundary": None, "optional": False, "purpose": None},
            ])

            scan_output = {
                "source_material_index": {
                    "ARCHITECTURE/overview": {"source_files": ["a.py"]},
                    "ARCHITECTURE/nonexistent-section": {"source_files": ["b.py"]},
                },
                "gap_analysis": {"covered": [], "gaps": []},
            }
            with open(input_file, "w") as f:
                json.dump(scan_output, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers",
                 "--sections-file", sections_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0
            assert "nonexistent-section" in result.stderr

    def test_invented_synthesized_from_rejects(self):
        """Entry with synthesized_from when template has none is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            sections_file = _make_sections_file(tmp, "ARCHITECTURE", [
                {"heading": "Overview", "slug": "overview", "level": 2,
                 "synthesized_from": None, "boundary": None, "optional": False, "purpose": None},
            ])

            scan_output = {
                "source_material_index": {
                    "ARCHITECTURE/overview": {
                        "source_files": [],
                        "synthesized_from": ["project_model.components"],
                    },
                },
                "gap_analysis": {"covered": [], "gaps": []},
            }
            with open(input_file, "w") as f:
                json.dump(scan_output, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers",
                 "--sections-file", sections_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0
            assert "synthesized_from" in result.stderr

    def test_invalid_synthesized_path_rejects(self):
        """Entry with invalid synthesized_from path is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            sections_file = _make_sections_file(tmp, "ARCHITECTURE", [
                {"heading": "Overview", "slug": "overview", "level": 2,
                 "synthesized_from": ["project_model.components"],
                 "boundary": None, "optional": False, "purpose": None},
            ])

            scan_output = {
                "source_material_index": {
                    "ARCHITECTURE/overview": {
                        "source_files": [],
                        "synthesized_from": ["project_model.nonexistent"],
                    },
                },
                "gap_analysis": {"covered": [], "gaps": []},
            }
            with open(input_file, "w") as f:
                json.dump(scan_output, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers",
                 "--sections-file", sections_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0
            assert "invalid synthesized_from path" in result.stderr

    def test_missing_non_optional_section_warns(self):
        """Non-optional section missing from SMI produces warning but passes."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            sections_file = _make_sections_file(tmp, "ARCHITECTURE", [
                {"heading": "Overview", "slug": "overview", "level": 2,
                 "synthesized_from": None, "boundary": None, "optional": False, "purpose": None},
                {"heading": "Components", "slug": "components", "level": 2,
                 "synthesized_from": None, "boundary": None, "optional": False, "purpose": None},
            ])

            scan_output = {
                "source_material_index": {
                    "ARCHITECTURE/overview": {"source_files": ["a.py"]},
                },
                "gap_analysis": {"covered": [], "gaps": []},
            }
            with open(input_file, "w") as f:
                json.dump(scan_output, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers",
                 "--sections-file", sections_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0  # Warning, not rejection
            assert "components" in result.stderr
            assert "missing" in result.stderr

    def test_missing_optional_section_no_warning(self):
        """Optional section missing from SMI does not produce warning."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            sections_file = _make_sections_file(tmp, "ARCHITECTURE", [
                {"heading": "Overview", "slug": "overview", "level": 2,
                 "synthesized_from": None, "boundary": None, "optional": False, "purpose": None},
                {"heading": "Advanced", "slug": "advanced", "level": 2,
                 "synthesized_from": None, "boundary": None, "optional": True, "purpose": None},
            ])

            scan_output = {
                "source_material_index": {
                    "ARCHITECTURE/overview": {"source_files": ["a.py"]},
                },
                "gap_analysis": {"covered": [], "gaps": []},
            }
            with open(input_file, "w") as f:
                json.dump(scan_output, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers",
                 "--sections-file", sections_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "advanced" not in result.stderr.lower()

    def test_no_sections_file_backward_compat(self):
        """Without --sections-file, only structural validation runs."""
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

    def test_unknown_document_entries_pass(self):
        """Entries for documents without a sections file are not validated."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            output_file = os.path.join(tmp, "output.json")

            # Only provide sections for ARCHITECTURE, not OTHER_DOC
            sections_file = _make_sections_file(tmp, "ARCHITECTURE", [
                {"heading": "Overview", "slug": "overview", "level": 2,
                 "synthesized_from": None, "boundary": None, "optional": False, "purpose": None},
            ])

            scan_output = {
                "source_material_index": {
                    "ARCHITECTURE/overview": {"source_files": ["a.py"]},
                    "OTHER_DOC/anything": {"source_files": ["b.py"]},
                },
                "gap_analysis": {"covered": [], "gaps": []},
            }
            with open(input_file, "w") as f:
                json.dump(scan_output, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--output", output_file,
                 "--audience", "developers",
                 "--sections-file", sections_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0


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
