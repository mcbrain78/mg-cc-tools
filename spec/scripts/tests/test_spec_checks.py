"""Determinism fixtures for spec_checks.py (concept D4, D5, D8, D9)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from spec.scripts import improve_files, spec_checks
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
        assert proj["finding_atoms"] == ["L1", "L2"]  # carried for continuation atoms-radius recompute

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


# ── atoms: full ledger (D13) — Phase 2 ──────────────────────────────────────


def _atom(aid, lid, atype, anchor, text, state="unverified", hash_=None, chash=None,
          fix_count=0, flips=0, last=None, sections=None, external=None, span=None):
    from spec.scripts.spec_checks import _atom_hash
    h = hash_ or _atom_hash(text)
    return {
        "id": aid, "lineage_id": lid, "type": atype, "anchor": anchor, "text": text,
        "hash": h, "span": span or {"start": 0, "end": len(text)},
        "input_set": {"sections": sections or [anchor], "external": external or []},
        "verdict": {"state": state, "computed_against_hash": chash},
        "churn": {"verdict_flips": flips, "fix_count": fix_count, "last_conclusion": last},
    }


def _ledger(tmp_path: Path, atoms: list, macro: list | None = None) -> Path:
    p = tmp_path / "L.json"
    p.write_text(json.dumps({"atoms": atoms, "macro_findings": macro or []}))
    return p


class TestCanonicalize:
    def test_bare_dblock_resolves_to_chain(self) -> None:
        from spec.scripts.spec_checks import _canonicalize
        doc = "## Design Decisions\n\n### D3: A decision\nbody\n"
        assert _canonicalize("### D3", doc) == "## Design Decisions / ### D3: A decision"

    def test_already_canonical_passthrough(self) -> None:
        from spec.scripts.spec_checks import _canonicalize
        doc = "## Situation\ntext\n"
        assert _canonicalize("## Situation", doc) == "## Situation"


class TestMerge:
    def _doc(self, tmp_path: Path, text: str) -> tuple[Path, Path]:
        doc = tmp_path / "concept-auto-improve.md"
        doc.write_text(text)
        ledger = tmp_path / "concept-ATOMS.json"
        main(["atoms", "extract", str(doc), "--ledger", str(ledger), "--write"])
        return doc, ledger

    def _merge(self, tmp_path: Path, doc: Path, ledger: Path, cands: list, capsys) -> list:
        cf = tmp_path / "cand.json"
        cf.write_text(json.dumps({"candidates": cands}))
        capsys.readouterr()
        assert main(["atoms", "merge", str(doc), "--ledger", str(ledger),
                     "--candidates", str(cf), "--write"]) == 0
        return _out(capsys)["merged_atoms"]

    def test_same_type_overlap_collapses_to_widest(self, tmp_path: Path, capsys) -> None:
        doc, ledger = self._doc(tmp_path, "## S\n\nThe cache is cold today.\n")
        merged = self._merge(tmp_path, doc, ledger, [
            {"type": "claim", "text": "The cache is cold"},
            {"type": "claim", "text": "The cache is cold today"},
        ], capsys)
        assert len(merged) == 1
        assert merged[0]["text"] == "The cache is cold today"  # widest

    def test_disjoint_survive(self, tmp_path: Path, capsys) -> None:
        doc, ledger = self._doc(tmp_path, "## S\n\nAlpha statement here. Beta statement there.\n")
        merged = self._merge(tmp_path, doc, ledger, [
            {"type": "claim", "text": "Alpha statement here"},
            {"type": "claim", "text": "Beta statement there"},
        ], capsys)
        assert len(merged) == 2

    def test_cross_type_scope_precedence(self, tmp_path: Path, capsys) -> None:
        doc, ledger = self._doc(
            tmp_path, "## Scope\n\n### What gets built\n\nBuild the widget carefully now.\n")
        merged = self._merge(tmp_path, doc, ledger, [
            {"type": "claim", "text": "Build the widget"},
            {"type": "assumption", "text": "Build the widget carefully now"},
        ], capsys)
        assert len(merged) == 1
        assert merged[0]["type"] == "scope-item"  # section-native precedence

    def test_drop_mechanical_overlap(self, tmp_path: Path, capsys) -> None:
        doc, ledger = self._doc(
            tmp_path, "## Scope\n\n### What gets built\n\n- A thing (D1)\n")
        # a prose candidate whose text IS the citation bullet must be dropped
        merged = self._merge(tmp_path, doc, ledger, [
            {"type": "scope-item", "text": "- A thing (D1)"},
        ], capsys)
        assert merged == []


class TestMarkDirty:
    def test_input_set_propagation_bare_dblock(self, tmp_path: Path, capsys) -> None:
        doc = tmp_path / "concept-auto-improve.md"
        doc.write_text("## Design Decisions\n\n### D3: Foo\nbody\n\n## Other\ntext\n")
        # an atom in ## Other whose CHECK reads ### D3 (input_set), own text unchanged
        atom = _atom("a1", "L1", "claim", "## Other", "text",
                     sections=["## Design Decisions / ### D3"])
        ledger = _ledger(tmp_path, [atom])
        assert main(["atoms", "mark-dirty", str(doc), "--ledger", str(ledger),
                     "--touched", json.dumps(["### D3"])]) == 0
        out = _out(capsys)
        assert out["dirty"] == ["a1"]  # bare ### D3 matched canonical input entry


class TestCoverage:
    def test_counts_and_incomplete(self, tmp_path: Path, capsys) -> None:
        from spec.scripts.spec_checks import _atom_hash
        atoms = [
            _atom("h1", "L0", "heading", "## S", "## S"),                       # excluded
            _atom("a1", "L1", "claim", "## S", "c1", state="verified", chash=_atom_hash("c1")),
            _atom("a2", "L2", "claim", "## S", "c2", state="unverifiable"),
            _atom("a3", "L3", "claim", "## S", "c3", state="dirty"),
            _atom("a4", "L4", "claim", "## S", "c4", state="unverified"),
            _atom("a5", "L5", "claim", "## S", "c5", state="verified", chash="sha256:stale"),
        ]
        ledger = _ledger(tmp_path, atoms)
        assert main(["atoms", "coverage", "--ledger", str(ledger)]) == 0
        out = _out(capsys)
        assert out["total"] == 5                # heading excluded
        assert out["verified"] == 1             # only a1 (a5 hash-stale → dirty)
        assert out["unverifiable"] == 1
        assert out["complete"] is False
        assert "a4" in out["never_verified"]

    def test_complete_when_all_settled(self, tmp_path: Path, capsys) -> None:
        from spec.scripts.spec_checks import _atom_hash
        atoms = [
            _atom("h1", "L0", "heading", "## S", "## S"),
            _atom("a1", "L1", "claim", "## S", "c1", state="verified", chash=_atom_hash("c1")),
            _atom("a2", "L2", "claim", "## S", "c2", state="unverifiable"),
        ]
        ledger = _ledger(tmp_path, atoms)
        main(["atoms", "coverage", "--ledger", str(ledger)])
        assert _out(capsys)["complete"] is True


class TestRadius:
    def test_anchor_units(self, tmp_path: Path, capsys) -> None:
        atoms = [
            _atom("a1", "L1", "claim", "## A / ### D1", "x"),
            _atom("a2", "L2", "claim", "## A / ### D1", "y"),
            _atom("a3", "L3", "claim", "## B", "z"),
        ]
        ledger = _ledger(tmp_path, atoms)
        assert main(["atoms", "radius", "--ledger", str(ledger),
                     "--atoms", json.dumps(["L1", "L3"])]) == 0
        out = _out(capsys)
        assert out["sections"] == ["## A / ### D1", "## B"]
        assert out["units"] == 2 and out["atoms"] == 2


class TestChurnCheck:
    def test_escalation_sets(self, tmp_path: Path, capsys) -> None:
        atoms = [
            _atom("a1", "L1", "claim", "## S", "x", flips=2),               # flip escalate
            _atom("a2", "L2", "claim", "## S", "y", flips=1),               # below flip bar
            _atom("a3", "L3", "claim", "## S", "z", fix_count=3),           # fix escalate
            _atom("a4", "L4", "claim", "## S", "w", fix_count=1),           # below fix bar
            _atom("a5", "L1", "claim", "## S", "v", flips=5),               # dup lineage L1
        ]
        macro = [
            {"id": "builds-wrong:## A", "fix_count": 2},                    # escalate
            {"id": "drift:## B", "fix_count": 1},                          # below bar
        ]
        ledger = _ledger(tmp_path, atoms, macro)
        assert main(["atoms", "churn-check", "--ledger", str(ledger)]) == 0
        out = _out(capsys)
        assert out["flip_escalate_lineages"] == ["L1"]         # sorted distinct
        assert out["fix_escalate_lineages"] == ["L3"]
        assert out["escalate_macros"] == ["builds-wrong:## A"]

    def test_empty_ledger(self, tmp_path: Path, capsys) -> None:
        ledger = _ledger(tmp_path, [])
        assert main(["atoms", "churn-check", "--ledger", str(ledger)]) == 0
        out = _out(capsys)
        assert out == {"flip_escalate_lineages": [], "fix_escalate_lineages": [],
                       "escalate_macros": []}


class TestMacroIds:
    def test_canonicalizes_and_joins(self, tmp_path: Path, capsys) -> None:
        doc = tmp_path / "concept.md"
        doc.write_text("## Design Decisions\n\n### D3: Foo\nbody\n\n## Scope\ntext\n")
        findings = [
            # bare ### D3 canonicalizes to its chain; duplicate collapses; sorted
            {"class": "builds-wrong-thing", "sections": ["## Scope", "### D3", "### D3"]},
            {"class": "scope-intent-drift", "sections": ["### D3"]},
        ]
        assert main(["atoms", "macro-ids", "--doc", str(doc),
                     "--findings", json.dumps(findings)]) == 0
        out = _out(capsys)
        assert out["ids"] == [
            "builds-wrong-thing:## Design Decisions / ### D3: Foo|## Scope",
            "scope-intent-drift:## Design Decisions / ### D3: Foo",
        ]

    def test_empty_findings(self, tmp_path: Path, capsys) -> None:
        doc = tmp_path / "concept.md"
        doc.write_text("## S\ntext\n")
        assert main(["atoms", "macro-ids", "--doc", str(doc), "--findings", "[]"]) == 0
        assert _out(capsys)["ids"] == []


class TestLineageAndChurn:
    def _apply(self, tmp_path: Path, ledger: Path, vf: dict, capsys) -> dict:
        vfile = tmp_path / "vf.json"
        vfile.write_text(json.dumps(vf))
        capsys.readouterr()
        assert main(["atoms", "record-verdicts", "--ledger", str(ledger),
                     "--verdicts", str(vfile)]) == 0
        return json.loads(ledger.read_text())

    def test_successor_inherits_lineage_and_bumps_fix_count(self, tmp_path: Path, capsys) -> None:
        ledger = _ledger(tmp_path, [_atom("a1", "L1", "claim", "## S", "old", fix_count=1)])
        led = self._apply(tmp_path, ledger, {
            "reanchor_delta": {"vanished": ["a1"]},
            "new_atoms": [{"type": "claim", "anchor": "## S", "text": "new", "span": {"start": 0, "end": 3}}],
        }, capsys)
        succ = next(a for a in led["atoms"] if a["text"] == "new")
        assert succ["lineage_id"] == "L1"                 # identity survives the fix
        assert succ["churn"]["fix_count"] == 2            # inherited 1 + this fix

    def test_split_forks_lineage(self, tmp_path: Path, capsys) -> None:
        ledger = _ledger(tmp_path, [_atom("a1", "L1", "claim", "## S", "old", fix_count=1)])
        led = self._apply(tmp_path, ledger, {
            "reanchor_delta": {"vanished": ["a1"]},
            "new_atoms": [
                {"type": "claim", "anchor": "## S", "text": "n1", "span": {"start": 0, "end": 2}},
                {"type": "claim", "anchor": "## S", "text": "n2", "span": {"start": 3, "end": 5}},
            ],
        }, capsys)
        lids = {a["text"]: a["lineage_id"] for a in led["atoms"]}
        assert lids["n1"] == "L1" and lids["n2"] == "L1"  # both inherit — a split forks

    def test_merge_inherits_highest_churn(self, tmp_path: Path, capsys) -> None:
        ledger = _ledger(tmp_path, [
            _atom("a1", "L1", "claim", "## S", "o1", fix_count=1),
            _atom("a2", "L2", "claim", "## S", "o2", fix_count=3),
        ])
        led = self._apply(tmp_path, ledger, {
            "reanchor_delta": {"vanished": ["a1", "a2"]},
            "new_atoms": [{"type": "claim", "anchor": "## S", "text": "merged", "span": {"start": 0, "end": 6}}],
        }, capsys)
        succ = next(a for a in led["atoms"] if a["text"] == "merged")
        assert succ["lineage_id"] == "L2"                 # highest-churn ancestor
        assert succ["churn"]["fix_count"] == 4            # 3 + this fix

    def test_retire_no_successor(self, tmp_path: Path, capsys) -> None:
        from spec.scripts.spec_checks import _atom_hash
        ledger = _ledger(tmp_path, [
            _atom("a1", "L1", "claim", "## S", "gone"),
            _atom("a2", "L2", "claim", "## S", "kept", state="verified", chash=_atom_hash("kept")),
        ])
        led = self._apply(tmp_path, ledger, {"reanchor_delta": {"vanished": ["a1"]}}, capsys)
        ids = {a["id"] for a in led["atoms"]}
        assert "a1" not in ids                            # retired, dropped from denominator
        capsys.readouterr()  # drain the record-verdicts emit before reading coverage
        main(["atoms", "coverage", "--ledger", str(ledger)])
        assert _out(capsys)["complete"] is True           # complete without the retired atom

    def test_verdict_flips_only_on_conclusion_change(self, tmp_path: Path, capsys) -> None:
        ledger = _ledger(tmp_path, [_atom("a1", "L1", "claim", "## S", "x")])
        self._apply(tmp_path, ledger, {"atom_verdicts": [
            {"atom_id": "a1", "state": "verified", "finding_conclusion": False}]}, capsys)
        led = self._apply(tmp_path, ledger, {"atom_verdicts": [
            {"atom_id": "a1", "state": "verified", "finding_conclusion": True}]}, capsys)  # changed
        assert next(a for a in led["atoms"] if a["id"] == "a1")["churn"]["verdict_flips"] == 1
        led = self._apply(tmp_path, ledger, {"atom_verdicts": [
            {"atom_id": "a1", "state": "verified", "finding_conclusion": True}]}, capsys)  # same
        assert next(a for a in led["atoms"] if a["id"] == "a1")["churn"]["verdict_flips"] == 1  # no bump

    def test_no_flip_on_state_cycle(self, tmp_path: Path, capsys) -> None:
        # verified → dirty → verified with no finding_conclusion must NOT flip
        ledger = _ledger(tmp_path, [_atom("a1", "L1", "claim", "## S", "x")])
        for st in ("verified", "dirty", "verified"):
            self._apply(tmp_path, ledger, {"atom_verdicts": [{"atom_id": "a1", "state": st}]}, capsys)
        led = json.loads(ledger.read_text())
        assert next(a for a in led["atoms"] if a["id"] == "a1")["churn"]["verdict_flips"] == 0

    def test_macro_fix_count(self, tmp_path: Path, capsys) -> None:
        ledger = _ledger(tmp_path, [_atom("a1", "L1", "claim", "## S", "x")])
        for _ in range(2):
            self._apply(tmp_path, ledger, {"macro_findings": [{"id": "contradiction:## S|## T", "fixed": True}]}, capsys)
        led = json.loads(ledger.read_text())
        mf = next(m for m in led["macro_findings"] if m["id"] == "contradiction:## S|## T")
        assert mf["fix_count"] == 2

    def test_overwrite_not_duplicate(self, tmp_path: Path, capsys) -> None:
        from spec.scripts.spec_checks import _atom_hash
        ledger = _ledger(tmp_path, [_atom("a1", "L1", "claim", "## S", "x")])
        self._apply(tmp_path, ledger, {"atom_verdicts": [
            {"atom_id": "a1", "state": "verified", "computed_against_hash": _atom_hash("x")}]}, capsys)
        led = self._apply(tmp_path, ledger, {"atom_verdicts": [
            {"atom_id": "a1", "state": "unverifiable"}]}, capsys)
        a1s = [a for a in led["atoms"] if a["id"] == "a1"]
        assert len(a1s) == 1 and a1s[0]["verdict"]["state"] == "unverifiable"  # overwritten, not duplicated


class TestExternalStaleness:
    def test_reanchor_flags_changed_external(self, tmp_path: Path, capsys) -> None:
        from spec.scripts.spec_checks import _atom_hash
        ext = tmp_path / "code.py"
        ext.write_text("original\n")
        doc = tmp_path / "concept-auto-improve.md"
        doc.write_text("## S\n\nthe claim text\n")
        atom = _atom("a1", "L1", "claim", "## S", "the claim text",
                     external=[{"path": str(ext), "hash": _atom_hash("original\n")}])
        ledger = _ledger(tmp_path, [atom])
        ext.write_text("CHANGED\n")  # cited code changed between runs
        assert main(["atoms", "reanchor", str(doc), "--ledger", str(ledger)]) == 0
        assert _out(capsys)["external_stale"] == ["a1"]


class TestDblockTyping:
    def test_dblock_typed_and_checkable(self, tmp_path: Path, capsys) -> None:
        doc = tmp_path / "concept-auto-improve.md"
        doc.write_text(CONFORMANT)
        assert main(["atoms", "extract", str(doc)]) == 0
        atoms = _out(capsys)["atoms"]
        dblocks = [a for a in atoms if a["type"] == "d-block"]
        assert any("### D1:" in a["text"] for a in dblocks)  # ### Dn: is a checkable d-block, not a plain heading


# ── usage-gate ───────────────────────────────────────────────────────────────

USAGE_OUTPUT = """\
You are currently using your subscription to power your Claude Code usage

