#!/usr/bin/env python3
"""PreToolUse hook that guards against dangerous operations.

For Bash: checks commands against 8 categories of dangerous patterns plus
an out-of-project path guard.

For Read/Edit/Write: checks file paths against sensitive file patterns.

Returns permissionDecision: "ask" for any match so the user gets an
approval prompt.

Active only in bypassPermissions mode — the one mode where CC approves
everything and this hook is the sole safety net. In every other permission
mode the hook defers (returns no output) so CC's native permission flow
applies; unknown/missing modes fail safe (the guard stays active).

PROJECT_ROOT is embedded at install time via sed. For --global installs
it's empty and falls back to cwd from the hook event.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import namedtuple
from datetime import datetime

PROJECT_ROOT = "{MG_INSTALL_PROJECT_ROOT}"

# ── Optional rule groups ────────────────────────────────────────────────────
# .env files and environment dumps. Disabled by default: reading and writing
# .env is routine work in this setup, so the ask-per-call cost outweighs the
# guard. Flip to True and reinstall to restore both the file patterns and the
# printenv/env dump rules. The tests gate on this same constant.
ENV_PROTECTION = False

_ENV_RULES = [
    (r">\s*\S*\.env\b", "writing .env file"),
    (r"\bprintenv\b", "environment dump"),
    (r"\benv\s*($|[|;>])", "environment dump"),
]

_ENV_FILE_PATTERNS = [
    (re.compile(r"(^|/)\.env(?!\.example|\.template|\.sample|\.test)(\b|$)"), ".env file"),
]

# PostgreSQL password file. Disabled by default for the same reason as
# ENV_PROTECTION: reading ~/.pgpass — and inspecting its mtime, which the
# path-based scan cannot tell apart from a read — is routine work in this
# setup, so the ask-per-call cost outweighs the guard. Flip to True and
# reinstall to restore it. Writes are unaffected: a redirect into ~/.pgpass
# still asks via the out-of-project home-directory guard. SSH keys, .netrc,
# .my.cnf and the rest of SENSITIVE_FILE_PATTERNS stay gated. The tests gate
# on this same constant.
PGPASS_PROTECTION = False

_PGPASS_FILE_PATTERNS = [
    (re.compile(r"(^|/)\.pgpass$"), "PostgreSQL password file"),
]

# ── git config ──────────────────────────────────────────────────────────────
# `git config` needs more than one pattern's worth of care: scope and format
# options sit between the subcommand and the operands, a key with no value is
# a read, and both spellings of the command are in the wild (`git config
# --unset x` and the newer `git config unset x`). Matching write intent
# directly beats listing read flags to exempt — the old exemption list ended
# in a bare `--`, which quietly spared every long option including
# `git config --global user.name "x"`.

# Options that may precede the operands. Consumed so they can't hide a write.
# The four that take a value swallow it too, whether attached or separate.
_GIT_CONFIG_OPTS = (
    r"(?:\s+(?:--(?:global|local|system|worktree|includes|no-includes|null"
    r"|name-only|show-origin|show-scope|fixed-value)"
    r"|--(?:file|blob|type|default)(?:=\S+|\s+\S+)"
    r"|-f\s+\S+|-z))*"
)

# A write is a mutating flag, a mutating subcommand, or a key with a value
# after it. The value cannot be a redirect or a shell terminator — those end
# the command, leaving a bare-key read.
_GIT_CONFIG_WRITE = (
    r"\bgit\s+config(?!\s+(?:get|list)\b)"
    + _GIT_CONFIG_OPTS
    + r"\s+(?:"
    r"--(?:add|unset|unset-all|replace-all|rename-section|remove-section|edit)\b"
    r"|-e\b"
    r"|(?:set|unset|edit|rename-section|remove-section)\b"
    r"|[\w.][\w.-]*[ \t]+[^\s)`;&|<>]"
    r")"
)

# ── Command position ────────────────────────────────────────────────────────
# Words like "service", "kill" and "systemctl" are common in prose, paths and
# regex alternations, and these rules scan the command string with heredocs
# stripped but quotes intact. Anchoring such a word to command position — start
# of the string, or after a shell separator — is what keeps the text cases
# quiet. `\n` belongs in the separator class because a multi-line Bash command
# is a script: without it only its first line is guarded.
_CMD_POS = r"(?:^|[;&\n]\s*)"

# Same, plus after a pipe. Only for commands that are never a word you would
# meet in text, so "| dd" can be read as syntax rather than as data.
_CMD_POS_PIPE = r"(?:^|[;&|\n]\s*)"

# ── systemctl ───────────────────────────────────────────────────────────────
# systemctl is mostly introspection: is-enabled, list-timers, show and friends
# report state and exit. Exempting the single literal `status` asked on every
# one of those, and any global option before the subcommand (`systemctl --user
# status foo`) defeated the exemption altogether.
#
# The read set is small and closed; the write set grows with systemd (freeze,
# thaw, mount-image, …). So name the reads and flag the rest — that keeps a
# subcommand systemd adds tomorrow on the asking side.

# Global options that may sit between `systemctl` and the subcommand. The short
# options that take a separate value swallow it, so the `service` in
# `systemctl -t service list-units` can't be mistaken for a subcommand.
_SYSTEMCTL_OPTS = r"(?:\s+(?:-[HMtpnosP]\s+\S+|--[\w-]+=\S+|--[\w-]+|-[A-Za-z]+))*"

_SYSTEMCTL_READ = (
    r"(?:status|show|show-environment|cat|help|get-default"
    r"|is-active|is-enabled|is-failed|is-system-running"
    r"|list-(?:units|unit-files|sockets|timers|jobs|dependencies|machines"
    r"|paths|automounts))(?![\w-])"
)

# Two negative lookaheads, not one match-the-write pattern: a greedy option
# group followed by a positive match backtracks until the option itself is
# taken for the subcommand, which is how `--user status` would get flagged. A
# lookahead that fails has nothing to backtrack into.
_SYSTEMCTL_WRITE = (
    _CMD_POS
    + r"systemctl(?![\w-])"
    # Bare `systemctl [options]`, redirected or not, just lists units.
    + r"(?!" + _SYSTEMCTL_OPTS + r"\s*(?:$|[)\n;&|]|\d*[<>]))"
    + r"(?!" + _SYSTEMCTL_OPTS + r"\s+" + _SYSTEMCTL_READ + r")"
)

# ── Category definitions ────────────────────────────────────────────────────
# Each category maps to a list of (regex_string, description) tuples.

CATEGORIES = {
    "Git Branch & History": [
        (r"\bgit\s+checkout\s+(?!--)", "git checkout (not file restore)"),
        (r"\bgit\s+switch\b", "git switch"),
        (r"\bgit\s+branch\s+(?!-)[A-Za-z]", "branch creation"),
        (r"\bgit\s+branch\s+(-[dD]|--delete)\b", "branch deletion"),
        (r"\bgit\s+merge\s+(?!--abort|--continue|--quit)", "git merge (not recovery)"),
        (r"\bgit\s+rebase\s+(?!--abort|--continue|--quit|--skip)", "git rebase (not recovery)"),
        (r"\bgit\s+cherry-pick\s+(?!--abort|--continue|--quit)", "git cherry-pick (not recovery)"),
        (r"\bgit\s+reset\s+--hard\b", "git reset --hard"),
        (r"\bgit\s+stash\s+(drop|clear)\b", "git stash destruction"),
        (r"\bgit\s+tag\s+(-d|--delete)\b", "git tag deletion"),
    ],
    "Git Destructive Remote": [
        (r"\bgit\s+push\s+.*(-f\b|--force|--force-with-lease)", "force push"),
        (r"\bgit\s+push\s+\S+\s+--delete\b", "remote branch deletion"),
        (r"\bgit\s+push\s+\S+\s+:", "remote branch deletion (colon syntax)"),
        (r"\bgit\s+push\s+.*--tags\b", "pushing tags"),
        (r"\bgit\s+remote\s+(add|remove|rm|set-url)\b", "remote management"),
        (_GIT_CONFIG_WRITE, "git config write"),
        (r"\bgit\s+submodule\s+(add|deinit)\b", "submodule management"),
    ],
    "GitHub CLI": [
        (r"\bgh\s+pr\s+(merge|close)\b", "PR merge/close"),
        (r"\bgh\s+repo\s+(create|delete|fork|archive)\b", "repo management"),
        (r"\bgh\s+release\s+(create|delete)\b", "release management"),
        (r"\bgh\s+api\b.*(-X\s*(POST|PUT|PATCH|DELETE)|--method\s*(POST|PUT|PATCH|DELETE)|-f\s|-F\s|--field\s|--raw-field\s|--input\s)", "GitHub API mutation"),
        (r"\bgh\s+auth\b", "GitHub auth"),
        (r"\bgh\s+secret\b", "GitHub secret management"),
    ],
    "Package Publishing": [
        (r"\b(npm|yarn|pnpm)\s+publish\b", "package publish"),
        (r"\b(pip|twine)\s+upload\b", "package upload"),
        (r"\bnpm\s+(adduser|token|login|unpublish)\b", "npm auth/unpublish"),
    ],
    "Infrastructure": [
        (r"\bssh\s", "remote access (ssh)"),
        (r"\bscp\s", "remote file transfer (scp)"),
    ],
    "Destructive Filesystem": [
        (r"\brm\s+(-\w+\s+)*-\w*[rR]", "recursive rm"),
        (r"\b(chmod|chown)\b", "permission/ownership change"),
        (_CMD_POS_PIPE + r"ln\s+(?!=)(?:-|\S+\s)", "symlink creation"),
        (r"\b(mkfs|mount|umount)\b", "disk operations"),
        (_CMD_POS_PIPE + r"dd\s", "raw disk operations"),
    ],
    "Secrets & Credentials": [
        *(_ENV_RULES if ENV_PROTECTION else []),
        (r"\bexport\s+\w*(TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL|API_KEY)=", "credential export"),
        (r"\b(curl|wget)\s+.*(-X\s*(POST|PUT|PATCH|DELETE)|-d\s|--data)", "HTTP data submission"),
        (r"\b(curl|wget)\s+.*\|\s*(bash|sh|zsh)\b", "pipe-to-shell"),
    ],
    "System Operations": [
        (r"\bsudo\b", "sudo"),
        (r"\b(apt|apt-get|brew|yum|dnf|pacman|apk)\s+(install|remove|purge|uninstall)\b", "package manager"),
        (r"\bcrontab\s+(?!-l\b)", "crontab modification"),
        (_SYSTEMCTL_WRITE, "systemctl (not a read subcommand)"),
        # Command-position only (see _CMD_POS), and must take an argument. NOT
        # after a pipe: you never pipe into service/launchctl, but "|service" is
        # common in TEXT (regex alternations, markdown tables) and the guard
        # scans the raw command string with quotes intact.
        (_CMD_POS + r"(launchctl|service)\s+\S", "service manager"),
        # Same command-position + argument anchoring as the service rule above:
        # these words are common in prose/paths ("kill the test", /etc/passwd,
        # "iptables rules"), so only flag them as an actual command invocation.
        (_CMD_POS + r"(useradd|userdel|usermod|passwd)\s+\S", "user management"),
        (_CMD_POS + r"(iptables|ufw)\s+\S", "firewall management"),
        (_CMD_POS + r"(kill|killall)\s+\S", "process termination"),
    ],
}

# Compile all rules into a flat list at module load
RULES = []
for category, patterns in CATEGORIES.items():
    for regex_str, description in patterns:
        RULES.append((re.compile(regex_str), description, category))

# Absolute paths that are always safe to reference
SAFE_ABSOLUTE_PATHS = ["/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr", "/tmp"]

# ── Session context (auto-approval via sidecar file with rolling TTL) ──────
# Stage 0 gates the emit-context.py script (human approval required).
# Once approved, the hook writes a sidecar file with a timestamp.
# Subsequent auto-approved tool calls bump the timestamp (rolling TTL).
# The context expires after CONTEXT_TTL_S of inactivity.
_EMIT_SCRIPT_RE = re.compile(r"\bemit-(context|edit-guard)\.py\b")
CONTEXT_TTL_S = 30 * 60  # 30 minutes

# Sidecar filename inside the session dir. Deliberately NOT "context.json":
# the GSD statusline caches its context-window percentage to
# <session-dir>/context.json on every render, which would overwrite the
# sidecar and silently disarm the window (fail-safe — the foreign payload has
# no "command" key — but auto-approval would never stick). Mirrored by
# scripts/auto-approve-session.py.
SIDECAR_FILENAME = "auto-approve.json"

# Pause latch, written by scripts/auto-approve-session.py (usually from another
# session) and cleared only by its `unpause` subcommand. Kept in its own file
# rather than merged into SIDECAR_FILENAME: this hook is a read-only consumer of
# the latch, so a concurrent TTL bump on the auto-approve sidecar can never drop
# a pause request. The latch is sticky on purpose — every guarded call asks for
# as long as it exists, so a whole wave of parallel subagents stops, not just
# whichever one happened to make the next tool call.
PAUSE_FILENAME = "pause.json"

# ── Usage gate ──────────────────────────────────────────────────────────────
# scripts/usage-watch.py publishes one account-wide reading (the daemon owns the
# thresholds and precomputes the verdict, so this hook stays a cheap file read on
# every tool call). A session silences it for the current window with
# `mute-session-limit`, which writes USAGE_MUTE_FILENAME into its session dir.
#
# Fail directions are deliberately opposite. An unreadable or stale reading must
# NOT gate work: a monitoring hiccup blocking every tool call is worse than the
# limit itself, which merely cuts off and resets. An unreadable mute must NOT
# grant silence: a corrupt file that happens to disable a warning is the bad
# direction.
USAGE_FILENAME = "usage.json"                 # account-wide, in the base dir
USAGE_MUTE_FILENAME = "usage-mute.json"       # per session
# Three missed ticks (the daemon's default interval is 10 min).
USAGE_STALE_S = 30 * 60
# Reported reset instants drift ~a minute between reads, so window identity is
# fuzzy — mirrored in scripts/auto-approve-session.py.
USAGE_WINDOW_TOL_MIN = 10

_DEFAULT_SESSION_BASE = "/tmp/claude-code"


def _session_base():
    """Base dir for session sidecars. Overridable so tests never touch the real one."""
    return os.environ.get("MG_SESSION_BASE", _DEFAULT_SESSION_BASE)


def _session_dir(session):
    return os.path.join(_session_base(), f"mg-session-{session}")

# Number of trailing JSONL lines to inspect for recent command invocation.
# Needs to be large enough to span the full slash-command load: <command-name>
# tag + body + attachments (one line each) + last-prompt + assistant thinking/
# tool_use. A /mg: command with many referenced attachments can push the tag
# ~20–40 lines back, so we use a generous window that still excludes ancient
# invocations.
_RECENT_LINES = 200


def _session_id(transcript_path):
    """Derive session ID from transcript path.

    Subagent transcripts live at .../SESSION_UUID/subagents/agent-xxx.jsonl.
    For these, return the parent session UUID so sidecar files are shared.
    """
    if not transcript_path:
        return None
    parts = transcript_path.replace("\\", "/").split("/")
    try:
        sub_idx = parts.index("subagents")
        if sub_idx > 0:
            return parts[sub_idx - 1] or None
    except ValueError:
        pass
    session = os.path.basename(transcript_path)
    if session.endswith(".jsonl"):
        session = session[:-6]
    return session or None


def _write_context_sidecar(transcript_path, command):
    """Write/update session context sidecar file. Best-effort."""
    try:
        session = _session_id(transcript_path)
        if not session:
            return
        session_dir = _session_dir(session)
        os.makedirs(session_dir, exist_ok=True)
        path = os.path.join(session_dir, SIDECAR_FILENAME)
        with open(path, "w") as f:
            json.dump({"command": command, "timestamp_ms": int(time.time() * 1000)}, f)
    except Exception:
        pass


def _update_context_timestamp(transcript_path):
    """Bump sidecar timestamp. Best-effort."""
    try:
        session = _session_id(transcript_path)
        if not session:
            return
        path = os.path.join(_session_dir(session), SIDECAR_FILENAME)
        with open(path) as f:
            data = json.load(f)
        data["timestamp_ms"] = int(time.time() * 1000)
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


_RECENT_CMD_RE = re.compile(
    r'<command-name>/mg:'                # slash-command invocation tag
    r'|"skill"\s*:\s*"mg:'               # Skill tool_use input (compact or pretty JSON)
    r'|Launching skill:\s*mg:'           # Skill tool_result body
)


def _emitter_follows_command(transcript_path):
    """Return True if a /mg: command was loaded in the recent transcript tail.

    A /mg: command can reach the LLM through two channels, each leaving a
    different fingerprint in the transcript:

    1. **Slash command** — CC injects a ``<command-name>/mg:...`` tag.
    2. **Skill tool** — CC emits an assistant ``tool_use`` with
       ``"name":"Skill"`` and ``"skill":"mg:..."``, followed by a
       ``tool_result`` whose body is ``Launching skill: mg:...``. No
       ``<command-name>`` tag is produced.

    The emit-context.py call happens some entries later — typically after
    the command body, referenced attachments, last-prompt marker, and any
    assistant thinking. With attachments, that gap can be 20–40 lines, so
    we scan a wide tail (``_RECENT_LINES``) to still catch the marker
    while excluding ancient invocations.

    Note: CC strips YAML frontmatter (including ``allowed-tools:``) before
    writing command content to the transcript, so for slash commands we
    match on the ``<command-name>`` tag rather than the body text.
    """
    if not transcript_path:
        return False
    try:
        with open(transcript_path) as f:
            lines = f.read().splitlines()
    except (OSError, IOError):
        return False

    tail = "\n".join(lines[-_RECENT_LINES:]) if lines else ""
    return bool(_RECENT_CMD_RE.search(tail))


def check_session_context(transcript_path):
    """Return the active context command name (e.g. 'AUTO-DOC') or None.

    Reads the session context sidecar file and checks whether its
    timestamp is within CONTEXT_TTL_S.
    """
    if not transcript_path:
        return None
    session = _session_id(transcript_path)
    if not session:
        return None
    path = os.path.join(_session_dir(session), SIDECAR_FILENAME)
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, IOError):
        return None

    command = data.get("command")
    timestamp_ms = data.get("timestamp_ms", 0)
    if not command or not isinstance(timestamp_ms, (int, float)):
        return None

    age_s = time.time() - timestamp_ms / 1000
    if age_s > CONTEXT_TTL_S or age_s < 0:
        return None
    return command


def check_pause(transcript_path):
    """Return latch info if the session is paused, else None.

    This hook is a read-only consumer: the latch is created by the ``pause``
    subcommand of scripts/auto-approve-session.py and removed only by
    ``unpause``. It never expires — it is a request that holds until cleared.

    A latch we cannot parse still counts as paused. Unlike the auto-approve
    sidecar, this marker *withholds* privilege, so ignoring an unreadable one
    would fail in the unsafe direction: a run the user asked to stop would keep
    going. ``unpause`` removes a corrupt latch as readily as a valid one.
    """
    if not transcript_path:
        return None
    session = _session_id(transcript_path)
    if not session:
        return None
    path = os.path.join(_session_dir(session), PAUSE_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, IOError):
        return {"paused_at_ms": None, "note": None}
    if not isinstance(data, dict):
        return {"paused_at_ms": None, "note": None}
    paused_at_ms = data.get("paused_at_ms")
    note = data.get("note")
    return {
        "paused_at_ms": paused_at_ms if isinstance(paused_at_ms, (int, float)) else None,
        "note": note.strip() if isinstance(note, str) and note.strip() else None,
    }


def _usage_windows_match(mute_iso, verdict_iso):
    """True when a mute was taken out for the window the verdict is about."""
    if not mute_iso or not verdict_iso:
        return False        # a mute with no window silences nothing
    try:
        a = datetime.fromisoformat(mute_iso)
        b = datetime.fromisoformat(verdict_iso)
    except (TypeError, ValueError):
        return False
    return abs((a - b).total_seconds()) <= USAGE_WINDOW_TOL_MIN * 60


def check_usage_gate(transcript_path):
    """Return the published usage verdict if this call should ask, else None.

    The daemon owns the thresholds and precomputes ``over``/``binding``, so this
    is a file read and two comparisons — cheap enough for every tool call.

    Returns None (no gate) when the reading is missing, unparseable, stale, not
    over the limit, or muted by this session for the window in question.
    """
    path = os.path.join(_session_base(), USAGE_FILENAME)
    try:
        with open(path) as f:
            reading = json.load(f)
    except (OSError, json.JSONDecodeError, IOError):
        return None
    if not isinstance(reading, dict) or not reading.get("ok") or not reading.get("over"):
        return None

    read_at_ms = reading.get("read_at_ms")
    if not isinstance(read_at_ms, (int, float)):
        return None
    age_s = time.time() - read_at_ms / 1000
    if age_s > USAGE_STALE_S or age_s < 0:
        return None                     # nobody is publishing; don't gate on guesses

    binding = reading.get("binding")
    verdict_window = reading.get("window_iso")
    if not _muted(transcript_path, binding, verdict_window):
        return reading
    return None


def _muted(transcript_path, binding, verdict_window):
    """True when this session muted the limit warning for this window.

    A mute records the window of *each* limit at the time it was taken out, so a
    pre-emptive mute works whichever limit later binds. Unlike the pause latch, an
    unreadable mute grants nothing: a corrupt file must not silence a warning.
    """
    session = _session_id(transcript_path)
    if not session:
        return False
    try:
        with open(os.path.join(_session_dir(session), USAGE_MUTE_FILENAME)) as f:
            mute = json.load(f)
    except (OSError, json.JSONDecodeError, IOError):
        return False
    if not isinstance(mute, dict):
        return False
    windows = mute.get("windows")
    if not isinstance(windows, dict):
        return False
    return _usage_windows_match(windows.get(binding), verdict_window)


def _usage_reason(reading):
    """Build the ask reason for a call made close to the usage limit.

    Like the pause latch, this deliberately does not name the command that
    silences it: on a deny the text is fed back to the agent, and it must not read
    as instructions for switching off its own warning.
    """
    kind = reading.get("binding") or "usage"
    pct = reading.get("pct")
    human = reading.get("window_human")
    pct_txt = f"{pct}% " if pct is not None else ""
    resets = f", resets {human}" if human else ""
    return (f"[permission-guard] {kind} limit at {pct_txt}used{resets} — close to a "
            f"rate-limit cutoff; approving continues this call")


def _pause_reason(latch):
    """Build the ask reason shown for a paused session.

    Deliberately does not name the command that clears the latch: on a deny the
    reason text is fed back to the agent, and it must not read as instructions
    for unlatching its own gate.
    """
    age = ""
    paused_at_ms = latch.get("paused_at_ms")
    if paused_at_ms:
        secs = max(0, int(time.time() - paused_at_ms / 1000))
        age = f" {secs}s ago" if secs < 60 else f" {secs // 60}m ago"
    note = f" — note: {latch['note']}" if latch.get("note") else ""
    return (
        f"[permission-guard] PAUSED by user{age} — this run stays paused until "
        f"the user resumes it; approving lets only this one call through" + note
    )


# ── Edit guard (manual toggle for Edit/Write/NotebookEdit) ──────────────────
# The emit-edit-guard.py script prints a SESSION_FEATURE marker into the
# transcript.  Default is ON (edits allowed).  When the latest marker is OFF,
# Edit/Write/NotebookEdit are blocked until the user runs /mg:edit-on.
_EDIT_GUARD_RE = re.compile(r"SESSION_FEATURE: MG:EDIT_GUARD_(ON|OFF)_(\d{10,})")


def check_edit_guard(transcript_path):
    """Return True if the edit guard is active (edits should be blocked).

    Scans for the most recent EDIT_GUARD marker with a valid timestamp.
    No marker or latest=ON means edits are allowed (returns False).
    Latest=OFF means blocked.

    The timestamp suffix distinguishes real emitter output from phantom
    matches (source code / grep output appearing in the transcript).
    Unlike session context markers, the edit guard never expires — it is
    a manual toggle that persists until explicitly flipped.
    """
    if not transcript_path:
        return False
    try:
        with open(transcript_path) as f:
            raw = f.read()
    except (OSError, IOError):
        return False

    matches = list(_EDIT_GUARD_RE.finditer(raw))
    if not matches:
        return False  # No marker → default ON (edits allowed)

    # Take the last marker; reject only future timestamps (clock skew)
    last = matches[-1]
    timestamp_ms = int(last.group(2))
    age_s = time.time() - timestamp_ms / 1000
    if age_s < 0:
        return False  # clock skew / forged future timestamp

    return last.group(1) == "OFF"


# ── Edit guard bridge writer (best-effort status for statusline) ──────────
def _write_edit_guard_bridge(event):
    """Write edit guard state to a session-scoped bridge file.

    The statusline hook reads this file to show an edit guard badge.
    Best-effort: never raises, never breaks the hook.
    """
    try:
        transcript_path = event.get("transcript_path", "")
        if not transcript_path:
            return
        session = _session_id(transcript_path)
        if not session:
            return
        blocked = check_edit_guard(transcript_path)
        state = "OFF" if blocked else "ON"
        session_dir = _session_dir(session)
        os.makedirs(session_dir, exist_ok=True)
        bridge_path = os.path.join(session_dir, "edit-guard.json")
        with open(bridge_path, "w") as f:
            json.dump({"state": state, "ts": int(time.time())}, f)
    except Exception:
        pass


# Claude's internal directory (memory, settings, etc.) — always allowed
_CLAUDE_DIR_TILDE = "~/.claude/"
_CLAUDE_DIR_ABS = os.path.expanduser("~/.claude/")

# The user's home directory (no trailing slash). The workspace-sibling
# allowance is suppressed when a project's parent directory IS $HOME (or the
# filesystem root), since every home dotfile/folder would otherwise look like a
# "sibling project" and be allowed implicitly.
_HOME_DIR = os.path.expanduser("~").rstrip("/")


def _is_claude_internal(path):
    """Return True if *path* points inside Claude's own ~/.claude/ directory."""
    return path.startswith(_CLAUDE_DIR_TILDE) or path.startswith(_CLAUDE_DIR_ABS)

