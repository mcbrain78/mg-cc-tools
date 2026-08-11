#!/usr/bin/env python3
"""File operations for the spec-improve / spec-improve-auto workflows.

Single source of truth for naming conventions and all deterministic file
operations. The LLM command orchestrates; this script acts. Reads and
status-derivation over the decision records live in ``spec_checks.py``
(``briefing`` / ``decisions summary``); only *writes* live here, per the
family read/write split (concept D9).

Naming conventions (given ``concept.md``):
    original backup   : concept.original.md
    working copy      : concept-auto-improve.md
    non-goals         : concept-NON-GOALS.md
    implementer notes : concept-IMPLEMENTER-NOTES.md   (new)
    changelog         : concept-CHANGELOG.md           (new)
    atom ledger       : concept-ATOMS.json             (new; managed by spec_checks.py atoms)
    decision records  : concept-DECISIONS.json         (new)
    run history        : history/run-N/                (new)

Subcommands
-----------
init <file> [--fresh]
    Back up the original (once) and create the working copy. Refuses to
    overwrite an existing working copy (exit 1) unless ``--fresh`` is given,
    which first archives the session sidecars (changelog, ledger, decisions,
    AND implementer-notes) into history/ then resets. Emits the resolved-paths
    JSON (see ``paths``) plus ``backup_created``.

paths <file>
    Emit the same resolved-paths JSON as ``init`` WITHOUT touching any file —
    the resume entry point after a guard failure or crash.

approve <file> / reject <file>
    approve copies the working copy over the original; reject leaves the
    original untouched. Both delete the working copy and MOVE (not copy) the
    changelog, ledger, and decisions into the latest history/run-N/ (skipping
    any that are absent — so plain spec-improve archives nothing). Notes stay.

append-non-goal <file> <text>
    Append a non-goal entry to the non-goals file (created if absent).

append-note <file> [--finding-id ID] <text>
    Append a below-bar finding to the implementer-notes file, tagging the
    bullet with its finding-id as metadata (gate memory, concept D6).

note-ids <file>
    Emit (JSON list on stdout) the finding-ids recorded in implementer-notes;
    empty list when the file is absent.

append-changelog <file> --run N --round M --kind fix|decision-take|resolution <text>
    Append one tagged audit entry per applied fix, decision-take, or (on Accept)
    a user resolution of an escalated Open Decision.

append-decision <file> --kind decision|non-goal-proposal --title T --finding F [--finding-atoms JSON]
    Create one record in DECISIONS.json, allocating the next R{n} id itself
    (echoed as {"id": "Rn"} on stdout). Creates the file if absent.

update-decision <file> --id Rn --set JSON
    Merge enrichment/resolution fields into an existing record by id. Refuses
    an unknown id (exit 1). A replaced ``taken`` moves into ``superseded``.

snapshot <file> --run N --round M [--verdicts PATH]
    Copy the working copy to history/run-N/round-M.md and store the verdict
    log. Idempotent when the target already byte-matches; a MISMATCHING
    existing round-M.md is a reused run number (exit 1).

scratch-dir <file> --run N --round M
    Make (mkdir -p) and print the absolute per-round scratch dir
    (``<spec-dir>/.spec-scratch/run-N/round-M``). Inter-agent plumbing for one
    round of the flat-context loop: the reviewer writes ``handoff-review.md``
    there, each decide-agent writes ``handoff-decide-<id>.md``, the exit exam
    writes ``handoff-exit.md`` — neutral ``handoff-*`` names because a subagent
    write to a ``findings``/``report``-named file trips a Claude Code behavioral
    guard. Ephemeral — regenerated every round, safe to delete anytime.

scratch-clean <file>
    Remove the whole ``<spec-dir>/.spec-scratch`` tree if present (idempotent).
    Called at terminal states (approve / reject / discard).

reconcile-audit <file>
    Read-only deterministic check of ONE markdown file — pass the working copy's
    path at finalize (or any spec path). Reports decision-heading numbering
    (``### Dn:`` contiguous 1..N, in document order, no duplicates) and
    cross-reference integrity (every ``Dn`` / ``ODn`` token in the prose resolves
    to a heading). Emits a JSON report; ``clean`` is true when both hold. The
    reconcile agent consumes it and re-runs it to confirm ``clean`` before finalize
    proceeds — the guard for its one destructive edit (renumbering). Audits the
    path AS GIVEN — no sidecar derivation (a content check, not a session op).

Exit codes: 0 = success, 1 = error (details on stderr).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path


# ── Naming conventions (single source of truth) ────────────────────────────


def _original_path(source: Path) -> Path:
    """concept.md → concept.original.md"""
    return source.with_suffix(f".original{source.suffix}")


def _auto_improve_path(source: Path) -> Path:
    """concept.md → concept-auto-improve.md"""
    return source.with_stem(f"{source.stem}-auto-improve")


def _non_goals_path(source: Path) -> Path:
    """concept.md → concept-NON-GOALS.md"""
    return source.with_stem(f"{source.stem}-NON-GOALS")


def _implementer_notes_path(source: Path) -> Path:
    """concept.md → concept-IMPLEMENTER-NOTES.md"""
    return source.with_stem(f"{source.stem}-IMPLEMENTER-NOTES")


def _changelog_path(source: Path) -> Path:
    """concept.md → concept-CHANGELOG.md"""
    return source.with_stem(f"{source.stem}-CHANGELOG")


def _atoms_path(source: Path) -> Path:
    """concept.md → concept-ATOMS.json"""
    return source.with_name(f"{source.stem}-ATOMS.json")


def _decisions_path(source: Path) -> Path:
    """concept.md → concept-DECISIONS.json"""
    return source.with_name(f"{source.stem}-DECISIONS.json")


def _history_dir(source: Path) -> Path:
    """The run-archive directory next to the spec."""
    return source.parent / "history"


def _scratch_root(source: Path) -> Path:
    """The ephemeral per-round inter-agent scratch tree next to the spec."""
    return source.parent / ".spec-scratch"


def _run_marker_path(source: Path) -> Path:
    """The in-progress run-number marker next to the spec.

    Present (holding the run number) exactly while a working copy is live —
    written by ``init``, removed by ``approve``/``reject``. Lets a resume bind
    the CURRENT run rather than ``_next_run``, which over-counts by one once the
    in-progress run has snapshotted a round. Sibling of ``.spec-scratch``."""
    return source.parent / ".spec-run"


# Canonical archive names inside history/run-N/ (un-prefixed, per the concept tree).
_ARCHIVE_NAMES: list[tuple] = [
    (_changelog_path, "CHANGELOG.md"),
    (_atoms_path, "ATOMS.json"),
    (_decisions_path, "DECISIONS.json"),
]
_NOTES_ARCHIVE = (_implementer_notes_path, "IMPLEMENTER-NOTES.md")

_RUN_DIR = re.compile(r"^run-(\d+)$")


# ── history/ helpers ────────────────────────────────────────────────────────


def _run_numbers(source: Path) -> list[int]:
    hist = _history_dir(source)
    if not hist.is_dir():
        return []
    nums: list[int] = []
    for p in hist.iterdir():
        m = _RUN_DIR.match(p.name)
        if p.is_dir() and m:
            nums.append(int(m.group(1)))
    return sorted(nums)


def _next_run(source: Path) -> int:
    nums = _run_numbers(source)
    return (nums[-1] + 1) if nums else 1


def _latest_run_dir(source: Path) -> Path | None:
    nums = _run_numbers(source)
    if not nums:
        return None
    return _history_dir(source) / f"run-{nums[-1]}"


def _current_run(source: Path) -> int:
    """Run number for THIS invocation's rounds — resume-aware.

    Unlike ``_next_run`` (cold-start semantics: highest history run + 1), this
    returns the run that OWNS the live working copy on a resume. The number is
    recorded in the ``.spec-run`` marker (authoritative); if the marker is
    absent (a run predating markers) it is inferred from the latest *un-sealed*
    history dir (a completed run archives its CHANGELOG into its dir). With no
    working copy there is no run in progress, so it falls back to ``_next_run``."""
    if not _auto_improve_path(source).is_file():
        return _next_run(source)
    marker = _run_marker_path(source)
    if marker.is_file():
        try:
            return int(marker.read_text().strip())
        except ValueError:
            pass
    nums = _run_numbers(source)
    if nums:
        latest_dir = _history_dir(source) / f"run-{nums[-1]}"
        sealed = (latest_dir / _ARCHIVE_NAMES[0][1]).is_file()
        if not sealed:
            return nums[-1]
    return _next_run(source)


def _archive_sidecars(source: Path, *, include_notes: bool) -> int:
    """MOVE the live sidecars into the latest history/run-N/ (or a freshly
    created next run-N/ if none exists yet). Each move is skipped when the
    sidecar is absent, so a caller with no sidecars (plain spec-improve)
    creates no history/ and errors on nothing. Returns the count moved."""
    targets = list(_ARCHIVE_NAMES) + ([_NOTES_ARCHIVE] if include_notes else [])
    present = [(fn(source), name) for fn, name in targets if fn(source).is_file()]
    if not present:
        return 0
    run_dir = _latest_run_dir(source) or (_history_dir(source) / f"run-{_next_run(source)}")
    run_dir.mkdir(parents=True, exist_ok=True)
    for path, archive_name in present:
        shutil.move(str(path), str(run_dir / archive_name))
    return len(present)


# ── Resolved-paths JSON (shared by init and paths) ──────────────────────────


def _resolve_paths(source: Path) -> dict:
    working = _auto_improve_path(source)
    non_goals = _non_goals_path(source)
    notes = _implementer_notes_path(source)
    changelog = _changelog_path(source)
    atoms = _atoms_path(source)
    decisions = _decisions_path(source)
    backup = _original_path(source)
    return {
        "source": str(source),
        "auto_improve": str(working),
        "auto_improve_exists": working.is_file(),
        "non_goals": str(non_goals),
        "non_goals_exists": non_goals.is_file(),
        "implementer_notes": str(notes),
        "implementer_notes_exists": notes.is_file(),
        "changelog": str(changelog),
        "changelog_exists": changelog.is_file(),
        "atoms": str(atoms),
        "atoms_exists": atoms.is_file(),
        "decisions": str(decisions),
        "decisions_exists": decisions.is_file(),
        "original_backup": str(backup),
        "history_dir": str(_history_dir(source)),
        "next_run": _next_run(source),
        "current_run": _current_run(source),
    }


# ── DECISIONS.json read/write helpers (writes only; reads live in spec_checks) ─


def _load_decisions(dpath: Path) -> list:
    """Load the decision-record list. Absent → []. Malformed → ValueError."""
    if not dpath.is_file():
        return []
    data = json.loads(dpath.read_text())
    if not isinstance(data, list):
        raise ValueError(f"{dpath} is not a JSON list of records")
    return data


def _write_decisions(dpath: Path, records: list) -> None:
    dpath.write_text(json.dumps(records, indent=2) + "\n")


def _alloc_decision_id(records: list) -> str:
    mx = 0
    for r in records:
        m = re.match(r"^R(\d+)$", str(r.get("id", "")))
        if m:
            mx = max(mx, int(m.group(1)))
    return f"R{mx + 1}"


# ── Tiny flag parsing (house style — no argparse, to keep return-code contract) ─


def _flag(argv: list[str], name: str) -> tuple[str | None, list[str]]:
    """Pop ``--name value``. Returns (value_or_None, remaining_argv). Returns
    (None, argv) if the flag is absent or present without a following value."""
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1], argv[:i] + argv[i + 2:]
        return None, argv[:i] + argv[i + 1:]
    return None, argv


def _bool_flag(argv: list[str], name: str) -> tuple[bool, list[str]]:
    if name in argv:
        return True, [a for a in argv if a != name]
    return False, argv


# ── Small emit helper ───────────────────────────────────────────────────────


def _fail(msg: str) -> int:
    print(f"Error: {msg}", file=sys.stderr)
    return 1


# ── Subcommands ─────────────────────────────────────────────────────────────


def cmd_init(source: Path, fresh: bool) -> int:
    """Back up the original (once), create the working copy, emit paths JSON.

    Guards against silently destroying an in-progress session: refuses to
    overwrite an existing working copy unless ``--fresh`` (which archives the
    session sidecars first). concept D7."""
    if not source.is_file():
        return _fail(f"source file not found: {source}")

    working = _auto_improve_path(source)
    if working.is_file() and not fresh:
        print(
            f"Error: a refinement session is already in progress — working copy exists:\n"
            f"  {working}\n"
            f"Resume it (read-only `paths`), or discard and restart with `init --fresh`.",
            file=sys.stderr,
        )
        return 1

    if fresh:
        # Discard the session: archive changelog + ledger + decisions + notes,
        # then reset. A stale ledger/decisions would poison the next run.
        _archive_sidecars(source, include_notes=True)

    backup = _original_path(source)
    backup_created = False
    if not backup.exists():
        shutil.copy2(source, backup)
        backup_created = True

    shutil.copy2(source, working)
    _run_marker_path(source).write_text(f"{_next_run(source)}\n")

    result = _resolve_paths(source)
    result["backup_created"] = backup_created
    print(json.dumps(result, indent=2))
    return 0


def cmd_paths(source: Path) -> int:
    """Emit the resolved-paths JSON without mutating anything (resume entry)."""
    if not source.is_file():
        return _fail(f"source file not found: {source}")
    print(json.dumps(_resolve_paths(source), indent=2))
    return 0


def cmd_approve(source: Path) -> int:
    """Copy working copy over original, delete it, archive session sidecars."""
    working = _auto_improve_path(source)
    if not working.is_file():
        return _fail(f"working copy not found: {working}")
    shutil.copy2(working, source)
    working.unlink()
    moved = _archive_sidecars(source, include_notes=False)
    _run_marker_path(source).unlink(missing_ok=True)
    print(f"Approved: {working} → {source} (archived {moved} sidecar(s))")
    return 0


def cmd_reject(source: Path) -> int:
    """Delete working copy (original untouched), archive session sidecars."""
    working = _auto_improve_path(source)
    if not working.is_file():
        return _fail(f"working copy not found: {working}")
    working.unlink()
    moved = _archive_sidecars(source, include_notes=False)
    _run_marker_path(source).unlink(missing_ok=True)
    print(f"Rejected: deleted {working} (archived {moved} sidecar(s))")
    return 0


def cmd_append_non_goal(source: Path, text: str) -> int:
    """Append a non-goal entry to the non-goals file."""
    non_goals = _non_goals_path(source)
    if non_goals.is_file():
        content = non_goals.read_text()
        if not content.endswith("\n"):
            content += "\n"
    else:
        content = f"# Non-Goals for {source.name}\n\n"
    content += f"- {text}\n"
    non_goals.write_text(content)
    print(f"Appended non-goal to {non_goals}")
    return 0


def cmd_append_note(source: Path, argv: list[str]) -> int:
    """Append a below-bar finding to implementer-notes, tagged with finding-id."""
    finding_id, argv = _flag(argv, "--finding-id")
    text = " ".join(argv).strip()
    if not text:
        return _fail("append-note requires <text>")
    notes = _implementer_notes_path(source)
    if notes.is_file():
        content = notes.read_text()
        if not content.endswith("\n"):
            content += "\n"
    else:
        content = f"# Implementer Notes for {source.name}\n\n"
    marker = f" <!-- finding-id: {finding_id} -->" if finding_id else ""
    content += f"- {text}{marker}\n"
    notes.write_text(content)
    print(f"Appended note to {notes}")
    return 0


def cmd_note_ids(source: Path) -> int:
    """Emit the finding-ids recorded in implementer-notes as a JSON list."""
    notes = _implementer_notes_path(source)
    ids: list[str] = []
    if notes.is_file():
        ids = re.findall(r"<!-- finding-id: (.+?) -->", notes.read_text())
    print(json.dumps(ids))
    return 0


def cmd_append_changelog(source: Path, argv: list[str]) -> int:
    """Append one tagged audit entry per applied fix or decision-take.

    ``--kind exit`` is not an applied change — it records the round's exit-exam
    count so the loop can read its own convergence trend off disk. That makes the
    stall check deterministic and compaction-proof without a second state file:
    ``grep '\\[exit\\]' <changelog>`` is the whole series.
    """
    run, argv = _flag(argv, "--run")
    rnd, argv = _flag(argv, "--round")
    kind, argv = _flag(argv, "--kind")
    text = " ".join(argv).strip()
    if kind not in ("fix", "decision-take", "resolution", "exit"):
        return _fail("append-changelog --kind must be fix|decision-take|resolution|exit")
    if not text:
        return _fail("append-changelog requires <text>")
    changelog = _changelog_path(source)
    if changelog.is_file():
        content = changelog.read_text()
        if not content.endswith("\n"):
            content += "\n"
    else:
        content = f"# Changelog for {source.name}\n\n"
    content += f"- [run {run or '?'} / round {rnd or '?'}] [{kind}] {text}\n"
    changelog.write_text(content)
    print(f"Appended {kind} changelog entry to {changelog}")
    return 0


def cmd_append_decision(source: Path, argv: list[str]) -> int:
    """Create one DECISIONS.json record, allocating its R{n} id."""
    kind, argv = _flag(argv, "--kind")
    title, argv = _flag(argv, "--title")
    finding, argv = _flag(argv, "--finding")
    fatoms, argv = _flag(argv, "--finding-atoms")
    if kind not in ("decision", "non-goal-proposal"):
        return _fail("append-decision --kind must be decision|non-goal-proposal")
    finding_atoms: list = []
    if fatoms:
        try:
            parsed = json.loads(fatoms)
        except json.JSONDecodeError:
            return _fail("append-decision --finding-atoms must be a JSON list")
        if not isinstance(parsed, list):
            return _fail("append-decision --finding-atoms must be a JSON list")
        finding_atoms = parsed
    dpath = _decisions_path(source)
    try:
        records = _load_decisions(dpath)
    except (ValueError, json.JSONDecodeError) as e:
        return _fail(f"cannot read decisions: {e}")
    new_id = _alloc_decision_id(records)
    records.append({
        "id": new_id,
        "kind": kind,
        "title": title or "",
        "finding": finding or "",
        "finding_atoms": finding_atoms,
    })
    _write_decisions(dpath, records)
    print(json.dumps({"id": new_id}))
    return 0


def cmd_update_decision(source: Path, argv: list[str]) -> int:
    """Merge fields into an existing record by id (unknown id → exit 1)."""
    rid, argv = _flag(argv, "--id")
    set_json, argv = _flag(argv, "--set")
    if not rid:
        return _fail("update-decision requires --id Rn")
    if not set_json:
        return _fail("update-decision requires --set <json object>")
    try:
        patch = json.loads(set_json)
    except json.JSONDecodeError:
        return _fail("update-decision --set must be a JSON object")
    if not isinstance(patch, dict):
        return _fail("update-decision --set must be a JSON object")
    dpath = _decisions_path(source)
    if not dpath.is_file():
        return _fail(f"decisions file not found: {dpath}")
    try:
        records = _load_decisions(dpath)
    except (ValueError, json.JSONDecodeError) as e:
        return _fail(f"cannot read decisions: {e}")
    record = next((r for r in records if r.get("id") == rid), None)
    if record is None:
        return _fail(f"update-decision: unknown decision id {rid}")
    # A replaced take is preserved, never erased (concept D11).
    if "taken" in patch and record.get("taken") is not None:
        record.setdefault("superseded", []).append(record["taken"])
    record.update(patch)
    _write_decisions(dpath, records)
    print(f"Updated decision {rid}")
    return 0


def cmd_snapshot(source: Path, argv: list[str]) -> int:
    """Archive the working copy + verdict log to history/run-N/round-M.*.

    Idempotent on a byte-matching re-invocation (failure-policy retry, D7); a
    mismatching existing round-M.md is a reused run number (exit 1)."""
    run, argv = _flag(argv, "--run")
    rnd, argv = _flag(argv, "--round")
    verdicts, argv = _flag(argv, "--verdicts")
    if not run or not rnd:
        return _fail("snapshot requires --run N --round M")
    working = _auto_improve_path(source)
    if not working.is_file():
        return _fail(f"working copy not found: {working}")
    working_bytes = working.read_bytes()

    verdict_bytes: bytes | None = None
    if verdicts:
        vp = Path(verdicts)
        if not vp.is_file():
            return _fail(f"verdict log not found: {vp}")
        verdict_bytes = vp.read_bytes()

    run_dir = _history_dir(source) / f"run-{run}"
    snap = run_dir / f"round-{rnd}.md"
    vlog = run_dir / f"round-{rnd}-verdicts.json"

    if snap.exists():
        same_md = snap.read_bytes() == working_bytes
        same_v = verdict_bytes is None or (vlog.is_file() and vlog.read_bytes() == verdict_bytes)
        if same_md and same_v:
            print(f"snapshot: idempotent no-op (run-{run}/round-{rnd} already current)")
            return 0
        return _fail(
            f"snapshot: run-{run}/round-{rnd}.md already exists and differs "
            f"(reused run number)"
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    snap.write_bytes(working_bytes)
    if verdict_bytes is not None:
        vlog.write_bytes(verdict_bytes)
    print(f"snapshot: wrote {snap}")
    return 0


def cmd_scratch_dir(source: Path, argv: list[str]) -> int:
    """Make + print the absolute per-round inter-agent scratch dir."""
    run, argv = _flag(argv, "--run")
    rnd, argv = _flag(argv, "--round")
    if not run or not rnd:
        return _fail("scratch-dir requires --run N --round M")
    d = _scratch_root(source) / f"run-{run}" / f"round-{rnd}"
    d.mkdir(parents=True, exist_ok=True)
    print(str(d.resolve()))
    return 0


def cmd_scratch_clean(source: Path) -> int:
    """Remove the whole .spec-scratch tree (idempotent — ephemeral plumbing)."""
    root = _scratch_root(source)
    if root.exists():
        shutil.rmtree(root)
        print(f"scratch-clean: removed {root}")
    else:
        print("scratch-clean: nothing to remove")
    return 0


# ── reconcile-audit (deterministic finalize guard) ──────────────────────────

# A decision heading is `### Dn: <title>`; an Open Decision heading is `### ODn …`.
# A reference is a bare `Dn` / `ODn` token in prose. The negative look-behind keeps
# the `D` in `ODn` (and in `wordDn`) from being mis-read as a decision reference.
_DEC_HEADING = re.compile(r"^###\s+D(\d+):")
_OD_HEADING = re.compile(r"^###\s+OD(\d+)\b")
_DEC_REF = re.compile(r"(?<![A-Za-z0-9_])D(\d+)\b")
_OD_REF = re.compile(r"(?<![A-Za-z0-9_])OD(\d+)\b")


def cmd_reconcile_audit(source: Path) -> int:
    """Deterministic pre-finalize audit of decision numbering + cross-references.

    Audits the file at ``source`` DIRECTLY — no working-copy derivation; pass the
    working copy's path during finalize, or any spec path standalone. Read-only.
    Emits a JSON report. ``clean`` is true when the ``### Dn:`` headings are
    contiguous ``1..N`` in document order with no duplicates AND every ``Dn`` /
    ``ODn`` token in the prose resolves to a heading. The reconcile agent consumes
    this and re-runs it to confirm ``clean`` before finalize proceeds — the guard
    for its one destructive edit (renumbering). Always exits 0 when it runs; the
    verdict is the ``clean`` field, not the return code."""
    if not source.is_file():
        return _fail(f"file to audit not found: {source}")
    lines = source.read_text().splitlines()

    d_nums: list[int] = []
    od_nums: list[int] = []
    heading_lines: set[int] = set()
    for i, line in enumerate(lines):
        md = _DEC_HEADING.match(line)
        if md:
            d_nums.append(int(md.group(1)))
            heading_lines.add(i)
            continue
        mo = _OD_HEADING.match(line)
        if mo:
            od_nums.append(int(mo.group(1)))
            heading_lines.add(i)

    numbering_issues: list[str] = []
    if len(d_nums) != len(set(d_nums)):
        dupes = sorted({n for n in d_nums if d_nums.count(n) > 1})
        numbering_issues.append("duplicate decision heading(s): " + ", ".join(f"D{n}" for n in dupes))
    if d_nums and d_nums != sorted(d_nums):
        numbering_issues.append("decision headings out of document order: " + ", ".join(f"D{n}" for n in d_nums))
    d_set = set(d_nums)
    if d_set:
        missing = sorted(set(range(1, max(d_set) + 1)) - d_set)
        if missing:
            numbering_issues.append(
                "non-contiguous numbering — missing "
                + ", ".join(f"D{n}" for n in missing)
                + f" (highest heading is D{max(d_set)}, {len(d_set)} decisions present)"
            )

    dec_refs: dict[int, int] = {}
    od_refs: dict[int, int] = {}
    for i, line in enumerate(lines):
        if i in heading_lines:
            continue
        for m in _OD_REF.finditer(line):
            n = int(m.group(1))
            od_refs[n] = od_refs.get(n, 0) + 1
        for m in _DEC_REF.finditer(line):
            n = int(m.group(1))
            dec_refs[n] = dec_refs.get(n, 0) + 1

    dangling: list[str] = []
    for n in sorted(dec_refs):
        if n not in d_set:
            dangling.append(f"D{n} (referenced {dec_refs[n]}x, no such ### Dn: heading)")
    od_set = set(od_nums)
    for n in sorted(od_refs):
        if n not in od_set:
            dangling.append(
                f"OD{n} (referenced {od_refs[n]}x, no such ### ODn heading — "
                "stale pointer left after finalize removed the Open Decisions?)"
            )

    report = {
        "file": str(source),
        "decisions": [f"D{n}" for n in d_nums],
        "open_decisions": [f"OD{n}" for n in od_nums],
        "decision_numbering_ok": not numbering_issues,
        "numbering_issues": numbering_issues,
        "dangling_references": dangling,
        "reference_counts": {f"D{n}": dec_refs[n] for n in sorted(dec_refs)},
        "clean": not numbering_issues and not dangling,
    }
    print(json.dumps(report, indent=2))
    return 0


# ── CLI dispatch ────────────────────────────────────────────────────────────

USAGE = """\
Usage: improve_files.py <command> <file> [args...]

