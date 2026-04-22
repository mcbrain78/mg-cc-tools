#!/usr/bin/env python3
"""PreToolUse hook that guards against dangerous operations.

For Bash: checks commands against 8 categories of dangerous patterns plus
an out-of-project path guard.

For Read/Edit/Write: checks file paths against sensitive file patterns.

Returns permissionDecision: "ask" for any match so the user gets an
approval prompt.

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

PROJECT_ROOT = "{MG_INSTALL_PROJECT_ROOT}"

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
        (r"\bgit\s+config\s+(?!--get\b|--list\b|-l\b|--)", "git config write"),
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
        (r"(?:^|[;&|]\s*)ln\s+(?!=)(?:-|\S+\s)", "symlink creation"),
        (r"\b(mkfs|mount|umount)\b", "disk operations"),
        (r"(?:^|[;&|]\s*)dd\s", "raw disk operations"),
    ],
    "Secrets & Credentials": [
        (r">\s*\S*\.env\b", "writing .env file"),
        (r"\bexport\s+\w*(TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL|API_KEY)=", "credential export"),
        (r"\b(curl|wget)\s+.*(-X\s*(POST|PUT|PATCH|DELETE)|-d\s|--data)", "HTTP data submission"),
        (r"\b(curl|wget)\s+.*\|\s*(bash|sh|zsh)\b", "pipe-to-shell"),
        (r"\bprintenv\b", "environment dump"),
        (r"\benv\s*($|[|;>])", "environment dump"),
    ],
    "System Operations": [
        (r"\bsudo\b", "sudo"),
        (r"\b(apt|apt-get|brew|yum|dnf|pacman|apk)\s+(install|remove|purge|uninstall)\b", "package manager"),
        (r"\bcrontab\s+(?!-l\b)", "crontab modification"),
        (r"\bsystemctl\s+(?!status\b)", "systemctl (not status)"),
        (r"\b(launchctl|service)\b", "service manager"),
        (r"\b(useradd|userdel|usermod|passwd)\b", "user management"),
        (r"\b(iptables|ufw)\b", "firewall management"),
        (r"\b(kill|killall)\b", "process termination"),
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
        session_dir = os.path.join("/tmp/claude-code", f"mg-session-{session}")
        os.makedirs(session_dir, exist_ok=True)
        path = os.path.join(session_dir, "context.json")
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
        path = os.path.join("/tmp/claude-code", f"mg-session-{session}", "context.json")
        with open(path) as f:
            data = json.load(f)
        data["timestamp_ms"] = int(time.time() * 1000)
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def _emitter_follows_command(transcript_path):
    """Return True if a /mg: slash command was loaded in the recent transcript tail.

    When a user invokes a /mg: command, Claude Code injects a
    ``<command-name>/mg:...`` tag into the transcript. The emit-context.py
    call happens some entries later — typically after the command body,
    referenced attachments, last-prompt marker, and any assistant thinking.
    With attachments, that gap can be 20–40 lines, so we scan a wide tail
    (``_RECENT_LINES``) to still catch the tag while excluding ancient
    invocations.

    Note: CC strips YAML frontmatter (including ``allowed-tools:``) before
    writing command content to the transcript, so we match on the
    ``<command-name>`` tag instead.
    """
    if not transcript_path:
        return False
    try:
        with open(transcript_path) as f:
            lines = f.read().splitlines()
    except (OSError, IOError):
        return False

    tail = "\n".join(lines[-_RECENT_LINES:]) if lines else ""
    return "<command-name>/mg:" in tail


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
    path = os.path.join("/tmp/claude-code", f"mg-session-{session}", "context.json")
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
        session_dir = os.path.join("/tmp/claude-code", f"mg-session-{session}")
        os.makedirs(session_dir, exist_ok=True)
        bridge_path = os.path.join(session_dir, "edit-guard.json")
        with open(bridge_path, "w") as f:
            json.dump({"state": state, "ts": int(time.time())}, f)
    except Exception:
        pass


# Claude's internal directory (memory, settings, etc.) — always allowed
_CLAUDE_DIR_TILDE = "~/.claude/"
_CLAUDE_DIR_ABS = os.path.expanduser("~/.claude/")


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
WRITE_REDIRECT = re.compile(r"(?<!\d)>{1,2}")

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
    (re.compile(r"(^|/)\.env(?!\.example|\.template|\.sample|\.test)(\b|$)"), ".env file"),
    (re.compile(r"(^|/)(\.netrc|\.npmrc|\.pypirc)$"), "credential file"),
    (re.compile(r"(^|/)id_(rsa|ed25519|ecdsa|dsa)(\.pub)?$"), "SSH key"),
    (re.compile(r"(^|/)credentials(\.json)?$"), "credentials file"),
    (re.compile(r"(^|/)\.git-credentials$"), "git credentials"),
    (re.compile(r"(^|/)\.pgpass$"), "PostgreSQL password file"),
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


def check_file_outside_project(file_path, project_root):
    """Check if a file path is outside the project root.

    Returns a description string or None.
    """
    if not project_root:
        return None

    project_root = project_root.rstrip("/")

    # Claude's own internal files (memory, settings) are always allowed
    if _is_claude_internal(file_path):
        return None

    # Expand ~ and check whether it resolves inside the project
    if file_path.startswith("~/") or file_path == "~":
        resolved = os.path.expanduser(file_path)
        if resolved.startswith(project_root + "/") or resolved == project_root:
            return None  # resolves inside the project
        return f"home directory path: {file_path}"

    # Parent traversal — resolve to absolute and check against project root
    if "../" in file_path:
        resolved = os.path.realpath(file_path)
        if resolved.startswith(project_root + "/") or resolved == project_root:
            return None  # resolves inside the project
        # Allow sibling projects in the same workspace directory
        workspace = os.path.dirname(project_root)
        if workspace and resolved.startswith(workspace + "/"):
            return None
        return f"parent directory traversal: {file_path}"

    # Absolute paths not under project root
    if file_path.startswith("/"):
        # Allow safe paths
        if any(file_path == safe or file_path.startswith(safe + "/")
               for safe in SAFE_ABSOLUTE_PATHS):
            return None
        # Allow sibling projects in the same workspace directory
        workspace = os.path.dirname(project_root)
        if workspace and file_path.startswith(workspace + "/"):
            return None
        if not file_path.startswith(project_root + "/") and file_path != project_root:
            return f"path outside project root: {file_path}"

    return None


def check_outside_project(command, project_root):
    """Check if command targets paths outside the project root.

    Returns (description, matched_path) or None.
    """
    if not project_root:
        return None

    # Strip heredoc bodies so their content isn't parsed as paths
    command = _strip_heredocs(command)

    # Normalize project root (remove trailing slash)
    project_root = project_root.rstrip("/")

    has_file_cmd = FILE_MODIFYING_CMDS.search(command)
    has_redirect = WRITE_REDIRECT.search(command)

    if not has_file_cmd and not has_redirect:
        return None

    # Extract potential paths from the command
    # Split on whitespace and common shell operators
    tokens = re.split(r'[\s;|&]+', command)

    for token in tokens:
        # Strip quotes and shell punctuation
        token = token.strip(_TOKEN_STRIP_CHARS)
        if not token:
            continue

        # Claude's own internal files (memory, settings) are always allowed
        if _is_claude_internal(token):
            continue

        # Check absolute paths not under project root
        if token.startswith("/"):
            # Skip bare slash tokens (e.g. Python's // operator)
            if token.rstrip("/") == "":
                continue
            # Allow safe paths
            if any(token == safe or token.startswith(safe + "/")
                   for safe in SAFE_ABSOLUTE_PATHS):
                continue
            # Allow sibling projects in the same workspace directory
            workspace = os.path.dirname(project_root)
            if workspace and token.startswith(workspace + "/"):
                continue
            # Block if not under project root
            if not token.startswith(project_root + "/") and token != project_root:
                return (
                    f"path outside project root: {token}",
                    token,
                )

        # Check home directory paths — resolve first to allow in-project tilde paths
        if token.startswith("~/"):
            resolved = os.path.expanduser(token)
            if resolved.startswith(project_root + "/") or resolved == project_root:
                continue  # resolves inside the project
            return (
                f"home directory path: {token}",
                token,
            )

        # Check parent traversal — resolve and allow if inside project
        if "../" in token:
            resolved = os.path.realpath(token)
            if resolved.startswith(project_root + "/") or resolved == project_root:
                continue  # resolves inside the project
            # Allow sibling projects in the same workspace directory
            workspace = os.path.dirname(project_root)
            if workspace and resolved.startswith(workspace + "/"):
                continue
            return (
                f"parent directory traversal: {token}",
                token,
            )

    return None


# ── Exit code masking detection ─────────────────────────────────────────────
# Piping pytest output to tail/head/grep etc. masks the exit code.
_PYTEST_PIPE_RE = re.compile(r"\bpytest\b.*\|")


def check_exit_code_masking(command):
    """Check if command pipes pytest output, masking exit codes.

    Returns a reason string or None.
    """
    command = _strip_heredocs(command)
    if _PYTEST_PIPE_RE.search(command):
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
    """Call the claude CLI with Haiku model. Returns response text or None."""
    claude_bin = _find_claude_cli()
    if not claude_bin:
        return None
    try:
        result = subprocess.run(
            [claude_bin, "-p", "--model", HAIKU_MODEL, "--output-format", "json"],
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
    """Return the resolved project root, or empty string if unavailable."""
    root = PROJECT_ROOT
    # Skip unresolved install-time placeholder
    if not root or root.startswith("{"):
        root = event.get("cwd", "")
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


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    # Best-effort: write edit guard state for statusline badge
    _write_edit_guard_bridge(event)

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
