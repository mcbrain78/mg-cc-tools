"""Tests for dismiss-entity.py."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(SCRIPTS_DIR, "dismiss-entity.py")


def _write_json(td, name, data):
    path = os.path.join(td, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _run(entity, section, uncleared_file, dismissed_this_run_file,
         audience="devops", document="OPERATIONS",
         protected_entities_file=None):
    cmd = [
        sys.executable, SCRIPT,
        "--entity", entity,
        "--section", section,
        "--uncleared-file", uncleared_file,
        "--dismissed-this-run-file", dismissed_this_run_file,
        "--audience", audience,
        "--document", document,
    ]
    if protected_entities_file:
        cmd.extend(["--protected-entities-file", protected_entities_file])
    return subprocess.run(cmd, capture_output=True, text=True)


class TestDismiss:
    """Entity removal from uncleared and addition to dismissed-this-run."""

    def test_entity_removed_from_all_sections(self):
        """Entity in multiple sections → all removed from uncleared."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
                {"name": "bash", "section": "deployment"},
                {"name": "bash", "section": "orchestration"},
                {"name": "PORT", "section": "deployment"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("bash", "monitoring", uf, df)
            assert result.returncode == 0

            uncleared = _read_json(uf)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "PORT"

    def test_entity_added_to_dismissed_this_run(self):
        """Dismissed entity appended to dismissed-this-run list."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            _run("bash", "monitoring", uf, df)

            dismissed = _read_json(df)
            assert len(dismissed) == 1
            assert dismissed[0]["name"] == "bash"
            assert dismissed[0]["dismissed_in"] == "monitoring"
            assert dismissed[0]["audience"] == "devops"
            assert dismissed[0]["document"] == "OPERATIONS"

    def test_dedup_dismissed_this_run(self):
        """Dismissing same entity twice does not duplicate in dismissed-this-run."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [
                {"name": "bash", "dismissed_in": "deployment",
                 "audience": "devops", "document": "OPERATIONS"},
            ])

            _run("bash", "monitoring", uf, df)

            dismissed = _read_json(df)
            assert len(dismissed) == 1
            assert dismissed[0]["dismissed_in"] == "deployment"  # original preserved

    def test_entity_not_in_uncleared(self):
        """Entity not in uncleared → no-op on uncleared, still added to dismissed."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "PORT", "section": "deployment"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("nonexistent", "monitoring", uf, df)
            assert result.returncode == 0

            uncleared = _read_json(uf)
            assert len(uncleared) == 1
            assert uncleared[0]["name"] == "PORT"

            dismissed = _read_json(df)
            assert len(dismissed) == 1
            assert dismissed[0]["name"] == "nonexistent"

    def test_empty_uncleared(self):
        """Empty uncleared file → no-op on uncleared."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("bash", "monitoring", uf, df)
            assert result.returncode == 0

            uncleared = _read_json(uf)
            assert uncleared == []

    def test_missing_dismissed_file(self):
        """Non-existent dismissed file → created with the entity."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            df = os.path.join(td, "dismissed-this-run.json")

            result = _run("bash", "monitoring", uf, df)
            assert result.returncode == 0

            dismissed = _read_json(df)
            assert len(dismissed) == 1
            assert dismissed[0]["name"] == "bash"

    def test_missing_uncleared_file(self):
        """Non-existent uncleared file → defaults to empty, created."""
        with tempfile.TemporaryDirectory() as td:
            uf = os.path.join(td, "uncleared.json")
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("bash", "monitoring", uf, df)
            assert result.returncode == 0

            uncleared = _read_json(uf)
            assert uncleared == []

    def test_summary_on_stderr(self):
        """Summary line printed to stderr."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
                {"name": "bash", "section": "deployment"},
                {"name": "PORT", "section": "deployment"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("bash", "monitoring", uf, df)
            assert "Dismissed: bash" in result.stderr
            assert "3 → 1" in result.stderr


class TestProtected:
    """Protected entity handling."""

    def test_protected_entity_refused(self):
        """Protected entity stays in uncleared, not written to dismissed."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "compute_hash", "section": "monitoring"},
                {"name": "PORT", "section": "deployment"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])
            pf = _write_json(td, "protected-entities.json", [
                {"name": "compute_hash", "reason": "Project function"},
            ])

            result = _run(
                "compute_hash", "monitoring", uf, df,
                protected_entities_file=pf,
            )
            assert result.returncode == 0
            assert "PROTECTED: compute_hash" in result.stderr

            # Uncleared unchanged
            uncleared = _read_json(uf)
            assert len(uncleared) == 2

            # Not written to dismissed
            dismissed = _read_json(df)
            assert len(dismissed) == 0

    def test_no_protected_file_means_no_check(self):
        """Omitting --protected-entities-file → dismiss proceeds normally."""
        with tempfile.TemporaryDirectory() as td:
            uf = _write_json(td, "uncleared.json", [
                {"name": "bash", "section": "monitoring"},
            ])
            df = _write_json(td, "dismissed-this-run.json", [])

            result = _run("bash", "monitoring", uf, df)
            assert result.returncode == 0
            assert "PROTECTED" not in result.stderr
            assert "Dismissed: bash" in result.stderr

            uncleared = _read_json(uf)
            assert len(uncleared) == 0

            dismissed = _read_json(df)
            assert len(dismissed) == 1
