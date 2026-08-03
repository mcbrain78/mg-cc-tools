#!/usr/bin/env python3
"""List Claude Code sessions and arm/disarm permission-guard auto-approval.

Companion to ``/mg:auto-approve`` (which arms the *current* session). This
targets *another* session by id — e.g. from a second, unblocked CC session,
arm the auto-approval flag for a session that is stuck on a permission prompt
and therefore can't run a command itself.

Subcommands:
    list                    Print up to 10 recent sessions as JSON, each with
                            the first/last user commands and what is running
                            right now, so the caller can recognise which one to
                            act on.
    arm     <id-prefix>     Write the auto-approve sidecar for the session.
    off     <id-prefix>     Clear the auto-approve sidecar for the session.
    pause   <id-prefix>     Latch the session: every guarded tool call asks for
                            approval until released, which stops a whole wave of
                            parallel subagents rather than only the next call.
    unpause <id-prefix>     Release the latch.
    mute-session-limit   <id-prefix>   Silence the usage-limit warning for the
                            current window (it warns again in the next one).
    unmute-session-limit <id-prefix>   Restore the warning.

Stdlib-only on purpose: the /mg: command invokes this via plain ``python3`` in
arbitrary target projects, which may have no virtualenv.

Transcript parsing mirrors the approach in the (separate-family) ``transcript``
tool — projects live under ~/.claude/projects/, sessions are <uuid>.jsonl, and
genuine user input is a ``type:"user"`` entry whose message content is text
(not a ``tool_result``) and which is not meta/sidechain.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Sidecar contract — MUST stay in sync with permission-guard.py ────────────
# check_session_context() reads exactly this path / JSON shape / TTL. Altering
# any of them is a breaking change to the hook↔sidecar protocol (so they don't
# move). We mirror rather than import because this script runs standalone under
# plain `python3` with no package context.
_DEFAULT_SESSION_BASE = "/tmp/claude-code"
CONTEXT_TTL_S = 30 * 60  # 30 minutes
AUTO_APPROVE_COMMAND = "AUTO-APPROVE"
# Not "context.json" — the GSD statusline owns that name in the same session
# dir and would clobber the sidecar on every render. See permission-guard.py.
SIDECAR_FILENAME = "auto-approve.json"
# Pause latch. Written here, read (never written) by the hook, removed only by
# `unpause` — so a TTL bump on the sidecar can never drop a pause request.
PAUSE_FILENAME = "pause.json"
# Edit-guard bridge. The hook writes it on every invocation that clears its
# permission-mode gate, which makes its freshness a proxy for "is the guard
# actually running in that session" — see guard_state().
BRIDGE_FILENAME = "edit-guard.json"
# Account-wide usage reading published by usage-watch.py (base dir, not per
# session) and the per-session mute that silences its warning for one window.
USAGE_FILENAME = "usage.json"
USAGE_MUTE_FILENAME = "usage-mute.json"
USAGE_STALE_S = 30 * 60
USAGE_WINDOW_TOL_MIN = 10
# How far the bridge may lag a session's latest activity while still counting as
# an active guard. Generous: a stretch of WebFetch/Task calls advances the
# transcript without producing a guarded tool call.
GUARD_LAG_S = 300

# Entry types the transcript tool skips entirely (non-conversation noise).
SKIP_TYPES = {
    "file-history-snapshot", "progress", "queue-operation", "last-prompt",
    "agent-name", "custom-title",
}

DEFAULT_LIST_LIMIT = 10
# An agent transcript written this recently counts as "working now" for the
# activity block. Wide enough to survive one slow tool call, narrow enough that
# a finished wave stops being reported as live.
LIVE_WINDOW_S = 120
# Subagents shown by name before the count carries the rest.
_ACTIVITY_MAX_LABELS = 3
# Sessions at/under this size are fully scanned (so we know the exact command
# count and can de-duplicate first/last). Larger ones use bounded head/tail
# reads — where the command count is high enough that overlap can't happen.
_FULL_SCAN_MAX_BYTES = 2_000_000
_TAIL_MAX_BYTES = 4_000_000
_LABEL_MAX_LEN = 70

_CMD_NAME_RE = re.compile(r"<command-name>\s*([^<]+?)\s*</command-name>")
_CMD_ARGS_RE = re.compile(r"<command-args>\s*([^<]*?)\s*</command-args>")
_WRAPPER_TAGS = ("system-reminder", "local-command-stdout", "local-command-caveat",
                 "command-message", "command-args")


# ── Environment (read per-call so tests can monkeypatch) ─────────────────────

def _session_base():
    return os.environ.get("MG_SESSION_BASE", _DEFAULT_SESSION_BASE)


def _projects_dir():
    override = os.environ.get("MG_CLAUDE_PROJECTS_DIR")
    if override:
        return Path(override)
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(cfg) if cfg else Path.home() / ".claude"
    return base / "projects"


# ── Sidecar (auto-approve flag) ──────────────────────────────────────────────

def _sidecar_path(session_id):
    return Path(_session_base()) / f"mg-session-{session_id}" / SIDECAR_FILENAME


def read_sidecar(session_id):
    try:
        with open(_sidecar_path(session_id)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def is_armed(session_id, now=None):
    data = read_sidecar(session_id)
    if not data:
        return False
    ts = data.get("timestamp_ms", 0)
    if not isinstance(ts, (int, float)):
        return False
    now = time.time() if now is None else now
    age = now - ts / 1000
    return 0 <= age <= CONTEXT_TTL_S


def arm_session(session_id):
    path = _sidecar_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"command": AUTO_APPROVE_COMMAND,
                   "timestamp_ms": int(time.time() * 1000)}, f)


def disarm_session(session_id):
    try:
        _sidecar_path(session_id).unlink()
        return True
    except FileNotFoundError:
        return False


# ── Pause latch ──────────────────────────────────────────────────────────────

def _pause_path(session_id):
    return Path(_session_base()) / f"mg-session-{session_id}" / PAUSE_FILENAME


def is_paused(session_id):
    """True while the latch exists — it has no TTL and the hook never clears it."""
    return _pause_path(session_id).exists()


def pause_session(session_id, note=None):
    path = _pause_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"paused_at_ms": int(time.time() * 1000)}
    if note:
        payload["note"] = note
    with open(path, "w") as f:
        json.dump(payload, f)


def unpause_session(session_id):
    try:
        _pause_path(session_id).unlink()
        return True
    except FileNotFoundError:
        return False


# ── Session-limit mute (silences the usage gate for one window) ──────────────

def _usage_mute_path(session_id):
    return Path(_session_base()) / f"mg-session-{session_id}" / USAGE_MUTE_FILENAME


def read_published_usage(now=None):
    """The daemon's latest reading, or None when missing/unparseable/stale."""
    try:
        with open(Path(_session_base()) / USAGE_FILENAME) as f:
            reading = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(reading, dict):
        return None
    ts = reading.get("read_at_ms")
    if not isinstance(ts, (int, float)):
        return None
    now = time.time() if now is None else now
    age = now - ts / 1000
    return reading if 0 <= age <= USAGE_STALE_S else None


