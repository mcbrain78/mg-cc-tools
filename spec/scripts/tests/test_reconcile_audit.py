"""Tests for the ``reconcile-audit`` subcommand used by the spec-improve-auto
finalize pass."""
from __future__ import annotations

import json
from pathlib import Path

from spec.scripts.improve_files import main


def _audit(capsys, path: Path) -> dict:
    rc = main(["reconcile-audit", str(path)])
    assert rc == 0
    return json.loads(capsys.readouterr().out)


CLEAN_SPEC = """\
# Title

## Design Decisions

### D1: first
Body refers to D2.

### D2: second
Body refers back to D1.
"""

DRIFT_SPEC = """\
# Title

## Decision Index
- D1, D2, D3

## Design Decisions

### D1: first

### D2: second
See D9 for details.

### D4: fourth
"""

STALE_OD_SPEC = """\
# Title

## Design Decisions

### D1: only
Resolved per OD3 earlier.
"""


class TestReconcileAudit:
    def test_clean_spec(self, tmp_path, capsys) -> None:
        p = tmp_path / "concept.md"
        p.write_text(CLEAN_SPEC)
        r = _audit(capsys, p)
        assert r["clean"] is True
        assert r["decisions"] == ["D1", "D2"]
        assert r["numbering_issues"] == []
        assert r["dangling_references"] == []

    def test_gap_and_dangling(self, tmp_path, capsys) -> None:
        p = tmp_path / "concept.md"
        p.write_text(DRIFT_SPEC)
        r = _audit(capsys, p)
        assert r["clean"] is False
        # Headings are D1, D2, D4 → D3 missing (non-contiguous).
        assert r["decisions"] == ["D1", "D2", "D4"]
        assert any("D3" in m for m in r["numbering_issues"])
        # D9 (body) and D3 (index) are referenced with no heading → dangling.
        dang = " ".join(r["dangling_references"])
        assert "D9" in dang and "D3" in dang

    def test_stale_open_decision_pointer(self, tmp_path, capsys) -> None:
        p = tmp_path / "concept.md"
        p.write_text(STALE_OD_SPEC)
        r = _audit(capsys, p)
        assert r["clean"] is False
        assert any("OD3" in d for d in r["dangling_references"])
        # The `D3` inside `OD3` must NOT be mis-counted as a decision reference.
        assert "D3" not in r["reference_counts"]

    def test_out_of_order(self, tmp_path, capsys) -> None:
        p = tmp_path / "concept.md"
        p.write_text("## Design Decisions\n\n### D2: b\n\n### D1: a\n")
        r = _audit(capsys, p)
        assert r["clean"] is False
        assert any("out of document order" in m for m in r["numbering_issues"])

    def test_missing_file(self) -> None:
        rc = main(["reconcile-audit", "/nonexistent/definitely/nope.md"])
        assert rc == 1


class TestDanglingCount:
    """``--dangling-count`` prints one number for the mid-loop check.

    spec-improve-auto reads this every third round and must ignore the numbering
    gaps the full report also carries -- mid-loop those are expected, and closing
    them is finalize's job. So the flag has to report dangling references ALONE,
    even on a spec the full audit calls unclean.
    """

    def _count(self, capsys, path: Path) -> str:
        rc = main(["reconcile-audit", str(path), "--dangling-count"])
        assert rc == 0
        return capsys.readouterr().out.strip()

    def test_clean_spec_prints_zero(self, tmp_path, capsys) -> None:
        p = tmp_path / "concept.md"
        p.write_text(CLEAN_SPEC)
        assert self._count(capsys, p) == "0"

    def test_counts_dangling_references(self, tmp_path, capsys) -> None:
        p = tmp_path / "concept.md"
        p.write_text(DRIFT_SPEC)
        assert self._count(capsys, p) == "2"

    def test_numbering_gaps_alone_still_count_zero(self, tmp_path, capsys) -> None:
        """The whole point of the flag: gaps must not be read as dangling refs."""
        p = tmp_path / "concept.md"
        p.write_text("## Design Decisions\n\n### D1: a\n\n### D3: c\n")
        assert self._count(capsys, p) == "0"

        full = main(["reconcile-audit", str(p)])
        assert full == 0
        report = json.loads(capsys.readouterr().out)
        assert report["clean"] is False
        assert report["numbering_issues"]
        assert report["dangling_references"] == []

    def test_prints_only_the_number(self, tmp_path, capsys) -> None:
        p = tmp_path / "concept.md"
        p.write_text(CLEAN_SPEC)
        rc = main(["reconcile-audit", str(p), "--dangling-count"])
        assert rc == 0
        assert capsys.readouterr().out == "0\n"

    def test_agrees_with_the_full_report(self, tmp_path, capsys) -> None:
        p = tmp_path / "concept.md"
        p.write_text(STALE_OD_SPEC)
        counted = self._count(capsys, p)
        main(["reconcile-audit", str(p)])
        report = json.loads(capsys.readouterr().out)
        assert counted == str(len(report["dangling_references"]))

    def test_without_the_flag_the_report_is_unchanged(self, tmp_path, capsys) -> None:
        p = tmp_path / "concept.md"
        p.write_text(CLEAN_SPEC)
        r = _audit(capsys, p)
        assert r["clean"] is True
        assert r["decisions"] == ["D1", "D2"]

    def test_missing_file_still_fails(self, tmp_path) -> None:
        rc = main(["reconcile-audit", "/nonexistent/nope.md", "--dangling-count"])
        assert rc == 1
