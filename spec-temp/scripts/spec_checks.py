#!/usr/bin/env python3
"""Deterministic core for mg:spec-improve-auto (concept D2, D4, D5, D8, D9, D13).

Everything the autonomous drain must NOT eyeball in-context — vote tallies,
the block-gate threshold, template-structure checks, the deterministic floor,
decision-record rendering and status projection, and (added in later build
phases) the atom ledger. The workflow's agents invoke these via Bash and relay
the raw JSON stdout; the JS branches only on values a script computed. stdlib
plus a subprocess call into the sibling ``milestone_checks.py`` (floor only).

Read/derive over the decision records lives here (``briefing`` /
``decisions summary``); the *writes* live in ``improve_files.py``
(``append-decision`` / ``update-decision``) — one schema, split along the
family read/write boundary (concept D9, Artifacts).

Subcommands
-----------
structure <spec>              Assert the required template headings are present.
tally [--head-to-head] <file> Gate vote math (pinned precedence) / competitive
                              rewrite 2-of-3 winner. Rejects panels < 3.
block-gate <file>             D5 take-vs-block from the union of two section sets
                              and two reversal booleans (takeable | blocked).
floor <spec>                  Wrap milestone_checks.py citations + structure into
                              one relay-JSON verdict (dedup by heading).
briefing <decisions-file>     Deterministic human render of the decision records.
decisions summary <file>      Thin JSON projection (id, kind, derived status,
                              radii, depends_on, confidence, review_first, dropped).

Exit codes: 0 = success/clean, 1 = error/violation (details on stderr;
structured verdicts on stdout).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


# ── Pinned constants (initial calibrations, tunable from history/ — D4, D5) ──

REQUIRED_HEADINGS: list[str] = [
    "## Situation",
    "## Problem",
    "## Solution",
    "### Overview",
    "## Design Decisions",
    "## Scope",
    "### What gets built",
    "### What does NOT get built",
    "## Verification",
]
# `## Open Items` is deliberately NOT required — the template defines it as a
# temporary section a mature spec legitimately empties or drops (concept D8).

BLOCK_THRESHOLD = 3          # D5: >= this many distinct anchor units → blocked
CHURN_ESCALATE = 2           # D2/D13: >= this many flips or fixes → step-7 escalation
JUDGES = ("builds-wrong-thing", "implementer-blocked", "scope-intent-drift")
MIN_PANEL = 3                # tally rejects vote sets smaller than this


# ── Emit helpers ─────────────────────────────────────────────────────────────


def _fail(msg: str) -> int:
    print(f"Error: {msg}", file=sys.stderr)
    return 1


def _emit(obj: object) -> None:
    print(json.dumps(obj, indent=2))


def _flag(argv: list[str], name: str) -> tuple[str | None, list[str]]:
    """Pop ``--name value``. Returns (value_or_None, remaining_argv)."""
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1], argv[:i] + argv[i + 2:]
        return None, argv[:i] + argv[i + 1:]
    return None, argv


# ── structure (D8) ───────────────────────────────────────────────────────────


def _present_headings(text: str) -> set[str]:
    out: set[str] = set()
    for line in text.splitlines():
        s = line.rstrip()
        if s.startswith("## ") or s.startswith("### "):
            out.add(s)
    return out


def _structure_findings(text: str) -> list[dict]:
    if not text.strip():
        return [{"source": "structure", "heading": None, "detail": "spec file is empty"}]
    present = _present_headings(text)
    return [
        {"source": "structure", "heading": h, "detail": f"required template heading missing: {h}"}
        for h in REQUIRED_HEADINGS
        if h not in present
    ]


def cmd_structure(spec: Path) -> int:
    if not spec.is_file():
        return _fail(f"spec file not found: {spec}")
    findings = _structure_findings(spec.read_text())
    status = "pass" if not findings else "fail"
    _emit({"check": "structure", "status": status, "findings": findings})
    return 0 if status == "pass" else 1


# ── tally (D4, D5) ───────────────────────────────────────────────────────────


def _tally_one(votes: dict) -> str:
    """Pinned precedence: needs-user → proposed-non-goal → auto-fixable → below-bar."""
    needs_user = sum(1 for v in votes.values() if v.get("needs_user"))
    exclusion = sum(1 for v in votes.values() if v.get("exclusion"))
    substantive = sum(1 for v in votes.values() if v.get("substantive"))
    if needs_user >= 1:            # permissive escalation (D5)
        return "needs-user"
    if exclusion >= 2:
        return "proposed-non-goal"
    if substantive >= 2:           # skeptical auto-fix (D5)
        return "auto-fixable"
    return "below-bar"


def _tally_head_to_head(votes: dict) -> str | None:
    """2-of-3 majority of 'A'/'B' ballots; None if no majority."""
    a = sum(1 for x in votes.values() if x == "A")
    b = sum(1 for x in votes.values() if x == "B")
    if a >= 2:
        return "A"
    if b >= 2:
        return "B"
    return None


def cmd_tally(votes_path: Path, head_to_head: bool) -> int:
    if not votes_path.is_file():
        return _fail(f"votes file not found: {votes_path}")
    try:
        data = json.loads(votes_path.read_text())
    except json.JSONDecodeError as e:
        return _fail(f"votes file is not valid JSON: {e}")
    if not isinstance(data, dict):
        return _fail("votes file must be a JSON object keyed by finding/anchor id")

    outcomes: dict = {}
    for key, votes in data.items():
        if not isinstance(votes, dict) or len(votes) < MIN_PANEL:
            n = len(votes) if isinstance(votes, dict) else 0
            return _fail(f"tally: '{key}' has {n} votes (need >= {MIN_PANEL}); short panel")
        if head_to_head:
            winner = _tally_head_to_head(votes)
            if winner is None:
                return _fail(f"tally: head-to-head '{key}' has no 2-of-3 majority")
            outcomes[key] = {"winner": winner, "votes": votes}
        else:
            outcomes[key] = _tally_one(votes)
    _emit(outcomes)
    return 0


# ── block-gate (D5) ──────────────────────────────────────────────────────────


def cmd_block_gate(inputs_path: Path) -> int:
    """takeable | blocked from the union of the two pre-take section sets and the
    two reversal booleans. All set arithmetic is the script's, never an LLM's."""
    if not inputs_path.is_file():
        return _fail(f"block-gate inputs file not found: {inputs_path}")
    try:
        data = json.loads(inputs_path.read_text())
    except json.JSONDecodeError as e:
        return _fail(f"block-gate inputs not valid JSON: {e}")

    evidence = set(data.get("evidence_sections", []) or [])
    estimate = set(data.get("estimate_sections", []) or [])
    union = evidence | estimate
    reverses = bool(data.get("reverses_directive")) or bool(data.get("reverses_non_goal"))
    blocked = reverses or (len(union) >= BLOCK_THRESHOLD)
    _emit({
        "verdict": "blocked" if blocked else "takeable",
        "unit_count": len(union),
        "reverses": reverses,
        "units": sorted(union),
    })
    return 0


# ── floor (D8) — wraps milestone_checks.py citations + structure ─────────────


_QUOTED_HEADING = re.compile(r"'(#{2,3} [^']+)'")


def _extract_heading(msg: str) -> str | None:
    m = _QUOTED_HEADING.search(msg)
    return m.group(1) if m else None


def cmd_floor(spec: Path) -> int:
    if not spec.is_file():
        return _fail(f"spec file not found: {spec}")
    text = spec.read_text()
    struct_findings = _structure_findings(text)
    struct_missing = {f["heading"] for f in struct_findings if f["heading"]}

    # citations exposes no structured list — it prints one `Error:` line per
    # violation to stderr and returns a nonzero exit code. Capture both.
    mc = Path(__file__).resolve().parent / "milestone_checks.py"
    proc = subprocess.run(
        [sys.executable, str(mc), "citations", str(spec)],
        capture_output=True, text=True,
    )
    cit_findings: list[dict] = []
    if proc.returncode != 0:
        for line in proc.stderr.splitlines():
            line = line.strip()
            if not line.startswith("Error:"):
                continue
            detail = line[len("Error:"):].strip()
            heading = _extract_heading(detail)
            # Dedup: a heading both checks report appears once, attributed to
            # structure (the dependent citations failure is suppressed).
            if heading and heading in struct_missing:
                continue
            cit_findings.append({"source": "citations", "heading": heading, "detail": detail})

    findings = struct_findings + cit_findings
    status = "pass" if not findings else "fail"
    _emit({"check": "floor", "status": status, "findings": findings})
    return 0 if status == "pass" else 1


# ── usage-gate (session/weekly usage-limit guard for the auto-loop) ──────────
#
# Reads the REAL subscription limits via Claude Code's own `/usage` (cost-free —
# num_turns:0), so the loop can pause before a mid-round cutoff and schedule its
# own resume at the reset. NOT a wall-clock proxy: the percentages and reset
# timestamps come straight from `/usage`.


def _parse_usage_line(line: str) -> tuple[int | None, str | None]:
    pm = re.search(r"(\d+)%\s*used", line)
    rm = re.search(r"resets\s+(.+?)\s*(?:\(|$)", line)
    return (int(pm.group(1)) if pm else None,
            rm.group(1).strip() if rm else None)


def _parse_reset(s: str | None) -> datetime | None:
    """'Jul 22, 1:49pm' → a future naive-local datetime (the reset instant).
    `/usage` prints local time and cron runs in local time, so no tz math."""
    if not s:
        return None
    s2 = re.sub(r"(?i)\b(am|pm)\b", lambda m: m.group(1).upper(), s.strip().rstrip("."))
    now = datetime.now()
    d: datetime | None = None
    for fmt in ("%b %d, %I:%M%p", "%b %d %I:%M%p", "%B %d, %I:%M%p"):
        try:
            d = datetime.strptime(s2, fmt).replace(year=now.year)
            break
        except ValueError:
            d = None
    if d is None:
        return None
    while d < now - timedelta(hours=1):        # a reset is always ahead; fix a year underflow
        d = d.replace(year=d.year + 1)
    return d


def cmd_usage_gate(session_max: int, weekly_max: int, buffer_min: int) -> int:
    """PAUSE if session% > session_max OR weekly% > weekly_max, and emit the
    binding reset as a one-shot cron string the loop hands to CronCreate. Any
    failure to read /usage returns verdict ERROR (the loop proceeds, degrading
    to pre-feature behaviour rather than halting on a monitoring hiccup)."""
    try:
        proc = subprocess.run(
            ["claude", "-p", "/usage", "--output-format", "json"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _emit({"check": "usage-gate", "verdict": "ERROR", "detail": f"could not run /usage: {e}"})
        return 0
    if proc.returncode != 0:
        _emit({"check": "usage-gate", "verdict": "ERROR", "detail": f"/usage exited {proc.returncode}"})
        return 0
    try:
        body = json.loads(proc.stdout).get("result", "")
    except (json.JSONDecodeError, AttributeError):
        body = proc.stdout

    session_pct = weekly_pct = None
    session_reset = weekly_reset = None
    for line in body.splitlines():
        ls = line.strip()
        if ls.startswith("Current session:"):
            session_pct, session_reset = _parse_usage_line(ls)
        elif ls.startswith("Current week (all models):"):
            weekly_pct, weekly_reset = _parse_usage_line(ls)
    if session_pct is None or weekly_pct is None:
        _emit({"check": "usage-gate", "verdict": "ERROR",
               "detail": "could not parse session/weekly lines from /usage output"})
        return 0

    session_over = session_pct > session_max
    weekly_over = weekly_pct > weekly_max
    verdict = "PAUSE" if (session_over or weekly_over) else "OK"
    # Weekly binds longer than session (a session reset won't clear a weekly cap),
    # so when weekly is over we wait for the weekly reset.
    binding = "weekly" if weekly_over else ("session" if session_over else None)
    resume_src = weekly_reset if binding == "weekly" else session_reset if binding == "session" else None

    resume_cron = resume_human = None
    resume_dt = _parse_reset(resume_src)
    if resume_dt is not None:
        resume_dt += timedelta(minutes=buffer_min)          # fire just after the window resets
        resume_cron = f"{resume_dt.minute} {resume_dt.hour} {resume_dt.day} {resume_dt.month} *"
        resume_human = resume_dt.strftime("%b %d, %H:%M")

    _emit({
        "check": "usage-gate",
        "verdict": verdict,
        "binding": binding,
        "session_pct": session_pct,
        "weekly_pct": weekly_pct,
        "session_max": session_max,
        "weekly_max": weekly_max,
        "session_reset": session_reset,
        "weekly_reset": weekly_reset,
        "resume_cron": resume_cron,
        "resume_human": resume_human,
    })
    return 0


# ── Decision records: shared load + dependency computation (D9) ──────────────


def _load_records(dpath: Path) -> list:
    if not dpath.is_file():
        return []
    data = json.loads(dpath.read_text())
    if not isinstance(data, list):
        raise ValueError(f"{dpath} is not a JSON list of records")
    return data


def _id_num(rid: object) -> int:
    m = re.match(r"^R(\d+)$", str(rid))
    return int(m.group(1)) if m else 0


def _derive_status(rec: dict) -> str:
    if rec.get("kind") == "non-goal-proposal":
        return "proposal"
    if rec.get("taken") is not None:
        return "taken"
    if rec.get("untakeable") is not None:
        return "blocked"
    return "pending"


def _post_sections(rec: dict) -> set:
    return set((rec.get("post_take_radius") or {}).get("sections", []) or [])


def _pre_atoms(rec: dict) -> int:
    return (rec.get("pre_take_radius") or {}).get("atoms", 0) or 0


def _all_deps(records: list) -> dict:
    """depends_on per record: mechanical edges (later id depends on earlier when
    their post-take radii overlap — a DAG by construction) unioned with stored
    semantic edges. Recomputed identically by briefing and decisions summary."""
    by_id = {r.get("id"): r for r in records}
    deps: dict = {r.get("id"): set() for r in records}
    ids = sorted(by_id, key=_id_num)
    for b in ids:
        for a in ids:
            if _id_num(a) < _id_num(b) and (_post_sections(by_id[b]) & _post_sections(by_id[a])):
                deps[b].add(a)
    for r in records:
        for s in (r.get("semantic_depends_on") or []):
            if s in deps:
                deps[r.get("id")].add(s)
    return deps


def _order_records(records: list) -> tuple[list, dict, dict]:
    """Dependency order (roots first), review_first floated up, ties by larger
    pre-take radius then id. Cycles (possible only via a stored semantic
    back-edge) break by a defined tiebreak and are flagged — every record is
    still emitted (the every-approval-gets-a-briefing invariant)."""
    deps = _all_deps(records)
    by_id = {r.get("id"): r for r in records}
    remaining = set(by_id)
    resolved: list = []
    resolved_set: set = set()
    circular: dict = {}

    def ready_key(rid: object) -> tuple:
        r = by_id[rid]
        return (0 if r.get("review_first") else 1, -_pre_atoms(r), _id_num(rid))

    def cycle_key(rid: object) -> tuple:
        return (-_pre_atoms(by_id[rid]), _id_num(rid))

    while remaining:
        ready = [rid for rid in remaining if deps[rid] <= resolved_set]
        if ready:
            chosen = sorted(ready, key=ready_key)[0]
        else:
            chosen = sorted(remaining, key=cycle_key)[0]
            circular[chosen] = sorted(deps[chosen] & remaining, key=_id_num)
        resolved.append(chosen)
        resolved_set.add(chosen)
        remaining.discard(chosen)
    return resolved, deps, circular


# ── decisions summary (Command flow projection) ─────────────────────────────


def cmd_decisions_summary(dpath: Path) -> int:
    try:
        records = _load_records(dpath)
    except (ValueError, json.JSONDecodeError) as e:
        return _fail(f"cannot read decisions: {e}")
    deps = _all_deps(records)
    projection = []
    for r in sorted(records, key=lambda x: _id_num(x.get("id"))):
        rid = r.get("id")
        projection.append({
            "id": rid,
            "kind": r.get("kind"),
            "status": _derive_status(r),
            "title": r.get("title", ""),
            "confidence": r.get("confidence"),
            "review_first": bool(r.get("review_first")),
            "dropped": bool(r.get("dropped")),
            "finding_atoms": r.get("finding_atoms", []),  # continuation rebuild recomputes atoms radius
            "pre_take_radius": r.get("pre_take_radius"),
            "post_take_radius": r.get("post_take_radius"),
            "depends_on": sorted(deps.get(rid, set()), key=_id_num),
        })
    _emit(projection)
    return 0


# ── briefing (D9) — deterministic human render, never omits a record ─────────


def _render_record(rec: dict, deps: list, circular: list | None) -> list[str]:
    rid = rec.get("id")
    status = _derive_status(rec)
    flags = []
    if rec.get("review_first"):
        flags.append("⭐ REVIEW FIRST")
    if rec.get("near_tie"):
        flags.append("near-tie")
    if rec.get("confidence") == "low":
        flags.append("low-confidence")
    if rec.get("dropped"):
        flags.append("dropped")
    flag_str = ("  [" + ", ".join(flags) + "]") if flags else ""

    lines = [f"## {rid}: {rec.get('title', '(untitled)')}{flag_str}",
             f"- Kind / Status: {rec.get('kind')} / {status}"]

    pre = rec.get("pre_take_radius") or {}
    post = rec.get("post_take_radius") or {}
    if pre:
        lines.append(f"- Pre-take radius: {len(pre.get('sections', []))} units, {pre.get('atoms', 0)} atoms")
    if post:
        lines.append(f"- Post-take radius: {len(post.get('sections', []))} units, {post.get('atoms', 0)} atoms")
    if deps:
        dep_str = ", ".join(deps)
        if circular:
            dep_str += f"   ⚠ circular edge with: {', '.join(circular)}"
        lines.append(f"- Depends on: {dep_str}")
    if rec.get("finding"):
        lines.append(f"- Finding: {rec['finding']}")
    if rec.get("research"):
        lines.append(f"- Research: {rec['research']}")
    for opt in (rec.get("options") or []):
        lines.append(f"  - Option: {opt.get('option', '')} — {opt.get('tradeoff', '')}")
    if status == "taken":
        lines.append(f"- Taken: {rec.get('taken')}  (by {rec.get('taken_by', '?')})")
    elif status == "blocked":
        lines.append(f"- BLOCKED (needs your decision): {rec.get('untakeable')}")
    elif status == "proposal":
        lines.append("- Proposed non-goal (approve to exclude from future reviews)")
    else:
        lines.append("- Pending: research or take did not complete")
    for old in (rec.get("superseded") or []):
        lines.append(f"  - superseded: {old}")
    lines.append("")
    return lines


def cmd_briefing(dpath: Path) -> int:
    try:
        records = _load_records(dpath)
    except (ValueError, json.JSONDecodeError) as e:
        return _fail(f"cannot read decisions: {e}")
    if not records:
        print("# Decision Briefing\n\nNo decisions recorded.")
        return 0
    order, deps, circular = _order_records(records)
    by_id = {r.get("id"): r for r in records}
    out = [f"# Decision Briefing ({len(records)} decision(s))", ""]
    for rid in order:
        out += _render_record(
            by_id[rid],
            sorted(deps.get(rid, set()), key=_id_num),
            circular.get(rid),
        )
    print("\n".join(out))
    return 0


# ── Atom ledger (D13) — extract, merge, reanchor, mark-dirty, record-verdicts,
#    coverage, radius; lineage + churn ─────────────────────────────────────────
#
# The pyramid's working state. Managed exclusively here (never hand-edited).
# Spans are CHARACTER offsets into the document so two distinct prose atoms on
# one line stay distinct (line spans would collapse them). Document text always
# comes from the working copy passed as <doc>; the ledger lives at the separate
# --ledger path (decoupled from improve_files' naming).


def _atom_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_ledger(path: Path) -> dict:
    if not path.is_file():
        return {"atoms": [], "macro_findings": []}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or "atoms" not in data:
        raise ValueError(f"{path} is not a valid atom ledger")
    data.setdefault("macro_findings", [])
    return data


def _write_ledger(path: Path, ledger: dict) -> None:
    path.write_text(json.dumps(ledger, indent=2) + "\n")


def _doc_lines(text: str) -> list[str]:
    return text.split("\n")


def _line_index(text: str, char_pos: int) -> int:
    return text.count("\n", 0, max(0, char_pos))


def _anchor_at(lines: list[str], idx: int) -> str:
    """Canonical section path enclosing line ``idx``: the ``##``-to-deepest-
    ``###`` chain joined by ' / ' (D13 anchoring; the script is the sole
    canonicalizer)."""
    h3: str | None = None
    h2: str | None = None
    for i in range(min(idx, len(lines) - 1), -1, -1):
        s = lines[i].rstrip()
        if h3 is None and s.startswith("### "):
            h3 = s
        if s.startswith("## ") and not s.startswith("### "):
            h2 = s
            break
    if h2 and h3:
        return f"{h2} / {h3}"
    if h2:
        return h2
    if h3:
        return h3
    return "(preamble)"


def _anchor_at_char(text: str, char_pos: int) -> str:
    return _anchor_at(_doc_lines(text), _line_index(text, char_pos))


def _heading_key(h: str) -> str:
    """Normalize a heading for matching — drop a trailing ': title' so a bare
    '### D3' in a report matches the document's '### D3: A decision'."""
    return re.sub(r":\s.*$", "", h.strip()).rstrip()