def mute_session_limit(session_id, reading):
    """Record both current windows, so the mute holds whichever limit binds.

    Muting is window-scoped on purpose: it expires with the window it was taken
    out for, and the next window warns again.
    """
    path = _usage_mute_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "muted_at_ms": int(time.time() * 1000),
        "windows": {"session": reading.get("session_reset_iso"),
                    "weekly": reading.get("weekly_reset_iso")},
    }
    with open(path, "w") as f:
        json.dump(payload, f)
    return payload


def unmute_session_limit(session_id):
    try:
        _usage_mute_path(session_id).unlink()
        return True
    except FileNotFoundError:
        return False


def _windows_match(a_iso, b_iso):
    if not a_iso or not b_iso:
        return False
    try:
        a, b = datetime.fromisoformat(a_iso), datetime.fromisoformat(b_iso)
    except (TypeError, ValueError):
        return False
    return abs((a - b).total_seconds()) <= USAGE_WINDOW_TOL_MIN * 60


def usage_state(session_id, now=None):
    """'muted' | 'gated' | 'clear' | 'unknown' for the picker's usage column."""
    reading = read_published_usage(now)
    if reading is None or not reading.get("ok"):
        return "unknown"          # nobody publishing → the guard does not gate
    if not reading.get("over"):
        return "clear"
    try:
        with open(_usage_mute_path(session_id)) as f:
            mute = json.load(f)
        windows = mute.get("windows") or {}
    except (OSError, ValueError, AttributeError):
        return "gated"
    return "muted" if _windows_match(windows.get(reading.get("binding")),
                                     reading.get("window_iso")) else "gated"


