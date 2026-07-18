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


# ── Atom ledger (D13) — minimal core: extract, reanchor, record-verdicts ─────
#
# The pyramid's working state. Managed exclusively here (never hand-edited).
# This is the minimal slice the ledger-fidelity spike (Gate B) exercises; Phase
# 2 extends it with prose merge tie-breaks, lineage, input-set propagation,
# coverage, and radius. The document text always comes from the working copy
# passed as <doc>; the ledger lives at the separate --ledger path (the two are
# decoupled, so this module never depends on improve_files' naming).


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


def _anchor_at(lines: list[str], idx: int) -> str:
    """Canonical section path enclosing line ``idx``: the ``##``-to-deepest-
    ``###`` chain joined by ' / ' (concept D13 anchoring; script is the sole
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


def _mk_atom(atype: str, anchor: str, text: str, start: int, end: int) -> dict:
    return {
        "id": None,
        "lineage_id": None,
        "type": atype,
        "anchor": anchor,
        "text": text,
        "hash": _atom_hash(text),
        "span": {"start_line": start, "end_line": end},
        "input_set": {"sections": [anchor], "external": []},
        "verdict": {"state": "unverified", "computed_against_hash": None},
        "churn": {"verdict_flips": 0, "fix_count": 0},
    }


_CITE = re.compile(r"\(D\d+(?:,\s*D\d+)*\)")


def _extract_mechanical(text: str) -> list[dict]:
    """Deterministic mechanical atoms: headings, code-fenced contracts, and
    citation bullets. (Prose atoms — claims/assumptions/scope-items/examples —
    come from the redundant extraction agents, merged in later.)"""
    lines = text.splitlines()
    atoms: list[dict] = []
    in_fence = False
    fence_start = 0
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            if not in_fence:
                in_fence = True
                fence_start = i
            else:
                in_fence = False
                block = "\n".join(lines[fence_start:i + 1])
                atoms.append(_mk_atom("contract", _anchor_at(lines, fence_start), block, fence_start, i))
            continue
        if in_fence:
            continue
        s = line.rstrip()
        if s.startswith("## ") or s.startswith("### "):
            atoms.append(_mk_atom("heading", _anchor_at(lines, i), s, i, i))
        elif line.startswith("- ") and _CITE.search(line):
            atoms.append(_mk_atom("citation", _anchor_at(lines, i), s, i, i))
    return atoms


def _assign_ids(atoms: list[dict], start: int = 1) -> list[dict]:
    for k, a in enumerate(atoms):
        a["id"] = f"a{start + k}"
        a["lineage_id"] = f"L{start + k}"
    return atoms


def _find_atom(new_lines: list[str], new_text: str, text: str) -> tuple[int, int] | None:
    """Locate an atom's stored text in the current document (content-hash
    re-walk, realized as a text search). Returns (start_line, end_line) or None
    if the atom vanished."""
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


def cmd_atoms_reanchor(doc: Path, ledger_path: Path) -> int:
    if not doc.is_file():
        return _fail(f"document not found: {doc}")
    try:
        ledger = _load_ledger(ledger_path)
    except (ValueError, json.JSONDecodeError) as e:
        return _fail(f"cannot read ledger: {e}")
    new_text = doc.read_text()
    new_lines = new_text.splitlines()
    relocated: list[dict] = []
    vanished: list[str] = []
    covered: set[int] = set()
    for atom in ledger["atoms"]:
        pos = _find_atom(new_lines, new_text, atom["text"])
        if pos is None:
            vanished.append(atom["id"])
            continue
        start, end = pos
        covered.update(range(start, end + 1))
        new_anchor = _anchor_at(new_lines, start)
        if new_anchor != atom["anchor"]:
            relocated.append({"id": atom["id"], "old": atom["anchor"], "new": new_anchor})
    _emit({
        "relocated": relocated,
        "vanished": vanished,
        "new_regions": _uncovered_regions(new_lines, covered),
    })
    return 0


def cmd_atoms_record_verdicts(ledger_path: Path, verdicts_path: Path) -> int:
    """Sole round-close ledger writer. Applies verdicts + reanchor delta + any
    incrementally-extracted atoms, and echoes the applied count so the JS can
    assert it equals what it marshaled in (reverse-relay guard, concept)."""
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
        atom["verdict"] = {"state": v.get("state"), "computed_against_hash": v.get("computed_against_hash")}
        if "input_set" in v:
            atom["input_set"] = v["input_set"]
        applied += 1

    delta = vf.get("reanchor_delta", {})
    for r in delta.get("relocated", []):
        atom = by_id.get(r["id"])
        if atom:
            atom["anchor"] = r["new"]
    vanished = set(delta.get("vanished", []))
    ledger["atoms"] = [a for a in ledger["atoms"] if a["id"] not in vanished]

    new_atoms = vf.get("new_atoms", [])
    nums = [int(m.group(1)) for a in ledger["atoms"] if (m := re.match(r"a(\d+)$", str(a.get("id"))))]
    next_a = (max(nums) + 1) if nums else 1
    for k, na in enumerate(new_atoms):
        na.setdefault("id", f"a{next_a + k}")
        na.setdefault("hash", _atom_hash(na.get("text", "")))
        ledger["atoms"].append(na)

    _write_ledger(ledger_path, ledger)
    _emit({"applied": applied, "new_atoms_added": len(new_atoms), "atom_count": len(ledger["atoms"])})
    return 0


def _dispatch_atoms(subargs: list[str]) -> int:
    if not subargs:
        return _fail("atoms requires a subcommand (extract | reanchor | record-verdicts)")
    sub, rest = subargs[0], subargs[1:]
    if sub == "extract":
        ledger, rest = _flag(rest, "--ledger")
        write = "--write" in rest
        positionals = [a for a in rest if not a.startswith("--")]
        if not positionals:
            return _fail("atoms extract requires <doc>")
        return cmd_atoms_extract(Path(positionals[0]), Path(ledger) if ledger else None, write)
    if sub == "reanchor":
        ledger, rest = _flag(rest, "--ledger")
        positionals = [a for a in rest if not a.startswith("--")]
        if not positionals or not ledger:
            return _fail("atoms reanchor requires <doc> --ledger <path>")
        return cmd_atoms_reanchor(Path(positionals[0]), Path(ledger))
    if sub == "record-verdicts":
        ledger, rest = _flag(rest, "--ledger")
        verdicts, rest = _flag(rest, "--verdicts")
        if not ledger or not verdicts:
            return _fail("atoms record-verdicts requires --ledger <path> --verdicts <file>")
        return cmd_atoms_record_verdicts(Path(ledger), Path(verdicts))
    return _fail(f"unknown atoms subcommand: {sub}")


# ── CLI dispatch ────────────────────────────────────────────────────────────

USAGE = """\
Usage: spec_checks.py <command> [args]

  structure <spec>                     Required-template-heading check
  tally [--head-to-head] <votes-file>  Gate vote math / competitive-rewrite winner
  block-gate <inputs-file>             D5 take-vs-block (takeable | blocked)
  floor <spec>                         citations + structure → one relay verdict
  briefing <decisions-file>            Deterministic human render of decisions
  decisions summary <decisions-file>   Thin decision projection (JSON)
  atoms extract <doc> [--ledger P --write]        Mechanical atom extraction
  atoms reanchor <doc> --ledger P                 Content-hash re-walk delta
  atoms record-verdicts --ledger P --verdicts F   Apply round delta (echoes count)
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
