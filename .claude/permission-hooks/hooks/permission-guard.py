#!/usr/bin/env python3
"""PreToolUse hook that guards against dangerous operations.

For Bash: checks commands against 8 categories of dangerous patterns, a
worktree-destruction stage that asks git what a restore would cost, plus an
out-of-project path guard.

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
import shlex
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
    # Unlike every other category rule this one matches an operand (the
    # redirect target) rather than a command verb, so check_command's quote
    # masking hides a quoted target: `echo x > "cfg/.env"` does not match.
    # Unquoted targets — the common form — still do, and the write itself
    # still reaches the out-of-project guard, which recovers quoted redirect
    # targets from the original string (see _candidate_write_targets).
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
# the command, leaving a bare-key read. The key must carry its section dot:
# git rejects a write to a sectionless key ("key does not contain a section"),
# and the rules scan the raw command string, so an undotted key would flag
# ordinary prose containing the words — `echo "=== git config rule ==="`. The
# middle of the key stays permissive for URL subsections
# (`url.https://github.com/.insteadOf`) but must end on a key character, so a
# trailing-dot abbreviation ("git config e.g. foo") is not a write either.
_GIT_CONFIG_WRITE = (
    r"\bgit\s+config(?!\s+(?:get|list)\b)"
    + _GIT_CONFIG_OPTS
    + r"\s+(?:"
    r"--(?:add|unset|unset-all|replace-all|rename-section|remove-section|edit)\b"
    r"|-e\b"
    r"|(?:set|unset|edit|rename-section|remove-section)\b"
    r"|[\w-]+\.\S*[\w-][ \t]+[^\s)`;&|<>]"
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

# The checkout rule carries no exemption on purpose. It used to read
# `git\s+checkout\s+(?!--)`, i.e. it treated the `--` spelling as the benign
# "file restore" case and let it through — which is the wrong way round (see
# the Git worktree destruction section). Every checkout now reaches a guard:
# the pathspec forms are claimed by check_worktree_destruction, which asks git
# whether there is anything to lose and suppresses this rule when there is
# not, and everything else — branch switches, --detach, --force — asks here.
GIT_CHECKOUT_RULE = "git checkout"

CATEGORIES = {
    "Git Branch & History": [
        (r"\bgit\s+checkout\b", GIT_CHECKOUT_RULE),
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


# ── Git worktree destruction ────────────────────────────────────────────────
# `git checkout -- <path>`, `git restore <path>` and `git clean -f` are the
# only operations this guard sees that can destroy work with NO recovery path.
# A discarded worktree modification leaves no reflog entry and no object in the
# database to recover from: the bytes are gone. (`git reset --hard` is in the
# same class and has its own always-ask rule.)
#
# The old checkout rule exempted the `--` spelling as "file restore", which had
# it exactly backwards. `git checkout <branch>` REFUSES when it would overwrite
# local modifications; `git checkout -- <file>` is *designed* to discard them.
# The exemption spared the irreversible form and asked about the recoverable
# one — and a real ~500-line loss went through it unprompted.
#
# Asking on every restore would be too noisy to stay readable, and a prompt
# nobody reads is not a guard. So the discriminator is whether there is
# anything to lose: git itself is asked, scoped to the pathspecs the command
# names, and a restore over a clean path stays silent. Uncertainty asks — an
# unresolvable working directory, a pathspec neither git nor the filesystem
# recognises (which means we resolved it wrong), or a git that will not answer
# all land on the ask side, because the cost of a spurious prompt here is a
# keystroke and the cost of a miss is unrecoverable work.
#
# `git stash push` is deliberately NOT here: it moves work rather than
# destroying it, `git stash list` still holds it, and the point where it does
# become irreversible — `git stash drop|clear` — already has its own rule.

_GIT_TIMEOUT_S = 5

# Redirects are stripped before tokenising so `2>/dev/null` is not read as a
# pathspec. Matches an optional fd, the operator, and its target.
_REDIRECT_STRIP_RE = re.compile(r"\d*(?:>>|>|<<<|<)\s*&?\S+")

# git's own options that take a separate value, so a value can never be read as
# the subcommand. `-C` is captured: it moves the repo the command acts on.
_GIT_GLOBAL_VALUE_OPTS = frozenset({
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
    "--super-prefix", "--config-env",
})

# Subcommand options taking a separate value, per verb. `-m` is absent on
# purpose: on checkout it means --merge and takes nothing.
_CHECKOUT_VALUE_OPTS = frozenset({"--conflict", "--pathspec-from-file"})
_RESTORE_VALUE_OPTS = frozenset({
    "-s", "--source", "--conflict", "--pathspec-from-file",
})
_CLEAN_VALUE_OPTS = frozenset({"-e", "--exclude", "--pathspec-from-file"})

# checkout options that mean "make or move a branch" rather than "restore a
# path". These are branch operations and belong to the category rule.
_CHECKOUT_BRANCH_OPTS = frozenset({
    "-b", "-B", "--orphan", "--detach", "--track", "-t", "--no-track",
    "--guess", "--no-guess",
})

# verb: the git subcommand. paths: the pathspecs it names. bounded: whether it
# named any (an unbounded `git clean -f` reaches the whole tree). ignored:
# whether ignored files are in scope (-x/-X). chdir: a `git -C <dir>` override.
GitWorktreeCmd = namedtuple("GitWorktreeCmd", "verb paths bounded ignored chdir")

# How many paths to name in a prompt before summarising the rest.
_REASON_PATH_LIMIT = 3


def _tokenize_segment(text):
    """Split one shell segment into tokens, quotes removed.

    shlex gets quoted paths with spaces right; an unbalanced quote makes it
    raise, and a whitespace split is a good enough fallback there.
    """
    try:
        return shlex.split(text, comments=False, posix=True)
    except ValueError:
        return text.split()


def _split_operands(args, value_opts):
    """Split *args* into (flags, before_dashdash, after_dashdash, saw_dashdash).

    Options in *value_opts* swallow their separate value so it is never
    mistaken for an operand. The `--` split is kept because it is the only
    unambiguous pathspec marker git offers.
    """
    flags, pre, post = [], [], []
    saw_dashdash = False
    i = 0
    while i < len(args):
        token = args[i]
        if saw_dashdash:
            post.append(token)
            i += 1
            continue
        if token == "--":
            saw_dashdash = True
            i += 1
            continue
        if token.startswith("-") and token != "-":
            flags.append(token)
            if token.split("=", 1)[0] in value_opts and "=" not in token:
                i += 2
            else:
                i += 1
            continue
        pre.append(token)
        i += 1
    return flags, pre, post, saw_dashdash


def _flag_names(flags):
    """Return the set of long-option names and the concatenated short letters.

    `-fd` and `--force -d` have to answer the same question, so short clusters
    are flattened into one string to test letters against.
    """
    names = {flag.split("=", 1)[0] for flag in flags}
    shorts = "".join(
        flag.lstrip("-") for flag in flags if not flag.startswith("--")
    )
    return names, shorts


def _path_exists_under(base_dir, path):
    """Return True if *path* names something on disk, resolved against base_dir.

    lexists, not exists: a dangling symlink is still a path the command names.
    """
    if not base_dir:
        return False
    candidate = path if os.path.isabs(path) else os.path.join(base_dir, path)
    return os.path.lexists(candidate)


def _parse_checkout(args, base_dir, chdir):
    """Classify a `git checkout` invocation, or None if it is a branch op."""
    flags, pre, post, saw_dashdash = _split_operands(args, _CHECKOUT_VALUE_OPTS)
    names, _ = _flag_names(flags)
    if names & _CHECKOUT_BRANCH_OPTS:
        return None
    if saw_dashdash:
        # Everything after `--` is a pathspec by definition. Anything before it
        # is a tree-ish, which changes what the worktree is overwritten WITH,
        # not whether it is overwritten.
        paths = post
    else:
        # `git checkout foo` is ambiguous: branch or path. Only claim it when
        # every operand names something on disk — a partial match means we are
        # guessing, and the category rule (which asks) is the safer reader.
        if not pre or not all(_path_exists_under(base_dir, p) for p in pre):
            return None
        paths = pre
    if not paths:
        return None
    return GitWorktreeCmd("checkout", paths, True, False, chdir)


def _parse_restore(args, chdir):
    """Classify a `git restore` invocation, or None if the worktree is safe."""
    flags, pre, post, saw_dashdash = _split_operands(args, _RESTORE_VALUE_OPTS)
    names, shorts = _flag_names(flags)
    staged = "--staged" in names or "S" in shorts
    worktree = "--worktree" in names or "W" in shorts
    if staged and not worktree:
        # Index-only: unstages, leaves the worktree untouched. Not a loss.
        return None
    paths = post if saw_dashdash else pre
    if not paths:
        # git restore refuses without a pathspec, so there is nothing to guard.
        return None
    return GitWorktreeCmd("restore", paths, True, False, chdir)


def _parse_clean(args, chdir):
    """Classify a `git clean` invocation, or None if it deletes nothing."""
    flags, pre, post, saw_dashdash = _split_operands(args, _CLEAN_VALUE_OPTS)
    names, shorts = _flag_names(flags)
    if "--dry-run" in names or "n" in shorts:
        return None
    if not ("--force" in names or "f" in shorts):
        # Without -f git refuses (clean.requireForce defaults to true).
        return None
    ignored = "x" in shorts or "X" in shorts
    paths = post if saw_dashdash else pre
    return GitWorktreeCmd("clean", paths, bool(paths), ignored, chdir)


def _parse_git_worktree_cmd(tokens, base_dir):
    """Return a GitWorktreeCmd for *tokens*, or None if it destroys nothing."""
    if not tokens or os.path.basename(tokens[0]) != "git":
        return None
    index, chdir = 1, None
    while index < len(tokens) and tokens[index].startswith("-"):
        option = tokens[index]
        name = option.split("=", 1)[0]
        if "=" in option or name not in _GIT_GLOBAL_VALUE_OPTS:
            index += 1
            continue
        if name == "-C" and index + 1 < len(tokens):
            chdir = tokens[index + 1]
        index += 2
    if index >= len(tokens):
        return None
    verb, args = tokens[index], tokens[index + 1:]
    if verb == "checkout":
        return _parse_checkout(args, base_dir, chdir)
    if verb == "restore":
        return _parse_restore(args, chdir)
    if verb == "clean":
        return _parse_clean(args, chdir)
    return None


def _run_git(root, args):
    """Run a git command in *root*. Returns stdout, or None if git would not answer."""
    try:
        result = subprocess.run(
            ["git", "-C", root] + args,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _git_knows_path(root, path):
    """Return True if *path* is on disk or tracked by the repo at *root*.

    The point is to catch our own misresolution. A pathspec that neither the
    filesystem nor the index recognises means the base directory we resolved it
    against is probably wrong — in which case a clean `git status` for it
    proves nothing, and the caller must ask rather than clear.
    """
    if _path_exists_under(root, path):
        return True
    return _run_git(root, ["ls-files", "--error-unmatch", "--", path]) is not None


def _git_pending(root, cmd):
    """Return the porcelain lines *cmd* would destroy, or None if unknown."""
    args = ["status", "--porcelain"]
    # Untracked files are what clean deletes and what a restore cannot touch.
    args.append("--untracked-files=" + ("all" if cmd.verb == "clean" else "no"))
    if cmd.ignored:
        args.append("--ignored=matching")
    if cmd.paths:
        args.append("--")
        args.extend(cmd.paths)
    output = _run_git(root, args)
    if output is None:
        return None
    lines = [line for line in output.splitlines() if line.strip()]
    if cmd.verb == "clean":
        return [line for line in lines if line[:2] in ("??", "!!")]
    return [line for line in lines if line[:2] not in ("??", "!!")]


def _porcelain_paths(lines):
    """Extract the path from each porcelain line, rename arrows resolved."""
    paths = []
    for line in lines:
        path = line[3:] if len(line) > 3 else line
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path.strip().strip('"'))
    return paths


def _worktree_reason(cmd, lines):
    """Build the prompt text naming what this command would destroy.

    The paths are the point of the prompt, so they lead. A count only appears
    when there is more than one, and the list is truncated so a wide sweep
    stays readable.
    """
    paths = _porcelain_paths(lines)
    shown = ", ".join(paths[:_REASON_PATH_LIMIT])
    if len(paths) > _REASON_PATH_LIMIT:
        shown += f", +{len(paths) - _REASON_PATH_LIMIT} more"
    if len(paths) > 1:
        shown = f"{len(paths)} paths ({shown})"
    verb = "deletes untracked" if cmd.verb == "clean" else "discards uncommitted changes in"
    scope = "" if cmd.bounded else ", across the whole tree"
    return f"git {cmd.verb} {verb} {shown}{scope} — not recoverable from git"


def _judge_worktree_cmd(cmd, base_dir):
    """Return ("ask", reason) or ("clear", None) for one parsed git command."""
    root = base_dir
    if cmd.chdir:
        root = cmd.chdir if os.path.isabs(cmd.chdir) else os.path.join(base_dir or "", cmd.chdir)
    if not root or not os.path.isdir(root):
        return ("ask", f"git {cmd.verb} destroys uncommitted work and the "
                       "directory it would run in could not be resolved")
    if cmd.bounded:
        unknown = [p for p in cmd.paths if not _git_knows_path(root, p)]
        if unknown:
            return ("ask", f"git {cmd.verb} targets a path this guard could not "
                           f"resolve, so what it would destroy is unknown: "
                           f"{', '.join(unknown[:_REASON_PATH_LIMIT])}")
    lines = _git_pending(root, cmd)
    if lines is None:
        return ("ask", f"git {cmd.verb} destroys uncommitted work and git would "
                       "not report what is pending")
    if not lines:
        return ("clear", None)
    return ("ask", _worktree_reason(cmd, lines))


def _resolve_cd(base_dir, target):
    """Return the directory a `cd <target>` lands in, or None if unknowable."""
    if target.startswith("-"):
        return None  # `cd -` needs shell history this hook does not have
    if os.path.isabs(target):
        return target
    if not base_dir:
        return None
    return os.path.normpath(os.path.join(base_dir, target))


def check_worktree_destruction(command, base_dir):
    """Check whether *command* would destroy unrecoverable worktree content.

    Returns ("ask", reason), ("clear", None), or None when no segment invokes a
    worktree-destroying git command. "clear" means a restore was recognised and
    git reports nothing pending for its paths — the caller uses it to suppress
    the broad checkout category rule, which would otherwise ask about a no-op.

    Segments are read off the quote-masked copy so a quoted `;` does not split
    the command, and sliced from the original so pathspecs keep their real
    text. A `cd` in an earlier segment moves the base directory, because that
    is where the git command will actually run.
    """
    command = _strip_heredocs(command)
    masked = command if _SHELL_INVOKER_RE.search(command) else _mask_quoted(command)
    cwd = base_dir
    cleared = False
    for segment in _SEGMENT_RE.finditer(masked):
        text = command[segment.start():segment.end()]
        tokens = _tokenize_segment(_REDIRECT_STRIP_RE.sub(" ", text))
        if not tokens:
            continue
        if os.path.basename(tokens[0]) == "cd" and len(tokens) > 1:
            cwd = _resolve_cd(cwd, tokens[1])
            continue
        parsed = _parse_git_worktree_cmd(tokens, cwd)
        if not parsed:
            continue
        decision, reason = _judge_worktree_cmd(parsed, cwd)
        if decision == "ask":
            # First loss wins: the prompt names the command that would destroy
            # work, and the user is deciding about the whole compound anyway.
            return ("ask", reason)
        cleared = True
    return ("clear", None) if cleared else None


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


def check_command(command, skip_descriptions=()):
    """Check command against category rules.

    Quoted text is data, not syntax: a grep whose search pattern contains
    "rm -rf" is not a recursive rm. Every rule in CATEGORIES matches a command
    verb together with its flags or subcommand, never a bare operand, so a
    quoted span can never carry the part a rule needs to match — masking it
    costs the rules nothing and retires a whole class of false positive.
    Nested shell invocations are the exception, since there the quoted string
    IS the command; same trade as check_write_targets and
    check_exit_code_masking.

    The one rule that does read an operand is _ENV_RULES' `> ….env` redirect;
    see the note there before enabling ENV_PROTECTION.

    *skip_descriptions* drops rules a more precise stage has already judged —
    only check_worktree_destruction uses it, to keep the broad checkout rule
    from asking about a restore it has proved is a no-op.

    Returns (description, category, matched_text) or None.
    """
    command = _strip_heredocs(command)
    # Masking is length-preserving, so a match found in the masked copy slices
    # the real text out of the original for reporting.
    scanned = command if _SHELL_INVOKER_RE.search(command) else _mask_quoted(command)
    for compiled_re, description, category in RULES:
        if description in skip_descriptions:
            continue
        match = compiled_re.search(scanned)
        if match:
            return (description, category, command[match.start():match.end()])
    return None


def check_file_path(file_path):
    """Check if a file path matches sensitive file patterns.

    Returns (description,) or None.
    """
    for compiled_re, description in SENSITIVE_FILE_PATTERNS:
        if compiled_re.search(file_path):
            return (description,)
    return None


# ── Pattern-position exemption ──────────────────────────────────────────────
# This guard strips quotes rather than masking them, so that a quoted path
# (`cat "~/.ssh/id_rsa"`) is still caught. The cost is that a search tool's
# pattern reads as a path: `grep id_rsa src/` searches FOR the name, it does
# not read the key. The discriminator is argument position, not quoting —
# quoting cannot tell a pattern from a path, but position can, and it lands the
# right way round either way: in `grep pattern ~/.ssh/id_rsa` the key is an
# operand and stays guarded, while in `grep ~/.ssh/id_rsa file` the key-shaped
# string really is just the text being searched for.

# Tools whose first non-flag argument is a pattern or script, not a path.
_PATTERN_ARG_TOOLS = re.compile(r"^(?:grep|egrep|fgrep|rg|ag|ack|sed|awk|jq)$")

# Tools whose arguments are all literal data and never paths.
_DATA_ARG_TOOLS = re.compile(r"^(?:echo|printf)$")

# -e/--regexp supplies the pattern itself, so the pattern position moves to
# that flag's value and no positional argument is exempt.
_PATTERN_FLAG_RE = re.compile(r"^(?:-e|--regexp)(?:=|$)")

# -f/--file reads the patterns from a FILE, so that argument is a real path and
# nothing in the segment is exempt.
_PATTERN_FILE_FLAG_RE = re.compile(r"^(?:-f|--file)(?:=|$)")

# Flags whose value is a separate following token, which would otherwise be
# mistaken for the pattern position (`grep -A 5 id_rsa f`). Enumerated rather
# than inferred: guessing "a number is not a pattern" would silently exempt a
# real path in `grep 5 ~/.ssh/id_rsa`.
_VALUE_FLAG_RE = re.compile(
    r"^(?:-[ABCm]|--(?:after-context|before-context|context|max-count))$"
)

# A leading `FOO=1 grep …` assignment belongs to the command that follows it.
_ASSIGN_TOKEN_RE = re.compile(r"^\w+=\S*$")


def _exempt_token_spans(segment, offset):
    """Yield (start, end) spans of tokens in *segment* that hold pattern or
    script data rather than a path.

    Spans are absolute offsets into the command *segment* was sliced from.
    Whole tokens are yielded: a glued `--regexp=~/.ssh/id_rsa` is a pattern in
    its entirety.
    """
    tokens = [(offset + m.start(), offset + m.end(), m.group())
              for m in _TOKEN_RE.finditer(segment)]

    index = 0
    while index < len(tokens) and _ASSIGN_TOKEN_RE.match(tokens[index][2]):
        index += 1
    if index >= len(tokens):
        return

    command_word = os.path.basename(tokens[index][2])
    rest = tokens[index + 1:]

    if _DATA_ARG_TOOLS.match(command_word):
        for start, end, _ in rest:
            yield (start, end)
        return

    if not _PATTERN_ARG_TOOLS.match(command_word):
        return

    # Patterns read from a file: the argument is a path, exempt nothing.
    if any(_PATTERN_FILE_FLAG_RE.match(text) for _, _, text in rest):
        return

    flagged = False
    for position, (start, end, text) in enumerate(rest):
        if not _PATTERN_FLAG_RE.match(text):
            continue
        flagged = True
        if "=" in text:
            yield (start, end)
        elif position + 1 < len(rest):
            yield (rest[position + 1][0], rest[position + 1][1])
    if flagged:
        return

    # No pattern flag, so the first argument that is neither a flag nor a
    # flag's separate value is the pattern.
    position = 0
    while position < len(rest):
        text = rest[position][2]
        if _VALUE_FLAG_RE.match(text):
            position += 2
            continue
        if text.startswith("-") and text != "-":
            position += 1
            continue
        yield (rest[position][0], rest[position][1])
        return


def check_sensitive_in_command(command):
    """Check if a Bash command references sensitive file paths.

    Tokenises the command on whitespace and shell operators, strips quotes
    and shell punctuation, and tests each token against SENSITIVE_FILE_PATTERNS.
    Tokens holding a search pattern or script rather than a path are skipped
    (see _exempt_token_spans); every other token stays guarded.

    Returns (description, matched_path) or None.
    """
    command = _strip_heredocs(command)
    # Segment and token boundaries are read off the masked copy so a quoted `;`
    # or a space inside a pattern does not split, but each token is sliced from
    # the original. Nested shell invocations are scanned raw — there the quoted
    # string is itself a command, and its leading word is `bash`, so no
    # exemption applies and every token is checked.
    scanned = command if _SHELL_INVOKER_RE.search(command) else _mask_quoted(command)

    for segment in _SEGMENT_RE.finditer(scanned):
        exempt = set(_exempt_token_spans(segment.group(), segment.start()))
        for match in _TOKEN_RE.finditer(segment.group()):
            span = (segment.start() + match.start(), segment.start() + match.end())
            if span in exempt:
                continue
            token = command[span[0]:span[1]].strip(_TOKEN_STRIP_CHARS)
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

    # ── Git worktree destruction ────────────────────────────────────────
    # Ahead of the auto-approve window, and for the same reason the pause latch
    # and the usage gate are: the window exists to skip ROUTINE approvals for
    # the duration of a known command, and an unrecoverable loss of uncommitted
    # work is not routine. Everything else in this guard interrupts something
    # that can be retried; this one cannot. The window still covers the common
    # case, because a restore over a clean path clears here and never prompts.
    skip_rules = ()
    if tool_name == "Bash" and tool_input.get("command"):
        verdict = check_worktree_destruction(
            tool_input["command"], _resolve_project_root(event)
        )
        if verdict and verdict[0] == "ask":
            _ask(f"[permission-guard] Git Worktree Destruction: {verdict[1]}")
            return
        if verdict:
            skip_rules = (GIT_CHECKOUT_RULE,)

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
    result = check_command(command, skip_rules)
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
