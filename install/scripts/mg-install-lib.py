#!/usr/bin/env python3
"""mg-install-lib.py -- unified installer library for mg-cc-tools.

Provides 5 subcommands for tool management:
  scan-status      Discover tools, compute checksums, compare with manifest
  update-manifest  Update manifest entry for one tool after install
  preflight        Run preflight checks for given tools
  validate         Validate installed files for placeholder and path issues
  adopt            Detect and adopt pre-manifest installations

Context-efficient: scan-status, validate, and adopt support --output to write
full details to a file while returning only a compact summary to stdout.
This prevents large JSON blobs from accumulating in LLM conversation context.

Zero pip dependencies -- all stdlib.
"""

import argparse
import datetime
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any

try:
    import tomllib
except ImportError:
    # Python < 3.11 fallback (should not happen in practice)
    raise SystemExit("Python 3.11+ required for tomllib support")

from pathlib import Path

# ============================================================
# Constants
# ============================================================

MANIFEST_FILENAME = "mg-cc-tools.manifest.json"

CHECKSUM_INCLUDE_EXTENSIONS = {".md", ".py", ".sh"}

CHECKSUM_EXCLUDE_PATTERNS = [
    "tests/",
    "__pycache__",
    ".pyc",
    ".pytest_cache",
    "tool.toml",
]

# Workspace directories that certain tools scaffold during --project install
WORKSPACE_DIRS = {
    "codebase-health": ".mg/health-scan",
    "auto-doc": ".mg/docs",
    "data-provider": ".mg/data-provider",
}

# Install-time placeholder detection: only {MG_INSTALL_*} placeholders are
# install-time artifacts. All other {UPPERCASE} patterns (e.g. {DOCUMENT},
# {STAGE_LABEL}, {DISK_PCT}) are runtime/template variables and are ignored.
INSTALL_PLACEHOLDER_RE = re.compile(r"\{MG_INSTALL_[A-Z_]+\}")

# Unresolved relative references: install.sh should resolve references/foo.md
# to absolute paths. Any remaining relative reference is a missed resolution.
RELATIVE_REF_RE = re.compile(r"(?<!/)\breferences/[a-zA-Z0-9._-]+\.\w+")

# install.sh sed target validation: extract sed replacement targets and check
# that placeholder targets use the MG_INSTALL_ prefix.
SED_TARGET_RE = re.compile(r'sed\s+-i\s+"s\|([^|]+)\|')
BARE_INSTALL_PLACEHOLDER_RE = re.compile(r"^\{[A-Z][A-Z_]+\}$")

# ============================================================
# Display fence (render output wrapping)
# ============================================================
#
# render-* subcommands emit user-facing output that the LLM must echo back
# in its response text. The fence markers identify the block for echoing.
# Configured via install/display.toml; falls back to "codeblock" if the file
# is missing or malformed. See install/display.toml for supported values.

_DISPLAY_CONFIG_PATH = Path(__file__).resolve().parent.parent / "display.toml"

try:
    with open(_DISPLAY_CONFIG_PATH, "rb") as _f:
        DISPLAY_FENCE = tomllib.load(_f).get("fence", "codeblock")
except (FileNotFoundError, tomllib.TOMLDecodeError):
    DISPLAY_FENCE = "codeblock"


def emit_display_open():
    """Print the opening fence marker for the configured display fence."""
    if DISPLAY_FENCE == "codeblock":
        print("```")
    elif DISPLAY_FENCE == "verbatim":
        print("<verbatim>")
    else:
        raise SystemExit(f"unsupported DISPLAY_FENCE: {DISPLAY_FENCE!r} (expected 'codeblock' or 'verbatim')")


def emit_display_close():
    """Print the closing fence marker for the configured display fence."""
    if DISPLAY_FENCE == "codeblock":
        print("```")
    elif DISPLAY_FENCE == "verbatim":
        print("</verbatim>")
    else:
        raise SystemExit(f"unsupported DISPLAY_FENCE: {DISPLAY_FENCE!r} (expected 'codeblock' or 'verbatim')")


# ============================================================
# Preflight checks registry
# ============================================================

CHECKS = {
    "python3": {
        "type": "venv_python",
        "parse_version": r"Python\s+(\d+\.\d+\.\d+)",
        "fix": {
            "general": "Create a .venv in the project: python3 -m venv .venv && .venv/bin/pip install <deps>",
        },
    },
    "git": {
        "type": "command",
        "command": "git --version",
        "parse_version": r"git version\s+(\d+\.\d+\.\d+)",
        "fix": {
            "linux": "sudo apt install git",
            "macos": "brew install git",
            "general": "Install Git from https://git-scm.com",
        },
    },
    "gsd": {
        "type": "path_exists",
        "path": "{target}/.claude/get-shit-done",
        "fix": {
            "general": "Install Get Shit Done: see https://github.com/gsd-build/get-shit-done",
        },
    },
    "lsp": {
        "type": "settings_scan",
        "fix": {
            "general": "Enable an LSP plugin in Claude Code settings (e.g., pyright-lsp)",
        },
    },
    "serena": {
        "type": "plugin_scan",
        "plugin_name": "serena",
        "fix": {
            "general": "Install Serena MCP server: see https://github.com/oraios/serena",
        },
    },
    "ruff": {
        "type": "command",
        "command": "ruff --version",
        "parse_version": r"ruff\s+(\d+\.\d+\.\d+)",
        "fix": {
            "general": "pip install ruff",
        },
    },
    "vulture": {
        "type": "command",
        "command": "vulture --version",
        "parse_version": r"vulture\s+(\d+\.\d+)",
        "fix": {
            "general": "pip install vulture",
        },
    },
    "pyright": {
        "type": "command",
        "command": "pyright --version",
        "parse_version": r"pyright\s+(\d+\.\d+\.\d+)",
        "fix": {
            "general": "pip install pyright  OR  npm install -g pyright",
        },
    },
    "jscpd": {
        "type": "command",
        "command": "jscpd --version",
        "parse_version": r"(\d+\.\d+\.\d+)",
        "fix": {
            "general": "npm install -g jscpd",
        },
    },
    "tiktoken": {
        "type": "python_import",
        "module": "tiktoken",
        "fix": {
            "general": "Install in project venv: .venv/bin/pip install tiktoken",
        },
    },
}


# ============================================================
# Helpers
# ============================================================


def _get_temp_dir(target_path):
    """Get per-target temp directory for inter-step files.

    Derives basename from target path (e.g. "/home/user/projects/road-runner"
    -> "road-runner"), returns /tmp/mg-install-{basename}/ (or tempfile.gettempdir()
    equivalent). Creates the directory if it does not exist.
    """
    basename = os.path.basename(os.path.normpath(target_path))
    temp_dir = os.path.join(tempfile.gettempdir(), f"mg-install-{basename}")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def read_pyproject_version(source_dir):
    """Read version from pyproject.toml in source_dir."""
    pyproject_path = os.path.join(source_dir, "pyproject.toml")
    if not os.path.isfile(pyproject_path):
        return "0.0.0"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    return data.get("project", {}).get("version", "0.0.0")


def read_tool_toml(tool_dir):
    """Read and parse tool.toml from a tool directory.

    Returns dict with keys: description, exclude, standard, required, optional,
    post_install_script, detect_paths.
    """
    toml_path = os.path.join(tool_dir, "tool.toml")
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    # Validate keys to catch typos (e.g., "file" instead of "script")
    _EXPECTED_KEYS = {
        "tool": {"description", "exclude", "standard"},
        "preflight": {"required", "optional"},
        "post_install": {"script"},
        "detect": {"paths"},
        "external": {"repo", "path", "archive"},
    }
    for section_name, expected in _EXPECTED_KEYS.items():
        actual = set(data.get(section_name, {}).keys())
        unexpected = actual - expected
        if unexpected:
            raise ValueError(
                f"{toml_path} [{section_name}]: unknown keys {unexpected}"
            )

    tool_section = data.get("tool", {})
    preflight_section = data.get("preflight", {})
    post_install_section = data.get("post_install", {})
    detect_section = data.get("detect", {})
    external_section = data.get("external", {})

    return {
        "description": tool_section.get("description", ""),
        "exclude": tool_section.get("exclude", False),
        "standard": tool_section.get("standard", True),
        "required": preflight_section.get("required", []),
        "optional": preflight_section.get("optional", []),
        "post_install_script": post_install_section.get("script"),
        "detect_paths": detect_section.get("paths", []),
        "external": bool(external_section),
    }


def discover_tools(source_dir):
    """Discover tools by scanning for tool.toml.

    Returns list of (tool_name, tool_dir) tuples, sorted by name.
    Install pattern derived from which files exist alongside tool.toml.
    """
    tools = []
    if not os.path.isdir(source_dir):
        return tools

    for entry in sorted(os.listdir(source_dir)):
        tool_dir = os.path.join(source_dir, entry)
        if not os.path.isdir(tool_dir):
            continue
        toml_path = os.path.join(tool_dir, "tool.toml")
        if os.path.isfile(toml_path):
            tools.append((entry, tool_dir))

    return tools