def _canonicalize(raw: str, text: str) -> str:
    """Resolve a raw/bare heading (e.g. '### D3', or an already-canonical chain)
    to canonical '## X / ### Y' form against the current heading tree."""
    target = raw.strip().split("/")[-1].strip()
    tkey = _heading_key(target)
    lines = _doc_lines(text)
    for i, ln in enumerate(lines):
        s = ln.rstrip()
        if (s.startswith("## ") or s.startswith("### ")) and _heading_key(s) == tkey:
            return _anchor_at(lines, i)
    return raw.strip()


def _mk_atom(atype: str, anchor: str, text: str, start: int, end: int) -> dict:
    return {
        "id": None,
        "lineage_id": None,
        "type": atype,
        "anchor": anchor,
        "text": text,
        "hash": _atom_hash(text),
        "span": {"start": start, "end": end},
        "input_set": {"sections": [anchor], "external": []},
        "verdict": {"state": "unverified", "computed_against_hash": None},
        "churn": {"verdict_flips": 0, "fix_count": 0, "last_conclusion": None},
    }


_CITE = re.compile(r"\(D\d+(?:,\s*D\d+)*\)")
_DBLOCK = re.compile(r"^### D\d+:")


def _extract_mechanical(text: str) -> list[dict]:
    """Deterministic mechanical atoms with CHARACTER spans: D-block frames
    (### Dn: heading), other headings, code-fenced contracts, citation bullets.
    Prose atoms come from the redundant extraction agents, merged in by `merge`."""
    atoms: list[dict] = []
    pos = 0
    in_fence = False
    fence_start = 0
    for line in _doc_lines(text):
        line_start = pos
        line_end = pos + len(line)
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            if not in_fence:
                in_fence = True
                fence_start = line_start
            else:
                in_fence = False
                atoms.append(_mk_atom("contract", _anchor_at_char(text, fence_start),
                                      text[fence_start:line_end], fence_start, line_end))
        elif not in_fence:
            s = line.rstrip()
            if _DBLOCK.match(s):
                atoms.append(_mk_atom("d-block", _anchor_at_char(text, line_start), s, line_start, line_end))
            elif s.startswith("## ") or s.startswith("### "):
                atoms.append(_mk_atom("heading", _anchor_at_char(text, line_start), s, line_start, line_end))
            elif line.startswith("- ") and _CITE.search(line):
                atoms.append(_mk_atom("citation", _anchor_at_char(text, line_start), s, line_start, line_end))
        pos = line_end + 1
    return atoms