# Characters to strip from tokens when extracting potential file paths.
# Quotes plus common shell/code punctuation that isn't part of real paths.
_TOKEN_STRIP_CHARS = "'\"`(),[]{}"

# Commands that modify files (used by out-of-project path guard)
FILE_MODIFYING_CMDS = re.compile(
    r"\b(rm|mv|cp|mkdir|touch|tee)\b"
)
# Captures the target of a write redirect (> or >>). The (?<!\d) lookbehind
# excludes fd-prefixed redirects (e.g. 2>) and the (?!&) lookahead excludes fd
# duplications (e.g. >&2 / 2>&1) — neither is a file write we guard. Group 1 is
# the file the redirect writes to.
_REDIRECT_TARGET_RE = re.compile(r"(?<!\d)>{1,2}\s*(?!&)([^\s;|&<>]+)")

# Heredoc body stripping — removes content between heredoc markers
# so that data inside heredocs is not mistaken for shell arguments.
_HEREDOC_RE = re.compile(
    r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n"  # start: <<'DELIM'...\n
    r".*?"                                 # body (non-greedy, crosses lines)
    r"^\1\s*$",                            # terminator: DELIM on its own line
    re.MULTILINE | re.DOTALL,
)


def _strip_heredocs(command):
    """Remove heredoc bodies so their content is not parsed as shell arguments."""
    return _HEREDOC_RE.sub("", command)


