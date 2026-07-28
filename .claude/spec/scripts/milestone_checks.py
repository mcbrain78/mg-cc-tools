#!/usr/bin/env python3
"""Deterministic gate/cross-check core for mg:spec-create-milestone.

Single source of truth for every parse the command must NOT eyeball
in-context: D-block ids, the ``### What gets built`` citation grammar,
``## Spec Traceability`` rows, ROADMAP phase/requirements lines,
MILESTONES versions, archive REQ-ids, and the spec-verification findings
table. The LLM command orchestrates; this script decides.

GSD-side inputs live at FIXED ``.planning/`` paths (never passed as
args); only ``citations``/``check`` take ``<spec-path>`` and
``preflight`` takes ``<version>``.

Subcommands
-----------
citations <spec-path>       Validate every ``### What gets built`` top-level
                            bullet cites >=1 existing ``Dx`` (never vacuous).
phase-start                 Print floor(max archived ``### Phase N``)+1, or 1.
preflight <version>         Classify GSD-side entry state into one named
                            verdict (JSON on stdout; facts that drove it).
check <spec-path>           Faithfulness gate over ``## Spec Traceability``.
coverage                    Bidirectional REQ<->phase check (gated set from
                            the snapshot, never a live file).
snapshot [--clear|--matches]  Write / clear / byte-compare the requirements
                            snapshot.
restore                     Restore REQUIREMENTS.md byte-exact from snapshot.
traceability                Fill the ``## Traceability`` placeholder from
                            ROADMAP.md.
research-pre / research-post  Set-difference janitor around the researcher.

Exit codes: 0 = success/clean, 1 = error/violation (details on stderr;
structured verdicts on stdout).
"""
from __future__ import annotations

import json
import math
import re
import shutil
import sys
from pathlib import Path
from typing import NamedTuple


# ── Fixed .planning/ paths (single source of truth) ─────────────────────────

PLANNING = Path(".planning")
REQUIREMENTS = PLANNING / "REQUIREMENTS.md"
SNAPSHOT = PLANNING / ".requirements.snapshot"
RESEARCH_DIR = PLANNING / "research"
VERIFICATION = RESEARCH_DIR / "spec-verification.md"
RESEARCH_MANIFEST = PLANNING / ".research-manifest"
ROADMAP = PLANNING / "ROADMAP.md"
PROJECT = PLANNING / "PROJECT.md"
MILESTONES = PLANNING / "MILESTONES.md"
MILESTONES_DIR = PLANNING / "milestones"
GSD_DIR = Path(".claude/get-shit-done")


# ── Pinned grammars (single source of truth — prevents two-implementer drift) ─

_D_HEADING = re.compile(r"^### D(\d+):", re.M)        # decision ids
_CITATION = re.compile(r"\(D\d+(?:, ?D\d+)*\)")       # D8 citation, position-free
_PHASE_HEAD = re.compile(r"^### Phase (\d+(?:\.\d+)?):", re.M)  # decimal-aware
_REQ_LINE = re.compile(r"^\*\*Requirements\*\*:[^\S\n]*([^\n]*)$", re.M)
_CHECKBOX = re.compile(r"^- \[[ xX]\] \*\*([A-Z]{2,5}-\d+)\*\*:", re.M)  # live v1
_V2_ITEM = re.compile(r"^- \*\*([A-Z]{2,5}-\d+)\*\*:", re.M)            # v2 (no box)
_ARCHIVE_ID = re.compile(r"\*\*([A-Z]{2,5}-\d+)\*\*")   # any bold id (glyph-agnostic)
_REQ_ID_TOKEN = re.compile(r"\b[A-Z]{2,5}-\d+\b")
_CURRENT_MS = re.compile(r"^## Current Milestone:(.*)$", re.M)
_MS_VERSION = re.compile(r"^## (v\d+\.\d+)\b", re.M)
_VERSION_OK = re.compile(r"^v\d+\.\d+$")