def _assign_ids(atoms: list[dict], start: int = 1) -> list[dict]:
    for k, a in enumerate(atoms):
        a["id"] = f"a{start + k}"
        a["lineage_id"] = f"L{start + k}"
    return atoms


def _next_num(ledger: dict, prefix: str, field: str) -> int:
    nums = [int(m.group(1)) for a in ledger["atoms"]
            if (m := re.match(rf"{prefix}(\d+)$", str(a.get(field, ""))))]
    return (max(nums) + 1) if nums else 1


def _locate(atext: str, doc_text: str) -> tuple[int, int] | None:
    idx = doc_text.find(atext)
    return None if idx == -1 else (idx, idx + len(atext))


def _spans_overlap(a: tuple, b: tuple) -> bool:
    return a[0] < b[1] and b[0] < a[1]


# ── extract ──────────────────────────────────────────────────────────────────


def cmd_atoms_extract(doc: Path, ledger_path: Path | None, write: bool) -> int:
    if not doc.is_file():
        return _fail(f"document not found: {doc}")
    atoms = _assign_ids(_extract_mechanical(doc.read_text()))
    if write:
        if ledger_path is None:
            return _fail("atoms extract --write requires --ledger <path>")
        _write_ledger(ledger_path, {"atoms": atoms, "macro_findings": []})
    _emit({"atoms": atoms})
    return 0