# Quote masking — the contents of quoted spans are replaced by this filler so
# shell punctuation inside a string literal (a `>` closing an XML tag in a sed
# pattern, an `rm` inside a commit message) is not read as shell syntax.
_MASK_CHAR = "x"

# Nested shell invocations: the quoted argument IS a command, so masking it
# would hide a real redirect or a real rm target. Those commands are scanned
# raw instead — a spurious prompt beats a missed out-of-project write.
_SHELL_INVOKER_RE = re.compile(
    r"\b(?:bash|sh|zsh|ksh|dash)\s+(?:-\w+\s+)*-\w*c\b"  # bash -c, sh -lc, …
    r"|\beval\b"
    r"|\bxargs\b"
    r"|\bssh\b"
)

# Shell segment (split points: newline ; | &) and whitespace-delimited token,
# both applied to the masked command so quoted separators don't split.
_SEGMENT_RE = re.compile(r"[^\n;|&]+")
_TOKEN_RE = re.compile(r"\S+")


def _mask_quoted(command):
    """Return *command* with the contents of quoted spans replaced by filler.

    Length and character offsets are preserved, so a match found in the masked
    string can be sliced straight out of the original. The quote characters
    themselves are kept — only what they enclose is masked, which is enough to
    stop a quoted `>` from reading as a redirect while a genuinely quoted
    write target (``> "/tmp/my file"``) still resolves to its real path.

    Backslash escapes are honoured outside single quotes; an unterminated
    quote masks to the end of the string, as the shell would keep reading.
    """
    out = list(command)
    i, n = 0, len(command)
    while i < n:
        char = command[i]
        if char == "\\":
            i += 2  # escaped char outside quotes — nothing to mask
            continue
        if char in "'\"":
            i += 1
            while i < n and command[i] != char:
                # Inside double quotes a backslash escapes the next char, so
                # \" does not close the span.
                width = 2 if (char == '"' and command[i] == "\\") else 1
                out[i:i + width] = _MASK_CHAR * min(width, n - i)
                i += width
            i += 1  # skip the closing quote (or run past the end)
            continue
        i += 1
    return "".join(out)