# Source-cell grammar for ## Spec Traceability (the exactly-legal forms)
_SRC_DX = r"D\d+(?:, ?D\d+)*"
_SRC_SV = r"SV-\d+(?:, ?SV-\d+)*"
_SRC_DECISION = re.compile(rf"^{_SRC_DX}$")
_SRC_AMENDED = re.compile(rf"^{_SRC_DX};\s*{_SRC_SV}\s+\(gate-approved\)$")
_SRC_NEWREQ = re.compile(rf"^{_SRC_SV}\s+\(gate-approved\)$")

_WAIVED_NOTE = re.compile(r"^waived:")
_DEFERRED_NOTE = re.compile(r"^deferred to v2 \(([A-Z]{2,5}-\d+)\):")


class _ParseError(Exception):
    """A file that must be well-formed cannot be parsed. Callers convert to a
    loud ERROR (exit 1) — never silently treated as empty/clean."""


# ── Parse result types ──────────────────────────────────────────────────────


class Bullet(NamedTuple):
    text: str
    cited_ids: set[int]
    has_citation: bool


class BulletParse(NamedTuple):
    section_found: bool
    bullets: list[Bullet]


class TraceRow(NamedTuple):
    req: str | None          # None when the REQ cell is an em-dash (waiver/deferred)
    source_raw: str
    note: str


class SourceKind(NamedTuple):
    dx_ids: set[int]
    sv_ids: set[str]         # full "SV-n" strings
    gate_approved: bool
    legal: bool


class Phase(NamedTuple):
    number: float
    req_ids: list[str]


class CurrentMilestone(NamedTuple):
    present: bool
    version: str | None      # None when a heading exists but its token isn't vX.Y
    raw_token: str | None


class Finding(NamedTuple):
    id: str
    decision_ref: str
    kind: str
    what: str
    severity: str


# ── Shared parsers (each returns plain data; none prints or exits) ───────────


def _extract_section(text: str, heading: str, stop_pattern: str) -> str | None:
    """Body of a section from its exact heading line to the next heading that
    matches ``stop_pattern`` (or EOF). Returns None if the heading is absent."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.rstrip() == heading:
            start = i + 1
            break
    if start is None:
        return None
    stop = re.compile(stop_pattern)
    body: list[str] = []
    for line in lines[start:]:
        if stop.match(line):
            break
        body.append(line)
    return "\n".join(body)


def _extract_decision_ids(spec_text: str) -> set[int]:
    """{n} from every ``### Dn:`` heading."""
    return {int(m.group(1)) for m in _D_HEADING.finditer(spec_text)}


def _parse_deliverable_bullets(spec_text: str) -> BulletParse:
    """Top-level ``- `` bullets (column 0) inside the verbatim
    ``### What gets built`` section. Indented/nested bullets, prose, and fenced
    code blocks (file-tree diagrams) are illustration and ignored. Each
    bullet's cited ids come from every ``(Dx)`` group on its single line."""
    body = _extract_section(spec_text, "### What gets built", r"^#{1,3} ")
    if body is None:
        return BulletParse(section_found=False, bullets=[])
    bullets: list[Bullet] = []
    in_fence = False
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("- "):
            cited: set[int] = set()
            for m in _CITATION.finditer(line):
                cited.update(int(d) for d in re.findall(r"D(\d+)", m.group(0)))
            bullets.append(
                Bullet(text=line, cited_ids=cited, has_citation=bool(cited))
            )
    return BulletParse(section_found=True, bullets=bullets)


def _table_rows(body: str, expected_cols: int, label: str) -> tuple[list[list[str]], bool]:
    """Data rows (as stripped cell lists) of the first markdown table in
    ``body``. Skips header + separator. Raises _ParseError on a header/row with
    the wrong column count. Returns (rows, header_seen)."""
    data: list[list[str]] = []
    header_seen = False
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and all(c and set(c) <= set("-: ") for c in cells):
            continue  # separator row
        if not header_seen:
            header_seen = True
            if len(cells) != expected_cols:
                raise _ParseError(
                    f"{label}: header must have {expected_cols} columns, "
                    f"got {len(cells)}: {s}"
                )
            continue
        if len(cells) != expected_cols:
            raise _ParseError(
                f"{label}: malformed row (expected {expected_cols} columns): {s}"
            )
        data.append(cells)
    return data, header_seen