# ── Guard activity (does the hook even run in that session?) ─────────────────

def _bridge_path(session_id):
    return Path(_session_base()) / f"mg-session-{session_id}" / BRIDGE_FILENAME


def guard_state(session_id, last_activity):
    """Return 'active', 'deferring' or 'never' for the guard in that session.

    The hook writes the edit-guard bridge on every invocation that clears its
    permission-mode gate, so a bridge that keeps pace with the session's latest
    activity means the guard is running there (bypassPermissions). A session
    that is demonstrably working while the bridge lags is in one of the modes
    the guard defers to — where arming and pausing write files nobody reads.
    """
    try:
        bridge_mtime = _bridge_path(session_id).stat().st_mtime
    except OSError:
        return "never"
    if last_activity is None:
        return "active"
    return "active" if last_activity - bridge_mtime <= GUARD_LAG_S else "deferring"


# ── Session discovery / resolution ───────────────────────────────────────────

def last_activity(path):
    """Newest mtime across a session transcript and every nested agent transcript.

    A session running subagents can leave its own transcript untouched for
    minutes while all the work lands in .../<uuid>/subagents/agent-*.jsonl.
    Going by the parent mtime alone makes a busy session read as idle — and
    sorts it in the picker below sessions that are doing nothing.

    Walks the whole session directory rather than one glob because workflow
    agents sit a level deeper, in .../subagents/workflows/wf_<runid>/. A single
    ``subagents/*.jsonl`` glob misses them entirely, so a session in the middle
    of a dynamic workflow used to read as idle for the whole run.
    """
    newest = path.stat().st_mtime
    try:
        for sub in (path.parent / path.stem).rglob("*.jsonl"):
            newest = max(newest, sub.stat().st_mtime)
    except OSError:
        pass
    return newest


def all_session_files():
    pdir = _projects_dir()
    if not pdir.exists():
        return []
    files = []
    for proj in pdir.iterdir():
        if proj.is_dir():
            files.extend(proj.glob("*.jsonl"))
    files.sort(key=last_activity, reverse=True)
    return files


def resolve_session_file(prefix):
    """Resolve a full id or prefix to one jsonl Path.

    Returns (path, error). Exactly one is non-None.
    """
    files = all_session_files()
    exact = [f for f in files if f.stem == prefix]
    if exact:
        return exact[0], None
    matches = [f for f in files if f.stem.startswith(prefix)]
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, f"no session matches '{prefix}'"
    sample = ", ".join(m.stem[:8] for m in matches[:6])
    return None, f"ambiguous prefix '{prefix}' matches {len(matches)} sessions: {sample}"


# ── User-command extraction ──────────────────────────────────────────────────

def _collapse(s):
    return " ".join(s.split())


