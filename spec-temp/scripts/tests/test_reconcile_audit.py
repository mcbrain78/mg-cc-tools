"""Tests for the ``reconcile-audit`` subcommand of the spec-improve-auto fork.

The fork lives in the hyphenated ``spec-temp/`` directory, which is not importable
as a package (unlike canonical ``spec/``), so ``improve_files`` is loaded by path.
AT PORT to canonical, replace the loader block with the package import the sibling
suite uses: ``from spec.scripts.improve_files import main``.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_MOD = Path(__file__).resolve().parents[1] / "improve_files.py"
_spec = importlib.util.spec_from_file_location("improve_files_fork", _MOD)
assert _spec and _spec.loader, f"cannot load {_MOD}"
improve_files = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(improve_files)
main = improve_files.main


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