def _parse_spec_traceability(req_text: str) -> list[TraceRow]:
    """Rows under ``## Spec Traceability`` (``| REQ | Source | Note |``). Absent
    section → []. Present but malformed table → _ParseError (fail-loud)."""
    body = _extract_section(req_text, "## Spec Traceability", r"^#{1,2} ")
    if body is None:
        return []
    data, _ = _table_rows(body, 3, "## Spec Traceability")
    rows: list[TraceRow] = []
    for req_cell, source, note in data:
        req = None if req_cell in ("—", "-", "") else req_cell
        rows.append(TraceRow(req=req, source_raw=source, note=note))
    return rows


def _classify_source(source_raw: str) -> SourceKind:
    """Classify one Source cell into the exactly-5 legal forms (decision-derived,
    amended, new-REQ-from-finding — waiver/deferred rows carry a decision-derived
    Source, distinguished at row level by the REQ column + Note)."""
    s = source_raw.strip()
    if _SRC_DECISION.match(s):
        dx = {int(x) for x in re.findall(r"D(\d+)", s)}
        return SourceKind(dx_ids=dx, sv_ids=set(), gate_approved=False, legal=True)
    if _SRC_AMENDED.match(s):
        dx = {int(x) for x in re.findall(r"D(\d+)", s.split(";", 1)[0])}
        sv = set(re.findall(r"SV-\d+", s))
        return SourceKind(dx_ids=dx, sv_ids=sv, gate_approved=True, legal=True)
    if _SRC_NEWREQ.match(s):
        sv = set(re.findall(r"SV-\d+", s))
        return SourceKind(dx_ids=set(), sv_ids=sv, gate_approved=True, legal=True)
    return SourceKind(dx_ids=set(), sv_ids=set(), gate_approved=False, legal=False)


def _parse_roadmap(roadmap_text: str) -> list[Phase]:
    """``### Phase N:`` headings (decimal-aware) each carrying the REQ-ids from
    its ``**Requirements**:`` line(s) (brackets stripped, ``TBD`` → none)."""
    phases: list[Phase] = []
    current: float | None = None
    reqs: list[str] = []
    for line in roadmap_text.splitlines():
        hm = _PHASE_HEAD.match(line)
        if hm:
            if current is not None:
                phases.append(Phase(number=current, req_ids=reqs))
            current = float(hm.group(1))
            reqs = []
            continue
        if current is not None:
            rm = _REQ_LINE.match(line)
            if rm:
                reqs.extend(_REQ_ID_TOKEN.findall(rm.group(1)))
    if current is not None:
        phases.append(Phase(number=current, req_ids=reqs))
    return phases


def _parse_milestones_versions(text: str) -> set[str]:
    """{"v1.1", ...} from ``## <version> ... (Shipped: ...)`` headings. A Shipped
    entry with no parseable version → _ParseError (fail-loud). The phase-*count*
    line is deliberately ignored."""
    for line in text.splitlines():
        if line.startswith("## ") and "Shipped" in line:
            if not re.search(r"v\d+\.\d+", line):
                raise _ParseError(
                    f"MILESTONES.md: cannot parse version from: {line.strip()}"
                )
    return set(_MS_VERSION.findall(text))


