"""Tests for improve_files.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec.scripts.improve_files import (
    _auto_improve_path,
    _non_goals_path,
    _original_path,
    main,
)


# ── Naming convention tests ─────────────────────────────────────────────────


class TestNamingConventions:
    def test_original_path(self) -> None:
        assert _original_path(Path("concept.md")) == Path("concept.original.md")

    def test_auto_improve_path(self) -> None:
        assert _auto_improve_path(Path("concept.md")) == Path("concept-auto-improve.md")

    def test_non_goals_path(self) -> None:
        assert _non_goals_path(Path("concept.md")) == Path("concept-NON-GOALS.md")

    def test_preserves_directory(self) -> None:
        src = Path("/a/b/DESIGN.md")
        assert _original_path(src) == Path("/a/b/DESIGN.original.md")
        assert _auto_improve_path(src) == Path("/a/b/DESIGN-auto-improve.md")
        assert _non_goals_path(src) == Path("/a/b/DESIGN-NON-GOALS.md")


# ── init ────────────────────────────────────────────────────────────────────


class TestInit:
    def test_creates_backup_and_working_copy(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("# Original\n")

        assert main(["init", str(src)]) == 0

        assert (tmp_path / "concept.original.md").read_text() == "# Original\n"
        assert (tmp_path / "concept-auto-improve.md").read_text() == "# Original\n"

    def test_output_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")

        main(["init", str(src)])
        result = json.loads(capsys.readouterr().out)

        assert result["auto_improve"] == str(tmp_path / "concept-auto-improve.md")
        assert result["non_goals"] == str(tmp_path / "concept-NON-GOALS.md")
        assert result["non_goals_exists"] is False
        assert result["original_backup"] == str(tmp_path / "concept.original.md")
        assert result["backup_created"] is True

    def test_skips_backup_if_exists(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = tmp_path / "concept.md"
        src.write_text("modified")
        backup = tmp_path / "concept.original.md"
        backup.write_text("original")

        main(["init", str(src)])
        result = json.loads(capsys.readouterr().out)

        assert backup.read_text() == "original"  # not overwritten
        assert result["backup_created"] is False

    def test_non_goals_exists_flag(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")
        (tmp_path / "concept-NON-GOALS.md").write_text("- something\n")

        main(["init", str(src)])
        result = json.loads(capsys.readouterr().out)
        assert result["non_goals_exists"] is True

    def test_missing_source(self, tmp_path: Path) -> None:
        assert main(["init", str(tmp_path / "nope.md")]) == 1

    def test_overwrites_stale_working_copy(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("current")
        working = tmp_path / "concept-auto-improve.md"
        working.write_text("stale")

        main(["init", str(src)])
        assert working.read_text() == "current"


# ── approve ─────────────────────────────────────────────────────────────────


class TestApprove:
    def test_copies_working_over_original(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("old")
        working = tmp_path / "concept-auto-improve.md"
        working.write_text("improved")

        assert main(["approve", str(src)]) == 0
        assert src.read_text() == "improved"
        assert not working.exists()

    def test_missing_working_copy(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")
        assert main(["approve", str(src)]) == 1


# ── reject ──────────────────────────────────────────────────────────────────


class TestReject:
    def test_deletes_working_copy(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("original")
        working = tmp_path / "concept-auto-improve.md"
        working.write_text("improved")

        assert main(["reject", str(src)]) == 0
        assert src.read_text() == "original"
        assert not working.exists()

    def test_missing_working_copy(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")
        assert main(["reject", str(src)]) == 1


# ── append-non-goal ─────────────────────────────────────────────────────────


class TestAppendNonGoal:
    def test_creates_file_if_absent(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")
        ng = tmp_path / "concept-NON-GOALS.md"

        assert main(["append-non-goal", str(src), "Performance optimization"]) == 0
        assert ng.exists()
        text = ng.read_text()
        assert "# Non-Goals" in text
        assert "- Performance optimization\n" in text

    def test_appends_to_existing(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")
        ng = tmp_path / "concept-NON-GOALS.md"
        ng.write_text("# Non-Goals for concept.md\n\n- First\n")

        main(["append-non-goal", str(src), "Second"])
        text = ng.read_text()
        assert "- First\n" in text
        assert "- Second\n" in text

    def test_handles_missing_trailing_newline(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")
        ng = tmp_path / "concept-NON-GOALS.md"
        ng.write_text("- First")  # no trailing newline

        main(["append-non-goal", str(src), "Second"])
        text = ng.read_text()
        assert "- First\n- Second\n" in text

    def test_missing_text_arg(self) -> None:
        assert main(["append-non-goal", "/some/file.md"]) == 1


# ── CLI dispatch ────────────────────────────────────────────────────────────


class TestCLI:
    def test_no_args(self) -> None:
        assert main([]) == 1

    def test_one_arg(self) -> None:
        assert main(["init"]) == 1

    def test_unknown_command(self) -> None:
        assert main(["explode", "/some/file.md"]) == 1