# ── merge (prose union, tie-breaks, drop-mechanical-overlap) ─────────────────


def _native_type(anchor: str, types: list[str]) -> str:
    """Section-native precedence for a cross-type overlap (D13): a scope section
    resolves to scope-item; otherwise claim > assumption > example."""
    if "What gets built" in anchor or "What does NOT get built" in anchor:
        return "scope-item"
    for t in ("claim", "assumption", "example"):
        if t in types:
            return t
    return types[0]


def _cluster_overlapping(items: list[dict]) -> list[list[dict]]:
    """Group candidates whose char spans transitively overlap."""
    items = sorted(items, key=lambda c: c["span"][0])
    clusters: list[list[dict]] = []
    cur: list[dict] = []
    cur_end = -1
    for c in items:
        s, e = c["span"]
        if cur and s < cur_end:
            cur.append(c)
            cur_end = max(cur_end, e)
        else:
            if cur:
                clusters.append(cur)
            cur = [c]
            cur_end = e
    if cur:
        clusters.append(cur)
    return clusters


def _merge_prose(located: list[dict]) -> list[dict]:
    """Same-type + same-section + overlapping candidates collapse to the WIDEST
    span; a cross-type overlap reconciles to one atom by section-native
    precedence; disjoint candidates survive. No flagged text is dropped — the
    widest span of a cluster contains the narrower ones."""
    by_anchor: dict = {}
    for c in located:
        by_anchor.setdefault(c["anchor"], []).append(c)
    result: list[dict] = []
    for anchor, group in by_anchor.items():
        for cluster in _cluster_overlapping(group):
            types = [c["type"] for c in cluster]
            widest = max(cluster, key=lambda c: c["span"][1] - c["span"][0])
            atype = types[0] if len(set(types)) == 1 else _native_type(anchor, types)
            result.append({"type": atype, "text": widest["text"], "anchor": anchor,
                           "span": {"start": widest["span"][0], "end": widest["span"][1]}})
    result.sort(key=lambda r: r["span"]["start"])
    return result