Session:
  init            <file> [--fresh]     Back up original + create working copy (guarded)
  paths           <file>               Emit resolved-paths JSON (read-only; resume entry)
  approve         <file>               Copy working copy over original; archive sidecars
  reject          <file>               Delete working copy; archive sidecars

Sidecars:
  append-non-goal <file> <text>                          Append to non-goals
  append-note     <file> [--finding-id ID] <text>        Append below-bar note (gate memory)
  note-ids        <file>                                 Emit recorded note finding-ids (JSON)
  append-changelog <file> --run N --round M --kind fix|decision-take|resolution|exit <text>
  append-decision  <file> --kind decision|non-goal-proposal --title T --finding F [--finding-atoms JSON]
  update-decision  <file> --id Rn --set JSON
  snapshot         <file> --run N --round M [--verdicts PATH]
  scratch-dir      <file> --run N --round M               Make + print per-round scratch dir
  scratch-clean    <file>                                 Remove the .spec-scratch tree

Finalize:
  reconcile-audit  <file>                                 Audit decision numbering + xrefs (JSON; clean=finalize guard)
"""


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if len(args) < 2:
        print(USAGE, file=sys.stderr)
        return 1

    command, file_arg = args[0], args[1]
    source = Path(file_arg)
    rest = args[2:]

    if command == "init":
        fresh, _ = _bool_flag(rest, "--fresh")
        return cmd_init(source, fresh)
    if command == "paths":
        return cmd_paths(source)
    if command == "approve":
        return cmd_approve(source)
    if command == "reject":
        return cmd_reject(source)
    if command == "append-non-goal":
        if not rest:
            return _fail("append-non-goal requires <file> and <text>")
        return cmd_append_non_goal(source, rest[0])
    if command == "append-note":
        return cmd_append_note(source, rest)
    if command == "note-ids":
        return cmd_note_ids(source)
    if command == "append-changelog":
        return cmd_append_changelog(source, rest)
    if command == "append-decision":
        return cmd_append_decision(source, rest)
    if command == "update-decision":
        return cmd_update_decision(source, rest)
    if command == "snapshot":
        return cmd_snapshot(source, rest)
    if command == "scratch-dir":
        return cmd_scratch_dir(source, rest)
    if command == "scratch-clean":
        return cmd_scratch_clean(source)
    if command == "reconcile-audit":
        return cmd_reconcile_audit(source)

    print(f"Error: unknown command: {command}", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