def _truncate(s, n=_LABEL_MAX_LEN):
    s = s.strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _extract_text(content):
    """Return user-typed text from a message ``content``, or None.

    None means the content carries no user text (e.g. a pure tool_result),
    so it is not a user command.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(texts) if texts else None
    return None


def user_command_label(entry):
    """Return a concise label for a genuine user command, else None."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return None
    msg = entry.get("message")
    if not isinstance(msg, dict):
        return None
    text = _extract_text(msg.get("content", ""))
    if not text or not text.strip():
        return None

    # Slash command — the most identifying signal.
    m = _CMD_NAME_RE.search(text)
    if m:
        name = m.group(1).strip()
        am = _CMD_ARGS_RE.search(text)
        args = am.group(1).strip() if am else ""
        return _truncate(_collapse(f"{name} {args}" if args else name))

    # Plain prompt — drop injected wrapper blocks, then collapse.
    for tag in _WRAPPER_TAGS:
        text = re.sub(rf"<{tag}>.*?</{tag}>", "", text, flags=re.DOTALL)
    text = _collapse(text)
    return _truncate(text) if text else None


def _iter_entries_forward(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def _tail_lines(path):
    size = path.stat().st_size
    with open(path, "rb") as f:
        if size > _TAIL_MAX_BYTES:
            f.seek(size - _TAIL_MAX_BYTES)
            f.readline()  # drop the partial line
        data = f.read()
    return data.decode("utf-8", errors="replace").splitlines()


def _first_commands(path, n=3):
    out = []
    for entry in _iter_entries_forward(path):
        label = user_command_label(entry)
        if label:
            out.append(label)
            if len(out) >= n:
                break
    return out


def _last_commands(path, n=3):
    out = []
    for line in reversed(_tail_lines(path)):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        label = user_command_label(entry)
        if label:
            out.append(label)
            if len(out) >= n:
                break
    out.reverse()
    return out


def session_commands(path):
    """Return {first, last, condensed} for a session.

    Small sessions are fully scanned so a short command list (≤6) collapses into
    one de-duplicated ``first`` (condensed). Large sessions use bounded head/tail
    reads, where >6 commands guarantees no first/last overlap.
    """
    if path.stat().st_size <= _FULL_SCAN_MAX_BYTES:
        all_cmds = [lbl for entry in _iter_entries_forward(path)
                    if (lbl := user_command_label(entry))]
        if len(all_cmds) <= 6:
            return {"first": all_cmds, "last": [], "condensed": True}
        return {"first": all_cmds[:3], "last": all_cmds[-3:], "condensed": False}
    return {"first": _first_commands(path), "last": _last_commands(path),
            "condensed": False}


# ── Live activity (what is running right now, not what was typed) ────────────
# The command list only ever shows genuine user input — user_command_label()
# drops sidechain entries on purpose. So a session whose guarded call comes from
# subagent #9 of a workflow shows nothing but a prompt typed twenty minutes ago.
# This reads the agent transcripts themselves to say what is working now.

def _is_live(mtime, now):
    return 0 <= now - mtime <= LIVE_WINDOW_S


def _agent_meta(jsonl_path):
    """The sidecar next to an agent transcript, or {}.

    CC writes agent-<id>.meta.json alongside agent-<id>.jsonl with agentType and
    (for Task subagents) the description passed at spawn time.
    """
    try:
        with open(jsonl_path.with_suffix(".meta.json")) as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return {}
    return meta if isinstance(meta, dict) else {}


def _live_agents(directory, now):
    """[(mtime, path)] for agent transcripts in *directory* touched recently."""
    out = []
    try:
        entries = list(directory.glob("agent-*.jsonl"))
    except OSError:
        return out
    for agent in entries:
        try:
            mtime = agent.stat().st_mtime
        except OSError:
            continue
        if _is_live(mtime, now):
            out.append((mtime, agent))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


def _workflow_name(session_dir, run_id):
    """Recover the script's meta.name from its persisted filename.

    Every Workflow invocation saves its script as
    ``workflows/scripts/<meta.name>-<runid>.js`` — the only place the run's
    human-readable name is on disk (the per-agent meta says only
    ``workflow-subagent``).
    """
    suffix = f"-{run_id}.js"
    try:
        for script in (session_dir / "workflows" / "scripts").glob(f"*{suffix}"):
            return script.name[: -len(suffix)]
    except OSError:
        pass
    return ""


def _live_workflow_runs(subagents_dir, session_dir, now):
    """One entry per workflow run with recent writes, newest run last.

    A run mid-barrier has no agent writing, so the journal counts as evidence of
    life too — otherwise a workflow between phases vanishes from the picker.
    """
    runs = []
    try:
        candidates = sorted((subagents_dir / "workflows").iterdir())
    except OSError:
        return runs
    for run in candidates:
        if not run.is_dir():
            continue
        live = _live_agents(run, now)
        try:
            journal_live = _is_live((run / "journal.jsonl").stat().st_mtime, now)
        except OSError:
            journal_live = False
        if live or journal_live:
            runs.append({"name": _workflow_name(session_dir, run.name) or run.name,
                         "run": run.name, "agents_live": len(live)})
    return runs


def session_activity(path, now=None):
    """What is running in the session right now.

    Stat-first: only the handful of agents that wrote inside LIVE_WINDOW_S get
    their (tiny) meta sidecar read, so this stays cheap across ten sessions.
    Workflow agents carry no individual label, so a run is summarised by name and
    live-agent count; Task subagents get their spawn description.
    """
    now = time.time() if now is None else now
    session_dir = path.parent / path.stem
    subagents_dir = session_dir / "subagents"

    live = _live_agents(subagents_dir, now)
    labels = []
    for _, agent in live[:_ACTIVITY_MAX_LABELS]:
        meta = _agent_meta(agent)
        labels.append({"type": meta.get("agentType") or "",
                       "description": _truncate(str(meta.get("description") or ""))})
    return {
        "workflows": _live_workflow_runs(subagents_dir, session_dir, now),
        "subagents_live": len(live),
        "subagents": labels,
    }


# ── Session info ─────────────────────────────────────────────────────────────

def _session_cwd(path):
    for entry in _iter_entries_forward(path):
        cwd = entry.get("cwd")
        if cwd:
            return cwd
    return ""


def _relative_time(mtime, now=None):
    now = time.time() if now is None else now
    d = max(0, int(now - mtime))
    if d < 60:
        return f"{d}s ago"
    if d < 3600:
        return f"{d // 60}m ago"
    if d < 86400:
        return f"{d // 3600}h ago"
    return f"{d // 86400}d ago"


def session_info(path, now=None):
    sid = path.stem
    cwd = _session_cwd(path)
    activity = last_activity(path)
    return {
        "id": sid,
        "short_id": sid[:8],
        "project": os.path.basename(cwd.rstrip("/")) if cwd else "",
        "cwd": cwd,
        "last_active": _relative_time(activity, now),
        "armed": is_armed(sid, now),
        "paused": is_paused(sid),
        "guard": guard_state(sid, activity),
        "usage": usage_state(sid, now),
        "activity": session_activity(path, now),
        "commands": session_commands(path),
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def cmd_list(args):
    files = all_session_files()[: args.limit]
    print(json.dumps({"sessions": [session_info(f) for f in files]}, indent=2))
    return 0


def cmd_arm(args):
    path, err = resolve_session_file(args.session)
    if path is None:
        print(json.dumps({"ok": False, "error": err}))
        return 1
    sid = path.stem
    arm_session(sid)
    print(json.dumps({
        "ok": True, "action": "armed", "id": sid, "short_id": sid[:8],
        "project": os.path.basename(_session_cwd(path).rstrip("/")),
        "ttl_minutes": CONTEXT_TTL_S // 60,
    }))
    return 0


def cmd_off(args):
    path, err = resolve_session_file(args.session)
    if path is None:
        print(json.dumps({"ok": False, "error": err}))
        return 1
    sid = path.stem
    existed = disarm_session(sid)
    print(json.dumps({"ok": True, "action": "disarmed", "id": sid,
                      "short_id": sid[:8], "was_armed": existed}))
    return 0


def cmd_pause(args):
    path, err = resolve_session_file(args.session)
    if path is None:
        print(json.dumps({"ok": False, "error": err}))
        return 1
    sid = path.stem
    note = " ".join(args.note).strip() if args.note else None
    pause_session(sid, note)
    print(json.dumps({
        "ok": True, "action": "paused", "id": sid, "short_id": sid[:8],
        "project": os.path.basename(_session_cwd(path).rstrip("/")),
        "guard": guard_state(sid, last_activity(path)),
        "note": note,
    }))
    return 0


def cmd_unpause(args):
    path, err = resolve_session_file(args.session)
    if path is None:
        print(json.dumps({"ok": False, "error": err}))
        return 1
    sid = path.stem
    existed = unpause_session(sid)
    print(json.dumps({"ok": True, "action": "unpaused", "id": sid,
                      "short_id": sid[:8], "was_paused": existed}))
    return 0


def cmd_mute_session_limit(args):
    path, err = resolve_session_file(args.session)
    if path is None:
        print(json.dumps({"ok": False, "error": err}))
        return 1
    reading = read_published_usage()
    if reading is None or not reading.get("ok"):
        # Muting without a window would silence nothing, so say so rather than
        # write a file that quietly never matches.
        print(json.dumps({"ok": False, "error": "no current usage reading to mute — "
                                                "is mg-usage-watch running?"}))
        return 1
    sid = path.stem
    payload = mute_session_limit(sid, reading)
    print(json.dumps({
        "ok": True, "action": "muted", "id": sid, "short_id": sid[:8],
        "project": os.path.basename(_session_cwd(path).rstrip("/")),
        "windows": payload["windows"], "usage": usage_state(sid),
    }))
    return 0


def cmd_unmute_session_limit(args):
    path, err = resolve_session_file(args.session)
    if path is None:
        print(json.dumps({"ok": False, "error": err}))
        return 1
    sid = path.stem
    existed = unmute_session_limit(sid)
    print(json.dumps({"ok": True, "action": "unmuted", "id": sid,
                      "short_id": sid[:8], "was_muted": existed,
                      "usage": usage_state(sid)}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list recent sessions as JSON")
    p_list.add_argument("--limit", type=int, default=DEFAULT_LIST_LIMIT)
    p_list.set_defaults(func=cmd_list)

    p_arm = sub.add_parser("arm", help="arm auto-approval for a session")
    p_arm.add_argument("session", help="session id or prefix")
    p_arm.set_defaults(func=cmd_arm)

    p_off = sub.add_parser("off", help="clear auto-approval for a session")
    p_off.add_argument("session", help="session id or prefix")
    p_off.set_defaults(func=cmd_off)

    p_pause = sub.add_parser("pause", help="latch a session's next guarded calls to ask")
    p_pause.add_argument("session", help="session id or prefix")
    p_pause.add_argument("note", nargs="*", help="optional note shown in the prompt")
    p_pause.set_defaults(func=cmd_pause)

    p_unpause = sub.add_parser("unpause", help="release a paused session")
    p_unpause.add_argument("session", help="session id or prefix")
    p_unpause.set_defaults(func=cmd_unpause)

    p_mute = sub.add_parser("mute-session-limit",
                            help="silence the usage-limit warning for this window")
    p_mute.add_argument("session", help="session id or prefix")
    p_mute.set_defaults(func=cmd_mute_session_limit)

    p_unmute = sub.add_parser("unmute-session-limit",
                              help="restore the usage-limit warning")
    p_unmute.add_argument("session", help="session id or prefix")
    p_unmute.set_defaults(func=cmd_unmute_session_limit)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
