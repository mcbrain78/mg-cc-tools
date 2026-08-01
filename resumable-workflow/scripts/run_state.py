#!/usr/bin/env python3
"""Durable run state for the resumable-workflow investigation loop.

The orchestrating command (`mg:resumable-workflow`) is a thin router: it holds no
durable state in its own context and re-derives everything from this ledger at the
top of every round. That is what makes a run survive a session death — resuming is
re-typing the same command.

Mechanism lives here; *policy* lives in the command .md. This script never decides
how many verdicts a finding needs or when a run has converged; it reports the folded
state and lets the loop decide.

Ledger
------
``<run-dir>/ledger.jsonl`` — append-only, one JSON object per line, written under
``flock`` (batched agents append concurrently; lock-free O_APPEND is a portability
bet on NFS / overlayfs / WSL ``/mnt/c``). Record kinds:

    domain nodes   {"kind":"question","id":"q-…","text":…,"round":N}
                   {"kind":"finding","id":"f-…","text":…,"question":"q-…"}
                   {"kind":"verdict","id":"v-…","finding":"f-…","lens":…,"refuted":bool}
    step lifecycle {"kind":"claimed","id":<step>,"token":…,"identity":…}
                   {"kind":"complete","id":<step>,"summary":…}
                   {"kind":"failed","id":<step>,"reason":…}
    round marker   {"kind":"round","n":N,"new_questions":K}

A *step* is any claimable unit of work, named by an arbitrary id the loop chooses
(``q-…`` to research a question, ``v-…`` to verify a finding by one lens, plus
``digest`` / ``decompose-rN`` / ``assess-rN`` / ``summary``). Domain nodes are
separate bookkeeping — they are what ``status`` folds the pending and unverified
sets out of.

Two invariants the fold enforces:

* **``complete`` is terminal.** Precedence, not line order: a zombie agent from an
  interrupted session appending a late ``claimed`` cannot un-complete a finished
  step and cause its good payload to be overwritten.
* **The ledger record is the done-marker, never file existence.** A payload with no
  ``complete`` record is redone and overwritten, because a file that exists may have
  been truncated by a kill mid-write. This is only safe because every step's sole
  durable effect is its own payload — a step that mutated source would double-apply.

Ids are slugs of *content*, never positional. An index-derived id names a different
item as soon as the set shrinks, so ``claim`` would skip the wrong work. Content
slugs also make ``add`` idempotent, which is what lets decomposition re-run every
round without duplicating research.

Subcommands
-----------
resolve --task <text> [--run-dir <path>] [--force]
    Resolve (creating if needed) the run dir for a task and emit the folded state.
    The entry point for both a cold start and a resume — ``status`` in the output
    tells them apart. Refuses to adopt a ``--run-dir`` whose task differs, or to
    create a new dir when a near-identical sibling exists, without ``--force``.

add <run-dir> --kind question|finding|verdict …
    Record a domain node, idempotent by content slug. Emits its id and whether it
    was new; the loop counts the new ones to drive the dry-round rule.
      question: --text T [--round N] [--parent ID]
      finding : --text T --question QID
      verdict : --finding FID --lens L --refuted true|false

claim <run-dir> --step <id> [--identity <str>]
    The gate every agent calls first. Emits ``action`` (skip | run | abandon), the
    guard-safe payload ``path``, a ``token`` that ``complete`` must present, and the
    prior ``summary`` on skip so a resumed run costs one Bash call per done step.

complete <run-dir> --step <id> --token <t> --summary <s> [--no-payload]
    Mark a step done. Takes no path — it recomputes what ``claim`` emitted, so an
    agent cannot mark step X complete pointing at step Y's payload.

fail <run-dir> --step <id> --reason <r>
    Record a failed attempt. Past MAX_ATTEMPTS ``claim`` returns ``abandon``, so an
    impossible step neither retries forever nor poisons the summary with a stub.

round <run-dir> --new-questions <n>
    Close the current round. ``status`` derives the dry-round count from these.

status <run-dir>
    Emit the folded state: pending questions, findings with verdict counts, current
    round, dry rounds, abandoned steps, all_complete, corrupt_lines.

Exit codes: 0 = success, 1 = error (details on stderr).
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

RUNS_ROOT = Path(".mg/resumable-workflow/runs")
LEDGER_NAME = "ledger.jsonl"
MANIFEST_NAME = "manifest.json"

# A step that has failed this many times is abandoned rather than retried forever.
MAX_ATTEMPTS = 3

# Payload floor for `complete`. Non-empty is not a liveness proof — a kill mid-write
# leaves a short, unterminated file — so require some substance AND a trailing
# newline, which a truncated write almost never has.
MIN_PAYLOAD_BYTES = 32

SLUG_MAX = 40
NODE_KINDS = ("question", "finding", "verdict")
_LIFECYCLE = ("claimed", "complete", "failed")


# ── Identity ────────────────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    """Collapse whitespace and case so trivially-different phrasings dedup.

    Hashing raw text would fork a run on a trailing space."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _slug(text: str, prefix: str) -> str:
    """``prefix-<readable>-<hash8>`` over the NORMALIZED text.

    The hash makes the id collision-free; the readable part makes a ledger and a
    directory listing diagnosable by eye."""
    norm = _normalize(text)
    readable = re.sub(r"[^a-z0-9]+", "-", norm).strip("-")[:SLUG_MAX].strip("-") or "x"
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{readable}-{digest}"