Current session: 93% used · resets Jul 29, 6:49pm (Europe/Berlin)
Current week (all models): 28% used · resets Aug 3, 8:59pm (Europe/Berlin)
Current week (Fable): 0% used
"""


class _Proc:
    returncode = 0

    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.stderr = ""


class TestUsageGate:
    def _stub(self, monkeypatch, body: str = USAGE_OUTPUT) -> list:
        """Capture the argv the gate would run, returning a canned /usage body."""
        seen: list = []

        def fake_run(argv, **kwargs):
            seen.append(argv)
            return _Proc(json.dumps({"result": body, "num_turns": 0}))

        monkeypatch.setattr(spec_checks.subprocess, "run", fake_run)
        return seen

    def test_runs_without_persisting_a_session(self, monkeypatch) -> None:
        """Without the flag, every check leaves a /usage transcript that then
        surfaces as a phantom row in pickers scanning ~/.claude/projects."""
        seen = self._stub(monkeypatch)
        assert main(["usage-gate"]) == 0
        assert "--no-session-persistence" in seen[0]
        assert seen[0][:4] == ["claude", "-p", "/usage", "--output-format"]

    def test_pause_when_session_over_max(self, monkeypatch, capsys) -> None:
        self._stub(monkeypatch)
        assert main(["usage-gate", "--session-max", "75"]) == 0
        out = _out(capsys)
        assert out["verdict"] == "PAUSE"
        assert out["binding"] == "session"
        assert out["session_pct"] == 93
        assert out["resume_cron"] and out["resume_human"]

    def test_ok_when_under_max(self, monkeypatch, capsys) -> None:
        self._stub(monkeypatch)
        assert main(["usage-gate", "--session-max", "95"]) == 0
        out = _out(capsys)
        assert out["verdict"] == "OK" and out["binding"] is None

    def test_unparseable_output_degrades_to_error(self, monkeypatch, capsys) -> None:
        self._stub(monkeypatch, body="nothing useful here")
        assert main(["usage-gate"]) == 0
        assert _out(capsys)["verdict"] == "ERROR"

    def test_reset_on_the_hour_still_schedules_a_resume(self, monkeypatch, capsys) -> None:
        """Observed live: 'Aug 3, 9pm'. Failing to parse it pauses with no wake-up."""
        body = USAGE_OUTPUT.replace("resets Jul 29, 6:49pm", "resets Jul 29, 7pm")
        self._stub(monkeypatch, body=body)
        assert main(["usage-gate", "--session-max", "75"]) == 0
        out = _out(capsys)
        assert out["verdict"] == "PAUSE" and out["binding"] == "session"
        assert out["resume_cron"] and out["resume_human"]


# ── CLI dispatch ─────────────────────────────────────────────────────────────


class TestCLI:
    def test_no_args(self) -> None:
        assert main([]) == 1

    def test_unknown_command(self) -> None:
        assert main(["explode"]) == 1

    def test_decisions_needs_subcommand(self) -> None:
        assert main(["decisions"]) == 1
