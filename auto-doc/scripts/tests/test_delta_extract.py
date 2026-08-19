"""Tests for delta-extract.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "delta-extract.py")


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _setup_prose_verify(td, sections):
    """Create prose-verify dir with manifest and section files.

    Args:
        sections: list of (path, content_hash) tuples
    """
    pvd = os.path.join(td, "prose-verify")
    os.makedirs(pvd, exist_ok=True)

    paths = []
    for section_path, content_hash in sections:
        slug = section_path.rsplit("/", 1)[-1] if "/" in section_path else section_path
        parent = os.path.dirname(section_path) if "/" in section_path else ""
        section_dir = os.path.join(pvd, parent) if parent else pvd
        os.makedirs(section_dir, exist_ok=True)
        _write_json(os.path.join(section_dir, f"{slug}.json"), {
            "path": section_path,
            "slug": slug,
            "body": "test body",
            "refs_as_text": "test refs",
            "content_hash": content_hash,
        })
        paths.append(section_path)

    _write_json(os.path.join(pvd, "manifest.json"), {"sections": paths})
    return pvd


def _run(prose_verify_dir, prev_entities_file, entities_file):
    return subprocess.run(
        [sys.executable, SCRIPT,
         "--prose-verify-dir", prose_verify_dir,
         "--prev-entities-file", prev_entities_file,
         "--entities-file", entities_file],
        capture_output=True, text=True,
    )


class TestDeltaExtractNoPrevious:
    """First run with no previous data."""

    def test_all_sections_changed(self):
        """No previous entities file → all sections are changed."""
        with tempfile.TemporaryDirectory() as td:
            pvd = _setup_prose_verify(td, [
                ("monitoring", "hash1"),
                ("deployment", "hash2"),
            ])
            prev_ent = os.path.join(td, "prev-entities.json")
            curr_ent = os.path.join(td, "entities.json")

            result = _run(pvd, prev_ent, curr_ent)
            assert result.returncode == 0

            output = json.loads(result.stdout)
            assert sorted(output["changed"]) == ["deployment", "monitoring"]
            assert output["reused"] == 0


class TestDeltaExtractWithPrevious:
    """Runs with previous data available."""

    def test_unchanged_sections_reused(self):
        """Sections with matching hashes carry forward entities."""
        with tempfile.TemporaryDirectory() as td:
            pvd = _setup_prose_verify(td, [
                ("monitoring", "hash1"),
                ("deployment", "hash2"),
            ])

            # Previous entities
            prev_ent = os.path.join(td, "prev-entities.json")
            _write_json(prev_ent, [
                {"name": "etl_runs", "section": "monitoring"},
                {"name": "PORT", "section": "deployment"},
            ])
            # Previous hashes (same as current)
            prev_hashes = os.path.join(td, "prev-entities-hashes.json")
            _write_json(prev_hashes, {
                "monitoring": "hash1",
                "deployment": "hash2",
            })

            curr_ent = os.path.join(td, "entities.json")

            result = _run(pvd, prev_ent, curr_ent)
            assert result.returncode == 0

            output = json.loads(result.stdout)
            assert output["changed"] == []
            assert output["reused"] == 2

            # Entities carried forward
            entities = _read_json(curr_ent)
            names = {e["name"] for e in entities}
            assert names == {"etl_runs", "PORT"}

    def test_mixed_changed_and_unchanged(self):
        """One changed, one unchanged — only changed in output."""
        with tempfile.TemporaryDirectory() as td:
            pvd = _setup_prose_verify(td, [
                ("monitoring", "hash1"),
                ("deployment", "hash2_new"),
            ])

            prev_ent = os.path.join(td, "prev-entities.json")
            _write_json(prev_ent, [
                {"name": "etl_runs", "section": "monitoring"},
                {"name": "PORT", "section": "deployment"},
            ])
            prev_hashes = os.path.join(td, "prev-entities-hashes.json")
            _write_json(prev_hashes, {
                "monitoring": "hash1",
                "deployment": "hash2_old",
            })

            curr_ent = os.path.join(td, "entities.json")

            result = _run(pvd, prev_ent, curr_ent)
            assert result.returncode == 0

            output = json.loads(result.stdout)
            assert output["changed"] == ["deployment"]
            assert output["reused"] == 1

            # Only monitoring entities carried forward
            entities = _read_json(curr_ent)
            assert len(entities) == 1
            assert entities[0]["name"] == "etl_runs"

    def test_hashes_written_for_next_run(self):
        """Current hashes saved as sidecar of entities file."""
        with tempfile.TemporaryDirectory() as td:
            pvd = _setup_prose_verify(td, [
                ("monitoring", "abc123"),
            ])
            prev_ent = os.path.join(td, "prev-entities.json")
            curr_ent = os.path.join(td, "entities.json")

            result = _run(pvd, prev_ent, curr_ent)
            assert result.returncode == 0

            hashes_path = os.path.join(td, "entities-hashes.json")
            assert os.path.isfile(hashes_path)
            hashes = _read_json(hashes_path)
            assert hashes["monitoring"] == "abc123"


class TestChangedSectionsOut:
    """--changed-sections-out writes the extraction agent's --sections-filter.

    The orchestrator used to read `changed` out of stdout and interpolate it back
    into a shell argument to produce this file. These tests pin the property that
    made that round trip removable: the file the agent reads and the list this
    script computed are the same object, not two transcriptions of it.
    """

    def test_written_file_matches_stdout_changed(self):
        with tempfile.TemporaryDirectory() as td:
            pvd = _setup_prose_verify(td, [
                ("monitoring", "hash1"),
                ("ops/deployment", "hash2"),
            ])
            out = os.path.join(td, "changed-sections.json")

            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--prose-verify-dir", pvd,
                 "--prev-entities-file", os.path.join(td, "prev.json"),
                 "--entities-file", os.path.join(td, "entities.json"),
                 "--changed-sections-out", out],
                capture_output=True, text=True,
            )

            assert result.returncode == 0, result.stderr
            assert _read_json(out) == json.loads(result.stdout)["changed"]
            assert _read_json(out) == ["monitoring", "ops/deployment"]

    def test_empty_list_is_still_written(self):
        """A stale filter from a previous run would be worse than an empty one."""
        with tempfile.TemporaryDirectory() as td:
            pvd = _setup_prose_verify(td, [("monitoring", "hash1")])
            prev_ent = os.path.join(td, "prev-entities.json")
            curr_ent = os.path.join(td, "entities.json")
            _write_json(prev_ent, [{"name": "etl_runs", "section": "monitoring"}])
            _write_json(os.path.join(td, "prev-entities-hashes.json"),
                        {"monitoring": "hash1"})
            out = os.path.join(td, "changed-sections.json")
            _write_json(out, ["monitoring", "stale-leftover"])

            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--prose-verify-dir", pvd,
                 "--prev-entities-file", prev_ent,
                 "--entities-file", curr_ent,
                 "--changed-sections-out", out],
                capture_output=True, text=True,
            )

            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout)["changed"] == []
            assert _read_json(out) == []

    def test_parent_directory_is_created(self):
        with tempfile.TemporaryDirectory() as td:
            pvd = _setup_prose_verify(td, [("monitoring", "hash1")])
            out = os.path.join(td, "run", "nested", "changed-sections.json")

            result = subprocess.run(
                [sys.executable, SCRIPT,
                 "--prose-verify-dir", pvd,
                 "--prev-entities-file", os.path.join(td, "prev.json"),
                 "--entities-file", os.path.join(td, "entities.json"),
                 "--changed-sections-out", out],
                capture_output=True, text=True,
            )

            assert result.returncode == 0, result.stderr
            assert _read_json(out) == ["monitoring"]

    def test_flag_is_optional(self):
        """Existing callers that omit it must behave exactly as before."""
        with tempfile.TemporaryDirectory() as td:
            pvd = _setup_prose_verify(td, [("monitoring", "hash1")])

            result = _run(pvd, os.path.join(td, "prev.json"),
                          os.path.join(td, "entities.json"))

            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout)["changed"] == ["monitoring"]