def sha256_file(filepath):
    """Compute SHA256 hex digest of a file with sha256: prefix."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _is_excluded(rel_path):
    """Check if a relative path should be excluded from checksums."""
    for pattern in CHECKSUM_EXCLUDE_PATTERNS:
        if pattern in rel_path:
            return True
    if rel_path == "tool.toml":
        return True
    return False


def compute_tool_checksums(tool_dir):
    """Compute SHA256 checksums for all .md, .py, .sh files in tool_dir.

    Walks all subdirectories. Excludes tests/, __pycache__/, .pyc, .pytest_cache/, tool.toml.
    """
    checksums = {}
    tool_path = Path(tool_dir)

    for path in sorted(tool_path.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in CHECKSUM_INCLUDE_EXTENSIONS:
            continue
        rel = str(path.relative_to(tool_path))
        if _is_excluded(rel):
            continue
        checksums[rel] = sha256_file(str(path))

    return checksums


def get_tool_commands(tool_dir):
    """Get list of .md command filenames for a tool."""
    commands_dir = os.path.join(tool_dir, "commands")
    if not os.path.isdir(commands_dir):
        return []
    return sorted(
        f for f in os.listdir(commands_dir)
        if f.endswith(".md")
    )


def read_manifest(target_dir):
    """Read manifest from target, returns None if not found."""
    manifest_path = os.path.join(
        target_dir, ".claude", MANIFEST_FILENAME
    )
    if not os.path.isfile(manifest_path):
        return None
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_manifest_atomic(manifest_path, data):
    """Write manifest atomically with file locking."""
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    lock_path = manifest_path + ".lock"

    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(manifest_path),
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(data, f, indent=2)
                    f.write("\n")
                os.replace(tmp_path, manifest_path)
            except BaseException:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)

    # Clean up lock file (best effort)
    try:
        os.unlink(lock_path)
    except OSError:
        pass


# ============================================================
# Subcommand: scan-status
# ============================================================


def scan_status(source_dir, target_dir):
    """Discover tools, compute checksums, compare with manifest."""
    version = read_pyproject_version(source_dir)
    manifest = read_manifest(target_dir)
    manifest_tools = manifest.get("tools", {}) if manifest else {}

    tools_result = []
    summary = {
        "total": 0,
        "installed_total": 0,
        "current": 0,
        "update": 0,
        "modified": 0,
        "corrupt": 0,
        "adopted": 0,
        "available": 0,
    }

    for tool_name, tool_dir in discover_tools(source_dir):
        toml_data = read_tool_toml(tool_dir)
        commands = get_tool_commands(tool_dir)
        current_checksums = compute_tool_checksums(tool_dir)

        manifest_entry = manifest_tools.get(tool_name)

        if manifest_entry is None:
            status = "available"
            installed_version = None
            changed_files = []
        else:
            installed_version = manifest_entry.get("version")
            manifest_commands = manifest_entry.get("commands", [])

            # Check if command files exist in target
            cmd_dir = os.path.join(target_dir, ".claude", "commands", "mg")
            commands_present = all(
                os.path.isfile(os.path.join(cmd_dir, cmd))
                for cmd in manifest_commands
            ) if manifest_commands else True

            if manifest_entry.get("adopted"):
                status = "adopted"
                changed_files = []
            elif not commands_present:
                status = "corrupt"
                changed_files = []
            elif installed_version != version:
                status = "update"
                changed_files = []
            else:
                # Compare checksums
                stored_checksums = manifest_entry.get("source_checksums", {})
                changed_files = []
                for key, val in current_checksums.items():
                    stored_val = stored_checksums.get(key)
                    if stored_val != val:
                        changed_files.append(key)
                # Also check for files that were removed
                for key in stored_checksums:
                    if key not in current_checksums:
                        changed_files.append(key)

                status = "modified" if changed_files else "current"

        # Resolve standard flag: manifest overrides > tool.toml default
        effective_standard = toml_data["standard"]
        if manifest:
            overrides = manifest.get("standard_overrides", {})
            if tool_name in overrides:
                effective_standard = overrides[tool_name]

        tool_info = {
            "name": tool_name,
            "description": toml_data["description"],
            "status": status,
            "installed_version": installed_version,
            "current_version": version,
            "changed_files": changed_files,
            "commands": commands,
            "excluded": toml_data["exclude"],
            "standard": effective_standard,
            "has_install_sh": os.path.isfile(
                os.path.join(tool_dir, "install.sh")
            ),
            "post_install": toml_data.get("post_install_script"),
            "external": toml_data.get("external", False),
        }
        tools_result.append(tool_info)

        summary["total"] += 1
        summary[status] += 1
        if status in ("current", "update", "modified", "corrupt", "adopted"):
            summary["installed_total"] += 1

    return {
        "mg_cc_tools_version": version,
        "target": os.path.abspath(target_dir),
        "manifest_exists": manifest is not None,
        "tools": tools_result,
        "summary": summary,
    }


# ============================================================
# Subcommand: update-manifest
# ============================================================


def update_manifest(target_dir, tool_name, source_tool_dir):
    """Update manifest entry for one tool after install.

    `source_tool_dir` is the tool's own directory -- the one holding tool.toml --
    never the mg-cc-tools root. Every path below is derived from it: checksums walk
    it recursively and `source_root` is its parent. Handed the root instead, the
    function would happily checksum the whole repo into this tool's entry and
    record `source_path` one level too high, so both invariants are asserted.
    """
    tool_path = os.path.abspath(source_tool_dir)
    if not os.path.isfile(os.path.join(tool_path, "tool.toml")):
        raise ValueError(
            f"--source is not a tool directory (no tool.toml): {tool_path}\n"
            f"Pass the tool's own directory, e.g. <mg-cc-tools>/{tool_name}"
        )
    if os.path.basename(tool_path) != tool_name:
        raise ValueError(
            f"--tool '{tool_name}' does not match --source directory "
            f"'{os.path.basename(tool_path)}': {tool_path}"
        )

    # Determine source root (parent of tool dir) for version
    source_root = os.path.dirname(tool_path)
    version = read_pyproject_version(source_root)

    manifest_path = os.path.join(
        target_dir, ".claude", MANIFEST_FILENAME
    )

    # Read existing manifest or create new
    manifest: dict[str, Any]
    if os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = {
            "tools": {},
            "capabilities": {},
        }

    # Update top-level fields
    manifest["mg_cc_tools_version"] = version
    manifest["source_path"] = source_root
    manifest["last_updated"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat()

    # Compute entry for this tool
    # For execute_only tools (no install.sh), commands aren't deployed to target
    has_install_sh = os.path.isfile(os.path.join(tool_path, "install.sh"))
    commands = get_tool_commands(tool_path) if has_install_sh else []
    checksums = compute_tool_checksums(tool_path)

    manifest.setdefault("tools", {})[tool_name] = {
        "version": version,
        "installed_at": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "commands": commands,
        "source_checksums": checksums,
    }

    write_manifest_atomic(manifest_path, manifest)


# ============================================================
# Subcommand: set-standard-overrides
# ============================================================


def set_standard_overrides(source_dir, target_dir, toggle_names):
    """Flip the standard-install flag for the named tools and persist the result.

    Takes the tools to TOGGLE, not the override map to store. The command file
    previously computed the map itself and pasted it in as a JSON literal, which
    put three separable jobs in the prompt: knowing each tool's tool.toml default,
    inverting the effective value, and dropping overrides that had returned to the
    default. Only the third is even stated in the instructions, so an override
    equal to the default was stored routinely -- harmless but permanent noise, and
    it meant the file no longer distinguished "the user chose this" from "this is
    just the default".

    An override is stored only when it disagrees with the tool.toml default, and
    removed when it agrees again, so the manifest records decisions rather than
    duplicating defaults.

    Excluded tools are rejected: they are out of every bulk operation by
    definition, so a standard flag on one has no meaning to act on.

    Returns (results, standard_map) where results maps each toggled tool to
    ("on"|"off", "stored"|"cleared").
    """
    available = dict(discover_tools(source_dir))
    if not available:
        raise ValueError(f"no tools found under {source_dir}")

    defaults = {}
    excluded = set()
    for name, tool_dir in available.items():
        toml_data = read_tool_toml(tool_dir)
        defaults[name] = toml_data["standard"]
        if toml_data["exclude"]:
            excluded.add(name)

    unknown = [n for n in toggle_names if n not in available]
    if unknown:
        raise ValueError(
            f"unknown tool(s): {', '.join(sorted(unknown))}\n"
            f"Known tools: {', '.join(sorted(available))}"
        )
    hit_excluded = [n for n in toggle_names if n in excluded]
    if hit_excluded:
        raise ValueError(
            f"tool(s) excluded from bulk operations, cannot be made standard: "
            f"{', '.join(sorted(hit_excluded))}"
        )

    manifest_path = os.path.join(target_dir, ".claude", MANIFEST_FILENAME)
    manifest: dict[str, Any]
    if os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = {"tools": {}, "capabilities": {}}

    # setdefault, not assignment: every other key in the manifest -- tools,
    # capabilities, version, source_path -- has to survive this write.
    overrides = manifest.setdefault("standard_overrides", {})

    results = {}
    for name in toggle_names:
        effective = overrides.get(name, defaults[name])
        new_value = not effective
        if new_value == defaults[name]:
            overrides.pop(name, None)
            results[name] = ("on" if new_value else "off", "cleared")
        else:
            overrides[name] = new_value
            results[name] = ("on" if new_value else "off", "stored")

    write_manifest_atomic(manifest_path, manifest)

    standard_map = {
        name: overrides.get(name, defaults[name])
        for name in sorted(available)
        if name not in excluded
    }
    return results, standard_map


# ============================================================
# Subcommand: preflight
# ============================================================


def run_preflight(source_dir, target_dir, tool_names):
    """Run preflight checks for given tools.

    Aggregates required and optional checks from tool.toml, deduplicates,
    runs each check, returns results.
    """
    # Collect unique check IDs with required/optional classification
    required_ids = set()
    optional_ids = set()

    for tool_name in tool_names:
        tool_dir = os.path.join(source_dir, tool_name)
        toml_path = os.path.join(tool_dir, "tool.toml")
        if not os.path.isfile(toml_path):
            continue
        toml_data = read_tool_toml(tool_dir)
        for cid in toml_data.get("required", []):
            required_ids.add(cid)
        for cid in toml_data.get("optional", []):
            optional_ids.add(cid)

    # Required takes precedence over optional
    optional_ids -= required_ids

    all_check_ids = sorted(required_ids | optional_ids)
    checks_result = []

    for cid in all_check_ids:
        check_def = CHECKS.get(cid)
        if check_def is None:
            checks_result.append({
                "id": cid,
                "type": "unknown",
                "passed": False,
                "required": cid in required_ids,
                "version": None,
                "error": f"Unknown check ID: {cid}",
                "fix": {},
            })
            continue

        check_type = check_def["type"]
        is_required = cid in required_ids

        if check_type == "settings_scan":
            passed, detail = _check_lsp_settings(target_dir)
            checks_result.append({
                "id": cid,
                "type": "settings_scan",
                "passed": passed,
                "required": is_required,
                "version": detail if passed else None,
                "error": None if passed else "No LSP plugin found in Claude Code settings",
                "fix": check_def.get("fix", {}) if not passed else {},
            })
            continue

        if check_type == "plugin_scan":
            plugin_name = check_def["plugin_name"]
            passed, detail = _check_plugin_installed(plugin_name)
            checks_result.append({
                "id": cid,
                "type": "plugin_scan",
                "passed": passed,
                "required": is_required,
                "version": detail if passed else None,
                "error": None if passed else f"Plugin '{plugin_name}' not found",
                "fix": check_def.get("fix", {}) if not passed else {},
            })
            continue

        if check_type == "command":
            passed, version_str, error = _run_command_check(check_def)
            checks_result.append({
                "id": cid,
                "type": "command",
                "passed": passed,
                "required": is_required,
                "version": version_str,
                "error": error,
                "fix": check_def.get("fix", {}) if not passed else {},
            })

        elif check_type == "venv_python":
            passed, version_str, error = _run_venv_python_check(
                target_dir, check_def)
            checks_result.append({
                "id": cid,
                "type": "venv_python",
                "passed": passed,
                "required": is_required,
                "version": version_str,
                "error": error,
                "fix": check_def.get("fix", {}) if not passed else {},
            })

        elif check_type == "python_import":
            module_name = check_def["module"]
            passed, version_str, error = _run_python_import_check(
                target_dir, module_name)
            checks_result.append({
                "id": cid,
                "type": "python_import",
                "passed": passed,
                "required": is_required,
                "version": version_str,
                "error": error,
                "fix": check_def.get("fix", {}) if not passed else {},
            })

        elif check_type == "path_exists":
            path_template = check_def["path"]
            check_path = path_template.replace("{target}", target_dir)
            passed = os.path.exists(check_path)
            checks_result.append({
                "id": cid,
                "type": "path_exists",
                "passed": passed,
                "required": is_required,
                "version": None,
                "error": None if passed else f"Path not found: {check_path}",
                "fix": check_def.get("fix", {}) if not passed else {},
            })

    all_passed = all(
        c["passed"] for c in checks_result if c["required"]
    )

    return {
        "checks": checks_result,
        "all_passed": all_passed,
    }


def _resolve_venv_python(target_dir):
    """Resolve the .venv/bin/python3 path for the target project.

    Returns:
        (python_path, None) if found, or (None, error_message) if not.
    """
    venv_python = os.path.join(target_dir, ".venv", "bin", "python3")
    if os.path.isfile(venv_python):
        return venv_python, None
    return None, f"No .venv found at {target_dir}/.venv/bin/python3"


def _run_command_check(check_def):
    """Run a command-based check, return (passed, version, error)."""
    command = check_def["command"]
    version_re = check_def.get("parse_version")

    try:
        result = subprocess.run(
            command.split(),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, None, f"Command failed: {command}"

        output = result.stdout.strip() or result.stderr.strip()
        version_str = None
        if version_re and output:
            match = re.search(version_re, output)
            if match:
                version_str = match.group(1)

        return True, version_str, None

    except FileNotFoundError:
        return False, None, f"Command not found: {command.split()[0]}"
    except subprocess.TimeoutExpired:
        return False, None, f"Command timed out: {command}"


def _run_venv_python_check(target_dir, check_def):
    """Check the target project's .venv/bin/python3, return (passed, version, error)."""
    python_path, err = _resolve_venv_python(target_dir)
    if python_path is None:
        return False, None, err

    version_re = check_def.get("parse_version")
    try:
        result = subprocess.run(
            [python_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, None, f"Command failed: {python_path} --version"

        output = result.stdout.strip() or result.stderr.strip()
        version_str = None
        if version_re and output:
            match = re.search(version_re, output)
            if match:
                version_str = match.group(1)

        return True, version_str, None

    except subprocess.TimeoutExpired:
        return False, None, f"Command timed out: {python_path} --version"


def _run_python_import_check(target_dir, module_name):
    """Check if a Python module is importable in the target venv.

    Returns (passed, version, error).
    """
    python_path, err = _resolve_venv_python(target_dir)
    if python_path is None:
        return False, None, err

    script = f"import {module_name}; print(getattr({module_name}, '__version__', 'unknown'))"
    try:
        result = subprocess.run(
            [python_path, "-c", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False, None, f"Python module not importable: {module_name}"

        version_str = result.stdout.strip() or None
        return True, version_str, None

    except subprocess.TimeoutExpired:
        return False, None, f"Import check timed out: {module_name}"


def _check_plugin_installed(plugin_name):
    """Check if a Claude Code plugin/MCP server is installed.

    Scans the global plugins directory for a matching plugin name in
    .mcp.json files or plugin directory names.

    Returns (passed, detail_string).
    """
    plugins_base = os.path.join(
        os.path.expanduser("~"), ".claude", "plugins", "marketplaces"
    )
    if not os.path.isdir(plugins_base):
        return False, None

    for root, _dirs, files in os.walk(plugins_base):
        # Check directory name match
        if os.path.basename(root) == plugin_name:
            mcp_json = os.path.join(root, ".mcp.json")
            if os.path.isfile(mcp_json):
                return True, f"plugin:{plugin_name}"
        # Check .mcp.json contents for plugin name as a key
        if ".mcp.json" in files:
            mcp_path = os.path.join(root, ".mcp.json")
            try:
                with open(mcp_path, "r", encoding="utf-8") as f:
                    mcp_data = json.load(f)
                if plugin_name in mcp_data:
                    return True, f"plugin:{plugin_name}"
            except (json.JSONDecodeError, OSError):
                continue

    return False, None


def _check_lsp_settings(target_dir):
    """Check if LSP is mentioned in Claude Code settings.

    Scans both project-level and global settings.json for any mention of
    'lsp' in enabledPlugins keys, env vars, or other config fields.

    Returns (passed, detail_string).
    """
    lsp_plugins = []

    settings_paths = [
        os.path.join(target_dir, ".claude", "settings.json"),
        os.path.join(os.path.expanduser("~"), ".claude", "settings.json"),
    ]

    for settings_path in settings_paths:
        if not os.path.isfile(settings_path):
            continue
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        # Check enabledPlugins for any key containing 'lsp'
        plugins = settings.get("enabledPlugins", {})
        for plugin_name, enabled in plugins.items():
            if "lsp" in plugin_name.lower() and enabled:
                lsp_plugins.append(plugin_name)

    if lsp_plugins:
        return True, ", ".join(lsp_plugins)
    return False, None


# ============================================================
# Subcommand: validate
# ============================================================


def validate_install(target_dir, tool_names=None, source_dir=None):
    """Validate installed files for placeholder and path issues.

    Args:
        target_dir: Target project directory.
        tool_names: If provided, only validate files belonging to these tools.
                    Uses command-to-tool mapping to scope the scan.
        source_dir: Source mg-cc-tools directory (needed for tool_names scoping).
    """
    issues = []

    # Build set of filenames to scope validation when tool_names specified
    scoped_filenames = None
    if tool_names and source_dir:
        scoped_filenames = set()
        for tool_name in tool_names:
            tool_dir = os.path.join(source_dir, tool_name)
            for cmd in get_tool_commands(tool_dir):
                scoped_filenames.add(cmd)
            # Also include agent files
            agents_dir = os.path.join(tool_dir, "agents")
            if os.path.isdir(agents_dir):
                for f in os.listdir(agents_dir):
                    if f.endswith(".md"):
                        scoped_filenames.add(f)

    # --- Shared scan dirs (filename-scoped filtering) ---
    shared_scan_dirs = [
        os.path.join(target_dir, ".claude", "commands", "mg"),
        os.path.join(target_dir, ".claude", "agents"),
    ]

    for scan_dir in shared_scan_dirs:
        if not os.path.isdir(scan_dir):
            continue
        for root, _dirs, files in os.walk(scan_dir):
            for fname in sorted(files):
                if scoped_filenames is not None and fname not in scoped_filenames:
                    continue
                fpath = os.path.join(root, fname)
                _check_file_for_issues(fpath, issues)

    # --- Tool-specific agent dirs (scan all .md files, no filename scoping) ---
    agent_scan_dirs = []
    if tool_names:
        for tool_name in tool_names:
            agents_path = os.path.join(target_dir, ".claude", tool_name, "agents")
            if os.path.isdir(agents_path):
                agent_scan_dirs.append(agents_path)
    else:
        claude_dir = os.path.join(target_dir, ".claude")
        if os.path.isdir(claude_dir):
            for entry in sorted(os.listdir(claude_dir)):
                agents_path = os.path.join(claude_dir, entry, "agents")
                if os.path.isdir(agents_path):
                    agent_scan_dirs.append(agents_path)

    for scan_dir in agent_scan_dirs:
        for root, _dirs, files in os.walk(scan_dir):
            for fname in sorted(files):
                if fname.endswith(".md"):
                    fpath = os.path.join(root, fname)
                    _check_file_for_issues(fpath, issues)

    # --- install.sh self-validation (sed target prefix check) ---
    if source_dir:
        check_tool_names = tool_names or _discover_tool_names(source_dir)
        for tool_name in check_tool_names:
            install_sh = os.path.join(source_dir, tool_name, "install.sh")
            if not os.path.isfile(install_sh):
                continue
            _check_install_sh_sed_targets(install_sh, tool_name, issues)

    # --- Source-vs-target file comparison ---
    if source_dir:
        check_tool_names = tool_names or _discover_tool_names(source_dir)
        for tool_name in check_tool_names:
            tool_dir = os.path.join(source_dir, tool_name)
            if not os.path.isfile(os.path.join(tool_dir, "install.sh")):
                continue
            checksums = compute_tool_checksums(tool_dir)
            for rel_path in checksums:
                if rel_path in ("install.sh", "post-install.md"):
                    continue
                if rel_path.startswith("commands/"):
                    target_path = os.path.join(
                        target_dir, ".claude", "commands", "mg",
                        os.path.basename(rel_path),
                    )
                else:
                    target_path = os.path.join(
                        target_dir, ".claude", tool_name, rel_path,
                    )
                if not os.path.exists(target_path):
                    issues.append({
                        "file": target_path,
                        "line": 0,
                        "type": "missing_source_file",
                        "pattern": rel_path,
                        "message": f"Source file not installed: {tool_name}/{rel_path}",
                    })

    # Check workspace directories for tools that scaffold them
    check_tools = tool_names or list(WORKSPACE_DIRS.keys())
    manifest = read_manifest(target_dir)
    if manifest:
        manifest_tools = manifest.get("tools", {})
        for tool_name, workspace_subdir in WORKSPACE_DIRS.items():
            if tool_name in check_tools and tool_name in manifest_tools:
                workspace_path = os.path.join(target_dir, workspace_subdir)
                if not os.path.isdir(workspace_path):
                    issues.append({
                        "file": workspace_path,
                        "line": 0,
                        "type": "missing_workspace",
                        "pattern": workspace_subdir,
                        "message": f"Workspace directory missing for {tool_name}: {workspace_subdir}",
                    })

    return {"valid": len(issues) == 0, "issue_count": len(issues), "issues": issues}


def _check_file_for_issues(fpath, issues):
    """Check a single installed file for placeholder and reference issues."""
    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except (OSError, IOError):
        return

    for line_num, line in enumerate(lines, start=1):
        # Check for unresolved install-time placeholders ({MG_INSTALL_*})
        for match in INSTALL_PLACEHOLDER_RE.finditer(line):
            placeholder = match.group(0)
            issues.append({
                "file": fpath,
                "line": line_num,
                "type": "placeholder",
                "pattern": placeholder,
                "message": f"Unresolved placeholder: {placeholder}",
            })

        # Check for unresolved relative references (references/foo.md)
        for match in RELATIVE_REF_RE.finditer(line):
            ref_path = match.group(0)
            issues.append({
                "file": fpath,
                "line": line_num,
                "type": "unresolved_reference",
                "pattern": ref_path,
                "message": f"Unresolved relative reference: {ref_path}",
            })


def _discover_tool_names(source_dir):
    """Return sorted list of tool directory names in source_dir."""
    names = []
    for entry in sorted(os.listdir(source_dir)):
        tool_path = os.path.join(source_dir, entry)
        if os.path.isdir(tool_path) and os.path.isfile(
            os.path.join(tool_path, "tool.toml")
        ):
            names.append(entry)
    return names


def _check_install_sh_sed_targets(install_sh_path, tool_name, issues):
    """Check that sed targets in install.sh use MG_INSTALL_ prefix."""
    try:
        with open(install_sh_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except (OSError, IOError):
        return

    for line_num, line in enumerate(content.splitlines(), start=1):
        for target in SED_TARGET_RE.findall(line):
            if BARE_INSTALL_PLACEHOLDER_RE.match(target) and not target.startswith(
                "{MG_INSTALL_"
            ):
                issues.append({
                    "file": install_sh_path,
                    "line": line_num,
                    "type": "invalid_sed_target",
                    "pattern": target,
                    "message": (
                        f"sed target missing MG_INSTALL_ prefix in {tool_name}: "
                        f"{target}"
                    ),
                })


# ============================================================
# Subcommand: adopt
# ============================================================


def adopt_tools(source_dir, target_dir):
    """Detect and adopt pre-manifest installations.

    Scans source tools' commands/ dirs to build command-to-tool mapping.
    Checks which commands exist in target's .claude/commands/mg/.
    A tool is 'detected' if ALL its .md command files are present.

    Writes adopted tools directly into the manifest.
    Returns a compact summary (tool names only) to stdout.
    """
    version = read_pyproject_version(source_dir)
    manifest = read_manifest(target_dir)
    if manifest is None:
        manifest = {
            "mg_cc_tools_version": version,
            "source_path": os.path.abspath(source_dir),
            "last_updated": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "tools": {},
            "capabilities": {},
        }
    manifest_tools = manifest.get("tools", {})

    cmd_dir = os.path.join(target_dir, ".claude", "commands", "mg")
    adopted_names = []

    for tool_name, tool_dir in discover_tools(source_dir):
        # Skip tools already in manifest
        if tool_name in manifest_tools:
            continue

        commands = get_tool_commands(tool_dir)
        toml_data = read_tool_toml(tool_dir)
        detect_paths = toml_data.get("detect_paths", [])

        # Detection: (has commands AND all present) OR
        #            (has detect paths AND all exist in target)
        commands_detected = (
            bool(commands) and
            all(os.path.isfile(os.path.join(cmd_dir, cmd))
                for cmd in commands)
        )
        detect_detected = (
            bool(detect_paths) and
            all(os.path.exists(os.path.join(target_dir, p))
                for p in detect_paths)
        )

        if not commands_detected and not detect_detected:
            continue

        # Tool is detected -- adopt it (no version/checksums since we
        # can't verify what's actually installed)
        manifest_tools[tool_name] = {
            "adopted": True,
            "installed_at": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "commands": commands,
        }
        adopted_names.append(tool_name)

    # Write manifest if any tools were adopted
    if adopted_names:
        manifest["tools"] = manifest_tools
        manifest["mg_cc_tools_version"] = version
        manifest["source_path"] = os.path.abspath(source_dir)
        manifest["last_updated"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat()
        manifest_path = os.path.join(
            target_dir, ".claude", MANIFEST_FILENAME
        )
        write_manifest_atomic(manifest_path, manifest)

    return {"adopted": adopted_names, "count": len(adopted_names)}


# ============================================================
# Subcommand: render-status-table
# ============================================================


def _get_ordered_tools(tools):
    """Return non-excluded tools in canonical order: standard first, then optional.

    Each tool retains its original dict from scan-status JSON.
    This is the SINGLE source of truth for tool numbering used by
    render-tool-picker and resolve-tool-selection.

    Within each tier, tools preserve scan-status order (alphabetical from
    discover_tools).
    """
    standard = [t for t in tools if not t["excluded"] and t["standard"]]
    optional = [t for t in tools if not t["excluded"] and not t["standard"]]
    return standard + optional


def _format_status(tool):
    """Format the status column for a tool in the status table."""
    status = tool["status"]
    if status == "current":
        return "\u2713 Current"
    elif status == "update":
        old_ver = tool.get("installed_version") or "?"
        new_ver = tool.get("current_version") or "?"
        return f"Update ({old_ver} -> {new_ver})"
    elif status == "modified":
        n = len(tool.get("changed_files", []))
        return f"Modified ({n} files)"
    elif status == "corrupt":
        return "Corrupt"
    elif status == "adopted":
        return "Adopted"
    elif status == "available":
        return "Available"
    elif status == "excluded":
        return "Excluded"
    else:
        return status.capitalize()


def render_status_table(scan_data):
    """Render formatted status table from scan-status JSON.

    Prints a three-tier table (standard, optional, excluded) with
    aligned columns, summary counts, and status legend to stdout.
    Wrapped in display-fence markers for faithful LLM reproduction.
    """
    emit_display_open()
    version = scan_data.get("mg_cc_tools_version", "?.?.?")
    target = scan_data.get("target", "?")
    tools = scan_data.get("tools", [])
    summary = scan_data.get("summary", {})

    # Separate tiers
    standard = [t for t in tools if not t["excluded"] and t["standard"]]
    optional = [t for t in tools if not t["excluded"] and not t["standard"]]
    excluded = [t for t in tools if t["excluded"]]

    # Build display rows: (name_col, description, status_str)
    # name_col includes the optional * and external [ext] markers
    rows = []
    for t in standard:
        suffix = "  [ext]" if t.get("external") else ""
        rows.append((t["name"] + suffix, t["description"], _format_status(t)))
    for t in optional:
        suffix = "  * [ext]" if t.get("external") else "  *"
        rows.append((t["name"] + suffix, t["description"], _format_status(t)))
    for t in excluded:
        status_str = "Excluded"
        rows.append((t["name"], t["description"], status_str))

    # Compute column widths dynamically
    name_width = max((len(r[0]) for r in rows), default=10) + 2
    desc_width = max((len(r[1]) for r in rows), default=20) + 2
    status_width = max((len(r[2]) for r in rows), default=10)

    # Ensure minimum widths for headers
    name_width = max(name_width, len("Tool") + 2)
    desc_width = max(desc_width, len("Description") + 2)
    status_width = max(status_width, len("Status"))

    total_width = 2 + name_width + desc_width + status_width  # 2 for leading indent

    # Header
    print(f"mg-cc-tools v{version} -> {target}")
    print()

    # Column headers
    print(f"  {'Tool':<{name_width}}{'Description':<{desc_width}}{'Status'}")
    print(f"  {'\u2500' * (total_width - 2)}")

    # Standard tools
    for t in standard:
        suffix = "  [ext]" if t.get("external") else ""
        name_col = t["name"] + suffix
        print(f"  {name_col:<{name_width}}{t['description']:<{desc_width}}{_format_status(t)}")

    # Dot separator between standard and optional
    if standard and optional:
        print(f"  \u00b7")

    # Optional tools
    for t in optional:
        suffix = "  * [ext]" if t.get("external") else "  *"
        name_col = t["name"] + suffix
        print(f"  {name_col:<{name_width}}{t['description']:<{desc_width}}{_format_status(t)}")

    # Dashed separator before excluded
    if excluded:
        dash_line = "\u2500 " * ((total_width - 2) // 2)
        print(f"  {dash_line.rstrip()}")
        for t in excluded:
            status_str = "Excluded"
            print(f"  {t['name']:<{name_width}}{t['description']:<{desc_width}}{status_str}")

    # Summary line
    non_excluded_total = len(standard) + len(optional)
    installed_total = summary.get("installed_total", 0)
    update_count = summary.get("update", 0)
    available_count = summary.get("available", 0)

    print()
    print(f"  Installed: {installed_total}/{non_excluded_total}  |  Outdated: {update_count}  |  Available: {available_count}")

    # Status legend
    print()
    print("  Status legend:")
    print("    \u2713 Current       Installed, version and source files match")
    print("    Update          Installed, but newer version available (old -> new)")
    print("    Modified        Installed, same version, source files changed (N files)")
    print("    Corrupt         In manifest but command files missing from disk")
    print("    Adopted         Detected on disk, version unknown (reinstall to verify)")
    print("    Available       Not yet installed")
    print("    Excluded        Internal tool, install by name only")
    print()
    print('  *     = optional tool (not included in "Install all standard")')
    print("        Edit the standard list with option [N] below")
    print("  [ext] = external tool (sourced from external-tools archive)")
    emit_display_close()


# ============================================================
# Subcommand: render-tool-picker
# ============================================================


def render_tool_picker(scan_data):
    """Render numbered tool picker from scan-status JSON.

    Prints a numbered list with Standard and Optional section headers,
    status annotations for non-available tools, to stdout.
    """
    tools = scan_data.get("tools", [])
    ordered = _get_ordered_tools(tools)

    # Separate into standard and optional for section headers
    standard = [t for t in ordered if t["standard"]]
    optional = [t for t in ordered if not t["standard"]]

    # Compute column widths
    max_name = max((len(t["name"]) for t in ordered), default=10)
    num_width = len(str(len(ordered)))

    # Separator width
    sep_width = num_width + 2 + max_name + 6 + 40  # generous

    emit_display_open()
    print("Select tools to install:")
    print()

    idx = 1

    # Standard section
    print("  Standard")
    print(f"  {'\u2500' * sep_width}")
    for t in standard:
        annotation = ""
        if t["status"] != "available":
            annotation = f" ({t['status'].capitalize()})"
        print(f"  {idx:>{num_width}}. {t['name']:<{max_name + 6}}{t['description']}{annotation}")
        idx += 1

    # Optional section
    if optional:
        print()
        print("  Optional")
        print(f"  {'\u2500' * sep_width}")
        for t in optional:
            annotation = ""
            if t["status"] != "available":
                annotation = f" ({t['status'].capitalize()})"
            print(f"  {idx:>{num_width}}. {t['name']:<{max_name + 6}}{t['description']}{annotation}")
            idx += 1

    print()
    print("Type numbers, names, or 'all':")
    emit_display_close()


# ============================================================
# Subcommand: resolve-tool-selection
# ============================================================


def resolve_tool_selection(scan_data, selection_text):
    """Resolve user's selection text to a list of tool names.

    Args:
        scan_data: Full scan-status JSON dict.
        selection_text: User's input (numbers, ranges, names, mixed, or "all").

    Returns:
        dict with either {"tools": [...]} or {"error": "..."}.
    """
    tools = scan_data.get("tools", [])
    ordered = _get_ordered_tools(tools)

    # Build lookup structures
    num_to_name = {}
    name_set = set()
    for i, t in enumerate(ordered, start=1):
        num_to_name[i] = t["name"]
        name_set.add(t["name"])

    total = len(ordered)

    # Handle "all" keyword
    stripped = selection_text.strip().lower()
    if stripped == "all":
        return {"tools": [t["name"] for t in ordered]}

    # Split on commas and process each token
    tokens = [tok.strip() for tok in selection_text.split(",")]
    result_names = []

    for token in tokens:
        if not token:
            continue

        # Check if it's a range (e.g., "1-3")
        range_match = re.match(r"^(\d+)\s*-\s*(\d+)$", token)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if start < 1 or end > total:
                return {"error": f"Invalid range: {token} (valid range is 1-{total})"}
            if start > end:
                return {"error": f"Invalid range: {token} (start > end)"}
            for n in range(start, end + 1):
                result_names.append(num_to_name[n])
            continue

        # Check if it's a number
        if token.isdigit():
            num = int(token)
            if num < 1 or num > total:
                return {"error": f"Invalid selection: number {num} is out of range (1-{total})"}
            result_names.append(num_to_name[num])
            continue

        # Must be a name
        if token in name_set:
            result_names.append(token)
            continue

        # Unknown
        return {"error": f"Unknown tool name: {token}"}

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for name in result_names:
        if name not in seen:
            seen.add(name)
            deduped.append(name)

    return {"tools": deduped}


# ============================================================
# Shared scenario logic
# ============================================================


def _determine_scenario(scan_data):
    """Determine install scenario from scan-status data.

    Returns:
        "A" if nothing installed (installed_total == 0)
        "B" if some tools need attention (update/modified/corrupt/adopted > 0)
        "C" if all installed tools are current
    """
    summary = scan_data.get("summary", {})
    installed_total = summary.get("installed_total", 0)
    if installed_total == 0:
        return "A"
    if (summary.get("update", 0) > 0
            or summary.get("modified", 0) > 0
            or summary.get("corrupt", 0) > 0
            or summary.get("adopted", 0) > 0):
        return "B"
    return "C"


# ============================================================
# Subcommand: render-action-menu
# ============================================================


def render_action_menu(scan_data):
    """Render scenario-appropriate action menu to stdout."""
    emit_display_open()
    scenario = _determine_scenario(scan_data)
    tools = scan_data.get("tools", [])
    summary = scan_data.get("summary", {})

    # Compute dynamic counts
    attention_count = (summary.get("update", 0) + summary.get("modified", 0)
                       + summary.get("corrupt", 0) + summary.get("adopted", 0))
    standard_available = sum(
        1 for t in tools
        if t["status"] == "available" and t["standard"] and not t["excluded"]
    )
    standard_total = sum(
        1 for t in tools if t["standard"] and not t["excluded"]
    )

    print("What would you like to do?")
    print()

    if scenario == "A":
        print("  [1] Select specific tools")
        print(f"  [2] Install all standard tools ({standard_total} tools)")
        print("  [3] Edit standard install list")
        print()
        print("Type a number, or tool names separated by commas:")
    elif scenario == "B":
        print("  [1] Select specific tools")
        print(f"  [2] Fix/update {attention_count} tools needing attention")
        print("  [3] Fix/update + install all missing standard")
        print(f"  [4] Install missing standard only ({standard_available} tools)")
        print("  [5] Edit standard install list")
        print("  [6] Check capabilities only")
        print()
        print("Type a number, tool names, or 'all':")
    elif scenario == "C":
        print("  [1] Select specific tools")
        print(f"  [2] Install remaining {standard_available} standard tools")
        print("  [3] Reinstall all")
        print("  [4] Edit standard install list")
        print("  [5] Check capabilities only")
        print()
        print("Type a number, tool names, or 'all':")
    emit_display_close()


# ============================================================
# Subcommand: resolve-action
# ============================================================


def _resolve_menu_option(scenario, num, tools, summary):
    """Map a menu number to an action dict for the given scenario.

    Returns dict with "action" and optionally "tools", or "error".
    """
    # Precompute tool lists needed across scenarios
    attention_statuses = {"update", "modified", "corrupt", "adopted"}
    attention_tools = [
        t["name"] for t in tools
        if not t["excluded"] and t["status"] in attention_statuses
    ]
    missing_standard = [
        t["name"] for t in tools
        if not t["excluded"] and t["standard"] and t["status"] == "available"
    ]
    standard_tools = [
        t["name"] for t in tools
        if not t["excluded"] and t["standard"]
    ]
    all_non_excluded = [
        t["name"] for t in _get_ordered_tools(tools)
    ]

    if scenario == "A":
        options = {
            1: {"action": "select_specific"},
            2: {"action": "install", "tools": standard_tools},
            3: {"action": "edit_standard"},
        }
    elif scenario == "B":
        options = {
            1: {"action": "select_specific"},
            2: {"action": "install", "tools": attention_tools},
            3: {"action": "install", "tools": attention_tools + missing_standard},
            4: {"action": "install", "tools": missing_standard},
            5: {"action": "edit_standard"},
            6: {"action": "check_capabilities"},
        }
    elif scenario == "C":
        options = {
            1: {"action": "select_specific"},
            2: {"action": "install", "tools": missing_standard},
            3: {"action": "install", "tools": all_non_excluded},
            4: {"action": "edit_standard"},
            5: {"action": "check_capabilities"},
        }
    else:
        return {"error": f"Unknown scenario: {scenario}"}

    if num in options:
        return options[num]
    max_opt = max(options.keys())
    return {"error": f"Invalid option: {num} (valid range is 1-{max_opt})"}


def resolve_action(scan_data, selection_text):
    """Resolve user's menu selection to action and tool list.

    Returns dict: {"action": "install", "tools": [...]} or
                  {"action": "select_specific"} or
                  {"action": "edit_standard"} or
                  {"action": "check_capabilities"} or
                  {"error": "..."}
    """
    scenario = _determine_scenario(scan_data)
    tools = scan_data.get("tools", [])
    summary = scan_data.get("summary", {})
    stripped = selection_text.strip()

    # Try to match a menu number
    if stripped.isdigit():
        num = int(stripped)
        return _resolve_menu_option(scenario, num, tools, summary)

    # Not a menu number -- try resolve_tool_selection for names/ranges
    result = resolve_tool_selection(scan_data, selection_text)
    if "error" in result:
        return result
    return {"action": "install", "tools": result["tools"]}


# ============================================================
# Subcommands: install plan, result tracking, renderers (Phase 11 Plan 02)
# ============================================================


def get_install_plan(scan_data, tool_names):
    """Generate install plan for given tools.

    Returns list of install instruction dicts.
    """
    target = scan_data.get("target", "")
    tools_by_name = {t["name"]: t for t in scan_data.get("tools", [])}
    plan = []

    for name in tool_names:
        tool = tools_by_name.get(name)
        if tool is None:
            continue

        has_sh = tool.get("has_install_sh", False)
        post_install = tool.get("post_install")

        # Determine pattern
        if has_sh and not post_install:
            pattern = "copy_only"
        elif has_sh and post_install:
            pattern = "copy_configure"
        else:
            pattern = "execute_only"

        # Determine expected action
        status = tool["status"]
        if status == "available":
            action = "installed"
        elif status in ("update", "modified", "corrupt", "adopted"):
            action = "updated"
        else:
            action = "reinstalled"

        if pattern in ("copy_configure", "execute_only"):
            action += " (configured)"

        # Build install command
        install_cmd = None
        if has_sh:
            install_cmd = f'bash ./{name}/install.sh --project "{target}"'

        plan.append({
            "tool": name,
            "pattern": pattern,
            "expected_action": action,
            "install_cmd": install_cmd,
            "post_install": f"{name}/{post_install}" if post_install else None,
            "commands": tool.get("commands", []),
        })

    return plan


def render_preflight(preflight_data):
    """Render preflight results as human-readable PASS/FAIL output.

    Prints header, per-check lines with [PASS]/[FAIL] markers,
    and summary counts with required/optional grouping.
    Wrapped in display-fence markers for faithful LLM reproduction.
    """
    emit_display_open()
    checks = preflight_data.get("checks", [])

    print("Preflight checks:")
    print()

    for check in checks:
        marker = "[PASS]" if check["passed"] else "[FAIL]"
        detail = check.get("version") or check.get("error") or ""
        req_text = "required" if check["required"] else "optional"
        print(f"  {marker} {check['id']}    {detail}    ({req_text})")

    print()

    # Summary counts
    required_checks = [c for c in checks if c["required"]]
    optional_checks = [c for c in checks if not c["required"]]

    req_passed = sum(1 for c in required_checks if c["passed"])
    req_total = len(required_checks)
    print(f"  Required: {req_passed}/{req_total} passed")

    if optional_checks:
        opt_passed = sum(1 for c in optional_checks if c["passed"])
        opt_total = len(optional_checks)
        print(f"  Optional: {opt_passed}/{opt_total} passed")
    emit_display_close()


def record_result(results_file, tool_name, success, plan_file):
    """Append install result for one tool to results file.

    Creates the file with [] if it doesn't exist.
    Reads plan file to look up expected_action and commands.
    """
    # Read install plan for tool's metadata
    with open(plan_file, "r", encoding="utf-8") as f:
        plan = json.load(f)

    tool_plan = next((p for p in plan if p["tool"] == tool_name), None)

    if success:
        entry = {
            "tool": tool_name,
            "action": tool_plan["expected_action"] if tool_plan else "installed",
            "commands": tool_plan["commands"] if tool_plan else [],
        }
    else:
        entry = {
            "tool": tool_name,
            "action": "failed",
            "commands": [],
        }

    # Read existing results or create empty
    if os.path.isfile(results_file):
        with open(results_file, "r", encoding="utf-8") as f:
            results = json.load(f)
    else:
        results = []

    results.append(entry)

    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        f.write("\n")


def render_summary(results_data, scan_data, preflight_data=None):
    """Render final install summary table from results, scan-status, and optional preflight.

    Prints header, target, action counts, tool table with commands,
    and optional capabilities section from preflight data.
    Wrapped in display-fence markers for faithful LLM reproduction.
    """
    emit_display_open()
    target = scan_data.get("target", "")

    # Compute action counts
    installed_count = 0
    updated_count = 0
    failed_count = 0
    for r in results_data:
        action = r.get("action", "")
        if action == "failed":
            failed_count += 1
        elif "installed" in action:
            installed_count += 1
        elif "updated" in action or "reinstalled" in action:
            updated_count += 1

    print("mg-cc-tools -- INSTALL COMPLETE")
    print(f"  Target: {target}")
    print(f"  Installed: {installed_count}  |  Updated: {updated_count}  |  Failed: {failed_count}")
    print()

    # Tool table
    # Compute column widths
    tool_width = max((len(r["tool"]) for r in results_data), default=10) + 2
    action_width = max((len(r["action"]) for r in results_data), default=10) + 2

    tool_width = max(tool_width, len("Tool") + 2)
    action_width = max(action_width, len("Action") + 2)

    print(f"  {'Tool':<{tool_width}}{'Action':<{action_width}}Commands")
    total_width = 2 + tool_width + action_width + 20
    sep = "\u2500" * (total_width - 2)
    print(f"  {sep}")

    for r in results_data:
        commands = r.get("commands", [])
        cmd_str = ", ".join(commands) if commands else "--"
        print(f"  {r['tool']:<{tool_width}}{r['action']:<{action_width}}{cmd_str}")

    # Capabilities section (from preflight data)
    if preflight_data:
        checks = preflight_data.get("checks", [])

        lsp_check = next((c for c in checks if c["id"] == "lsp"), None)
        missing_optional = [
            c for c in checks
            if not c["required"] and not c["passed"] and c["id"] != "lsp"
        ]

        if lsp_check or missing_optional:
            print()
            print("  Capabilities:")
            if lsp_check:
                if lsp_check["passed"]:
                    print(f"    LSP: functional ({lsp_check.get('version', 'unknown')})")
                else:
                    print("    LSP: not configured")
            if missing_optional:
                names = ", ".join(c["id"] for c in missing_optional)
                print(f"    Missing optional tools: {names}")
        else:
            print()
            print("  Capabilities: not applicable")
    emit_display_close()


def render_validation(validate_data):
    """Render validation results as human-readable PASS/WARNING output.

    For clean validation (0 issues): prints success message.
    For issues: prints WARNING lines with messages.
    Wrapped in display-fence markers for faithful LLM reproduction.
    """
    emit_display_open()
    print("Post-install validation:")

    if validate_data.get("issue_count", 0) == 0:
        print("  All checks passed -- no unresolved placeholders or references")
        emit_display_close()
        return

    for issue in validate_data.get("issues", []):
        print(f"  WARNING: {issue['message']}")

    count = validate_data["issue_count"]
    print(f"  {count} issue{'s' if count != 1 else ''} found")
    emit_display_close()


# ============================================================
# CLI entry point
# ============================================================



def render_target_menu(source_dir):
    """Render numbered target selection menu from sibling directories.

    Scans ../*/ for directories, prints a numbered list, and adds a
    manual entry option. Wrapped in display-fence markers.
    """
    parent = os.path.abspath(os.path.join(source_dir, ".."))
    siblings = []
    if os.path.isdir(parent):
        for entry in sorted(os.listdir(parent)):
            full = os.path.join(parent, entry)
            if os.path.isdir(full):
                siblings.append(entry)

    emit_display_open()
    print("Target project:")
    print()
    for i, name in enumerate(siblings, 1):
        print(f"  [{i}] {name}")
    manual_num = len(siblings) + 1
    print(f"  [{manual_num}] Enter path manually")
    print()
    print("Type a number or project name:")
    emit_display_close()


def resolve_target_selection(source_dir, selection_text):
    """Resolve user's target menu selection to a directory path.

    Returns {"target": "<absolute_path>"} or
            {"action": "manual"} or
            {"error": "..."}.
    """
    parent = os.path.abspath(os.path.join(source_dir, ".."))
    siblings = []
    if os.path.isdir(parent):
        for entry in sorted(os.listdir(parent)):
            full = os.path.join(parent, entry)
            if os.path.isdir(full):
                siblings.append(entry)

    stripped = selection_text.strip()
    manual_num = len(siblings) + 1

    # Try as a menu number
    if stripped.isdigit():
        num = int(stripped)
        if num == manual_num:
            return {"action": "manual"}
        if 1 <= num <= len(siblings):
            return resolve_target(siblings[num - 1])
        return {"error": f"Invalid selection: {num}. Choose 1-{manual_num}."}

    # Try as a bare name or path
    return resolve_target(stripped)


def resolve_target(target: str) -> dict:
    """Resolve a target argument to an absolute directory path.

    Bare names (no path separators) are treated as sibling directories (../<name>).
    Paths containing '/' or starting with '~' are used as-is after expansion.
    Returns {"target": "<absolute_path>"} or {"error": "<message>"}.
    """
    if "/" not in target and not target.startswith("~"):
        # Bare project name → sibling directory
        candidate = os.path.join("..", target)
    else:
        candidate = target

    resolved = os.path.abspath(os.path.expanduser(candidate))

    if not os.path.isdir(resolved):
        return {"error": f"Directory does not exist: {resolved}"}

    return {"target": resolved}


def cmd_render_target_menu(args):
    """CLI handler for render-target-menu."""
    render_target_menu(args.source)


def cmd_resolve_target_selection(args):
    """CLI handler for resolve-target-selection."""
    result = resolve_target_selection(args.source, args.selection)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


def cmd_resolve_target(args):
    """CLI handler for resolve-target."""
    result = resolve_target(args.target)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


def cmd_scan_status(args):
    """CLI handler for scan-status."""
    auto_adopted = []

    # Auto-adopt: when flag set and no manifest exists, adopt first
    if args.auto_adopt:
        manifest = read_manifest(args.target)
        if manifest is None:
            adopt_result = adopt_tools(args.source, args.target)
            auto_adopted = adopt_result.get("adopted", [])

    result = scan_status(args.source, args.target)

    # Add auto_adopted field only when --auto-adopt was used
    if args.auto_adopt:
        result["auto_adopted"] = auto_adopted

    if args.output:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        # Write full details to file, compact summary to stdout
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
            f.write("\n")
        # Compact summary: tool list without checksums/changed_files
        compact_tools = []
        for t in result["tools"]:
            compact_tools.append({
                "name": t["name"],
                "description": t["description"],
                "status": t["status"],
                "excluded": t["excluded"],
                "standard": t["standard"],
                "has_install_sh": t["has_install_sh"],
                "post_install": t["post_install"],
                "external": t.get("external", False),
            })
        summary = {
            "mg_cc_tools_version": result["mg_cc_tools_version"],
            "target": result["target"],
            "manifest_exists": result["manifest_exists"],
            "tools": compact_tools,
            "summary": result["summary"],
            "details": args.output,
        }
        if args.auto_adopt:
            summary["auto_adopted"] = auto_adopted
        json.dump(summary, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")


def cmd_update_manifest(args):
    """CLI handler for update-manifest."""
    try:
        update_manifest(args.target, args.tool, args.source)
    except ValueError as e:
        sys.stderr.write(f"update-manifest: {e}\n")
        sys.exit(2)


def cmd_set_standard_overrides(args):
    """CLI handler for set-standard-overrides."""
    toggle_names = [t.strip() for t in args.toggle.split(",") if t.strip()]
    if not toggle_names:
        sys.stderr.write("set-standard-overrides: --toggle listed no tools\n")
        sys.exit(2)
    try:
        results, standard_map = set_standard_overrides(
            args.source, args.target, toggle_names
        )
    except (ValueError, OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"set-standard-overrides: {e}\n")
        sys.exit(2)

    print(json.dumps({
        "toggled": {
            name: {"standard": state == "on", "override": disposition}
            for name, (state, disposition) in results.items()
        },
        "standard": standard_map,
    }, indent=2))


def cmd_preflight(args):
    """CLI handler for preflight."""
    tool_names = [t.strip() for t in args.tools.split(",")]
    result = run_preflight(args.source, args.target, tool_names)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
            f.write("\n")
        compact = {
            "all_passed": result["all_passed"],
            "check_count": len(result["checks"]),
            "details": args.output,
        }
        json.dump(compact, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")


def cmd_validate(args):
    """CLI handler for validate."""
    tool_names = None
    if args.tools:
        tool_names = [t.strip() for t in args.tools.split(",")]
    result = validate_install(args.target, tool_names=tool_names,
                              source_dir=args.source)

    if args.output:
        # Write full details to file, compact summary to stdout
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
            f.write("\n")
        summary = {
            "valid": result["valid"],
            "issue_count": result["issue_count"],
            "details": args.output,
        }
        json.dump(summary, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")


def cmd_adopt(args):
    """CLI handler for adopt."""
    result = adopt_tools(args.source, args.target)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


def cmd_render_status_table(args):
    """CLI handler for render-status-table."""
    with open(args.input, "r", encoding="utf-8") as f:
        scan_data = json.load(f)
    render_status_table(scan_data)


def cmd_render_tool_picker(args):
    """CLI handler for render-tool-picker."""
    with open(args.input, "r", encoding="utf-8") as f:
        scan_data = json.load(f)
    render_tool_picker(scan_data)


def cmd_resolve_tool_selection(args):
    """CLI handler for resolve-tool-selection."""
    with open(args.input, "r", encoding="utf-8") as f:
        scan_data = json.load(f)
    result = resolve_tool_selection(scan_data, args.selection)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


def cmd_render_action_menu(args):
    """CLI handler for render-action-menu."""
    with open(args.input, "r", encoding="utf-8") as f:
        scan_data = json.load(f)
    render_action_menu(scan_data)


def cmd_resolve_action(args):
    """CLI handler for resolve-action."""
    with open(args.input, "r", encoding="utf-8") as f:
        scan_data = json.load(f)
    result = resolve_action(scan_data, args.selection)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


def cmd_get_install_plan(args):
    """CLI handler for get-install-plan."""
    with open(args.input, "r", encoding="utf-8") as f:
        scan_data = json.load(f)
    tool_names = [t.strip() for t in args.tools.split(",")]
    plan = get_install_plan(scan_data, tool_names)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
            f.write("\n")
        # Compact summary: tool + pattern + install_cmd + post_install per entry
        compact = [
            {"tool": p["tool"], "pattern": p["pattern"],
             "install_cmd": p["install_cmd"],
             "post_install": p["post_install"]}
            for p in plan
        ]
        json.dump(compact, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        json.dump(plan, sys.stdout, indent=2)
        sys.stdout.write("\n")


def cmd_render_preflight(args):
    """CLI handler for render-preflight."""
    with open(args.input, "r", encoding="utf-8") as f:
        preflight_data = json.load(f)
    render_preflight(preflight_data)


def cmd_record_result(args):
    """CLI handler for record-result."""
    success = args.success
    record_result(args.file, args.tool, success, args.plan)


def cmd_render_summary(args):
    """CLI handler for render-summary."""
    with open(args.results, "r", encoding="utf-8") as f:
        results_data = json.load(f)
    with open(args.input, "r", encoding="utf-8") as f:
        scan_data = json.load(f)
    preflight_data = None
    if args.preflight:
        with open(args.preflight, "r", encoding="utf-8") as f:
            preflight_data = json.load(f)
    render_summary(results_data, scan_data, preflight_data)


def cmd_render_validation(args):
    """CLI handler for render-validation."""
    with open(args.input, "r", encoding="utf-8") as f:
        validate_data = json.load(f)
    render_validation(validate_data)


def main():
    parser = argparse.ArgumentParser(
        description="mg-cc-tools installer library",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # render-target-menu
    p_render_target = sub.add_parser(
        "render-target-menu",
        help="Render numbered target selection menu from sibling directories",
    )
    p_render_target.add_argument("--source", required=True,
                                 help="Path to mg-cc-tools source directory")
    p_render_target.set_defaults(func=cmd_render_target_menu)

    # resolve-target-selection
    p_resolve_target_sel = sub.add_parser(
        "resolve-target-selection",
        help="Resolve user's target menu selection to a directory path",
    )
    p_resolve_target_sel.add_argument("--source", required=True,
                                      help="Path to mg-cc-tools source directory")
    p_resolve_target_sel.add_argument("--selection", required=True,
                                      help="User's menu selection text")
    p_resolve_target_sel.set_defaults(func=cmd_resolve_target_selection)

    # resolve-target
    p_resolve_target = sub.add_parser(
        "resolve-target",
        help="Resolve a target argument to an absolute directory path",
    )
    p_resolve_target.add_argument("--target", required=True,
                                  help="Target argument (bare name or path)")
    p_resolve_target.set_defaults(func=cmd_resolve_target)

    # scan-status
    p_scan = sub.add_parser(
        "scan-status",
        help="Discover tools, compute checksums, compare with manifest",
    )
    p_scan.add_argument("--source", required=True,
                        help="Path to mg-cc-tools source directory")
    p_scan.add_argument("--target", required=True,
                        help="Path to target project directory")
    p_scan.add_argument("--output",
                        help="Write full details to file, compact summary to stdout")
    p_scan.add_argument("--auto-adopt", action="store_true", dest="auto_adopt",
                        help="Auto-adopt existing installations when no manifest exists")
    p_scan.set_defaults(func=cmd_scan_status)

    # update-manifest
    p_manifest = sub.add_parser(
        "update-manifest",
        help="Update manifest entry for one tool after install",
    )
    p_manifest.add_argument("--target", required=True,
                            help="Path to target project directory")
    p_manifest.add_argument("--tool", required=True,
                            help="Tool name (directory name)")
    p_manifest.add_argument("--source", required=True,
                            help="Path to the tool's own source directory (the one "
                                 "holding tool.toml), not the mg-cc-tools root")
    p_manifest.set_defaults(func=cmd_update_manifest)

    # set-standard-overrides
    p_std = sub.add_parser(
        "set-standard-overrides",
        help="Toggle which tools are part of the standard install list",
    )
    p_std.add_argument("--source", required=True,
                       help="Path to mg-cc-tools source directory")
    p_std.add_argument("--target", required=True,
                       help="Path to target project directory")
    p_std.add_argument("--toggle", required=True,
                       help="Comma-separated tool names to flip on/off")
    p_std.set_defaults(func=cmd_set_standard_overrides)

    # preflight
    p_pre = sub.add_parser(
        "preflight",
        help="Run preflight checks for given tools",
    )
    p_pre.add_argument("--source", required=True,
                       help="Path to mg-cc-tools source directory")
    p_pre.add_argument("--target", required=True,
                       help="Path to target project directory")
    p_pre.add_argument("--tools", required=True,
                       help="Comma-separated tool names")
    p_pre.add_argument("--output",
                       help="Write full details to file, compact summary to stdout")
    p_pre.set_defaults(func=cmd_preflight)

    # validate
    p_val = sub.add_parser(
        "validate",
        help="Validate installed files for placeholder and path issues",
    )
    p_val.add_argument("--target", required=True,
                       help="Path to target project directory")
    p_val.add_argument("--tools",
                       help="Comma-separated tool names to scope validation")
    p_val.add_argument("--source",
                       help="Path to mg-cc-tools source (needed with --tools)")
    p_val.add_argument("--output",
                       help="Write full details to file, compact summary to stdout")
    p_val.set_defaults(func=cmd_validate)

    # adopt
    p_adopt = sub.add_parser(
        "adopt",
        help="Detect and adopt pre-manifest installations",
    )
    p_adopt.add_argument("--source", required=True,
                         help="Path to mg-cc-tools source directory")
    p_adopt.add_argument("--target", required=True,
                         help="Path to target project directory")
    p_adopt.set_defaults(func=cmd_adopt)

    # render-status-table
    p_render_table = sub.add_parser(
        "render-status-table",
        help="Render formatted status table from scan-status JSON",
    )
    p_render_table.add_argument("--input", required=True,
                                help="Path to scan-status JSON file")
    p_render_table.set_defaults(func=cmd_render_status_table)

    # render-tool-picker
    p_render_picker = sub.add_parser(
        "render-tool-picker",
        help="Render numbered tool picker from scan-status JSON",
    )
    p_render_picker.add_argument("--input", required=True,
                                 help="Path to scan-status JSON file")
    p_render_picker.set_defaults(func=cmd_render_tool_picker)

    # resolve-tool-selection
    p_resolve = sub.add_parser(
        "resolve-tool-selection",
        help="Resolve tool selection text to tool names",
    )
    p_resolve.add_argument("--input", required=True,
                           help="Path to scan-status JSON file")
    p_resolve.add_argument("--selection", required=True,
                           help="User's selection text (numbers, ranges, names, or 'all')")
    p_resolve.set_defaults(func=cmd_resolve_tool_selection)

    # render-action-menu
    p_action_menu = sub.add_parser(
        "render-action-menu",
        help="Render scenario-appropriate action menu from scan-status JSON",
    )
    p_action_menu.add_argument("--input", required=True,
                               help="Path to scan-status JSON file")
    p_action_menu.set_defaults(func=cmd_render_action_menu)

    # resolve-action
    p_resolve_action = sub.add_parser(
        "resolve-action",
        help="Resolve user's menu selection to action and tool list",
    )
    p_resolve_action.add_argument("--input", required=True,
                                  help="Path to scan-status JSON file")
    p_resolve_action.add_argument("--selection", required=True,
                                  help="User's menu selection text")
    p_resolve_action.set_defaults(func=cmd_resolve_action)

    # get-install-plan
    p_install_plan = sub.add_parser(
        "get-install-plan",
        help="Generate install plan for given tools from scan-status",
    )
    p_install_plan.add_argument("--input", required=True,
                                help="Path to scan-status JSON file")
    p_install_plan.add_argument("--tools", required=True,
                                help="Comma-separated tool names")
    p_install_plan.add_argument("--output",
                                help="Write full plan to file, compact summary to stdout")
    p_install_plan.set_defaults(func=cmd_get_install_plan)

    # render-preflight
    p_render_pre = sub.add_parser(
        "render-preflight",
        help="Render preflight results as human-readable output",
    )
    p_render_pre.add_argument("--input", required=True,
                              help="Path to preflight JSON file")
    p_render_pre.set_defaults(func=cmd_render_preflight)

    # record-result
    p_record = sub.add_parser(
        "record-result",
        help="Append per-tool install result to results file",
    )
    p_record.add_argument("--file", required=True,
                          help="Path to install results JSON file")
    p_record.add_argument("--tool", required=True,
                          help="Tool name")
    p_record.add_argument("--plan", required=True,
                          help="Path to install plan JSON file")
    outcome = p_record.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--success", action="store_true",
                         help="Record successful install")
    outcome.add_argument("--failed", action="store_true",
                         help="Record failed install")
    p_record.set_defaults(func=cmd_record_result)

    # render-summary
    p_render_sum = sub.add_parser(
        "render-summary",
        help="Render final install summary table",
    )
    p_render_sum.add_argument("--results", required=True,
                              help="Path to install results JSON file")
    p_render_sum.add_argument("--input", required=True,
                              help="Path to scan-status JSON file")
    p_render_sum.add_argument("--preflight",
                              help="Path to preflight JSON file (optional)")
    p_render_sum.set_defaults(func=cmd_render_summary)

    # render-validation
    p_render_val = sub.add_parser(
        "render-validation",
        help="Render validation results as human-readable output",
    )
    p_render_val.add_argument("--input", required=True,
                              help="Path to validate JSON file")
    p_render_val.set_defaults(func=cmd_render_validation)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