def cmd_atoms_merge(doc: Path, ledger_path: Path, cand_files: list[str], write: bool) -> int:
    if not doc.is_file():
        return _fail(f"document not found: {doc}")
    try:
        ledger = _load_ledger(ledger_path)
    except (ValueError, json.JSONDecodeError) as e:
        return _fail(f"cannot read ledger: {e}")
    doc_text = doc.read_text()
    mech_spans = [(a["span"]["start"], a["span"]["end"]) for a in ledger["atoms"] if "span" in a]

    located: list[dict] = []
    for cf in cand_files:
        p = Path(cf)
        if not p.is_file():
            return _fail(f"candidates file not found: {p}")
        data = json.loads(p.read_text())
        items = data if isinstance(data, list) else data.get("candidates", [])
        for c in items:
            t = c.get("text", "")
            if not t:
                continue
            span = _locate(t, doc_text)
            if span is None:
                continue                                    # unlocatable (fidelity miss) — skip
            if any(_spans_overlap(span, ms) for ms in mech_spans):
                continue                                    # overlaps a mechanical span — dropped at merge
            located.append({"type": c.get("type", "claim"), "text": t,
                            "anchor": _anchor_at_char(doc_text, span[0]), "span": span})

    merged = _merge_prose(located)
    na = _next_num(ledger, "a", "id")
    nl = _next_num(ledger, "L", "lineage_id")
    new_atoms: list[dict] = []
    for k, mg in enumerate(merged):
        atom = _mk_atom(mg["type"], mg["anchor"], mg["text"], mg["span"]["start"], mg["span"]["end"])
        atom["id"] = f"a{na + k}"
        atom["lineage_id"] = f"L{nl + k}"
        new_atoms.append(atom)
    if write:
        ledger["atoms"].extend(new_atoms)
        _write_ledger(ledger_path, ledger)
    _emit({"merged_atoms": new_atoms})
    return 0


# ── reanchor (content-hash re-walk + external-input staleness) ───────────────


def _find_atom(new_lines: list[str], new_text: str, text: str) -> tuple[int, int] | None:
    """Locate an atom's stored text in the current document (content-hash re-walk
    as a text search). Returns (start_line, end_line) or None if vanished."""
    if "\n" in text:
        idx = new_text.find(text)
        if idx == -1:
            return None
        start = new_text.count("\n", 0, idx)
        return (start, start + text.count("\n"))
    for i, ln in enumerate(new_lines):
        if ln.rstrip() == text:
            return (i, i)
    return None


def _uncovered_regions(new_lines: list[str], covered: set[int]) -> list[dict]:
    regions: list[dict] = []
    cur: dict | None = None
    for i, ln in enumerate(new_lines):
        if i in covered or not ln.strip():
            if cur:
                regions.append(cur)
                cur = None
        elif cur is None:
            cur = {"start_line": i, "end_line": i}
        else:
            cur["end_line"] = i
    if cur:
        regions.append(cur)
    return regions


