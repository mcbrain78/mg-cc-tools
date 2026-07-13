"""Tests for milestone_checks.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec.scripts.milestone_checks import (
    _classify_source,
    _extract_decision_ids,
    _parse_current_milestone,
    _parse_deliverable_bullets,
    _parse_findings,
    _parse_milestones_versions,
    _parse_roadmap,
    _parse_spec_traceability,
    _ParseError,
    main,
)


# ── Builders / fixtures (inline, no fixture dir) ─────────────────────────────

SPEC = """\
# Demo Spec

## Design Decisions

### D1: First decision
**Choice:** do a thing.

### D2: Second decision
**Choice:** do another.

## Scope

### What gets built
- Deliverable one (D1)
- Deliverable two (D2)

### What does NOT get built
- Nothing here
"""

FINDINGS_SV1 = """\
| id | decision-ref | kind | what | suggested-addition | severity |
|----|--------------|------|------|--------------------|----------|
| SV-1 | D2 | missing-constraint | view needs GRANT | add GRANT | major |
"""

PROJECT_NO_CURRENT = (
    "# Project\n\n## Current State (post-v1.1)\n\n**Shipped:** v1.1\n"
)
MILESTONES_V11 = (
    "# Milestones\n\n## v1.1 milestone (Shipped: 2026-05-04)\n\n"
    "**Phases completed:** 24 phases, 64 plans\n\n---\n"
)
ARCHIVE_ROADMAP_24 = (
    "# Roadmap\n\n### Phase 1: A\n**Requirements**: INF-01\n\n"
    "### Phase 24: Z\n**Requirements**: DOC-05\n"
)
RESIDUE_ROADMAP = (
    "# Roadmap\n\n## Phases\n\n<details>\n<summary>v1.1 SHIPPED</summary>\n\n"
    "- [x] Phase 1: A (4/4)\n- [x] Phase 24: Z (2/2)\n\n</details>\n"
)


def project_current(version: str, name: str = "Demo") -> str:
    return f"# Project\n\n## Current Milestone: {version} {name}\n\n**Goal:** x\n"


def build_requirements(v1, spec_rows, v2=None, traceability="(placeholder)"):
    """v1: [(id, desc)]; spec_rows: [(req, source, note)]; v2: [(id, desc)]."""
    lines = ["# Requirements: Demo", "", "## v1 Requirements", "", "### Core"]
    for cid, desc in v1:
        lines.append(f"- [ ] **{cid}**: {desc}")
    if v2:
        lines += ["", "## v2 Requirements", "", "### Later"]
        for cid, desc in v2:
            lines.append(f"- **{cid}**: {desc}")
    lines += [
        "",
        "## Spec Traceability",
        "",
        "| REQ | Source | Note |",
        "|-----|--------|------|",
    ]
    for req, source, note in spec_rows:
        lines.append(f"| {req} | {source} | {note} |")
    lines += ["", "## Traceability", "", traceability, "", "---", "*footer*", ""]
    return "\n".join(lines)


def scaffold(tmp_path, monkeypatch, **files):
    """Build a .planning/ tree under tmp_path and chdir into it."""
    monkeypatch.chdir(tmp_path)
    planning = tmp_path / ".planning"
    planning.mkdir(exist_ok=True)
    simple = {
        "requirements": "REQUIREMENTS.md",
        "snapshot": ".requirements.snapshot",
        "roadmap": "ROADMAP.md",
        "project": "PROJECT.md",
        "milestones": "MILESTONES.md",
    }
    for key, name in simple.items():
        if files.get(key) is not None:
            (planning / name).write_text(files[key])
    if files.get("verification") is not None:
        research = planning / "research"
        research.mkdir(exist_ok=True)
        (research / "spec-verification.md").write_text(files["verification"])
    for name, content in (files.get("research_files") or {}).items():
        research = planning / "research"
        research.mkdir(exist_ok=True)
        (research / name).write_text(content)
    if files.get("archives_roadmap") or files.get("archives_req"):
        md = planning / "milestones"
        md.mkdir(exist_ok=True)
        for name, content in (files.get("archives_roadmap") or {}).items():
            (md / name).write_text(content)
        for name, content in (files.get("archives_req") or {}).items():
            (md / name).write_text(content)
    if files.get("gsd", True):
        (tmp_path / ".claude" / "get-shit-done").mkdir(parents=True, exist_ok=True)
    return planning


# ── Shared parsers ───────────────────────────────────────────────────────────


class TestSharedParsers:
    def test_decision_ids_noncontiguous(self) -> None:
        text = "## Design Decisions\n### D1: a\n### D3: b\n### D8: c\n"
        assert _extract_decision_ids(text) == {1, 3, 8}

    def test_bullets_toplevel_only_and_position_free(self) -> None:
        text = (
            "### What gets built\n"
            "- normal bullet (D1)\n"
            "  - nested bullet (D2)\n"
            "- trailing paren bullet (some note). (D3)\n"
            "prose line (D4)\n"
            "```\n- fenced bullet (D5)\n```\n"
            "#### deeper heading (D6)\n"
            "- after deeper (D7)\n"
            "### What does NOT get built\n"
            "- excluded (D9)\n"
        )
        parse = _parse_deliverable_bullets(text)
        assert parse.section_found is True
        assert len(parse.bullets) == 3
        assert [sorted(b.cited_ids) for b in parse.bullets] == [[1], [3], [7]]
        assert all(b.has_citation for b in parse.bullets)

    def test_bullets_section_absent(self) -> None:
        parse = _parse_deliverable_bullets("# Title\nno section here\n")
        assert parse.section_found is False
        assert parse.bullets == []

    def test_bullets_zero_bullets(self) -> None:
        text = "### What gets built\n\nprose only, no bullets\n\n### Next\n"
        parse = _parse_deliverable_bullets(text)
        assert parse.section_found is True
        assert parse.bullets == []

    def test_bullet_uncited(self) -> None:
        parse = _parse_deliverable_bullets("### What gets built\n- uncited bullet\n")
        assert len(parse.bullets) == 1
        assert parse.bullets[0].has_citation is False

    def test_classify_source_forms(self) -> None:
        assert _classify_source("D1").legal
        assert _classify_source("D1").dx_ids == {1}
        assert _classify_source("D1, D2").dx_ids == {1, 2}
        amended = _classify_source("D3; SV-1 (gate-approved)")
        assert amended.legal and amended.dx_ids == {3} and amended.sv_ids == {"SV-1"}
        assert amended.gate_approved
        multi = _classify_source("D3; SV-1, SV-2 (gate-approved)")
        assert multi.sv_ids == {"SV-1", "SV-2"}
        newreq = _classify_source("SV-1 (gate-approved)")
        assert newreq.legal and newreq.dx_ids == set() and newreq.sv_ids == {"SV-1"}
        assert _classify_source("garbage").legal is False
        assert _classify_source("D1 and stuff").legal is False

    def test_parse_roadmap(self) -> None:
        text = (
            "### Phase 24: A\n**Requirements**: [INF-01, INF-02]\n"
            "**Success Criteria**: whatever\n"
            "### Phase 24.1: B\n**Requirements**: DOC-03\n"
            "### Phase 25: C\n**Requirements**: TBD\n"
        )
        phases = _parse_roadmap(text)
        assert [p.number for p in phases] == [24.0, 24.1, 25.0]
        assert phases[0].req_ids == ["INF-01", "INF-02"]
        assert phases[1].req_ids == ["DOC-03"]
        assert phases[2].req_ids == []

    def test_milestones_versions(self) -> None:
        assert _parse_milestones_versions(MILESTONES_V11) == {"v1.1"}

    def test_milestones_garbled_raises(self) -> None:
        with pytest.raises(_ParseError):
            _parse_milestones_versions("# Milestones\n\n## broken (Shipped: 2026)\n")

    def test_current_milestone_variants(self) -> None:
        assert _parse_current_milestone(PROJECT_NO_CURRENT).present is False
        clean = _parse_current_milestone(project_current("v6.0"))
        assert clean.present and clean.version == "v6.0"
        garbled = _parse_current_milestone(
            "## Current Milestone: garbage name\n"
        )
        assert garbled.present is True and garbled.version is None

    def test_spec_traceability_absent_vs_malformed(self) -> None:
        assert _parse_spec_traceability("# Requirements\n\n## v1 Requirements\n") == []
        bad = (
            "## Spec Traceability\n\n| REQ | Source | Note |\n"
            "|-----|--------|------|\n| only-two | cols |\n"
        )
        with pytest.raises(_ParseError):
            _parse_spec_traceability(bad)

    def test_findings_header_only_and_malformed(self) -> None:
        header_only = (
            "| id | decision-ref | kind | what | suggested-addition | severity |\n"
            "|----|----|----|----|----|----|\n"
        )
        assert _parse_findings(header_only) == []
        with pytest.raises(_ParseError):
            _parse_findings("just prose, no table\n")


# ── citations ────────────────────────────────────────────────────────────────


class TestCitations:
    def test_compliant_spec_passes(self, tmp_path: Path) -> None:
        spec = tmp_path / "concept.md"
        spec.write_text(SPEC)
        assert main(["citations", str(spec)]) == 0

    def test_uncited_bullet_fails(self, tmp_path: Path) -> None:
        spec = tmp_path / "concept.md"
        spec.write_text(SPEC.replace("- Deliverable two (D2)", "- Deliverable two"))
        assert main(["citations", str(spec)]) == 1

    def test_unknown_dx_fails(self, tmp_path: Path) -> None:
        spec = tmp_path / "concept.md"
        spec.write_text(SPEC.replace("- Deliverable two (D2)", "- Deliverable two (D9)"))
        assert main(["citations", str(spec)]) == 1

    def test_missing_section_fails(self, tmp_path: Path) -> None:
        spec = tmp_path / "concept.md"
        spec.write_text("# T\n\n## Design Decisions\n### D1: a\n**Choice:** x\n")
        assert main(["citations", str(spec)]) == 1

    def test_bulletless_section_no_vacuous_pass(self, tmp_path: Path) -> None:
        spec = tmp_path / "concept.md"
        spec.write_text(
            "# T\n\n## Design Decisions\n### D1: a\n\n"
            "## Scope\n\n### What gets built\n\nprose, no bullets\n"
        )
        assert main(["citations", str(spec)]) == 1

    def test_no_d_blocks_fails(self, tmp_path: Path) -> None:
        spec = tmp_path / "concept.md"
        spec.write_text("# T\n\n### What gets built\n- thing (D1)\n")
        assert main(["citations", str(spec)]) == 1

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        assert main(["citations", str(tmp_path / "nope.md")]) == 1


# ── phase-start ──────────────────────────────────────────────────────────────


class TestPhaseStart:
    def test_highest_plus_one(self, tmp_path, monkeypatch, capsys) -> None:
        scaffold(tmp_path, monkeypatch,
                 archives_roadmap={"v1.1-ROADMAP.md": ARCHIVE_ROADMAP_24})
        assert main(["phase-start"]) == 0
        assert capsys.readouterr().out.strip() == "25"

    def test_decimal_floor(self, tmp_path, monkeypatch, capsys) -> None:
        scaffold(tmp_path, monkeypatch, archives_roadmap={
            "v1.1-ROADMAP.md": "### Phase 24.1: X\n**Requirements**: A-01\n"})
        assert main(["phase-start"]) == 0
        assert capsys.readouterr().out.strip() == "25"

    def test_no_archives_is_one(self, tmp_path, monkeypatch, capsys) -> None:
        scaffold(tmp_path, monkeypatch)
        assert main(["phase-start"]) == 0
        assert capsys.readouterr().out.strip() == "1"


# ── preflight ────────────────────────────────────────────────────────────────


def _verdict(capsys) -> str:
    return json.loads(capsys.readouterr().out)["verdict"]


class TestPreflight:
    def test_clean_over_residue(self, tmp_path, monkeypatch, capsys) -> None:
        scaffold(tmp_path, monkeypatch, project=PROJECT_NO_CURRENT,
                 milestones=MILESTONES_V11, roadmap=RESIDUE_ROADMAP,
                 archives_roadmap={"v1.1-ROADMAP.md": ARCHIVE_ROADMAP_24})
        assert main(["preflight", "v1.2"]) == 0
        assert _verdict(capsys) == "clean"

    def test_resume_pre_roadmap(self, tmp_path, monkeypatch, capsys) -> None:
        scaffold(tmp_path, monkeypatch, project=project_current("v1.2"),
                 milestones=MILESTONES_V11,
                 archives_roadmap={"v1.1-ROADMAP.md": ARCHIVE_ROADMAP_24})
        assert main(["preflight", "v1.2"]) == 0
        assert _verdict(capsys) == "resume-pre-roadmap"

    def test_live_phase_current(self, tmp_path, monkeypatch, capsys) -> None:
        scaffold(tmp_path, monkeypatch, project=project_current("v1.2"),
                 milestones=MILESTONES_V11,
                 roadmap="### Phase 25: New\n**Requirements**: NEW-01\n",
                 archives_roadmap={"v1.1-ROADMAP.md": ARCHIVE_ROADMAP_24})
        assert main(["preflight", "v1.2"]) == 1
        assert _verdict(capsys) == "live-phase-current"

    def test_open_other_milestone(self, tmp_path, monkeypatch, capsys) -> None:
        scaffold(tmp_path, monkeypatch, project=project_current("v1.2"),
                 milestones=MILESTONES_V11,
                 requirements=build_requirements([("C-01", "x")], [("C-01", "D1", "n")]),
                 archives_roadmap={"v1.1-ROADMAP.md": ARCHIVE_ROADMAP_24})
        assert main(["preflight", "v1.3"]) == 1
        assert _verdict(capsys) == "open-other-milestone"

    def test_version_completed(self, tmp_path, monkeypatch, capsys) -> None:
        scaffold(tmp_path, monkeypatch, project=PROJECT_NO_CURRENT,
                 milestones=MILESTONES_V11, roadmap=RESIDUE_ROADMAP)
        assert main(["preflight", "v1.1"]) == 1
        assert _verdict(capsys) == "version-completed"

    def test_abandoned_bookkeeping(self, tmp_path, monkeypatch, capsys) -> None:
        scaffold(tmp_path, monkeypatch, project=project_current("v9.9"),
                 milestones=MILESTONES_V11)
        assert main(["preflight", "v1.2"]) == 0
        assert _verdict(capsys) == "abandoned-bookkeeping"

    def test_abandoned_garbled_token(self, tmp_path, monkeypatch, capsys) -> None:
        scaffold(tmp_path, monkeypatch,
                 project="## Current Milestone: garbage-token\n",
                 milestones=MILESTONES_V11)
        assert main(["preflight", "v1.2"]) == 0
        assert _verdict(capsys) == "abandoned-bookkeeping"

    def test_bad_version(self, tmp_path, monkeypatch, capsys) -> None:
        scaffold(tmp_path, monkeypatch, project=PROJECT_NO_CURRENT)
        assert main(["preflight", "6.0"]) == 1
        assert _verdict(capsys) == "bad-version"

    def test_missing_project(self, tmp_path, monkeypatch, capsys) -> None:
        scaffold(tmp_path, monkeypatch)
        assert main(["preflight", "v1.2"]) == 1
        assert _verdict(capsys) == "missing-project"

    def test_missing_gsd(self, tmp_path, monkeypatch, capsys) -> None:
        scaffold(tmp_path, monkeypatch, project=PROJECT_NO_CURRENT, gsd=False)
        assert main(["preflight", "v1.2"]) == 1
        assert _verdict(capsys) == "missing-gsd"

    def test_garbled_milestones_fails_loud(self, tmp_path, monkeypatch) -> None:
        scaffold(tmp_path, monkeypatch, project=PROJECT_NO_CURRENT,
                 milestones="# Milestones\n\n## broken (Shipped: 2026)\n")
        assert main(["preflight", "v1.2"]) == 1


# ── check ────────────────────────────────────────────────────────────────────


class TestCheck:
    def _run(self, tmp_path, monkeypatch, requirements, **kw) -> int:
        spec = tmp_path / "concept.md"
        spec.write_text(SPEC)
        scaffold(tmp_path, monkeypatch, requirements=requirements, **kw)
        return main(["check", str(spec)])

    def test_plain_pass(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one"), ("CORE-02", "two")],
            [("CORE-01", "D1", "one"), ("CORE-02", "D2", "two")],
        )
        assert self._run(tmp_path, monkeypatch, req) == 0

    def test_waiver_pass(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one")],
            [("CORE-01", "D1", "one"), ("—", "D2", "waived: pure constraint")],
        )
        assert self._run(tmp_path, monkeypatch, req) == 0

    def test_deferred_pass(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one")],
            [("CORE-01", "D1", "one"),
             ("—", "D2", "deferred to v2 (LATER-01): next time")],
            v2=[("LATER-01", "later")],
        )
        assert self._run(tmp_path, monkeypatch, req) == 0

    def test_multi_decision_source_pass(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "both")], [("CORE-01", "D1, D2", "both")]
        )
        assert self._run(tmp_path, monkeypatch, req) == 0

    def test_amended_pass(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one"), ("CORE-02", "two")],
            [("CORE-01", "D1; SV-1 (gate-approved)", "amended"),
             ("CORE-02", "D2", "two")],
        )
        assert self._run(tmp_path, monkeypatch, req, verification=FINDINGS_SV1) == 0

    def test_ticked_checkboxes_pass(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one"), ("CORE-02", "two")],
            [("CORE-01", "D1", "one"), ("CORE-02", "D2", "two")],
        )
        req = req.replace("- [ ] **CORE-01**", "- [x] **CORE-01**")
        req = req.replace("- [ ] **CORE-02**", "- [X] **CORE-02**")
        assert self._run(tmp_path, monkeypatch, req) == 0

    def test_new_req_from_finding_pass(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one"), ("CORE-02", "two"), ("NEW-01", "grant")],
            [("CORE-01", "D1", "one"), ("CORE-02", "D2", "two"),
             ("NEW-01", "SV-1 (gate-approved)", "new req")],
        )
        assert self._run(tmp_path, monkeypatch, req, verification=FINDINGS_SV1) == 0

    def test_dropped_decision_fails(self, tmp_path, monkeypatch) -> None:
        req = build_requirements([("CORE-01", "one")], [("CORE-01", "D1", "one")])
        assert self._run(tmp_path, monkeypatch, req) == 1

    def test_illegal_source_fails(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one"), ("CORE-02", "two")],
            [("CORE-01", "garbage", "x"), ("CORE-02", "D2", "two")],
        )
        assert self._run(tmp_path, monkeypatch, req) == 1

    def test_sv_without_finding_fails(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one"), ("CORE-02", "two")],
            [("CORE-01", "D1; SV-9 (gate-approved)", "x"), ("CORE-02", "D2", "two")],
        )
        assert self._run(tmp_path, monkeypatch, req, verification=FINDINGS_SV1) == 1

    def test_unparseable_findings_fails_loud(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one"), ("CORE-02", "two")],
            [("CORE-01", "D1", "one"), ("CORE-02", "D2", "two")],
        )
        bad_findings = "| id | decision-ref |\n|----|----|\n| SV-1 | D2 |\n"
        assert self._run(tmp_path, monkeypatch, req, verification=bad_findings) == 1

    def test_req_without_row_fails(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one"), ("CORE-02", "two")],
            [("CORE-01", "D1", "one"), ("—", "D2", "waived: x")],
        )
        assert self._run(tmp_path, monkeypatch, req) == 1

    def test_forgotten_twin_fails(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one")],
            [("CORE-01", "D1", "one"), ("CORE-02", "D2", "ghost row")],
        )
        assert self._run(tmp_path, monkeypatch, req) == 1

    def test_deferred_names_nonexistent_v2_fails(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one")],
            [("CORE-01", "D1", "one"),
             ("—", "D2", "deferred to v2 (GHOST-01): x")],
        )
        assert self._run(tmp_path, monkeypatch, req) == 1

    def test_v2_without_deferred_row_fails(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one"), ("CORE-02", "two")],
            [("CORE-01", "D1", "one"), ("CORE-02", "D2", "two")],
            v2=[("LATER-01", "orphan v2")],
        )
        assert self._run(tmp_path, monkeypatch, req) == 1

    def test_req_id_collision_fails(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CMD-01", "one"), ("CORE-02", "two")],
            [("CMD-01", "D1", "one"), ("CORE-02", "D2", "two")],
        )
        assert self._run(
            tmp_path, monkeypatch, req,
            archives_req={"v1.1-REQUIREMENTS.md": "- [x] **CMD-01**: old\n"},
        ) == 1


# ── coverage ─────────────────────────────────────────────────────────────────


class TestCoverage:
    SNAP = build_requirements(
        [("CORE-01", "one"), ("CORE-02", "two")],
        [("CORE-01", "D1", "one"), ("CORE-02", "D2", "two")],
    )

    def test_pass(self, tmp_path, monkeypatch) -> None:
        roadmap = (
            "### Phase 1: A\n**Requirements**: CORE-01\n"
            "### Phase 2: B\n**Requirements**: CORE-02\n"
        )
        scaffold(tmp_path, monkeypatch, snapshot=self.SNAP, roadmap=roadmap)
        assert main(["coverage"]) == 0

    def test_unmapped_fails(self, tmp_path, monkeypatch) -> None:
        roadmap = "### Phase 1: A\n**Requirements**: CORE-01\n"
        scaffold(tmp_path, monkeypatch, snapshot=self.SNAP, roadmap=roadmap)
        assert main(["coverage"]) == 1

    def test_double_mapped_fails(self, tmp_path, monkeypatch) -> None:
        roadmap = (
            "### Phase 1: A\n**Requirements**: CORE-01, CORE-02\n"
            "### Phase 2: B\n**Requirements**: CORE-01\n"
        )
        scaffold(tmp_path, monkeypatch, snapshot=self.SNAP, roadmap=roadmap)
        assert main(["coverage"]) == 1

    def test_invented_req_fails(self, tmp_path, monkeypatch) -> None:
        roadmap = (
            "### Phase 1: A\n**Requirements**: CORE-01, CORE-02\n"
            "### Phase 2: B\n**Requirements**: GHOST-01\n"
        )
        scaffold(tmp_path, monkeypatch, snapshot=self.SNAP, roadmap=roadmap)
        assert main(["coverage"]) == 1

    def test_missing_snapshot_errors(self, tmp_path, monkeypatch) -> None:
        scaffold(tmp_path, monkeypatch, roadmap="### Phase 1: A\n")
        assert main(["coverage"]) == 1

    def test_reads_snapshot_not_live(self, tmp_path, monkeypatch) -> None:
        # Live REQUIREMENTS.md has a SMALLER gated set than the snapshot. If
        # coverage wrongly read the live file, CORE-02 would look invented.
        live = build_requirements(
            [("CORE-01", "one")], [("CORE-01", "D1", "one")]
        )
        roadmap = (
            "### Phase 1: A\n**Requirements**: CORE-01\n"
            "### Phase 2: B\n**Requirements**: CORE-02\n"
        )
        scaffold(tmp_path, monkeypatch, snapshot=self.SNAP, requirements=live,
                 roadmap=roadmap)
        assert main(["coverage"]) == 0


# ── snapshot / restore ───────────────────────────────────────────────────────


class TestSnapshotRestore:
    def test_write_and_matches(self, tmp_path, monkeypatch) -> None:
        scaffold(tmp_path, monkeypatch, requirements="body\n")
        assert main(["snapshot"]) == 0
        assert (tmp_path / ".planning" / ".requirements.snapshot").read_bytes() == b"body\n"
        assert main(["snapshot", "--matches"]) == 0

    def test_matches_detects_one_byte(self, tmp_path, monkeypatch) -> None:
        planning = scaffold(tmp_path, monkeypatch, requirements="body\n")
        main(["snapshot"])
        (planning / "REQUIREMENTS.md").write_text("body!\n")
        assert main(["snapshot", "--matches"]) == 1

    def test_matches_missing_snapshot(self, tmp_path, monkeypatch) -> None:
        scaffold(tmp_path, monkeypatch, requirements="body\n")
        assert main(["snapshot", "--matches"]) == 1

    def test_clear(self, tmp_path, monkeypatch) -> None:
        planning = scaffold(tmp_path, monkeypatch, requirements="body\n",
                            snapshot="body\n")
        assert main(["snapshot", "--clear"]) == 0
        assert not (planning / ".requirements.snapshot").exists()
        assert main(["snapshot", "--clear"]) == 0  # idempotent

    def test_restore_overwrites_diverged(self, tmp_path, monkeypatch) -> None:
        planning = scaffold(tmp_path, monkeypatch,
                            requirements="roadmapper edited this\n",
                            snapshot="approved bytes\n")
        assert main(["restore"]) == 0
        assert (planning / "REQUIREMENTS.md").read_bytes() == b"approved bytes\n"

    def test_restore_after_edit_byte_identical(self, tmp_path, monkeypatch) -> None:
        planning = scaffold(tmp_path, monkeypatch, requirements="approved\n")
        main(["snapshot"])
        (planning / "REQUIREMENTS.md").write_text("approved\n- [ ] **X-01**: added\n")
        main(["restore"])
        assert main(["snapshot", "--matches"]) == 0

    def test_restore_missing_snapshot_errors(self, tmp_path, monkeypatch) -> None:
        scaffold(tmp_path, monkeypatch, requirements="body\n")
        assert main(["restore"]) == 1


# ── traceability ─────────────────────────────────────────────────────────────


class TestTraceability:
    def test_fills_table_and_coverage(self, tmp_path, monkeypatch) -> None:
        req = build_requirements(
            [("CORE-01", "one"), ("CORE-02", "two")],
            [("CORE-01", "D1", "one"), ("CORE-02", "D2", "two")],
        )
        roadmap = (
            "### Phase 1: A\n**Requirements**: CORE-01\n"
            "### Phase 2: B\n**Requirements**: CORE-02\n"
        )
        planning = scaffold(tmp_path, monkeypatch, requirements=req, roadmap=roadmap)
        assert main(["traceability"]) == 0
        out = (planning / "REQUIREMENTS.md").read_text()
        assert "| CORE-01 | Phase 1 | Pending |" in out
        assert "| CORE-02 | Phase 2 | Pending |" in out
        assert "- v1 requirements: 2 total" in out
        assert "- Mapped to phases: 2" in out
        assert "- Unmapped: 0 ✓" in out
        assert "*footer*" in out  # footer preserved
        assert "## Spec Traceability" in out  # net-new section untouched

    def test_missing_placeholder_errors(self, tmp_path, monkeypatch) -> None:
        scaffold(tmp_path, monkeypatch, requirements="# Requirements\n\nno trace\n",
                 roadmap="### Phase 1: A\n**Requirements**: CORE-01\n")
        assert main(["traceability"]) == 1


# ── research janitor ─────────────────────────────────────────────────────────


class TestResearchPrePost:
    def test_pre_records_filenames(self, tmp_path, monkeypatch) -> None:
        planning = scaffold(tmp_path, monkeypatch,
                            research_files={"SUMMARY.md": "old\n"})
        assert main(["research-pre"]) == 0
        manifest = (planning / ".research-manifest").read_text()
        assert "SUMMARY.md" in manifest

    def test_pre_empty_when_no_dir(self, tmp_path, monkeypatch) -> None:
        planning = scaffold(tmp_path, monkeypatch)
        assert main(["research-pre"]) == 0
        assert (planning / ".research-manifest").read_text() == ""

    def test_post_deletes_strays_keeps_rest(self, tmp_path, monkeypatch) -> None:
        planning = scaffold(tmp_path, monkeypatch,
                            research_files={"SUMMARY.md": "preexisting\n"})
        main(["research-pre"])  # records SUMMARY.md
        research = planning / "research"
        (research / "spec-verification.md").write_text("findings\n")
        (research / "STACK.md").write_text("stray\n")
        assert main(["research-post"]) == 0
        assert (research / "SUMMARY.md").exists()          # in manifest
        assert (research / "spec-verification.md").exists()  # always kept
        assert not (research / "STACK.md").exists()        # stray deleted
        # idempotent
        assert main(["research-post"]) == 0
        assert (research / "spec-verification.md").exists()


# ── CLI dispatch ─────────────────────────────────────────────────────────────


class TestCLI:
    def test_no_args(self) -> None:
        assert main([]) == 1

    def test_citations_needs_spec(self) -> None:
        assert main(["citations"]) == 1

    def test_check_needs_spec(self) -> None:
        assert main(["check"]) == 1

    def test_preflight_needs_version(self) -> None:
        assert main(["preflight"]) == 1

    def test_snapshot_unknown_flag(self, tmp_path, monkeypatch) -> None:
        scaffold(tmp_path, monkeypatch, requirements="x\n")
        assert main(["snapshot", "--bogus"]) == 1

    def test_unknown_command(self) -> None:
        assert main(["explode"]) == 1