def _parse_current_milestone(text: str) -> CurrentMilestone:
    """Read PROJECT.md's ``## Current Milestone:`` heading. Absent → present=False.
    Present but token not well-formed vX.Y → version=None (routes to a visible
    confirm/ERROR, never the silent ``clean`` verdict)."""
    m = _CURRENT_MS.search(text)
    if not m:
        return CurrentMilestone(present=False, version=None, raw_token=None)
    rest = m.group(1).split()
    token = rest[0] if rest else None
    if token and _VERSION_OK.match(token):
        return CurrentMilestone(present=True, version=token, raw_token=token)
    return CurrentMilestone(present=True, version=None, raw_token=token)


def _scan_archive_req_id_set() -> set[str]:
    """Every bold REQ-id across archived ``v*-REQUIREMENTS.md`` (glyph-agnostic:
    captures ``[ ]``/``[x]``/``[X]``/``[~]`` and v2 ids alike)."""
    ids: set[str] = set()
    if not MILESTONES_DIR.is_dir():
        return ids
    for archive in sorted(MILESTONES_DIR.glob("v*-REQUIREMENTS.md")):
        ids.update(_ARCHIVE_ID.findall(archive.read_text()))
    return ids


def _parse_findings(text: str) -> list[Finding]:
    """Rows of the spec-verification findings table
    (``| id | decision-ref | kind | what | suggested-addition | severity |``).
    Header row only → []. No table / malformed → _ParseError (never empty)."""
    data, header_seen = _table_rows(text, 6, "spec-verification.md")
    if not header_seen:
        raise _ParseError("spec-verification.md: no findings table found")
    return [
        Finding(id=c[0], decision_ref=c[1], kind=c[2], what=c[3], severity=c[5])
        for c in data
    ]


# ── Small emit/verdict helpers ──────────────────────────────────────────────


def _fail(msg: str) -> int:
    print(f"Error: {msg}", file=sys.stderr)
    return 1


def _report(violations: list[str], ok_msg: str) -> int:
    if violations:
        for v in violations:
            print(f"Error: {v}", file=sys.stderr)
        return 1
    print(ok_msg)
    return 0


def _fmt_phase(n: float) -> str:
    return f"Phase {int(n)}" if n == int(n) else f"Phase {n}"


def _phase_start_value() -> int:
    nums: list[float] = []
    if MILESTONES_DIR.is_dir():
        for archive in MILESTONES_DIR.glob("v*-ROADMAP.md"):
            nums.extend(float(x) for x in _PHASE_HEAD.findall(archive.read_text()))
    return 1 if not nums else math.floor(max(nums)) + 1


def _live_phase_numbers(phase_start: int) -> list[float]:
    """``### Phase N:`` heading numbers (NOT ``- [x]`` bullets) with raw
    N >= phase_start. Post-completion residue never emits such headings, and any
    residue phase is < phase_start by construction."""
    if not ROADMAP.is_file():
        return []
    nums = [float(x) for x in _PHASE_HEAD.findall(ROADMAP.read_text())]
    return [n for n in nums if n >= phase_start]


# ── Subcommands ──────────────────────────────────────────────────────────────


def cmd_citations(spec: Path) -> int:
    """Startup: every top-level ``### What gets built`` bullet cites >=1 existing
    Dx. Missing file, no D-blocks, missing/bullet-less section, uncited bullet,
    or unknown-Dx citation each fail. Never a vacuous pass."""
    if not spec.is_file():
        return _fail(f"spec file not found: {spec}")
    text = spec.read_text()
    if not text.strip():
        return _fail(f"spec file is empty: {spec}")
    ids = _extract_decision_ids(text)
    if not ids:
        return _fail("spec has no D1..Dn decision blocks")
    parse = _parse_deliverable_bullets(text)
    if not parse.section_found:
        return _fail("spec has no '### What gets built' section")
    if not parse.bullets:
        return _fail("'### What gets built' has zero top-level bullets")
    violations: list[str] = []
    for b in parse.bullets:
        if not b.has_citation:
            violations.append(f"uncited deliverable bullet: {b.text.strip()}")
        else:
            unknown = b.cited_ids - ids
            if unknown:
                names = ", ".join(f"D{n}" for n in sorted(unknown))
                violations.append(
                    f"bullet cites unknown decision(s) {names}: {b.text.strip()}"
                )
    return _report(
        violations,
        f"citations: OK ({len(parse.bullets)} bullets, all cite existing decisions)",
    )