def cmd_atoms_reanchor(doc: Path, ledger_path: Path) -> int:
    if not doc.is_file():
        return _fail(f"document not found: {doc}")
    try:
        ledger = _load_ledger(ledger_path)
    except (ValueError, json.JSONDecodeError) as e:
        return _fail(f"cannot read ledger: {e}")
    new_text = doc.read_text()
    new_lines = new_text.split("\n")
    relocated: list[dict] = []
    vanished: list[str] = []
    external_stale: list[str] = []
    covered: set[int] = set()
    for atom in ledger["atoms"]:
        pos = _find_atom(new_lines, new_text, atom["text"])
        if pos is None:
            vanished.append(atom["id"])
        else:
            start, end = pos
            covered.update(range(start, end + 1))
            new_anchor = _anchor_at(new_lines, start)
            if new_anchor != atom["anchor"]:
                relocated.append({"id": atom["id"], "old": atom["anchor"], "new": new_anchor})
        for ext in atom.get("input_set", {}).get("external", []):
            ep = Path(ext.get("path", ""))
            if ep.is_file() and _atom_hash(ep.read_text()) != ext.get("hash"):
                external_stale.append(atom["id"])
                break
    _emit({
        "relocated": relocated,
        "vanished": vanished,
        "external_stale": external_stale,
        "new_regions": _uncovered_regions(new_lines, covered),
    })
    return 0


# ── mark-dirty (canonicalize + input-set propagation) ────────────────────────


def cmd_atoms_mark_dirty(doc: Path, ledger_path: Path, touched_json: str) -> int:
    if not doc.is_file():
        return _fail(f"document not found: {doc}")
    try:
        ledger = _load_ledger(ledger_path)
    except (ValueError, json.JSONDecodeError) as e:
        return _fail(f"cannot read ledger: {e}")
    try:
        touched_raw = json.loads(touched_json)
    except json.JSONDecodeError:
        return _fail("mark-dirty --touched must be a JSON list of section paths")
    doc_text = doc.read_text()
    canon_touched = {_canonicalize(t, doc_text) for t in touched_raw}
    dirty: list[str] = []
    for atom in ledger["atoms"]:
        atom_sections = {_canonicalize(s, doc_text) for s in atom.get("input_set", {}).get("sections", [])}
        if atom_sections & canon_touched:
            dirty.append(atom["id"])
    _emit({"dirty": dirty, "canonical_touched": sorted(canon_touched)})
    return 0


# ── record-verdicts (sole round-close writer) ────────────────────────────────


def _assign_new_lineage(new_atoms: list[dict], vanished_atoms: list[dict], ledger: dict) -> None:
    """A successor inherits its predecessor's lineage id + churn counters, matched
    by anchor locality (same section; among several, the highest-churn ancestor —
    the merge rule; a split forks the same id to every successor). fix_count += 1
    for the edit that produced the successor. No predecessor → a fresh lineage."""
    next_l = _next_num(ledger, "L", "lineage_id")
    for na in new_atoms:
        if na.get("lineage_id"):
            continue
        cands = [va for va in vanished_atoms if va.get("anchor") == na.get("anchor")]
        if cands:
            pred = max(cands, key=lambda va: (va.get("churn", {}).get("fix_count", 0),
                                              va.get("churn", {}).get("verdict_flips", 0)))
            pc = pred.get("churn", {})
            na["lineage_id"] = pred.get("lineage_id")
            na["churn"] = {"verdict_flips": pc.get("verdict_flips", 0),
                           "fix_count": pc.get("fix_count", 0) + 1,
                           "last_conclusion": pc.get("last_conclusion")}
        else:
            na["lineage_id"] = f"L{next_l}"
            next_l += 1
            na.setdefault("churn", {"verdict_flips": 0, "fix_count": 0, "last_conclusion": None})


def cmd_atoms_record_verdicts(ledger_path: Path, verdicts_path: Path) -> int:
    """Sole round-close ledger writer. Applies the whole round delta — verdicts
    (overwriting prior), churn (verdict_flips only on a finding-conclusion change),
    input-set-propagation dirty flags, reanchor delta (relocations, vanished
    removal, external-stale dirtying), incrementally-extracted atoms (with
    lineage), and macro-finding fix_count bumps — and echoes the applied verdict
    count so the JS can assert it equals what it marshaled in."""
    try:
        ledger = _load_ledger(ledger_path)
    except (ValueError, json.JSONDecodeError) as e:
        return _fail(f"cannot read ledger: {e}")
    if not verdicts_path.is_file():
        return _fail(f"verdict log not found: {verdicts_path}")
    try:
        vf = json.loads(verdicts_path.read_text())
    except json.JSONDecodeError as e:
        return _fail(f"verdict log not valid JSON: {e}")

    by_id = {a["id"]: a for a in ledger["atoms"]}
    applied = 0
    for v in vf.get("atom_verdicts", []):
        atom = by_id.get(v.get("atom_id"))
        if atom is None:
            continue
        conclusion = v.get("finding_conclusion")
        if conclusion is not None:
            churn = atom.setdefault("churn", {"verdict_flips": 0, "fix_count": 0, "last_conclusion": None})
            last = churn.get("last_conclusion")
            if last is not None and last != conclusion:
                churn["verdict_flips"] = churn.get("verdict_flips", 0) + 1
            churn["last_conclusion"] = conclusion
        atom["verdict"] = {"state": v.get("state"), "computed_against_hash": v.get("computed_against_hash")}
        if "input_set" in v:
            atom["input_set"] = v["input_set"]
        applied += 1

    delta = vf.get("reanchor_delta", {})
    for r in delta.get("relocated", []):
        atom = by_id.get(r["id"])
        if atom:
            atom["anchor"] = r["new"]

    def _dirty(atom_id: str) -> None:
        atom = by_id.get(atom_id)
        if atom and atom["verdict"].get("state") == "verified":
            atom["verdict"]["state"] = "dirty"

    for did in vf.get("dirty", []):
        _dirty(did)
    for did in delta.get("external_stale", []):
        _dirty(did)

    vanished_ids = set(delta.get("vanished", []))
    vanished_atoms = [a for a in ledger["atoms"] if a["id"] in vanished_ids]
    new_atoms = vf.get("new_atoms", [])
    _assign_new_lineage(new_atoms, vanished_atoms, ledger)
    ledger["atoms"] = [a for a in ledger["atoms"] if a["id"] not in vanished_ids]

    next_a = _next_num(ledger, "a", "id")
    for k, na in enumerate(new_atoms):
        na.setdefault("id", f"a{next_a + k}")
        na.setdefault("hash", _atom_hash(na.get("text", "")))
        ledger["atoms"].append(na)

    macro = {m["id"]: m for m in ledger.get("macro_findings", [])}
    for mf in vf.get("macro_findings", []):
        mid = mf.get("id")
        entry = macro.get(mid)
        if entry is None:
            entry = {"id": mid, "fix_count": 0}
            macro[mid] = entry
            ledger.setdefault("macro_findings", []).append(entry)
        if mf.get("fixed"):
            entry["fix_count"] = entry.get("fix_count", 0) + 1

    _write_ledger(ledger_path, ledger)
    _emit({"applied": applied, "new_atoms_added": len(new_atoms), "atom_count": len(ledger["atoms"])})
    return 0