# ── LLM evaluator constants ─────────────────────────────────────────────────
HAIKU_TIMEOUT_S = 12
HAIKU_MODEL = "haiku"
TRANSCRIPT_CONTEXT_LINES = 10
TRANSCRIPT_MSG_MAX_CHARS = 200

# Paths where recursive rm is considered safe (temp/test cleanup)
SAFE_RM_PATH_PREFIXES = ("temp/", "./temp/", "/tmp/")

# Directory components that indicate a temp/scratch directory
_TEMP_COMPONENTS = ("/tmp/", "/temp/")


def _path_is_temp(path):
    """Return True if *path* is inside a tmp or temp directory."""
    # Prefix match (original behaviour)
    if any(path.startswith(prefix) for prefix in SAFE_RM_PATH_PREFIXES):
        return True
    # Component match — /tmp/ or /temp/ anywhere in the path
    return any(comp in path for comp in _TEMP_COMPONENTS)


def _is_safe_rm(command):
    """Return True if every rm segment in *command* targets only temp directories.

    Compound commands joined by ``&&``, ``||``, or ``;`` are split into
    segments.  Only segments containing an ``rm`` invocation are examined —
    non-rm segments are irrelevant.  If no segment contains ``rm``, return
    False (this function is specifically about rm safety).
    """
    # Split on shell compound operators (&&, ||, ;)
    segments = re.split(r'\s*(?:&&|\|\||;)\s*', command)

    rm_segments = [seg for seg in segments if re.match(r'^\s*rm\s', seg.strip())]

    # Must have at least one rm segment
    if not rm_segments:
        return False

    for seg in rm_segments:
        tokens = seg.split()
        paths = [t.strip("'\"") for t in tokens[1:] if not t.startswith('-')]
        if not paths:
            return False
        if not all(_path_is_temp(p) for p in paths):
            return False

    return True

