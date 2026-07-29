#!/usr/bin/env python3
"""List Claude Code sessions and arm/disarm permission-guard auto-approval.

Companion to ``/mg:auto-approve`` (which arms the *current* session). This
targets *another* session by id — e.g. from a second, unblocked CC session,
arm the auto-approval flag for a session that is stuck on a permission prompt
and therefore can't run a command itself.

Subcommands:
    list                 Print up to 10 recent sessions as JSON, each with the
                         first/last user commands so the caller can recognise
                         which one to arm.
    arm   <id-prefix>    Write the auto-approve sidecar for the matched session.
    off   <id-prefix>    Clear the auto-approve sidecar for the matched session.

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

# Entry types the transcript tool skips entirely (non-conversation noise).
SKIP_TYPES = {
    "file-history-snapshot", "progress", "queue-operation", "last-prompt",
    "agent-name", "custom-title",
}

DEFAULT_LIST_LIMIT = 10
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


# ── Session discovery / resolution ───────────────────────────────────────────

def all_session_files():
    pdir = _projects_dir()
    if not pdir.exists():
        return []
    files = []
    for proj in pdir.iterdir():
        if proj.is_dir():
            files.extend(proj.glob("*.jsonl"))
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
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
    return {
        "id": sid,
        "short_id": sid[:8],
        "project": os.path.basename(cwd.rstrip("/")) if cwd else "",
        "cwd": cwd,
        "last_active": _relative_time(path.stat().st_mtime, now),
        "armed": is_armed(sid, now),
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