# ── coverage + radius ────────────────────────────────────────────────────────


def cmd_atoms_coverage(ledger_path: Path) -> int:
    """{verified, unverifiable, total, complete, never_verified}. Denominator
    excludes heading atoms (no micro-check) and vanished atoms (already removed).
    An atom is verified only if state==verified AND computed against the current
    hash; a hash-stale 'verified' atom counts as dirty."""
    try:
        ledger = _load_ledger(ledger_path)
    except (ValueError, json.JSONDecodeError) as e:
        return _fail(f"cannot read ledger: {e}")
    non_heading = [a for a in ledger["atoms"] if a.get("type") != "heading"]
    verified = unverifiable = 0
    never_verified: list[str] = []
    dirty: list[str] = []
    for a in non_heading:
        st = a.get("verdict", {}).get("state")
        if st == "verified":
            if a["verdict"].get("computed_against_hash") == a.get("hash"):
                verified += 1
            else:
                dirty.append(a["id"])
        elif st == "unverifiable":
            unverifiable += 1
        elif st == "dirty":
            dirty.append(a["id"])
        else:
            never_verified.append(a["id"])
    total = len(non_heading)
    _emit({
        "verified": verified,
        "unverifiable": unverifiable,
        "total": total,
        "complete": verified + unverifiable == total,
        "never_verified": never_verified,
        "dirty": dirty,
    })
    return 0


def cmd_atoms_radius(ledger_path: Path, lineage_json: str) -> int:
    """Anchor-unit footprint of a set of lineage ids (the evidence footprint the
    pre-take blast radius and briefing ranking consume)."""
    try:
        ledger = _load_ledger(ledger_path)
    except (ValueError, json.JSONDecodeError) as e:
        return _fail(f"cannot read ledger: {e}")
    try:
        lids = set(json.loads(lineage_json))
    except json.JSONDecodeError:
        return _fail("radius --atoms must be a JSON list of lineage ids")
    atoms = [a for a in ledger["atoms"] if a.get("lineage_id") in lids]
    sections = sorted({a.get("anchor") for a in atoms})
    _emit({"sections": sections, "units": len(sections), "atoms": len(atoms)})
    return 0


def cmd_atoms_churn_check(ledger_path: Path) -> int:
    """Step-7 escalation threshold (D2/D13). Returns the lineage ids whose churn
    has crossed CHURN_ESCALATE and the macro-finding ids that have been fixed
    that many times, so the drain does only set-membership lookups."""
    try:
        ledger = _load_ledger(ledger_path)
    except (ValueError, json.JSONDecodeError) as e:
        return _fail(f"cannot read ledger: {e}")
    flip_lids: set[str] = set()
    fix_lids: set[str] = set()
    for atom in ledger["atoms"]:
        lid = atom.get("lineage_id")
        if lid is None:
            continue
        churn = atom.get("churn", {})
        if churn.get("verdict_flips", 0) >= CHURN_ESCALATE:
            flip_lids.add(lid)
        if churn.get("fix_count", 0) >= CHURN_ESCALATE:
            fix_lids.add(lid)
    macros = sorted(
        m["id"] for m in ledger.get("macro_findings", [])
        if m.get("fix_count", 0) >= CHURN_ESCALATE
    )
    _emit({
        "flip_escalate_lineages": sorted(flip_lids),
        "fix_escalate_lineages": sorted(fix_lids),
        "escalate_macros": macros,
    })
    return 0


def cmd_atoms_macro_ids(doc: Path, findings_json: str) -> int:
    """Canonical macro-finding ids (D13: the script is its sole canonicalizer).
    Each finding is '<class>:<sorted distinct canonical sections joined by |>'."""
    if not doc.is_file():
        return _fail(f"doc not found: {doc}")
    try:
        findings = json.loads(findings_json)
    except json.JSONDecodeError:
        return _fail("macro-ids --findings must be a JSON list")
    doc_text = doc.read_text()
    ids: list[str] = []
    for finding in findings:
        cls = finding.get("class", "")
        canon = sorted({_canonicalize(s, doc_text) for s in finding.get("sections", [])})
        ids.append(f"{cls}:" + "|".join(canon))
    _emit({"ids": ids})
    return 0


# ── atoms dispatch ───────────────────────────────────────────────────────────