def cmd_phase_start() -> int:
    print(_phase_start_value())
    return 0


def _preflight_result(verdict: str, facts: dict, exit_code: int, err: str | None) -> int:
    facts["verdict"] = verdict
    print(json.dumps(facts, indent=2))
    if exit_code != 0 and err:
        print(f"Error: preflight {verdict}: {err}", file=sys.stderr)
    return exit_code


def cmd_preflight(version: str) -> int:
    """Classify the GSD-side entry state (ordered decision table, first match
    wins). Prints the driving facts as JSON. Fail-loud on unparseable state."""
    facts: dict = {}
    if not PROJECT.is_file():
        return _preflight_result(
            "missing-project", facts, 1, "`.planning/PROJECT.md` not found"
        )
    if not GSD_DIR.is_dir():
        return _preflight_result(
            "missing-gsd", facts, 1, "`.claude/get-shit-done/` not found"
        )
    if not _VERSION_OK.match(version):
        facts["version"] = version
        return _preflight_result(
            "bad-version", facts, 1, f"version not well-formed vX.Y: {version}"
        )
    try:
        current = _parse_current_milestone(PROJECT.read_text())
    except _ParseError as e:
        return _fail(str(e))
    ms_versions: set[str] = set()
    if MILESTONES.is_file():
        try:
            ms_versions = _parse_milestones_versions(MILESTONES.read_text())
        except _ParseError as e:
            return _fail(str(e))
    phase_start = _phase_start_value()
    live = _live_phase_numbers(phase_start)
    req_exists = REQUIREMENTS.is_file()

    facts.update(
        version=version,
        current_milestone=current.version,
        current_milestone_raw=current.raw_token,
        current_milestone_present=current.present,
        milestones_versions=sorted(ms_versions),
        phase_start=phase_start,
        live_phase_numbers=[int(n) if n == int(n) else n for n in live],
        requirements_exists=req_exists,
    )

    if version in ms_versions:
        return _preflight_result(
            "version-completed", facts, 1,
            f"{version} already recorded in MILESTONES.md",
        )
    if live and current.version == version:
        return _preflight_result(
            "live-phase-current", facts, 1,
            "live-phase ROADMAP.md for the current milestone",
        )
    if (req_exists or live) and current.version != version:
        return _preflight_result(
            "open-other-milestone", facts, 1,
            "a previous milestone is still open",
        )
    if current.version == version and not live:
        return _preflight_result("resume-pre-roadmap", facts, 0, None)
    no_live_markers = (not req_exists) and (not live)
    if no_live_markers and current.present and (
        current.version not in ({version} | ms_versions)
    ):
        return _preflight_result("abandoned-bookkeeping", facts, 0, None)
    return _preflight_result("clean", facts, 0, None)


