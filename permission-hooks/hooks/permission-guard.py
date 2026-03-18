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
import sys

PROJECT_ROOT = "{PROJECT_ROOT}"

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
        (r"\bgh\s+api\b", "GitHub API call"),
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
        (r"\brm\s+.*-\w*[rR]", "recursive rm"),
        (r"\b(chmod|chown)\b", "permission/ownership change"),
        (r"(?:^|[;&|]\s*)ln\s+(?!=)(?:-|\S+\s)", "symlink creation"),
        (r"\b(mkfs|mount|umount)\b", "disk operations"),
        (r"\bdd\s", "raw disk operations"),
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
WRITE_REDIRECT = re.compile(r">{1,2}")

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


# Paths where recursive rm is considered safe (temp/test cleanup)
SAFE_RM_PATH_PREFIXES = ("temp/", "./temp/", "/tmp/")


def _is_safe_rm(command):
    """Return True if command is a simple rm targeting only temp directories."""
    # Reject compound commands — they need full checking
    if re.search(r'[;&|]', command):
        return False
    if not re.match(r'^\s*rm\s', command):
        return False
    tokens = command.split()
    paths = [t.strip("'\"") for t in tokens[1:] if not t.startswith('-')]
    if not paths:
        return False
    return all(
        any(p.startswith(prefix) for prefix in SAFE_RM_PATH_PREFIXES)
        for p in paths
    )

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

    # Expand ~ to detect home directory paths
    if file_path.startswith("~/") or file_path == "~":
        return f"home directory path: {file_path}"

    # Parent traversal — resolve to absolute and check against project root
    if "../" in file_path:
        resolved = os.path.realpath(file_path)
        if resolved.startswith(project_root + "/") or resolved == project_root:
            return None  # resolves inside the project
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

        # Check home directory paths
        if token.startswith("~/"):
            return (
                f"home directory path: {token}",
                token,
            )

        # Check parent traversal — resolve and allow if inside project
        if "../" in token:
            resolved = os.path.realpath(token)
            if resolved.startswith(project_root + "/") or resolved == project_root:
                continue  # resolves inside the project
            return (
                f"parent directory traversal: {token}",
                token,
            )

    return None


def _ask(reason):
    """Print a permissionDecision: ask response and exit."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(output))


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})

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
            root = PROJECT_ROOT or event.get("cwd", "")
            if root:
                desc = check_file_outside_project(file_path, root)
                if desc:
                    _ask(f"[permission-guard] Out-of-project: {desc}")
                    return
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

    # 1. Category rules
    result = check_command(command)
    if result:
        description, category, _matched = result
        _ask(f"[permission-guard] {category}: {description}")
        return

    # 2. Sensitive file paths in command arguments
    result = check_sensitive_in_command(command)
    if result:
        description, matched_path = result
        _ask(f"[permission-guard] Secrets & Credentials: {description} ({matched_path})")
        return

    # 3. Out-of-project path guard
    root = PROJECT_ROOT or event.get("cwd", "")
    if root:
        result = check_outside_project(command, root)
        if result:
            description, _matched_path = result
            _ask(f"[permission-guard] Out-of-project: {description}")
            return


if __name__ == "__main__":
    main()
