"""Tests for merge-manifests.py -- merge temp writer manifests into persisted.

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
    "merge-manifests.py",
)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestMergeManifestsInitialMode:
    """Empty persisted → full copy from temp."""

    def test_initial_mode_copies_from_temp(self):
        """When no persisted manifest exists, temp manifest becomes the persisted one."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = os.path.join(tmp, "temp")
            output_dir = os.path.join(tmp, "output")
            os.makedirs(tmp_dir)
            os.makedirs(output_dir)

            temp_manifest = {
                "documents": {
                    "ARCHITECTURE": {
                        "overview": {
                            "symbols": ["load_json"],
                            "file_paths": ["lib/json_io.py"],
                        }
                    }
                }
            }
            _write_json(os.path.join(tmp_dir, "manifest-developers.json"), temp_manifest)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--tmp-dir", tmp_dir,
                 "--output-dir", output_dir,
                 "--audiences", "developers"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            persisted = _read_json(os.path.join(output_dir, "developers.json"))
            assert persisted["audience"] == "developers"
            assert persisted["generated"] != ""
            assert "ARCHITECTURE" in persisted["documents"]
            assert persisted["documents"]["ARCHITECTURE"]["overview"]["symbols"] == ["load_json"]


class TestMergeManifestsUpdateMode:
    """Temp overlays persisted, untouched sections preserved."""

    def test_update_mode_overlays(self):
        """Temp sections replace persisted, but untouched persisted sections are preserved."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = os.path.join(tmp, "temp")
            output_dir = os.path.join(tmp, "output")
            os.makedirs(tmp_dir)

            # Existing persisted manifest
            persisted = {
                "audience": "developers",
                "generated": "2026-03-20T00:00:00Z",
                "documents": {
                    "ARCHITECTURE": {
                        "overview": {
                            "symbols": ["old_func"],
                            "file_paths": ["old.py"],
                        },
                        "data-model": {
                            "symbols": ["User"],
                            "file_paths": ["models.py"],
                        },
                    }
                },
            }
            _write_json(os.path.join(output_dir, "developers.json"), persisted)

            # Temp manifest only updates overview
            temp_manifest = {
                "documents": {
                    "ARCHITECTURE": {
                        "overview": {
                            "symbols": ["new_func"],
                            "file_paths": ["new.py"],
                        }
                    }
                }
            }
            _write_json(os.path.join(tmp_dir, "manifest-developers.json"), temp_manifest)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--tmp-dir", tmp_dir,
                 "--output-dir", output_dir,
                 "--audiences", "developers"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            merged = _read_json(os.path.join(output_dir, "developers.json"))
            # Overview updated
            assert merged["documents"]["ARCHITECTURE"]["overview"]["symbols"] == ["new_func"]
            # data-model preserved
            assert merged["documents"]["ARCHITECTURE"]["data-model"]["symbols"] == ["User"]
            # Timestamp updated
            assert merged["generated"] != "2026-03-20T00:00:00Z"


class TestMergeManifestsWrittenSections:
    """_written_sections metadata cleanup."""

    def test_written_sections_cleanup(self):
        """Stale sections not in sections_written are removed from persisted manifest."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = os.path.join(tmp, "temp")
            output_dir = os.path.join(tmp, "output")
            os.makedirs(tmp_dir)

            # Persisted has 3 sections
            persisted = {
                "audience": "developers",
                "generated": "",
                "documents": {
                    "GUIDE": {
                        "intro": {"symbols": ["a"], "file_paths": []},
                        "setup": {"symbols": ["b"], "file_paths": []},
                        "advanced": {"symbols": ["c"], "file_paths": []},
                    }
                },
            }
            _write_json(os.path.join(output_dir, "developers.json"), persisted)

            # Temp says only intro and setup were written (advanced is stale)
            temp_manifest = {
                "documents": {
                    "GUIDE": {
                        "_written_sections": {
                            "sections_written": ["intro", "setup"],
                            "symbols": [],
                            "file_paths": [],
                        },
                        "intro": {"symbols": ["a_new"], "file_paths": []},
                        "setup": {"symbols": ["b_new"], "file_paths": []},
                    }
                }
            }
            _write_json(os.path.join(tmp_dir, "manifest-developers.json"), temp_manifest)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--tmp-dir", tmp_dir,
                 "--output-dir", output_dir,
                 "--audiences", "developers"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            merged = _read_json(os.path.join(output_dir, "developers.json"))
            guide = merged["documents"]["GUIDE"]

            # intro and setup updated
            assert guide["intro"]["symbols"] == ["a_new"]
            assert guide["setup"]["symbols"] == ["b_new"]
            # advanced removed (stale)
            assert "advanced" not in guide
            # _written_sections not persisted
            assert "_written_sections" not in guide


class TestMergeManifestsMissing:
    """Missing temp manifest handling."""

    def test_missing_temp_skipped(self):
        """Audience with no temp manifest is skipped without error."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = os.path.join(tmp, "temp")
            output_dir = os.path.join(tmp, "output")
            os.makedirs(tmp_dir)
            os.makedirs(output_dir)

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--tmp-dir", tmp_dir,
                 "--output-dir", output_dir,
                 "--audiences", "developers,agents"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0
            assert "skipped" in result.stderr

            # No output files created
            assert not os.path.exists(os.path.join(output_dir, "developers.json"))
            assert not os.path.exists(os.path.join(output_dir, "agents.json"))

    def test_partial_audiences(self):
        """Only audiences with temp manifests are processed."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = os.path.join(tmp, "temp")
            output_dir = os.path.join(tmp, "output")
            os.makedirs(tmp_dir)
            os.makedirs(output_dir)

            # Only developers has a temp manifest
            _write_json(
                os.path.join(tmp_dir, "manifest-developers.json"),
                {"documents": {"DOC": {"sec": {"symbols": ["x"], "file_paths": []}}}},
            )

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--tmp-dir", tmp_dir,
                 "--output-dir", output_dir,
                 "--audiences", "developers,agents"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            assert os.path.exists(os.path.join(output_dir, "developers.json"))
            assert not os.path.exists(os.path.join(output_dir, "agents.json"))


class TestMergeManifestsMetadata:
    """Audience and generated fields set correctly."""

    def test_audience_and_generated_set(self):
        """Merged manifest has correct audience and non-empty generated timestamp."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = os.path.join(tmp, "temp")
            output_dir = os.path.join(tmp, "output")
            os.makedirs(tmp_dir)
            os.makedirs(output_dir)

            _write_json(
                os.path.join(tmp_dir, "manifest-end-users.json"),
                {"documents": {"DOC": {"sec": {"symbols": ["x"], "file_paths": []}}}},
            )

            result = subprocess.run(
                [sys.executable, SCRIPT_PATH,
                 "--tmp-dir", tmp_dir,
                 "--output-dir", output_dir,
                 "--audiences", "end-users"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0

            merged = _read_json(os.path.join(output_dir, "end-users.json"))
            assert merged["audience"] == "end-users"
            assert merged["generated"] != ""
            # Should be an ISO timestamp
            assert "T" in merged["generated"]