# ── Sensitive file patterns (for Read/Edit/Write tool guards) ───────────────
# Each is (compiled_regex, description). Matched against the file_path.

SENSITIVE_FILE_PATTERNS = [
    (re.compile(r"~/\.\S*(ssh|aws|gnupg|kube)/"), "sensitive dotfile directory"),
    *(_ENV_FILE_PATTERNS if ENV_PROTECTION else []),
    (re.compile(r"(^|/)(\.netrc|\.npmrc|\.pypirc)$"), "credential file"),
    (re.compile(r"(^|/)id_(rsa|ed25519|ecdsa|dsa)(\.pub)?$"), "SSH key"),
    (re.compile(r"(^|/)credentials(\.json)?$"), "credentials file"),
    (re.compile(r"(^|/)\.git-credentials$"), "git credentials"),
    *(_PGPASS_FILE_PATTERNS if PGPASS_PROTECTION else []),
    (re.compile(r"(^|/)\.my\.cnf$"), "MySQL config (may contain passwords)"),
    (re.compile(r"(^|/)\.docker/config\.json$"), "Docker registry credentials"),
    (re.compile(r"(^|/)\.htpasswd$"), "web server password file"),
    (re.compile(r"\.(pem|key)$"), "TLS certificate/private key"),
]


def check_command(command):
    """Check command against category rules.

    Returns (description, category, matched_text) or None.
    """
    command = _strip_heredocs(command)
    for compiled_re, description, category in RULES:
        match = compiled_re.search(command)
        if match:
            return (description, category, match.group())
    return None


def check_file_path(file_path):
    """Check if a file path matches sensitive file patterns.

    Returns (description,) or None.
    """
    for compiled_re, description in SENSITIVE_FILE_PATTERNS:
        if compiled_re.search(file_path):
            return (description,)
    return None


def check_sensitive_in_command(command):
    """Check if a Bash command references sensitive file paths.

    Tokenises the command on whitespace and shell operators, strips quotes
    and shell punctuation, and tests each token against SENSITIVE_FILE_PATTERNS.

    Returns (description, matched_path) or None.
    """
    command = _strip_heredocs(command)
    tokens = re.split(r'[\s;|&]+', command)
    for token in tokens:
        token = token.strip(_TOKEN_STRIP_CHARS)
        if not token:
            continue
        for compiled_re, description in SENSITIVE_FILE_PATTERNS:
            if compiled_re.search(token):
                return (description, token)
    return None


def _resolved_path_allowed(resolved, project_root):
    """Return True if *resolved* (an already-expanded absolute path) is allowed
    by the out-of-project guard.

    A path is allowed when it is:
      * inside the project root,
      * a known-safe absolute path (/dev/null, /tmp, …), or
      * inside the workspace directory (the parent of the project root) — i.e. a
        sibling project — UNLESS that workspace is ``$HOME`` or the filesystem
        root, where "sibling" would mean "all of $HOME" / "everything" and is
        too broad to allow implicitly.

    Shared by the Read/Edit/Write guard and the Bash write-target guard so that
    ``~/``, ``../`` and absolute paths are judged identically — only the
    description string differs by caller.
    """
    if resolved.startswith(project_root + "/") or resolved == project_root:
        return True
    if any(resolved == safe or resolved.startswith(safe + "/")
           for safe in SAFE_ABSOLUTE_PATHS):
        return True
    workspace = os.path.dirname(project_root)
    if workspace and workspace not in ("/", _HOME_DIR) and resolved.startswith(workspace + "/"):
        return True
    return False


def check_file_outside_project(file_path, project_root):
    """Check if a file path is outside the project root.

    Returns a description string or None. Tilde, parent-traversal and absolute
    paths are each expanded to an absolute path and judged by the shared
    _resolved_path_allowed check; only the description differs. Bare relative
    paths are assumed in-project (CC resolves them against the project-root cwd).
    """
    if not project_root:
        return None

    project_root = project_root.rstrip("/")

    # Claude's own internal files (memory, settings) are always allowed
    if _is_claude_internal(file_path):
        return None

    # Expand ~ and judge the resolved path
    if file_path.startswith("~/") or file_path == "~":
        resolved = os.path.expanduser(file_path)
        if not _resolved_path_allowed(resolved, project_root):
            return f"home directory path: {file_path}"
        return None

    # Parent traversal — resolve to absolute and judge
    if "../" in file_path:
        resolved = os.path.realpath(file_path)
        if not _resolved_path_allowed(resolved, project_root):
            return f"parent directory traversal: {file_path}"
        return None

    # Absolute paths
    if file_path.startswith("/"):
        if not _resolved_path_allowed(file_path, project_root):
            return f"path outside project root: {file_path}"

    return None


