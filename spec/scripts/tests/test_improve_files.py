"""Tests for improve_files.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec.scripts.improve_files import (
    _atoms_path,
    _auto_improve_path,
    _changelog_path,
    _decisions_path,
    _history_dir,
    _implementer_notes_path,
    _next_run,
    _non_goals_path,
    _original_path,
    main,
)


def _out(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out)


# ── Naming convention tests ─────────────────────────────────────────────────


class TestNamingConventions:
    def test_original_path(self) -> None:
        assert _original_path(Path("concept.md")) == Path("concept.original.md")

    def test_auto_improve_path(self) -> None:
        assert _auto_improve_path(Path("concept.md")) == Path("concept-auto-improve.md")

    def test_non_goals_path(self) -> None:
        assert _non_goals_path(Path("concept.md")) == Path("concept-NON-GOALS.md")

    def test_sidecar_paths(self) -> None:
        assert _implementer_notes_path(Path("concept.md")) == Path("concept-IMPLEMENTER-NOTES.md")
        assert _changelog_path(Path("concept.md")) == Path("concept-CHANGELOG.md")
        assert _atoms_path(Path("concept.md")) == Path("concept-ATOMS.json")
        assert _decisions_path(Path("concept.md")) == Path("concept-DECISIONS.json")

    def test_preserves_directory(self) -> None:
        src = Path("/a/b/DESIGN.md")
        assert _original_path(src) == Path("/a/b/DESIGN.original.md")
        assert _auto_improve_path(src) == Path("/a/b/DESIGN-auto-improve.md")
        assert _non_goals_path(src) == Path("/a/b/DESIGN-NON-GOALS.md")
        assert _atoms_path(src) == Path("/a/b/DESIGN-ATOMS.json")
        assert _history_dir(src) == Path("/a/b/history")


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
        result = _out(capsys)

        assert result["source"] == str(src)
        assert result["auto_improve"] == str(tmp_path / "concept-auto-improve.md")
        assert result["non_goals"] == str(tmp_path / "concept-NON-GOALS.md")
        assert result["non_goals_exists"] is False
        assert result["original_backup"] == str(tmp_path / "concept.original.md")
        assert result["backup_created"] is True
        # New keys
        assert result["implementer_notes"] == str(tmp_path / "concept-IMPLEMENTER-NOTES.md")
        assert result["changelog"] == str(tmp_path / "concept-CHANGELOG.md")
        assert result["atoms"] == str(tmp_path / "concept-ATOMS.json")
        assert result["decisions"] == str(tmp_path / "concept-DECISIONS.json")
        assert result["next_run"] == 1
        assert result["atoms_exists"] is False

    def test_skips_backup_if_exists(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = tmp_path / "concept.md"
        src.write_text("modified")
        backup = tmp_path / "concept.original.md"
        backup.write_text("original")

        main(["init", str(src)])
        result = _out(capsys)

        assert backup.read_text() == "original"  # not overwritten
        assert result["backup_created"] is False

    def test_non_goals_exists_flag(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")
        (tmp_path / "concept-NON-GOALS.md").write_text("- something\n")

        main(["init", str(src)])
        result = _out(capsys)
        assert result["non_goals_exists"] is True

    def test_missing_source(self, tmp_path: Path) -> None:
        assert main(["init", str(tmp_path / "nope.md")]) == 1

    def test_guards_stale_working_copy(self, tmp_path: Path) -> None:
        """BREAKING change (D7): init refuses to overwrite an existing working copy."""
        src = tmp_path / "concept.md"
        src.write_text("current")
        working = tmp_path / "concept-auto-improve.md"
        working.write_text("in-progress edits")

        assert main(["init", str(src)]) == 1
        assert working.read_text() == "in-progress edits"  # untouched

    def test_fresh_overwrites_working_copy(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("current")
        working = tmp_path / "concept-auto-improve.md"
        working.write_text("stale")

        assert main(["init", str(src), "--fresh"]) == 0
        assert working.read_text() == "current"

    def test_fresh_archives_all_sidecars_including_notes(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("current")
        (tmp_path / "concept-auto-improve.md").write_text("stale")
        (tmp_path / "concept-CHANGELOG.md").write_text("# cl\n")
        (tmp_path / "concept-ATOMS.json").write_text("[]")
        (tmp_path / "concept-DECISIONS.json").write_text("[]")
        (tmp_path / "concept-IMPLEMENTER-NOTES.md").write_text("# notes\n")

        assert main(["init", str(src), "--fresh"]) == 0

        run1 = tmp_path / "history" / "run-1"
        assert (run1 / "CHANGELOG.md").is_file()
        assert (run1 / "ATOMS.json").is_file()
        assert (run1 / "DECISIONS.json").is_file()
        assert (run1 / "IMPLEMENTER-NOTES.md").is_file()  # --fresh archives notes too
        # Live copies gone
        assert not (tmp_path / "concept-CHANGELOG.md").exists()
        assert not (tmp_path / "concept-IMPLEMENTER-NOTES.md").exists()


# ── paths ───────────────────────────────────────────────────────────────────


class TestPaths:
    def test_read_only(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")

        assert main(["paths", str(src)]) == 0
        result = _out(capsys)
        assert result["source"] == str(src)
        assert result["auto_improve_exists"] is False
        assert result["next_run"] == 1
        # Touches nothing
        assert not (tmp_path / "concept-auto-improve.md").exists()
        assert not (tmp_path / "concept.original.md").exists()

    def test_reflects_existing_working_copy(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")
        (tmp_path / "concept-auto-improve.md").write_text("wip")

        main(["paths", str(src)])
        assert _out(capsys)["auto_improve_exists"] is True

    def test_missing_source(self, tmp_path: Path) -> None:
        assert main(["paths", str(tmp_path / "nope.md")]) == 1


# ── approve / reject archival ───────────────────────────────────────────────


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

    def test_no_sidecars_creates_no_history(self, tmp_path: Path) -> None:
        """Plain spec-improve path: approve archives nothing and errors on nothing."""
        src = tmp_path / "concept.md"
        src.write_text("old")
        (tmp_path / "concept-auto-improve.md").write_text("new")

        assert main(["approve", str(src)]) == 0
        assert not _history_dir(src).exists()

    def test_archives_sidecars_keeps_notes(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("old")
        (tmp_path / "concept-auto-improve.md").write_text("new")
        (tmp_path / "concept-CHANGELOG.md").write_text("# cl\n")
        (tmp_path / "concept-DECISIONS.json").write_text("[]")
        (tmp_path / "concept-IMPLEMENTER-NOTES.md").write_text("# notes\n")

        assert main(["approve", str(src)]) == 0
        run1 = tmp_path / "history" / "run-1"
        assert (run1 / "CHANGELOG.md").is_file()
        assert (run1 / "DECISIONS.json").is_file()
        assert not (run1 / "IMPLEMENTER-NOTES.md").exists()          # notes NOT archived
        assert (tmp_path / "concept-IMPLEMENTER-NOTES.md").is_file()  # notes stay live
        assert not (tmp_path / "concept-CHANGELOG.md").exists()       # sidecars moved


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

    def test_archives_into_existing_latest_run(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("original")
        (tmp_path / "concept-auto-improve.md").write_text("wip")
        (tmp_path / "concept-CHANGELOG.md").write_text("# cl\n")
        # A prior snapshot already created run-1/
        (tmp_path / "history" / "run-1").mkdir(parents=True)
        (tmp_path / "history" / "run-1" / "round-1.md").write_text("snap")

        assert main(["reject", str(src)]) == 0
        assert (tmp_path / "history" / "run-1" / "CHANGELOG.md").is_file()


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

    def test_missing_text_arg(self) -> None:
        assert main(["append-non-goal", "/some/file.md"]) == 1


# ── append-note / note-ids ──────────────────────────────────────────────────


class TestNotes:
    def test_append_and_read_ids(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")

        assert main(["append-note", str(src), "--finding-id", "claim:L12", "Some minor nit"]) == 0
        assert main(["append-note", str(src), "--finding-id", "example:L4", "Another"]) == 0

        notes = tmp_path / "concept-IMPLEMENTER-NOTES.md"
        assert "- Some minor nit <!-- finding-id: claim:L12 -->\n" in notes.read_text()

        capsys.readouterr()  # drain the append-note stdout
        assert main(["note-ids", str(src)]) == 0
        ids = json.loads(capsys.readouterr().out)
        assert ids == ["claim:L12", "example:L4"]

    def test_note_ids_empty_when_absent(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")
        assert main(["note-ids", str(src)]) == 0
        assert json.loads(capsys.readouterr().out) == []

    def test_note_without_id(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")
        main(["append-note", str(src), "untagged note"])
        capsys.readouterr()  # drain the append-note stdout
        main(["note-ids", str(src)])
        assert json.loads(capsys.readouterr().out) == []  # no id metadata → not listed

    def test_missing_text(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")
        assert main(["append-note", str(src), "--finding-id", "x"]) == 1


# ── append-changelog ────────────────────────────────────────────────────────


class TestAppendChangelog:
    def test_tagged_entries(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")

        assert main(["append-changelog", str(src), "--run", "1", "--round", "2",
                     "--kind", "fix", "fixed a false claim"]) == 0
        assert main(["append-changelog", str(src), "--run", "1", "--round", "3",
                     "--kind", "decision-take", "took option A for D3"]) == 0

        text = (tmp_path / "concept-CHANGELOG.md").read_text()
        assert "[run 1 / round 2] [fix] fixed a false claim\n" in text
        assert "[run 1 / round 3] [decision-take] took option A for D3\n" in text
        # The --kind tag lets a cumulative-fix recount exclude decision-takes.
        assert text.count("[fix]") == 1

    def test_bad_kind(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")
        assert main(["append-changelog", str(src), "--run", "1", "--round", "1",
                     "--kind", "bogus", "text"]) == 1

    def test_missing_text(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")
        assert main(["append-changelog", str(src), "--run", "1", "--round", "1",
                     "--kind", "fix"]) == 1


# ── append-decision / update-decision ───────────────────────────────────────


class TestDecisions:
    def _mk(self, tmp_path: Path) -> Path:
        src = tmp_path / "concept.md"
        src.write_text("content")
        return src

    def test_allocates_sequential_ids(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = self._mk(tmp_path)

        assert main(["append-decision", str(src), "--kind", "decision",
                     "--title", "First", "--finding", "f1"]) == 0
        assert json.loads(capsys.readouterr().out)["id"] == "R1"

        assert main(["append-decision", str(src), "--kind", "non-goal-proposal",
                     "--title", "Second", "--finding", "f2",
                     "--finding-atoms", '["L4","L9"]']) == 0
        assert json.loads(capsys.readouterr().out)["id"] == "R2"

        records = json.loads((tmp_path / "concept-DECISIONS.json").read_text())
        assert [r["id"] for r in records] == ["R1", "R2"]
        assert records[1]["kind"] == "non-goal-proposal"
        assert records[1]["finding_atoms"] == ["L4", "L9"]

    def test_bad_kind(self, tmp_path: Path) -> None:
        src = self._mk(tmp_path)
        assert main(["append-decision", str(src), "--kind", "bogus",
                     "--title", "x", "--finding", "y"]) == 1

    def test_bad_finding_atoms(self, tmp_path: Path) -> None:
        src = self._mk(tmp_path)
        assert main(["append-decision", str(src), "--kind", "decision",
                     "--title", "x", "--finding", "y", "--finding-atoms", "not-json"]) == 1

    def test_update_merges_fields(self, tmp_path: Path) -> None:
        src = self._mk(tmp_path)
        main(["append-decision", str(src), "--kind", "decision", "--title", "T", "--finding", "F"])

        assert main(["update-decision", str(src), "--id", "R1",
                     "--set", '{"taken": "option A", "taken_by": "auto", "confidence": "high"}']) == 0
        rec = json.loads((tmp_path / "concept-DECISIONS.json").read_text())[0]
        assert rec["taken"] == "option A"
        assert rec["taken_by"] == "auto"
        assert rec["confidence"] == "high"

    def test_replaced_take_moves_to_superseded(self, tmp_path: Path) -> None:
        src = self._mk(tmp_path)
        main(["append-decision", str(src), "--kind", "decision", "--title", "T", "--finding", "F"])
        main(["update-decision", str(src), "--id", "R1", "--set", '{"taken": "option A"}'])
        main(["update-decision", str(src), "--id", "R1", "--set", '{"taken": "option B", "taken_by": "user"}'])

        rec = json.loads((tmp_path / "concept-DECISIONS.json").read_text())[0]
        assert rec["taken"] == "option B"
        assert rec["superseded"] == ["option A"]  # prior take preserved, never erased

    def test_update_unknown_id(self, tmp_path: Path) -> None:
        src = self._mk(tmp_path)
        main(["append-decision", str(src), "--kind", "decision", "--title", "T", "--finding", "F"])
        assert main(["update-decision", str(src), "--id", "R99", "--set", '{"taken": "x"}']) == 1

    def test_update_no_file(self, tmp_path: Path) -> None:
        src = self._mk(tmp_path)
        assert main(["update-decision", str(src), "--id", "R1", "--set", "{}"]) == 1

    def test_update_bad_set(self, tmp_path: Path) -> None:
        src = self._mk(tmp_path)
        main(["append-decision", str(src), "--kind", "decision", "--title", "T", "--finding", "F"])
        assert main(["update-decision", str(src), "--id", "R1", "--set", "[1,2]"]) == 1


# ── snapshot ────────────────────────────────────────────────────────────────


class TestSnapshot:
    def _session(self, tmp_path: Path, working_text: str = "v1") -> Path:
        src = tmp_path / "concept.md"
        src.write_text("orig")
        (tmp_path / "concept-auto-improve.md").write_text(working_text)
        return src

    def test_writes_snapshot_and_verdicts(self, tmp_path: Path) -> None:
        src = self._session(tmp_path)
        vlog = tmp_path / "verdicts.json"
        vlog.write_text('{"round": 1}')

        assert main(["snapshot", str(src), "--run", "1", "--round", "1",
                     "--verdicts", str(vlog)]) == 0
        run1 = tmp_path / "history" / "run-1"
        assert (run1 / "round-1.md").read_text() == "v1"
        assert (run1 / "round-1-verdicts.json").read_text() == '{"round": 1}'

    def test_idempotent_on_byte_match(self, tmp_path: Path) -> None:
        src = self._session(tmp_path)
        vlog = tmp_path / "verdicts.json"
        vlog.write_text('{"r": 1}')
        main(["snapshot", str(src), "--run", "1", "--round", "1", "--verdicts", str(vlog)])

        # Re-invocation (failure-policy retry) with identical content → success, no error.
        assert main(["snapshot", str(src), "--run", "1", "--round", "1", "--verdicts", str(vlog)]) == 0

    def test_mismatch_is_reused_run_number(self, tmp_path: Path) -> None:
        src = self._session(tmp_path, "v1")
        main(["snapshot", str(src), "--run", "1", "--round", "1"])
        # Working copy changed but same run/round → genuinely reused run number.
        (tmp_path / "concept-auto-improve.md").write_text("v2-different")
        assert main(["snapshot", str(src), "--run", "1", "--round", "1"]) == 1

    def test_requires_run_and_round(self, tmp_path: Path) -> None:
        src = self._session(tmp_path)
        assert main(["snapshot", str(src), "--run", "1"]) == 1

    def test_missing_working_copy(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        src.write_text("orig")
        assert main(["snapshot", str(src), "--run", "1", "--round", "1"]) == 1


# ── next_run derivation ─────────────────────────────────────────────────────


class TestNextRun:
    def test_empty(self, tmp_path: Path) -> None:
        assert _next_run(tmp_path / "concept.md") == 1

    def test_scans_history(self, tmp_path: Path) -> None:
        src = tmp_path / "concept.md"
        (tmp_path / "history" / "run-1").mkdir(parents=True)
        (tmp_path / "history" / "run-2").mkdir(parents=True)
        (tmp_path / "history" / "not-a-run").mkdir(parents=True)
        assert _next_run(src) == 3


# ── CLI dispatch ────────────────────────────────────────────────────────────


class TestCLI:
    def test_no_args(self) -> None:
        assert main([]) == 1

    def test_one_arg(self) -> None:
        assert main(["init"]) == 1

    def test_unknown_command(self) -> None:
        assert main(["explode", "/some/file.md"]) == 1