def cmd_check(spec: Path) -> int:
    """Stage-3 gate. Collects every violation (presented together): completeness,
    no-drift, REQ<->row bidirectional (v1 checkboxes), v2-anchoring bidirectional,
    SV-citation existence, REQ-id collision vs archives. Fail-loud on an
    unparseable spec-verification.md."""
    if not spec.is_file():
        return _fail(f"spec file not found: {spec}")
    d_ids = _extract_decision_ids(spec.read_text())
    if not d_ids:
        return _fail("spec has no D1..Dn decision blocks")
    if not REQUIREMENTS.is_file():
        return _fail("`.planning/REQUIREMENTS.md` not found")
    req_text = REQUIREMENTS.read_text()

    finding_ids: set[str] = set()
    if VERIFICATION.is_file():
        try:
            finding_ids = {f.id for f in _parse_findings(VERIFICATION.read_text())}
        except _ParseError as e:
            return _fail(str(e))
    try:
        rows = _parse_spec_traceability(req_text)
    except _ParseError as e:
        return _fail(str(e))

    checkbox_set = set(_CHECKBOX.findall(req_text))
    v2_items = set(_V2_ITEM.findall(req_text)) - checkbox_set

    violations: list[str] = []
    covered_dx: set[int] = set()
    cited_sv: set[str] = set()
    req_rows: dict[str, int] = {}
    deferred_targets: dict[str, int] = {}

    for row in rows:
        kind = _classify_source(row.source_raw)
        covered_dx |= kind.dx_ids
        cited_sv |= kind.sv_ids
        if row.req is None:
            is_waiver = bool(_WAIVED_NOTE.match(row.note))
            deferred_m = _DEFERRED_NOTE.match(row.note)
            if not (is_waiver or deferred_m):
                violations.append(
                    f"no-drift: empty-REQ row is neither waiver nor deferred "
                    f"(source={row.source_raw!r}, note={row.note!r})"
                )
            if not kind.legal:
                violations.append(
                    f"no-drift: illegal Source in waiver/deferred row: "
                    f"{row.source_raw!r}"
                )
            if deferred_m:
                cat = deferred_m.group(1)
                deferred_targets[cat] = deferred_targets.get(cat, 0) + 1
        else:
            if not kind.legal:
                violations.append(
                    f"no-drift: illegal Source {row.source_raw!r} for REQ {row.req}"
                )
            req_rows[row.req] = req_rows.get(row.req, 0) + 1

    for n in sorted(d_ids - covered_dx):
        violations.append(f"completeness: decision D{n} has no Source row (dropped)")

    for sv in sorted(cited_sv):
        if sv not in finding_ids:
            violations.append(
                f"SV-citation: {sv} cited in a Source but has no matching finding "
                f"in spec-verification.md"
            )

    for cb in sorted(checkbox_set):
        count = req_rows.get(cb, 0)
        if count == 0:
            violations.append(f"REQ<->row: checkbox {cb} has no traceability row")
        elif count > 1:
            violations.append(
                f"REQ<->row: checkbox {cb} has {count} rows (expected 1)"
            )
    for req in sorted(req_rows):
        if req not in checkbox_set:
            violations.append(
                f"REQ<->row: row for {req} has no live v1 checkbox (forgotten-twin)"
            )

    for cat, count in sorted(deferred_targets.items()):
        if cat not in v2_items:
            violations.append(
                f"v2-anchoring: deferred row names {cat} but no such v2 item exists"
            )
        elif count > 1:
            violations.append(
                f"v2-anchoring: v2 item {cat} named by {count} deferred rows (expected 1)"
            )
    for v2 in sorted(v2_items):
        if v2 not in deferred_targets:
            violations.append(
                f"v2-anchoring: v2 item {v2} is named by no deferred row"
            )

    archived = _scan_archive_req_id_set()
    for rid in sorted(checkbox_set | v2_items):
        if rid in archived:
            violations.append(
                f"REQ-id collision: {rid} already exists in a prior milestone archive"
            )

    return _report(
        violations,
        f"check: OK ({len(checkbox_set)} v1 requirements, {len(v2_items)} v2 items, "
        f"all {len(d_ids)} decisions covered)",
    )


