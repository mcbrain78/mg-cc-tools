"""Determinism fixtures for spec_checks.py (concept D4, D5, D8, D9)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from spec.scripts import improve_files
from spec.scripts.spec_checks import main


def _out(capsys: pytest.CaptureFixture[str]) -> Any:
    return json.loads(capsys.readouterr().out)


CONFORMANT = """\
# Concept

## Situation
Some situation.

## Problem
Some problem.

## Solution

### Overview
Overview text.

## Design Decisions

### D1: A decision
**Choice:** X
**Why:** Y

## Scope

### What gets built
- A thing (D1)

### What does NOT get built
- Not this

## Verification
- A check
"""


def _write(tmp_path: Path, name: str, obj: object) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(obj))
    return p


# ── structure (D8) ───────────────────────────────────────────────────────────


class TestStructure:
    def test_conformant(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        spec = tmp_path / "c.md"
        spec.write_text(CONFORMANT)
        assert main(["structure", str(spec)]) == 0
        assert _out(capsys)["status"] == "pass"

    def test_missing_heading(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        spec = tmp_path / "c.md"
        spec.write_text(CONFORMANT.replace("## Verification\n- A check\n", ""))
        assert main(["structure", str(spec)]) == 1
        headings = [f["heading"] for f in _out(capsys)["findings"]]
        assert "## Verification" in headings

    def test_open_items_not_required(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        spec = tmp_path / "c.md"
        spec.write_text(CONFORMANT)  # no `## Open Items`
        assert main(["structure", str(spec)]) == 0
        assert _out(capsys)["findings"] == []

    def test_empty(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        spec = tmp_path / "c.md"
        spec.write_text("   \n")
        assert main(["structure", str(spec)]) == 1
        assert "empty" in _out(capsys)["findings"][0]["detail"]


# ── tally (D4, D5) ───────────────────────────────────────────────────────────


def _votes(sub: bool, nu: bool, ex: bool) -> dict:
    return {"substantive": sub, "needs_user": nu, "exclusion": ex}


class TestTally:
    def _panel(self, *triples: tuple[bool, bool, bool]) -> dict:
        return {j: _votes(*t) for j, t in zip(
            ["builds-wrong-thing", "implementer-blocked", "scope-intent-drift"], triples)}

    def test_needs_user_overrides_all(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # one needs_user vote wins even against 2 substantive + 2 exclusion
        panel = self._panel((True, True, True), (True, False, True), (False, False, False))
        vf = _write(tmp_path, "v.json", {"f1": panel})
        assert main(["tally", str(vf)]) == 0
        assert _out(capsys)["f1"] == "needs-user"

    def test_proposed_non_goal(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        panel = self._panel((True, False, True), (False, False, True), (False, False, False))
        vf = _write(tmp_path, "v.json", {"f1": panel})
        main(["tally", str(vf)])
        assert _out(capsys)["f1"] == "proposed-non-goal"

    def test_auto_fixable(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        panel = self._panel((True, False, False), (True, False, False), (False, False, True))
        vf = _write(tmp_path, "v.json", {"f1": panel})
        main(["tally", str(vf)])
        assert _out(capsys)["f1"] == "auto-fixable"

    def test_below_bar(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        panel = self._panel((True, False, False), (False, False, False), (False, False, False))
        vf = _write(tmp_path, "v.json", {"f1": panel})
        main(["tally", str(vf)])
        assert _out(capsys)["f1"] == "below-bar"

    def test_short_panel_rejected(self, tmp_path: Path) -> None:
        panel = {"builds-wrong-thing": _votes(True, False, False),
                 "implementer-blocked": _votes(True, False, False)}
        vf = _write(tmp_path, "v.json", {"f1": panel})
        assert main(["tally", str(vf)]) == 1

    def test_head_to_head_winner(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        votes = {"builds-wrong-thing": "A", "implementer-blocked": "B", "scope-intent-drift": "A"}
        vf = _write(tmp_path, "hh.json", {"## Solution / ### Overview": votes})
        assert main(["tally", "--head-to-head", str(vf)]) == 0
        result = _out(capsys)["## Solution / ### Overview"]
        assert result["winner"] == "A"

    def test_head_to_head_no_majority(self, tmp_path: Path) -> None:
        votes = {"builds-wrong-thing": "A", "implementer-blocked": "B", "scope-intent-drift": "skip"}
        vf = _write(tmp_path, "hh.json", {"x": votes})
        assert main(["tally", "--head-to-head", str(vf)]) == 1


# ── block-gate (D5) ──────────────────────────────────────────────────────────


class TestBlockGate:
    def test_one_unit_takeable(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        f = _write(tmp_path, "b.json", {"evidence_sections": ["## Design Decisions / ### D3"],
                                        "estimate_sections": ["## Design Decisions / ### D3"]})
        assert main(["block-gate", str(f)]) == 0
        r = _out(capsys)
        assert r["verdict"] == "takeable" and r["unit_count"] == 1

    def test_two_units_takeable(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        f = _write(tmp_path, "b.json", {"evidence_sections": ["## A / ### D1", "## A / ### D2"],
                                        "estimate_sections": ["## A / ### D1"]})
        main(["block-gate", str(f)])
        r = _out(capsys)
        assert r["verdict"] == "takeable" and r["unit_count"] == 2  # union, not sum (3)

    def test_three_units_blocked(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        f = _write(tmp_path, "b.json", {"evidence_sections": ["## A / ### D1", "## A / ### D2"],
                                        "estimate_sections": ["## A / ### D3"]})
        main(["block-gate", str(f)])
        assert _out(capsys)["verdict"] == "blocked"

    def test_reversal_boolean_forces_block(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        f = _write(tmp_path, "b.json", {"evidence_sections": ["## A / ### D1"],
                                        "estimate_sections": [], "reverses_non_goal": True})
        main(["block-gate", str(f)])
        r = _out(capsys)
        assert r["verdict"] == "blocked" and r["unit_count"] == 1  # blocked despite 1 unit


# ── floor (D8) ───────────────────────────────────────────────────────────────


class TestFloor:
    def test_clean(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        spec = tmp_path / "c.md"
        spec.write_text(CONFORMANT)
        assert main(["floor", str(spec)]) == 0
        assert _out(capsys)["status"] == "pass"

    def test_both_violations(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # missing ## Verification (structure) + uncited bullet (citations)
        text = CONFORMANT.replace("## Verification\n- A check\n", "").replace("- A thing (D1)", "- A thing")
        spec = tmp_path / "c.md"
        spec.write_text(text)
        assert main(["floor", str(spec)]) == 1
        sources = {f["source"] for f in _out(capsys)["findings"]}
        assert sources == {"structure", "citations"}

    def test_dedup_shared_heading(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # remove `### What gets built` entirely — both structure and citations flag it
        text = CONFORMANT.replace("### What gets built\n- A thing (D1)\n\n", "")
        spec = tmp_path / "c.md"
        spec.write_text(text)
        assert main(["floor", str(spec)]) == 1
        findings = _out(capsys)["findings"]
        wgb = [f for f in findings if f["heading"] == "### What gets built"]
        assert len(wgb) == 1 and wgb[0]["source"] == "structure"


# ── decisions summary + briefing (D9) ────────────────────────────────────────


class TestDecisionsSummary:
    def test_status_derivation(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        records = [
            {"id": "R1", "kind": "decision", "title": "taken one", "taken": "opt"},
            {"id": "R2", "kind": "decision", "title": "blocked one", "untakeable": "reverses X"},
            {"id": "R3", "kind": "decision", "title": "pending one"},
            {"id": "R4", "kind": "non-goal-proposal", "title": "proposal"},
        ]
        d = _write(tmp_path, "DECISIONS.json", records)
        assert main(["decisions", "summary", str(d)]) == 0
        proj = {r["id"]: r["status"] for r in _out(capsys)}
        assert proj == {"R1": "taken", "R2": "blocked", "R3": "pending", "R4": "proposal"}

    def test_depends_on_mechanical(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # R2's post-take radius overlaps R1's → R2 depends on R1 (later on earlier)
        records = [
            {"id": "R1", "kind": "decision", "taken": "a", "post_take_radius": {"sections": ["## S / ### D1"], "atoms": 3}},
            {"id": "R2", "kind": "decision", "taken": "b", "post_take_radius": {"sections": ["## S / ### D1"], "atoms": 2}},
        ]
        d = _write(tmp_path, "DECISIONS.json", records)
        main(["decisions", "summary", str(d)])
        proj = {r["id"]: r["depends_on"] for r in _out(capsys)}
        assert proj["R2"] == ["R1"] and proj["R1"] == []


class TestBriefing:
    def test_renders_every_record_root_first(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        records = [
            {"id": "R1", "kind": "decision", "title": "root", "taken": "a",
             "post_take_radius": {"sections": ["## S / ### D1"], "atoms": 3}},
            {"id": "R2", "kind": "decision", "title": "dependent", "taken": "b",
             "post_take_radius": {"sections": ["## S / ### D1"], "atoms": 2}},
        ]
        d = _write(tmp_path, "DECISIONS.json", records)
        assert main(["briefing", str(d)]) == 0
        out = capsys.readouterr().out
        assert "R1: root" in out and "R2: dependent" in out
        assert out.index("R1: root") < out.index("R2: dependent")  # root first

    def test_semantic_cycle_still_renders_all(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # a stored semantic back-edge closes a cycle against the mechanical DAG
        records = [
            {"id": "R1", "kind": "decision", "title": "one", "taken": "a",
             "post_take_radius": {"sections": ["## S / ### D1"], "atoms": 3},
             "semantic_depends_on": ["R2"]},
            {"id": "R2", "kind": "decision", "title": "two", "taken": "b",
             "post_take_radius": {"sections": ["## S / ### D1"], "atoms": 2}},
        ]
        d = _write(tmp_path, "DECISIONS.json", records)
        assert main(["briefing", str(d)]) == 0
        out = capsys.readouterr().out
        assert "R1: one" in out and "R2: two" in out  # never exits without a briefing
        assert "circular" in out

    def test_empty(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        d = _write(tmp_path, "DECISIONS.json", [])
        assert main(["briefing", str(d)]) == 0
        assert "No decisions recorded" in capsys.readouterr().out


# ── cross-script schema round-trip (D9, Artifacts) ──────────────────────────


class TestCrossScriptRoundTrip:
    """A record WRITTEN by improve_files is READ back by spec_checks without loss."""

    def test_round_trip(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        src = tmp_path / "concept.md"
        src.write_text("content")

        # write side (improve_files.py)
        assert improve_files.main(["append-decision", str(src), "--kind", "decision",
                                   "--title", "Cross-script", "--finding", "surfaced by X",
                                   "--finding-atoms", '["L1","L2"]']) == 0
        capsys.readouterr()
        assert improve_files.main(["update-decision", str(src), "--id", "R1", "--set",
                                   json.dumps({"taken": "option A", "taken_by": "auto",
                                               "confidence": "high", "review_first": True,
                                               "post_take_radius": {"sections": ["## S / ### D1"], "atoms": 4}})]) == 0
        capsys.readouterr()

        decisions = tmp_path / "concept-DECISIONS.json"

        # read side (spec_checks.py) — decisions summary
        assert main(["decisions", "summary", str(decisions)]) == 0
        proj = _out(capsys)[0]
        assert proj["id"] == "R1"
        assert proj["status"] == "taken"
        assert proj["title"] == "Cross-script"
        assert proj["confidence"] == "high"
        assert proj["review_first"] is True

        # read side — briefing renders it
        assert main(["briefing", str(decisions)]) == 0
        out = capsys.readouterr().out
        assert "R1: Cross-script" in out
        assert "option A" in out


# ── atoms: minimal ledger core (D13) — Gate B slice ─────────────────────────


class TestAtoms:
    def _extract(self, tmp_path: Path, text: str, capsys: pytest.CaptureFixture[str]) -> tuple[Path, Path, list]:
        doc = tmp_path / "concept-auto-improve.md"
        doc.write_text(text)
        ledger = tmp_path / "concept-ATOMS.json"
        assert main(["atoms", "extract", str(doc), "--ledger", str(ledger), "--write"]) == 0
        atoms = _out(capsys)["atoms"]
        return doc, ledger, atoms

    def test_extract_mechanical(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _, _, atoms = self._extract(tmp_path, CONFORMANT, capsys)
        types = {a["type"] for a in atoms}
        assert "heading" in types
        assert "citation" in types
        # the cited deliverable bullet became a citation atom
        cites = [a for a in atoms if a["type"] == "citation"]
        assert any("A thing" in a["text"] for a in cites)
        # ids and hashes assigned
        assert all(a["id"] and a["hash"].startswith("sha256:") for a in atoms)

    def test_extract_deterministic(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _, _, a1 = self._extract(tmp_path, CONFORMANT, capsys)
        (tmp_path / "concept-ATOMS.json").unlink()
        doc2 = tmp_path / "d2.md"
        doc2.write_text(CONFORMANT)
        main(["atoms", "extract", str(doc2)])
        a2 = _out(capsys)["atoms"]
        # same ids, hashes, anchors — no run-to-run jitter
        assert [(a["id"], a["hash"], a["anchor"]) for a in a1] == \
               [(a["id"], a["hash"], a["anchor"]) for a in a2]

    def test_reanchor_stable_on_unchanged_doc(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        doc, ledger, _ = self._extract(tmp_path, CONFORMANT, capsys)
        assert main(["atoms", "reanchor", str(doc), "--ledger", str(ledger)]) == 0
        delta = _out(capsys)
        assert delta["relocated"] == [] and delta["vanished"] == []

    def test_reanchor_relocation_and_vanish(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        doc = tmp_path / "concept-auto-improve.md"
        doc.write_text("## A\n\n- item (D1)\n\n## B\n")
        ledger = tmp_path / "concept-ATOMS.json"
        main(["atoms", "extract", str(doc), "--ledger", str(ledger), "--write"])
        capsys.readouterr()
        # rename ## A → ## Renamed: the heading atom vanishes; the bullet relocates
        doc.write_text("## Renamed\n\n- item (D1)\n\n## B\n")
        main(["atoms", "reanchor", str(doc), "--ledger", str(ledger)])
        delta = _out(capsys)
        relocated_new = {r["new"] for r in delta["relocated"]}
        assert "## Renamed" in relocated_new       # the bullet moved section
        assert delta["vanished"]                    # the `## A` heading atom vanished

    def test_record_verdicts_echoes_applied_count(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        doc, ledger, atoms = self._extract(tmp_path, CONFORMANT, capsys)
        target = atoms[0]["id"]
        verdicts = tmp_path / "verdicts.json"
        verdicts.write_text(json.dumps({"atom_verdicts": [
            {"atom_id": target, "state": "verified", "computed_against_hash": atoms[0]["hash"],
             "input_set": {"sections": ["## Situation"], "external": []}},
        ]}))
        assert main(["atoms", "record-verdicts", "--ledger", str(ledger), "--verdicts", str(verdicts)]) == 0
        assert _out(capsys)["applied"] == 1  # echoed count the JS asserts against its marshal
        # persisted
        led = json.loads(ledger.read_text())
        rec = next(a for a in led["atoms"] if a["id"] == target)
        assert rec["verdict"]["state"] == "verified"

    def test_record_verdicts_new_atoms_and_vanish(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        doc, ledger, atoms = self._extract(tmp_path, CONFORMANT, capsys)
        drop_id = atoms[0]["id"]
        verdicts = tmp_path / "v.json"
        verdicts.write_text(json.dumps({
            "atom_verdicts": [],
            "reanchor_delta": {"relocated": [], "vanished": [drop_id]},
            "new_atoms": [{"type": "claim", "anchor": "## Problem", "text": "a new claim",
                           "verdict": {"state": "unverified", "computed_against_hash": None},
                           "input_set": {"sections": ["## Problem"], "external": []},
                           "churn": {"verdict_flips": 0, "fix_count": 0}, "lineage_id": "Lx"}],
        }))
        main(["atoms", "record-verdicts", "--ledger", str(ledger), "--verdicts", str(verdicts)])
        result = _out(capsys)
        assert result["new_atoms_added"] == 1
        led = json.loads(ledger.read_text())
        ids = {a["id"] for a in led["atoms"]}
        assert drop_id not in ids                       # vanished atom dropped
        assert any(a.get("text") == "a new claim" for a in led["atoms"])  # new atom added w/ id


# ── CLI dispatch ─────────────────────────────────────────────────────────────


class TestCLI:
    def test_no_args(self) -> None:
        assert main([]) == 1

    def test_unknown_command(self) -> None:
        assert main(["explode"]) == 1

    def test_decisions_needs_subcommand(self) -> None:
        assert main(["decisions"]) == 1