def _candidate_write_targets(command):
    """Yield tokens that are genuine write targets in *command*.

    Only these positions can write outside the project, so only these are
    worth checking. A path-shaped substring anywhere else — a grep/sed
    pattern, a regex, a URL, an HTTP request path in a log line — is not a
    write and must not be flagged.

    Sources:
      1. Redirect targets — the file after ``>`` / ``>>`` (fd redirects like
         ``2>`` and fd duplications like ``>&2`` are excluded).
      2. Arguments of file-modifying commands (rm/mv/cp/mkdir/touch/tee),
         scanned per shell-segment (split on ``; | & newline``) so only the
         segment that actually runs the command is examined — a path-pattern
         sitting in an unrelated segment is never treated as a write target.

    Both sources match against the quote-masked command: shell punctuation
    inside a string literal is not shell syntax, so ``sed '/<tag>/,/<\\/tag>/p'``
    yields no redirect and ``git commit -m "rm /etc/x"`` runs no rm. Every
    token is sliced back out of the original command by offset, so a quoted
    write target keeps its real text (spaces included).
    """
    masked = command if _SHELL_INVOKER_RE.search(command) else _mask_quoted(command)

    # 1. Redirect targets (scanned across the whole command)
    for match in _REDIRECT_TARGET_RE.finditer(masked):
        yield command[match.start(1):match.end(1)]

    # 2. File-modifying command arguments (per segment)
    for segment in _SEGMENT_RE.finditer(masked):
        if FILE_MODIFYING_CMDS.search(segment.group()):
            for token in _TOKEN_RE.finditer(segment.group()):
                start = segment.start() + token.start()
                yield command[start:start + len(token.group())]


def check_outside_project(command, project_root):
    """Check if command writes to a path outside the project root.

    Only genuine write targets are examined (see _candidate_write_targets);
    path-shaped substrings elsewhere in the command are ignored.

    Returns (description, matched_path) or None.
    """
    if not project_root:
        return None

    # Strip heredoc bodies so their content isn't parsed as paths
    command = _strip_heredocs(command)

    # Normalize project root (remove trailing slash)
    project_root = project_root.rstrip("/")

    for token in _candidate_write_targets(command):
        # Strip quotes and shell punctuation
        token = token.strip(_TOKEN_STRIP_CHARS)
        if not token:
            continue

        # Claude's own internal files (memory, settings) are always allowed
        if _is_claude_internal(token):
            continue

        # Absolute, ~/, and ../ write targets are each expanded to an absolute
        # path and judged by the shared _resolved_path_allowed check; only the
        # description differs.
        if token.startswith("/"):
            # Skip bare slash tokens (e.g. Python's // operator)
            if token.rstrip("/") == "":
                continue
            if not _resolved_path_allowed(token, project_root):
                return (f"path outside project root: {token}", token)

        elif token.startswith("~/") or token == "~":
            resolved = os.path.expanduser(token)
            if not _resolved_path_allowed(resolved, project_root):
                return (f"home directory path: {token}", token)

        elif "../" in token:
            resolved = os.path.realpath(token)
            if not _resolved_path_allowed(resolved, project_root):
                return (f"parent directory traversal: {token}", token)

    return None


# ── Exit code masking detection ─────────────────────────────────────────────
# A pipeline reports the status of its LAST stage, so `pytest | head` exits 0
# however many tests failed. What makes that worth a deny is not the lost number
# but the false green: the run is reported as passing. So the rule is scoped to
# pipes that drop the output which would have shown the failure, in the pipeline
# the pytest run actually belongs to.

# Sinks that pass the stream through whole. The failure summary still reaches
# the transcript, so the lost status hides nothing.
_PASSTHROUGH_SINK = r"(?:tee|cat|less|more|bat)"

# Commands whose arguments are patterns or paths rather than code to run:
# `grep -rn pytest CLAUDE.md | head` searches for the word, it does not run
# tests. Anchored to the head of a stage, the same command-position reasoning
# as _CMD_POS, applied one pipeline stage at a time.
_TEXT_TOOL = (
    r"(?:grep|egrep|fgrep|rg|ag|ack|sed|awk|echo|printf|ls|find|cat|head|tail"
    r"|git|jq|wc|sort|uniq|column|man)"
)

# Status kept by hand: `pipefail` makes $? the first failing stage, PIPESTATUS
# reads the producer's status directly. A bare `echo $?` after a pipe is NOT an
# escape — it reports the sink's status, which is the bug itself.
_PIPESTATUS_RE = re.compile(r"\bpipefail\b|\bPIPESTATUS\b")

# Pipeline boundaries. `||` and `&&` are consumed before the single-character
# class so a lone `|` survives — it is the operator this rule is looking for.
# The `&` of a redirect (`2>&1`, `&>log`) is not a separator; splitting there
# would cut the producer off from its own pipe.
_PIPELINE_SPLIT_RE = re.compile(r"\|\||&&|[;\n]|(?<![>&])&(?![>&])")

_PYTEST_WORD_RE = re.compile(r"\bpytest\b")
# A leading assignment prefix (`FOO=1 pytest`) belongs to the command that
# follows it, so step over it before reading the stage's command word.
_ASSIGN_PREFIX = r"^\s*(?:\w+=\S+\s+)*"
_LEADING_TEXT_TOOL_RE = re.compile(_ASSIGN_PREFIX + _TEXT_TOOL + r"\b")
_PASSTHROUGH_SINK_RE = re.compile(_ASSIGN_PREFIX + _PASSTHROUGH_SINK + r"\b")


def check_exit_code_masking(command):
    """Check if a pytest run's output is piped into a stage that hides failures.

    Returns a reason string or None.
    """
    command = _strip_heredocs(command)
    # Quoted text is data: a commit message about this rule is not a test run.
    # Nested shell invocations are the exception — there the quoted string IS
    # the command, so scan it raw (same trade as check_write_targets).
    if not _SHELL_INVOKER_RE.search(command):
        command = _mask_quoted(command)

    if _PIPESTATUS_RE.search(command):
        return None

    for pipeline in _PIPELINE_SPLIT_RE.split(command):
        stages = pipeline.split("|")
        # The last stage's status is the pipeline's own, so only a pytest with
        # a pipe downstream of it loses anything.
        for index, stage in enumerate(stages[:-1]):
            if not _PYTEST_WORD_RE.search(stage):
                continue
            if _LEADING_TEXT_TOOL_RE.search(stage):
                continue  # the word is an argument, not an invocation
            downstream = stages[index + 1:]
            if all(_PASSTHROUGH_SINK_RE.search(s) for s in downstream):
                continue  # nothing dropped, so nothing hidden
            return (
                "Exit code masking — use instead: "
                "pytest --tb=short -q --no-header"
            )
    return None