def cmd_coverage() -> int:
    """Stage-4: bidirectional REQ<->phase. The gated set is the snapshot's
    ``## Spec Traceability`` non-waiver rows (never a live file)."""
    if not SNAPSHOT.is_file():
        return _fail("`.planning/.requirements.snapshot` not found (gate first)")
    if not ROADMAP.is_file():
        return _fail("`.planning/ROADMAP.md` not found")
    try:
        rows = _parse_spec_traceability(SNAPSHOT.read_text())
    except _ParseError as e:
        return _fail(str(e))
    gated = {row.req for row in rows if row.req is not None}

    placement: dict[str, list[float]] = {}
    cited: set[str] = set()
    for ph in _parse_roadmap(ROADMAP.read_text()):
        for rid in ph.req_ids:
            cited.add(rid)
            placement.setdefault(rid, []).append(ph.number)

    violations: list[str] = []
    for g in sorted(gated):
        locs = placement.get(g, [])
        if not locs:
            violations.append(f"coverage: gated REQ {g} is mapped to no phase")
        elif len(locs) > 1:
            where = ", ".join(_fmt_phase(n) for n in locs)
            violations.append(
                f"coverage: gated REQ {g} is mapped to {len(locs)} phases "
                f"({where}); expected exactly 1"
            )
    for c in sorted(cited):
        if c not in gated:
            violations.append(
                f"coverage: ROADMAP.md cites REQ {c} not in the gated set (invented)"
            )

    return _report(
        violations,
        f"coverage: OK ({len(gated)} gated REQs, each mapped to exactly one phase)",
    )


def cmd_snapshot(mode: str | None) -> int:
    """--clear: delete. --matches: exit 0 iff live REQUIREMENTS.md is
    byte-identical to the snapshot. Default: write the whole file."""
    if mode == "--clear":
        SNAPSHOT.unlink(missing_ok=True)
        print("snapshot: cleared")
        return 0
    if mode == "--matches":
        if not REQUIREMENTS.is_file() or not SNAPSHOT.is_file():
            return 1
        return 0 if REQUIREMENTS.read_bytes() == SNAPSHOT.read_bytes() else 1
    if not REQUIREMENTS.is_file():
        return _fail("`.planning/REQUIREMENTS.md` not found")
    shutil.copy2(REQUIREMENTS, SNAPSHOT)
    print(f"snapshot: wrote {SNAPSHOT}")
    return 0


def cmd_restore() -> int:
    """Unconditional byte-exact restore of REQUIREMENTS.md from the snapshot."""
    if not SNAPSHOT.is_file():
        return _fail("`.planning/.requirements.snapshot` not found")
    shutil.copy2(SNAPSHOT, REQUIREMENTS)
    print("restore: REQUIREMENTS.md <- snapshot")
    return 0