def _payload_path(run_dir: Path, step_id: str) -> Path:
    """Deterministic payload path for a step.

    The ``handoff-`` prefix is load-bearing, not cosmetic: a subagent ``Write`` to a
    ``findings``/``report``-named file trips a Claude Code guard that pushes the
    content back into the response instead of to disk, which would break the step.
    Deriving the name here rather than in a prompt means an agent cannot get it
    wrong."""
    return run_dir / f"handoff-{step_id}.md"


def _token(step_id: str, seq: int) -> str:
    """Claim token. Bound to the claim's position in the ledger, so a token from a
    superseded claim is rejected by ``complete``."""
    return hashlib.sha256(f"{step_id}:{seq}".encode("utf-8")).hexdigest()[:12]


# ── Ledger I/O ──────────────────────────────────────────────────────────────


def _append(run_dir: Path, record: dict) -> None:
    """Append one record under an exclusive lock, as a single write of pre-encoded
    bytes. Two agents appending concurrently cannot interleave a line.

    If the file does not currently end in a newline — a previous write was torn by a
    kill — close that broken line off first. Without this the new record is
    concatenated onto the damaged one and BOTH are lost to the fold, so a single torn
    write would silently eat every subsequent record."""
    line = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(run_dir / LEDGER_NAME, os.O_CREAT | os.O_RDWR | os.O_APPEND, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        size = os.fstat(fd).st_size
        if size and os.pread(fd, 1, size - 1) != b"\n":
            line = b"\n" + line
        os.write(fd, line)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _read_records(run_dir: Path) -> tuple[list[dict], int]:
    """Read the ledger, tolerating damage.

    A torn line must not make the run permanently unresumable: a strict
    json.loads-per-line fold would raise forever, on the line that is almost always
    the last one, with no repair path. Unparseable lines are skipped and counted."""
    path = run_dir / LEDGER_NAME
    if not path.is_file():
        return [], 0
    records: list[dict] = []
    corrupt = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            corrupt += 1
            continue
        if isinstance(obj, dict) and "kind" in obj:
            records.append(obj)
        else:
            corrupt += 1
    return records, corrupt


# ── Fold ────────────────────────────────────────────────────────────────────


class Fold:
    """The folded ledger — the single source of truth for a resumed run."""

    def __init__(self, records: list[dict], corrupt: int) -> None:
        self.corrupt = corrupt
        self.questions: dict[str, dict] = {}
        self.findings: dict[str, dict] = {}
        self.verdicts: list[dict] = []
        self.rounds: list[dict] = []
        # step id → {"status": claimed|complete|failed, "token", "identity",
        #            "summary", "attempts", "claim_seq"}
        self.steps: dict[str, dict] = {}

        for seq, rec in enumerate(records):
            kind = rec.get("kind")
            rid = rec.get("id")
            if kind == "question" and rid:
                self.questions.setdefault(rid, rec)
            elif kind == "finding" and rid:
                self.findings.setdefault(rid, rec)
            elif kind == "verdict" and rid:
                self.verdicts.append(rec)
            elif kind == "round":
                self.rounds.append(rec)
            elif kind in _LIFECYCLE and rid:
                self._apply_lifecycle(kind, rid, rec, seq)

    def _apply_lifecycle(self, kind: str, rid: str, rec: dict, seq: int) -> None:
        st = self.steps.setdefault(
            rid, {"status": None, "attempts": 0, "identity": None,
                  "token": None, "summary": None, "claim_seq": None}
        )
        # `complete` is terminal: a late record cannot reopen a finished step.
        if st["status"] == "complete":
            return
        if kind == "claimed":
            st["status"] = "claimed"
            st["token"] = rec.get("token")
            st["claim_seq"] = seq
            if rec.get("identity") is not None:
                st["identity"] = rec["identity"]
        elif kind == "complete":
            st["status"] = "complete"
            st["summary"] = rec.get("summary")
        elif kind == "failed":
            st["status"] = "failed"
            st["attempts"] += 1

    # ── derived views ───────────────────────────────────────────────────────

    def step_status(self, step_id: str) -> str:
        st = self.steps.get(step_id)
        if st is None:
            return "absent"
        if st["status"] == "failed" and st["attempts"] >= MAX_ATTEMPTS:
            return "abandoned"
        return st["status"] or "absent"

    def is_done(self, step_id: str) -> bool:
        return self.step_status(step_id) == "complete"

    def pending_questions(self) -> list[str]:
        """Questions whose research step is neither complete nor abandoned."""
        return [q for q in self.questions
                if self.step_status(q) not in ("complete", "abandoned")]

    def finding_verdicts(self) -> dict[str, dict]:
        """Per finding: how many verdicts landed and how many refuted it.

        The loop owns the threshold (how many lenses, what majority) — this only
        reports what exists."""
        out = {f: {"verdicts": 0, "refuted": 0} for f in self.findings}
        for v in self.verdicts:
            fid = v.get("finding")
            if fid in out:
                out[fid]["verdicts"] += 1
                if v.get("refuted"):
                    out[fid]["refuted"] += 1
        return out

    def current_round(self) -> int:
        """Derived, never stored. A stored counter loses a round on one side of a
        crash or the other; the closed-round markers cannot."""
        return len(self.rounds) + 1

    def dry_rounds(self) -> int:
        """Trailing closed rounds that added no new questions."""
        n = 0
        for rec in reversed(self.rounds):
            if rec.get("new_questions", 0) == 0:
                n += 1
            else:
                break
        return n

    def abandoned(self) -> list[str]:
        return [s for s in self.steps if self.step_status(s) == "abandoned"]

    def open_steps(self) -> list[str]:
        return [s for s in self.steps if self.step_status(s) == "claimed"]

    def all_complete(self) -> bool:
        """No work left that the loop could still do. Note this is *not* the
        convergence rule — the loop also requires dry rounds; this is the gate that
        stops the summary from silently composing a partial answer.

        A run with no questions is NOT complete, it has not started: without this a
        fresh ledger reports True and a caller that gates only on this would jump
        straight to summarising nothing."""
        if not self.questions:
            return False
        unverified = [f for f, v in self.finding_verdicts().items()
                      if v["verdicts"] == 0]
        return not self.pending_questions() and not unverified and not self.open_steps()

    def as_json(self) -> dict:
        fv = self.finding_verdicts()
        return {
            "round": self.current_round(),
            "dry_rounds": self.dry_rounds(),
            "questions_total": len(self.questions),
            "pending": sorted(self.pending_questions()),
            "findings": fv,
            "unverified": sorted(f for f, v in fv.items() if v["verdicts"] == 0),
            "abandoned": sorted(self.abandoned()),
            "open_steps": sorted(self.open_steps()),
            "all_complete": self.all_complete(),
            "corrupt_lines": self.corrupt,
        }


def _load(run_dir: Path) -> Fold:
    records, corrupt = _read_records(run_dir)
    return Fold(records, corrupt)


# ── Tiny flag parsing (house style — no argparse, to keep the 0/1 contract) ──


def _flag(argv: list[str], name: str) -> tuple[str | None, list[str]]:
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


def _fail(msg: str) -> int:
    print(f"Error: {msg}", file=sys.stderr)
    return 1


def _emit(obj: object) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── resolve ─────────────────────────────────────────────────────────────────


def cmd_resolve(argv: list[str]) -> int:
    task, argv = _flag(argv, "--task")
    explicit, argv = _flag(argv, "--run-dir")
    force, argv = _bool_flag(argv, "--force")
    if not task or not task.strip():
        return _fail("resolve requires --task <text>")

    slug = _slug(task, "run")
    task_sha = hashlib.sha256(_normalize(task).encode("utf-8")).hexdigest()

    if explicit:
        run_dir = Path(explicit)
        existing = _read_manifest(run_dir)
        if existing and existing.get("task_sha") != task_sha and not force:
            return _fail(
                f"--run-dir {run_dir} belongs to a different task "
                f"(its manifest records another task hash). Adopting it would merge "
                f"two id namespaces in one ledger. Pass --force to override."
            )
    else:
        run_dir = RUNS_ROOT / slug

    fresh = not (run_dir / MANIFEST_NAME).is_file()

    # A near-identical sibling means the task was reworded. Creating a second dir
    # silently forks the run and re-does all the work, so make the user choose.
    similar = _similar_siblings(slug) if fresh and not explicit else []
    if similar and not force:
        return _fail(
            "a near-identical run already exists:\n  "
            + "\n  ".join(similar)
            + "\nResume it with --run-dir <path>, or pass --force to start a new run."
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = _read_manifest(run_dir) or {
        "task": task, "task_sha": task_sha, "slug": slug,
        "created_at": _now(), "invocations": 0,
    }
    manifest["invocations"] = int(manifest.get("invocations", 0)) + 1
    manifest["last_invoked_at"] = _now()
    (run_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    state = _load(run_dir).as_json()
    state.update({
        "run_dir": str(run_dir.resolve()),
        "digest_path": str((run_dir / "digest.md").resolve()),
        "summary_path": str((run_dir / "summary.md").resolve()),
        "status": "new" if fresh else "resumed",
        "invocation": manifest["invocations"],
        "similar": similar,
    })
    _emit(state)
    return 0


def _read_manifest(run_dir: Path) -> dict | None:
    path = run_dir / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return obj if isinstance(obj, dict) else None


def _similar_siblings(slug: str) -> list[str]:
    """Existing run dirs whose readable slug part matches but whose hash differs."""
    if not RUNS_ROOT.is_dir():
        return []
    stem = slug.rsplit("-", 1)[0]
    return sorted(
        str(p) for p in RUNS_ROOT.iterdir()
        if p.is_dir() and p.name != slug and p.name.rsplit("-", 1)[0] == stem
    )


# ── add ─────────────────────────────────────────────────────────────────────


def cmd_add(run_dir: Path, argv: list[str]) -> int:
    kind, argv = _flag(argv, "--kind")
    if kind not in NODE_KINDS:
        return _fail(f"add requires --kind {'|'.join(NODE_KINDS)}")

    fold = _load(run_dir)

    if kind == "question":
        text, argv = _flag(argv, "--text")
        rnd, argv = _flag(argv, "--round")
        parent, argv = _flag(argv, "--parent")
        if not text or not text.strip():
            return _fail("add --kind question requires --text")
        nid = _slug(text, "q")
        is_new = nid not in fold.questions
        if is_new:
            _append(run_dir, {"kind": "question", "id": nid, "text": text.strip(),
                              "round": int(rnd) if rnd else fold.current_round(),
                              "parent": parent, "ts": _now()})
    elif kind == "finding":
        text, argv = _flag(argv, "--text")
        qid, argv = _flag(argv, "--question")
        if not text or not text.strip():
            return _fail("add --kind finding requires --text")
        if not qid:
            return _fail("add --kind finding requires --question <qid>")
        nid = _slug(text, "f")
        is_new = nid not in fold.findings
        if is_new:
            _append(run_dir, {"kind": "finding", "id": nid, "text": text.strip(),
                              "question": qid, "ts": _now()})
    else:  # verdict
        fid, argv = _flag(argv, "--finding")
        lens, argv = _flag(argv, "--lens")
        refuted, argv = _flag(argv, "--refuted")
        if not fid or not lens:
            return _fail("add --kind verdict requires --finding <fid> and --lens <name>")
        if refuted not in ("true", "false"):
            return _fail("add --kind verdict requires --refuted true|false")
        nid = _slug(f"{fid} {lens}", "v")
        is_new = not any(v.get("id") == nid for v in fold.verdicts)
        if is_new:
            _append(run_dir, {"kind": "verdict", "id": nid, "finding": fid,
                              "lens": lens, "refuted": refuted == "true",
                              "ts": _now()})

    _emit({"id": nid, "kind": kind, "new": is_new})
    return 0


# ── claim / complete / fail ─────────────────────────────────────────────────


def cmd_claim(run_dir: Path, argv: list[str]) -> int:
    step, argv = _flag(argv, "--step")
    identity, argv = _flag(argv, "--identity")
    if not step:
        return _fail("claim requires --step <id>")

    records, corrupt = _read_records(run_dir)
    fold = Fold(records, corrupt)
    status = fold.step_status(step)
    path = _payload_path(run_dir, step)

    if status == "complete":
        st = fold.steps[step]
        _emit({"action": "skip", "step": step, "path": str(path.resolve()),
               "summary": st.get("summary")})
        return 0

    if status == "abandoned":
        _emit({"action": "abandon", "step": step, "path": str(path.resolve()),
               "attempts": fold.steps[step]["attempts"]})
        return 0

    # Guard id aliasing: the same id must always name the same work. Without this a
    # positional id (step-3) silently points at a different item once the set
    # shrinks, and `claim` skips work that was never done.
    if identity is not None:
        known = fold.steps.get(step, {}).get("identity")
        if known is not None and known != identity:
            return _fail(
                f"step id {step!r} already names different work "
                f"({known!r}, not {identity!r}) — ids must be derived from content, "
                f"not from position"
            )

    token = _token(step, len(records))
    _append(run_dir, {"kind": "claimed", "id": step, "token": token,
                      "identity": identity, "ts": _now()})
    _emit({"action": "run", "step": step, "path": str(path.resolve()),
           "token": token})
    return 0


def cmd_complete(run_dir: Path, argv: list[str]) -> int:
    step, argv = _flag(argv, "--step")
    token, argv = _flag(argv, "--token")
    summary, argv = _flag(argv, "--summary")
    no_payload, argv = _bool_flag(argv, "--no-payload")
    if not step or not token:
        return _fail("complete requires --step <id> and --token <t>")
    if not summary or not summary.strip():
        return _fail("complete requires --summary <one line>")

    fold = _load(run_dir)
    st = fold.steps.get(step)
    if st is None:
        return _fail(f"step {step!r} was never claimed — call claim first")
    if st["status"] == "complete":
        # Idempotent: a retried Bash call must not append a second record.
        _emit({"step": step, "status": "complete", "idempotent": True})
        return 0
    if st.get("token") != token:
        return _fail(
            f"stale or wrong token for step {step!r} — it was re-claimed by another "
            f"invocation, so this result is discarded rather than recorded"
        )

    # No --path parameter by design: recomputing what claim emitted means an agent
    # cannot mark step X complete pointing at step Y's payload.
    path = _payload_path(run_dir, step)
    if not no_payload:
        if not path.is_file():
            return _fail(f"payload not found at {path} (pass --no-payload for a step "
                         f"that legitimately writes none)")
        data = path.read_bytes()
        terminated = data.endswith(b"\n")
        if len(data) < MIN_PAYLOAD_BYTES or not terminated:
            newline = "has" if terminated else "no"
            return _fail(
                f"payload at {path} looks truncated ({len(data)} bytes, "
                f"{newline} trailing newline) — not marking the step done"
            )

    _append(run_dir, {"kind": "complete", "id": step, "summary": summary.strip(),
                      "ts": _now()})
    _emit({"step": step, "status": "complete", "path": str(path.resolve())})
    return 0


def cmd_fail(run_dir: Path, argv: list[str]) -> int:
    step, argv = _flag(argv, "--step")
    reason, argv = _flag(argv, "--reason")
    if not step or not reason:
        return _fail("fail requires --step <id> and --reason <text>")

    fold = _load(run_dir)
    if fold.is_done(step):
        return _fail(f"step {step!r} is already complete — refusing to record a failure")

    _append(run_dir, {"kind": "failed", "id": step, "reason": reason.strip(),
                      "ts": _now()})
    after = _load(run_dir)
    _emit({"step": step, "status": after.step_status(step),
           "attempts": after.steps[step]["attempts"],
           "max_attempts": MAX_ATTEMPTS})
    return 0


# ── round / status ──────────────────────────────────────────────────────────


def cmd_round(run_dir: Path, argv: list[str]) -> int:
    new_q, argv = _flag(argv, "--new-questions")
    if new_q is None:
        return _fail("round requires --new-questions <n>")
    try:
        n_new = int(new_q)
    except ValueError:
        return _fail(f"--new-questions must be an integer, got {new_q!r}")

    fold = _load(run_dir)
    n = fold.current_round()
    _append(run_dir, {"kind": "round", "n": n, "new_questions": n_new, "ts": _now()})
    after = _load(run_dir)
    _emit({"closed_round": n, "new_questions": n_new,
           "next_round": after.current_round(), "dry_rounds": after.dry_rounds()})
    return 0


def cmd_status(run_dir: Path) -> int:
    if not run_dir.is_dir():
        return _fail(f"run dir not found: {run_dir}")
    state = _load(run_dir).as_json()
    state["run_dir"] = str(run_dir.resolve())
    _emit(state)
    return 0


# ── main ────────────────────────────────────────────────────────────────────

USAGE = """\
Usage: run_state.py <command> [<run-dir>] [flags...]

  resolve  --task <text> [--run-dir <path>] [--force]
  add      <run-dir> --kind question --text T [--round N] [--parent ID]
           <run-dir> --kind finding  --text T --question QID
           <run-dir> --kind verdict  --finding FID --lens L --refuted true|false
  claim    <run-dir> --step <id> [--identity <str>]
  complete <run-dir> --step <id> --token <t> --summary <s> [--no-payload]
  fail     <run-dir> --step <id> --reason <r>
  round    <run-dir> --new-questions <n>
  status   <run-dir>
"""


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(USAGE, file=sys.stderr)
        return 1

    command, rest = args[0], args[1:]

    if command == "resolve":
        return cmd_resolve(rest)

    if command in ("add", "claim", "complete", "fail", "round", "status"):
        if not rest:
            return _fail(f"{command} requires <run-dir>")
        run_dir, rest = Path(rest[0]), rest[1:]
        if command != "status" and not run_dir.is_dir():
            return _fail(f"run dir not found: {run_dir}")
        if command == "add":
            return cmd_add(run_dir, rest)
        if command == "claim":
            return cmd_claim(run_dir, rest)
        if command == "complete":
            return cmd_complete(run_dir, rest)
        if command == "fail":
            return cmd_fail(run_dir, rest)
        if command == "round":
            return cmd_round(run_dir, rest)
        return cmd_status(run_dir)

    print(f"Error: unknown command: {command}", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