def _dispatch_atoms(subargs: list[str]) -> int:
    if not subargs:
        return _fail("atoms requires a subcommand "
                     "(extract | merge | reanchor | mark-dirty | record-verdicts | "
                     "coverage | radius | churn-check | macro-ids)")
    sub, rest = subargs[0], subargs[1:]
    if sub == "extract":
        ledger, rest = _flag(rest, "--ledger")
        write = "--write" in rest
        positionals = [a for a in rest if not a.startswith("--")]
        if not positionals:
            return _fail("atoms extract requires <doc>")
        return cmd_atoms_extract(Path(positionals[0]), Path(ledger) if ledger else None, write)
    if sub == "merge":
        ledger, rest = _flag(rest, "--ledger")
        cands, rest = _flag(rest, "--candidates")
        write = "--write" in rest
        positionals = [a for a in rest if not a.startswith("--")]
        if not positionals or not ledger or not cands:
            return _fail("atoms merge requires <doc> --ledger <path> --candidates <f1[,f2]>")
        return cmd_atoms_merge(Path(positionals[0]), Path(ledger), cands.split(","), write)
    if sub == "reanchor":
        ledger, rest = _flag(rest, "--ledger")
        positionals = [a for a in rest if not a.startswith("--")]
        if not positionals or not ledger:
            return _fail("atoms reanchor requires <doc> --ledger <path>")
        return cmd_atoms_reanchor(Path(positionals[0]), Path(ledger))
    if sub == "mark-dirty":
        ledger, rest = _flag(rest, "--ledger")
        touched, rest = _flag(rest, "--touched")
        positionals = [a for a in rest if not a.startswith("--")]
        if not positionals or not ledger or touched is None:
            return _fail("atoms mark-dirty requires <doc> --ledger <path> --touched <json>")
        return cmd_atoms_mark_dirty(Path(positionals[0]), Path(ledger), touched)
    if sub == "record-verdicts":
        ledger, rest = _flag(rest, "--ledger")
        verdicts, rest = _flag(rest, "--verdicts")
        if not ledger or not verdicts:
            return _fail("atoms record-verdicts requires --ledger <path> --verdicts <file>")
        return cmd_atoms_record_verdicts(Path(ledger), Path(verdicts))
    if sub == "coverage":
        ledger, rest = _flag(rest, "--ledger")
        if not ledger:
            return _fail("atoms coverage requires --ledger <path>")
        return cmd_atoms_coverage(Path(ledger))
    if sub == "radius":
        ledger, rest = _flag(rest, "--ledger")
        atoms_json, rest = _flag(rest, "--atoms")
        if not ledger or atoms_json is None:
            return _fail("atoms radius requires --ledger <path> --atoms <json>")
        return cmd_atoms_radius(Path(ledger), atoms_json)
    if sub == "churn-check":
        ledger, rest = _flag(rest, "--ledger")
        if not ledger:
            return _fail("atoms churn-check requires --ledger <path>")
        return cmd_atoms_churn_check(Path(ledger))
    if sub == "macro-ids":
        doc, rest = _flag(rest, "--doc")
        findings, rest = _flag(rest, "--findings")
        if not doc or findings is None:
            return _fail("atoms macro-ids requires --doc <path> --findings <json>")
        return cmd_atoms_macro_ids(Path(doc), findings)
    return _fail(f"unknown atoms subcommand: {sub}")


# ── CLI dispatch ────────────────────────────────────────────────────────────

USAGE = """\
Usage: spec_checks.py <command> [args]

  structure <spec>                     Required-template-heading check
  tally [--head-to-head] <votes-file>  Gate vote math / competitive-rewrite winner
  block-gate <inputs-file>             D5 take-vs-block (takeable | blocked)
  floor <spec>                         citations + structure → one relay verdict
  usage-gate [--session-max N] [--weekly-max N] [--buffer-min N]
                                       Read /usage; PAUSE|OK + resume cron string
  briefing <decisions-file>            Deterministic human render of decisions
  decisions summary <decisions-file>   Thin decision projection (JSON)
  atoms extract <doc> [--ledger P --write]           Mechanical atom extraction
  atoms merge <doc> --ledger P --candidates F1[,F2] [--write]  Prose union-merge
  atoms reanchor <doc> --ledger P                     Content-hash re-walk delta
  atoms mark-dirty <doc> --ledger P --touched JSON    Input-set-propagation dirty set
  atoms record-verdicts --ledger P --verdicts F       Apply round delta (echoes count)
  atoms coverage --ledger P                           Coverage-completeness verdict
  atoms radius --ledger P --atoms JSON                Anchor-unit footprint of lineage ids
  atoms churn-check --ledger P                        Step-7 escalation lineage/macro sets
  atoms macro-ids --doc D --findings JSON             Canonical macro-finding ids
"""


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(USAGE, file=sys.stderr)
        return 1
    command = args[0]

    if command == "structure":
        if len(args) < 2:
            return _fail("structure requires <spec>")
        return cmd_structure(Path(args[1]))
    if command == "tally":
        rest = [a for a in args[1:] if a != "--head-to-head"]
        head_to_head = "--head-to-head" in args[1:]
        if not rest:
            return _fail("tally requires <votes-file>")
        return cmd_tally(Path(rest[0]), head_to_head)
    if command == "block-gate":
        if len(args) < 2:
            return _fail("block-gate requires <inputs-file>")
        return cmd_block_gate(Path(args[1]))
    if command == "floor":
        if len(args) < 2:
            return _fail("floor requires <spec>")
        return cmd_floor(Path(args[1]))
    if command == "usage-gate":
        rest = args[1:]
        smax, rest = _flag(rest, "--session-max")
        wmax, rest = _flag(rest, "--weekly-max")
        buf, rest = _flag(rest, "--buffer-min")
        try:
            return cmd_usage_gate(int(smax) if smax else 75,
                                  int(wmax) if wmax else 90,
                                  int(buf) if buf else 2)
        except ValueError:
            return _fail("usage-gate flags must be integers")
    if command == "briefing":
        if len(args) < 2:
            return _fail("briefing requires <decisions-file>")
        return cmd_briefing(Path(args[1]))
    if command == "decisions":
        if len(args) < 2:
            return _fail("decisions requires a subcommand (summary)")
        if args[1] == "summary":
            if len(args) < 3:
                return _fail("decisions summary requires <decisions-file>")
            return cmd_decisions_summary(Path(args[2]))
        return _fail(f"unknown decisions subcommand: {args[1]}")
    if command == "atoms":
        return _dispatch_atoms(args[1:])

    print(f"Error: unknown command: {command}", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