def _replace_section_body(text: str, heading: str, new_body: str) -> str | None:
    """Replace a section's body (from its heading to the next ``#``/``##``
    heading or a ``---`` rule or EOF) with ``new_body``. Preserves a trailing
    footer that begins with ``---``. Returns None if the heading is absent."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.rstrip() == heading:
            start = i
            break
    if start is None:
        return None
    hd = re.compile(r"^#{1,2} ")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if hd.match(lines[j]) or lines[j].rstrip() == "---":
            end = j
            break
    new_lines = lines[: start + 1] + ["", new_body, ""] + lines[end:]
    joined = "\n".join(new_lines)
    return joined + "\n" if text.endswith("\n") else joined


def cmd_traceability() -> int:
    """Stage-5: fill the ``## Traceability`` placeholder from ROADMAP.md — one
    ``| REQ | Phase N | Pending |`` row per mapping + the ``**Coverage:**``
    summary (unmapped 0 once coverage has passed)."""
    if not REQUIREMENTS.is_file():
        return _fail("`.planning/REQUIREMENTS.md` not found")
    if not ROADMAP.is_file():
        return _fail("`.planning/ROADMAP.md` not found")
    req_text = REQUIREMENTS.read_text()

    mapping: list[tuple[str, float]] = []
    mapped: set[str] = set()
    for ph in _parse_roadmap(ROADMAP.read_text()):
        for rid in ph.req_ids:
            mapping.append((rid, ph.number))
            mapped.add(rid)

    v1_total = len(set(_CHECKBOX.findall(req_text)))
    unmapped = v1_total - len(mapped)
    mark = "✓" if unmapped == 0 else "⚠️"

    lines = ["| Requirement | Phase | Status |", "|-------------|-------|--------|"]
    lines += [f"| {rid} | {_fmt_phase(num)} | Pending |" for rid, num in mapping]
    lines += [
        "",
        "**Coverage:**",
        f"- v1 requirements: {v1_total} total",
        f"- Mapped to phases: {len(mapped)}",
        f"- Unmapped: {unmapped} {mark}",
    ]
    new_text = _replace_section_body(req_text, "## Traceability", "\n".join(lines))
    if new_text is None:
        return _fail("REQUIREMENTS.md has no `## Traceability` section to fill")
    REQUIREMENTS.write_text(new_text)
    print(f"traceability: filled {len(mapping)} mapping row(s)")
    return 0


def cmd_research_pre() -> int:
    """Record .planning/research/ filenames to the manifest (missing dir →
    empty manifest). Run exactly once, before the first researcher spawn."""
    if RESEARCH_DIR.is_dir():
        names = sorted(p.name for p in RESEARCH_DIR.iterdir() if p.is_file())
    else:
        names = []
    RESEARCH_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    RESEARCH_MANIFEST.write_text("".join(f"{n}\n" for n in names))
    print(f"research-pre: recorded {len(names)} file(s)")
    return 0


def cmd_research_post() -> int:
    """Delete any file in .planning/research/ that is neither in the manifest nor
    named spec-verification.md. Idempotent against a fixed manifest."""
    if not RESEARCH_DIR.is_dir():
        print("research-post: no research directory")
        return 0
    manifest: set[str] = set()
    if RESEARCH_MANIFEST.is_file():
        manifest = {
            line.strip()
            for line in RESEARCH_MANIFEST.read_text().splitlines()
            if line.strip()
        }
    deleted = 0
    for p in sorted(RESEARCH_DIR.iterdir()):
        if not p.is_file():
            continue
        if p.name in manifest or p.name == "spec-verification.md":
            continue
        p.unlink()
        print(f"research-post: deleted {p.name}")
        deleted += 1
    print(f"research-post: removed {deleted} stray file(s)")
    return 0


# ── CLI dispatch ──────────────────────────────────────────────────────────────

USAGE = """\
Usage: milestone_checks.py <command> [args]

Startup:
  citations <spec-path>          Validate ### What gets built bullets cite Dx
  phase-start                    Print floor(max archived phase)+1, or 1
  preflight <version>            Classify GSD-side entry state (JSON verdict)

Gate:
  check <spec-path>              Faithfulness check over ## Spec Traceability
  snapshot [--clear|--matches]   Write / clear / byte-compare the snapshot
  restore                        Restore REQUIREMENTS.md byte-exact from snapshot

Roadmap:
  coverage                       Bidirectional REQ<->phase (gated set = snapshot)
  traceability                   Fill the ## Traceability placeholder from ROADMAP

Research janitor:
  research-pre                   Record .planning/research/ filenames
  research-post                  Delete stray research files
"""


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(USAGE, file=sys.stderr)
        return 1
    command = args[0]

    if command == "citations":
        if len(args) < 2:
            return _fail("citations requires <spec-path>")
        return cmd_citations(Path(args[1]))
    if command == "check":
        if len(args) < 2:
            return _fail("check requires <spec-path>")
        return cmd_check(Path(args[1]))
    if command == "preflight":
        if len(args) < 2:
            return _fail("preflight requires <version>")
        return cmd_preflight(args[1])
    if command == "phase-start":
        return cmd_phase_start()
    if command == "coverage":
        return cmd_coverage()
    if command == "snapshot":
        mode = args[1] if len(args) > 1 else None
        if mode is not None and mode not in ("--clear", "--matches"):
            return _fail(f"snapshot: unknown flag {mode}")
        return cmd_snapshot(mode)
    if command == "restore":
        return cmd_restore()
    if command == "traceability":
        return cmd_traceability()
    if command == "research-pre":
        return cmd_research_pre()
    if command == "research-post":
        return cmd_research_post()

    print(f"Error: unknown command: {command}", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