# ── LLM evaluator framework ──────────────────────────────────────────────────
Evaluator = namedtuple("Evaluator", ["name", "gate", "prompt_builder"])


def _extract_transcript_context(event):
    """Parse the JSONL transcript and return last N user/assistant text messages.

    Returns a formatted string. Returns empty string on any failure.
    """
    transcript_path = event.get("transcript_path", "")
    if not transcript_path:
        return ""
    try:
        with open(transcript_path) as f:
            lines = f.readlines()
    except (OSError, IOError):
        return ""

    messages = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = entry.get("role")
        if role not in ("user", "assistant"):
            continue
        # Extract text content, skip tool_use/tool_result
        content = entry.get("content", "")
        if isinstance(content, list):
            text_parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            content = " ".join(text_parts)
        if not isinstance(content, str) or not content.strip():
            continue
        truncated = content.strip()[:TRANSCRIPT_MSG_MAX_CHARS]
        messages.append(f"{role}: {truncated}")

    return "\n".join(messages[-TRANSCRIPT_CONTEXT_LINES:])


def _find_claude_cli():
    """Locate the claude CLI binary, checking PATH and common install locations."""
    found = shutil.which("claude")
    if found:
        return found
    # Hook subprocesses may have a stripped PATH — check common locations
    for candidate in [
        os.path.expanduser("~/.local/bin/claude"),
        os.path.expanduser("~/.claude/local/claude"),
        "/usr/local/bin/claude",
    ]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _call_haiku(prompt):
    """Call the claude CLI with Haiku model. Returns response text or None.

    ``--no-session-persistence`` matters twice over here, since this runs inside
    the latency path of a tool call: without it every evaluator check persists a
    throwaway session transcript under ~/.claude/projects/ (which session
    pickers scanning that directory then read as a real session), and pays the
    session-setup cost — measured at ~3s of the call. Should a CLI ever reject
    the flag, the non-zero exit lands on the ``return None`` below, which the
    evaluator layer treats as "no verdict" and falls through to asking — more
    prompts, never fewer.
    """
    claude_bin = _find_claude_cli()
    if not claude_bin:
        return None
    try:
        result = subprocess.run(
            [claude_bin, "-p", "--model", HAIKU_MODEL, "--output-format", "json",
             "--no-session-persistence"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=HAIKU_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if data.get("is_error"):
        return None
    return data.get("result", "")


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _parse_verdict(response_text):
    """Parse JSON verdict from Haiku response.

    Expects {"verdict": "SAFE|UNSURE|DENY", "reason": "..."}.
    Strips markdown code fences if present.
    Returns None if JSON doesn't parse or verdict field is missing/invalid
    — caller treats None as "fall through to user prompt".
    """
    if not response_text:
        return None
    text = response_text.strip()
    # Strip markdown code fences (```json ... ```)
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    verdict = data.get("verdict", "").upper() if isinstance(data, dict) else None
    if verdict in ("SAFE", "UNSURE", "DENY"):
        return verdict
    return None


def run_evaluators(command, event):
    """Run narrowly-scoped LLM evaluators on the command.

    Returns (decision, trace) where decision is "allow"/"ask"/None.
    - "allow" + trace: evaluator said SAFE
    - "ask" + trace: evaluator fired but returned UNSURE/DENY/error
    - (None, None): no evaluator matched
    """
    for evaluator in EVALUATORS:
        if not evaluator.gate(command, event):
            continue
        ctx = _extract_transcript_context(event)
        prompt = evaluator.prompt_builder(command, ctx, event)
        response = _call_haiku(prompt)
        verdict = _parse_verdict(response)
        tag = f"eval:{evaluator.name}"
        if verdict == "SAFE":
            return ("allow", f"[{tag}→SAFE]")
        label = verdict or "no-response"
        return ("ask", f"[{tag}→{label}]")
    return (None, None)


# ── Evaluator definitions ────────────────────────────────────────────────────

_RM_VARIABLE_RE = re.compile(
    r'\brm\s+(-\S+\s+)*-\S*[rR]\S*\s+.*(\$\w+|\$\{[^}]+\}|\$\([^)]+\))'
)


def _gate_rm_variable_cleanup(command, event):
    """True if command has recursive rm with shell variables that _is_safe_rm can't resolve."""
    if not _RM_VARIABLE_RE.search(command):
        return False
    # If _is_safe_rm already handles it, no need for LLM
    if _is_safe_rm(command):
        return False
    return True


def _resolve_project_root(event):
    """Return the resolved project root, or empty string if unavailable.

    When the install-time PROJECT_ROOT placeholder is unresolved/empty:
      1. Prefer CLAUDE_PROJECT_DIR — the project root CC exports to hooks. It is
         stable regardless of the session's working directory.
      2. Fall back to the event cwd only when the env var is absent.

    Using the event cwd as the root is wrong when the session was launched from
    (or cd'd into) a subdirectory: the guard would then treat the project's own
    files elsewhere in the tree as out-of-project. CLAUDE_PROJECT_DIR always
    points at the real root, so it takes precedence.
    """
    root = PROJECT_ROOT
    # Skip unresolved install-time placeholder
    if not root or root.startswith("{"):
        root = os.environ.get("CLAUDE_PROJECT_DIR", "").strip() or event.get("cwd", "")
    return root


def _prompt_rm_variable_cleanup(command, ctx, event):
    """Build a prompt asking Haiku to resolve rm target paths from context."""
    project_root = _resolve_project_root(event)

    safe_dirs = "/tmp/"
    if project_root:
        safe_dirs += f" and {project_root}"

    prompt = f"""You are a security reviewer for a CLI coding assistant. A command contains `rm` with shell variable substitutions. The deterministic safety check could not resolve the variables.

Your job: resolve the shell variables in the rm command to determine the ACTUAL path being deleted. Only answer SAFE if the resolved path is inside one of these safe directories: {safe_dirs}

Command: {command}

"""
    if ctx:
        prompt += f"""Recent conversation context:
{ctx}

"""
    prompt += f"""Instructions:
1. Look at the command for variable assignments (e.g. DIR=/tmp/foo && rm -rf $DIR)
2. Look at the conversation context for variable definitions
3. Resolve the rm target path from the evidence you find

Verdicts:
- SAFE — the resolved path is inside: {safe_dirs}
- UNSURE — you cannot resolve the variable, or cannot confirm the resolved path is inside a safe directory
- DENY — the resolved path is clearly outside the safe directories listed above

Default to UNSURE if there is any doubt.

Respond with ONLY a JSON object, no other text:
{{"verdict": "SAFE|UNSURE|DENY", "resolved_path": "/the/resolved/path", "reason": "brief explanation"}}"""
    return prompt


_RM_RECURSIVE_RE = re.compile(r'\brm\s+(-\S+\s+)*-\S*[rR]')


def _gate_rm_user_approved(command, event):
    """True if command has recursive rm with literal paths (no variables).

    The rm-variable-cleanup evaluator handles the variable case.
    This evaluator handles literal in-project paths where the user may have
    explicitly approved the deletion in conversation.
    """
    if not _RM_RECURSIVE_RE.search(command):
        return False
    # Variable paths are handled by rm-variable-cleanup
    if _RM_VARIABLE_RE.search(command):
        return False
    # Already safe (temp dirs)
    if _is_safe_rm(command):
        return False
    # Only fire if we have transcript context to check
    if not event.get("transcript_path"):
        return False
    return True


def _prompt_rm_user_approved(command, ctx, event):
    """Build prompt asking Haiku if user explicitly approved this deletion."""
    project_root = _resolve_project_root(event)

    prompt = f"""You are a security reviewer for a CLI coding assistant. A recursive rm command is about to execute. The deterministic safety check flagged it because the target is not a known temp directory.

Your job: check the conversation context to determine if the USER explicitly requested or confirmed this deletion.

Command: {command}
Project root: {project_root}

"""
    if ctx:
        prompt += f"""Recent conversation context:
{ctx}

"""
    prompt += """Instructions:
1. Check if the user explicitly asked for files/directories to be deleted
2. Check if the assistant listed what would be deleted and the user confirmed (e.g. "yes", "go ahead", "do it")
3. Verify the rm targets match what the user approved

Verdicts:
- SAFE — the user explicitly requested or confirmed this exact deletion
- UNSURE — no clear user approval, or the targets don't match what was discussed
- DENY — the deletion contradicts what the user asked for

Default to UNSURE if there is any doubt.

Respond with ONLY a JSON object, no other text:
{"verdict": "SAFE|UNSURE|DENY", "reason": "brief explanation"}"""
    return prompt


EVALUATORS = [
    Evaluator("rm-variable-cleanup", _gate_rm_variable_cleanup, _prompt_rm_variable_cleanup),
    Evaluator("rm-user-approved", _gate_rm_user_approved, _prompt_rm_user_approved),
]


def _decide(reason, decision="ask"):
    """Print a permissionDecision response and exit."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output))


def _ask(reason):
    """Print a permissionDecision: ask response and exit."""
    _decide(reason, "ask")


def _deny(reason):
    """Print a permissionDecision: deny response and exit (no user prompt)."""
    _decide(reason, "deny")


# Permission modes in which this guard stands down. It is the user's safety net
# for bypassPermissions (CC approves everything there), so it stays active in
# that mode — and in any unknown/missing mode (fail safe) — but defers to CC's
# native permission flow in the modes below, which already vet tool calls.
_DEFER_PERMISSION_MODES = frozenset({"default", "plan", "acceptEdits", "auto", "dontAsk"})


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    # ── Permission-mode gate ────────────────────────────────────────────
    # Active only in bypassPermissions (and any unknown/missing mode — fail
    # safe). In the modes CC vets itself, stand down: returning with no output
    # is the documented neutral "defer to the normal permission flow" signal.
    if event.get("permission_mode") in _DEFER_PERMISSION_MODES:
        return

    # Best-effort: write edit guard state for statusline badge
    _write_edit_guard_bridge(event)

    # ── Pause latch ─────────────────────────────────────────────────────
    # Checked ahead of stage 0 and of the auto-approve window: an armed window
    # returns "allow", which would otherwise swallow the pause. Sticky, so
    # every guarded call in the session tree asks — including calls from
    # sibling subagents that would sail past a one-shot marker.
    latch = check_pause(event.get("transcript_path", ""))
    if latch:
        _ask(_pause_reason(latch))
        return

    # ── Usage gate ──────────────────────────────────────────────────────
    # Also ahead of the auto-approve window: an armed unattended run is exactly
    # the thing that would otherwise burn the last of a window unsupervised.
    usage = check_usage_gate(event.get("transcript_path", ""))
    if usage:
        _ask(_usage_reason(usage))
        return

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

    # ── Stage 0: gate emitter scripts (unless preceded by a command) ──
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if _EMIT_SCRIPT_RE.search(command):
            if _emitter_follows_command(event.get("transcript_path", "")):
                # Extract command name: "... emit-context.py AUTO-DOC" → "AUTO-DOC"
                cmd_match = re.search(r'emit-context\.py\s+(\S+)', command)
                ctx_name = cmd_match.group(1).upper() if cmd_match else "UNKNOWN"
                _write_context_sidecar(event.get("transcript_path", ""), ctx_name)
                _decide(
                    "[permission-guard] Session context emitter — "
                    "auto-approved (slash command active)",
                    "allow",
                )
            else:
                _ask("[permission-guard] Session context emitter — requires human approval")
            return

    # ── Session context auto-approve ───────────────────────────────────
    ctx_cmd = check_session_context(event.get("transcript_path", ""))
    if ctx_cmd:
        _update_context_timestamp(event.get("transcript_path", ""))
        _decide(
            f"[permission-guard] Auto-approved by session context MG:{ctx_cmd}",
            "allow",
        )
        return

    # ── Edit guard (manual toggle) ──────────────────────────────────────
    if tool_name in ("Edit", "Write", "NotebookEdit"):
        if check_edit_guard(event.get("transcript_path", "")):
            _deny(
                "[permission-guard] Implementation/edits are not approved yet "
                "by the user."
            )
            return

    # ── Read / Edit / Write tool guard ──────────────────────────────────
    if tool_name in ("Read", "Edit", "Write"):
        file_path = tool_input.get("file_path", "")
        if file_path:
            # 1. Sensitive file patterns
            result = check_file_path(file_path)
            if result:
                _ask(f"[permission-guard] Secrets & Credentials: {result[0]} ({file_path})")
                return
            # 2. Out-of-project path guard
            root = _resolve_project_root(event)
            if root:
                desc = check_file_outside_project(file_path, root)
                if desc:
                    _ask(f"[permission-guard] Out-of-project: {desc}")
                    return
        # File passed all safety checks — approve explicitly so the hook
        # doesn't fall through to CC's default permission mode (which prompts).
        _decide("[permission-guard] In-project file", "allow")
        return

    # ── Bash tool guard ─────────────────────────────────────────────────
    if tool_name != "Bash":
        return

    command = tool_input.get("command", "")
    if not command:
        return

    # 0. Allow rm targeting only temp directories
    if _is_safe_rm(command):
        return

    # 0a. LLM evaluator layer (narrowly-scoped Haiku checks)
    eval_decision, eval_trace = run_evaluators(command, event)
    if eval_decision == "allow":
        _decide(f"[permission-guard] {eval_trace}", "allow")
        return

    # 0b. Block exit code masking (pytest piped to tail/head/grep etc.)
    reason = check_exit_code_masking(command)
    if reason:
        _deny(f"[permission-guard] {reason}")
        return

    # Prefix for eval trace when an evaluator fired but didn't approve
    trace_prefix = f"{eval_trace} " if eval_trace else ""

    # 1. Category rules
    result = check_command(command)
    if result:
        description, category, _matched = result
        _ask(f"[permission-guard] {trace_prefix}{category}: {description}")
        return

    # 2. Sensitive file paths in command arguments
    result = check_sensitive_in_command(command)
    if result:
        description, matched_path = result
        _ask(f"[permission-guard] {trace_prefix}Secrets & Credentials: {description} ({matched_path})")
        return

    # 3. Out-of-project path guard
    root = _resolve_project_root(event)
    if root:
        result = check_outside_project(command, root)
        if result:
            description, _matched_path = result
            _ask(f"[permission-guard] {trace_prefix}Out-of-project: {description}")
            return


if __name__ == "__main__":
    main()
