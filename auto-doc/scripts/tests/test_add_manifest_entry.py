"""Tests for add-manifest-entry.py -- validate and upsert manifest entries.

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
    "add-manifest-entry.py",
)


def _valid_entry():
    """Return a valid manifest entry dict with symbols and file_paths."""
    return {
        "document": "ARCHITECTURE",
        "section": "overview",
        "symbols": ["load_json", "save_json"],
        "file_paths": ["scripts/lib/json_io.py"],
    }


class TestAddManifestEntryBasic:
    """Core upsert and creation behavior."""

    def test_valid_entry_upserts_into_empty_manifest(self):
        """Valid entry with both symbols and file_paths upserts into empty manifest, creates file."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest_file = os.path.join(tmp, "manifest.json")
            input_file = os.path.join(tmp, "input.json")

            with open(input_file, "w") as f:
                json.dump(_valid_entry(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--manifest", manifest_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(manifest_file) as f:
                data = json.load(f)

            assert "documents" in data
            assert "ARCHITECTURE" in data["documents"]
            assert "overview" in data["documents"]["ARCHITECTURE"]
            section = data["documents"]["ARCHITECTURE"]["overview"]
            assert section["symbols"] == ["load_json", "save_json"]
            assert section["file_paths"] == ["scripts/lib/json_io.py"]

    def test_valid_entry_upserts_into_existing_manifest(self):
        """Valid entry upserts into existing manifest, preserving other entries."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest_file = os.path.join(tmp, "manifest.json")
            input_file = os.path.join(tmp, "input.json")

            # Seed with existing manifest
            existing = {
                "audience": "developers",
                "generated": "2026-03-22T00:00:00Z",
                "documents": {
                    "ARCHITECTURE": {
                        "data-model": {
                            "symbols": ["User", "Session"],
                            "file_paths": ["src/models.py"],
                        }
                    }
                },
            }
            with open(manifest_file, "w") as f:
                json.dump(existing, f)

            entry = _valid_entry()
            with open(input_file, "w") as f:
                json.dump(entry, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--manifest", manifest_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(manifest_file) as f:
                data = json.load(f)

            # Old entry preserved
            assert "data-model" in data["documents"]["ARCHITECTURE"]
            assert data["documents"]["ARCHITECTURE"]["data-model"]["symbols"] == ["User", "Session"]
            # New entry added
            assert "overview" in data["documents"]["ARCHITECTURE"]
            assert data["documents"]["ARCHITECTURE"]["overview"]["symbols"] == ["load_json", "save_json"]

    def test_entry_with_symbols_only_accepted(self):
        """Entry with symbols only (no file_paths) is accepted."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest_file = os.path.join(tmp, "manifest.json")
            input_file = os.path.join(tmp, "input.json")

            entry = {
                "document": "API_REFERENCE",
                "section": "endpoints",
                "symbols": ["get_user", "create_session"],
                "file_paths": [],
            }
            with open(input_file, "w") as f:
                json.dump(entry, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--manifest", manifest_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(manifest_file) as f:
                data = json.load(f)

            section = data["documents"]["API_REFERENCE"]["endpoints"]
            assert section["symbols"] == ["get_user", "create_session"]
            assert section["file_paths"] == []

    def test_entry_with_file_paths_only_accepted(self):
        """Entry with file_paths only (no symbols) is accepted."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest_file = os.path.join(tmp, "manifest.json")
            input_file = os.path.join(tmp, "input.json")

            entry = {
                "document": "OPERATIONS",
                "section": "deployment",
                "symbols": [],
                "file_paths": ["deploy/Dockerfile", "deploy/compose.yaml"],
            }
            with open(input_file, "w") as f:
                json.dump(entry, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--manifest", manifest_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(manifest_file) as f:
                data = json.load(f)

            section = data["documents"]["OPERATIONS"]["deployment"]
            assert section["symbols"] == []
            assert section["file_paths"] == ["deploy/Dockerfile", "deploy/compose.yaml"]

    def test_manifest_preserves_audience_and_generated(self):
        """Manifest preserves 'audience' and 'generated' top-level fields."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest_file = os.path.join(tmp, "manifest.json")
            input_file = os.path.join(tmp, "input.json")

            existing = {
                "audience": "devops",
                "generated": "2026-03-22T12:00:00Z",
                "documents": {},
            }
            with open(manifest_file, "w") as f:
                json.dump(existing, f)

            with open(input_file, "w") as f:
                json.dump(_valid_entry(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--manifest", manifest_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(manifest_file) as f:
                data = json.load(f)

            assert data["audience"] == "devops"
            assert data["generated"] == "2026-03-22T12:00:00Z"

    def test_confirmation_message_on_stderr(self):
        """Confirmation message printed to stderr with document and section."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest_file = os.path.join(tmp, "manifest.json")
            input_file = os.path.join(tmp, "input.json")

            with open(input_file, "w") as f:
                json.dump(_valid_entry(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--manifest", manifest_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "ARCHITECTURE" in result.stderr
            assert "overview" in result.stderr


class TestAddManifestEntryUpsert:
    """Upsert replaces existing (document, section) entry."""

    def test_upsert_replaces_existing_entry(self):
        """Upsert replaces existing (document, section) entry, not duplicates."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest_file = os.path.join(tmp, "manifest.json")
            input_file = os.path.join(tmp, "input.json")

            # Seed with existing entry for same (document, section)
            existing = {
                "documents": {
                    "ARCHITECTURE": {
                        "overview": {
                            "symbols": ["old_func"],
                            "file_paths": ["old/path.py"],
                        }
                    }
                },
            }
            with open(manifest_file, "w") as f:
                json.dump(existing, f)

            entry = _valid_entry()  # Same document=ARCHITECTURE, section=overview
            with open(input_file, "w") as f:
                json.dump(entry, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--manifest", manifest_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(manifest_file) as f:
                data = json.load(f)

            section = data["documents"]["ARCHITECTURE"]["overview"]
            # Should be replaced, not merged
            assert section["symbols"] == ["load_json", "save_json"]
            assert section["file_paths"] == ["scripts/lib/json_io.py"]


class TestAddManifestEntryRejection:
    """Invalid input rejection with .rejected files."""

    def test_both_empty_symbols_and_file_paths_rejected(self):
        """Entry with neither symbols nor file_paths is rejected (both empty)."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest_file = os.path.join(tmp, "manifest.json")
            input_file = os.path.join(tmp, "input.json")

            entry = {
                "document": "ARCHITECTURE",
                "section": "overview",
                "symbols": [],
                "file_paths": [],
            }
            with open(input_file, "w") as f:
                json.dump(entry, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--manifest", manifest_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)

    def test_missing_required_field_rejected(self):
        """Missing required field (document or section) is rejected with .rejected file."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest_file = os.path.join(tmp, "manifest.json")
            input_file = os.path.join(tmp, "input.json")

            entry = _valid_entry()
            del entry["document"]
            with open(input_file, "w") as f:
                json.dump(entry, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--manifest", manifest_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)
            with open(rejected_path) as f:
                rejected = json.load(f)
            assert "reason" in rejected
            assert "document" in rejected["reason"]

    def test_invalid_json_input_rejected(self):
        """Invalid JSON input is rejected with .rejected file."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest_file = os.path.join(tmp, "manifest.json")
            input_file = os.path.join(tmp, "input.json")

            with open(input_file, "w") as f:
                f.write("{not valid json")

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--manifest", manifest_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

            rejected_path = input_file + ".rejected"
            assert os.path.exists(rejected_path)


class TestAddManifestEntryCLI:
    """CLI argument validation."""

    def test_missing_input_arg_fails(self):
        """Missing --input arg exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest_file = os.path.join(tmp, "manifest.json")
            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--manifest", manifest_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0

    def test_missing_manifest_arg_fails(self):
        """Missing --manifest arg exits non-zero."""
        with tempfile.TemporaryDirectory() as tmp:
            input_file = os.path.join(tmp, "input.json")
            with open(input_file, "w") as f:
                json.dump(_valid_entry(), f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file],
                capture_output=True, text=True,
            )
            assert result.returncode != 0


class TestAddManifestEntryMetadata:
    """_written_sections metadata entry handling."""

    def test_written_sections_metadata_accepted(self):
        """_written_sections metadata entry (empty symbols/file_paths + sections_written list) is accepted."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest_file = os.path.join(tmp, "manifest.json")
            input_file = os.path.join(tmp, "input.json")

            entry = {
                "document": "ARCHITECTURE",
                "section": "_written_sections",
                "symbols": [],
                "file_paths": [],
                "sections_written": ["overview", "data-model", "auth-flow"],
            }
            with open(input_file, "w") as f:
                json.dump(entry, f)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--input", input_file,
                 "--manifest", manifest_file],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            with open(manifest_file) as f:
                data = json.load(f)

            section = data["documents"]["ARCHITECTURE"]["_written_sections"]
            assert section["sections_written"] == ["overview", "data-model", "auth-flow"]
