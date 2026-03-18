#!/usr/bin/env bash
set -euo pipefail

# ── CC Regression Test — Installer ───────────────────────────────────────────
#
# Installs the mg:cc-regression-test command, hook, and trigger script into
# a Claude Code configuration.
#
# What it does:
#   1. Copies command file to <target>/commands/mg/
#   2. Copies hooks/ and scripts/ to <target>/cc-regression-test/
#   3. Resolves path placeholders in the command file
#   4. Merges PreToolUse hook entry into settings.json
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=(
  cc-regression-test
)

# ── Parse arguments ──────────────────────────────────────────────────────────

TARGET_DIR=""
MODE=""
PROJECT_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      MODE="project"
      shift
      if [[ $# -gt 0 && "$1" != -* ]]; then
        PROJECT_PATH="$1"
        shift
      fi
      ;;
    --global)
      MODE="global"
      shift
      ;;
    --target)
      MODE="custom"
      TARGET_DIR="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: ./install.sh [--project [<dir>] | --global | --target <path>]"
      echo ""
      echo "  --project [<dir>]  Install into <dir>/.claude/ (default: current directory)"
      echo "  --global           Install into ~/.claude/"
      echo "  --target <path>    Install into a custom .claude/ directory"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run ./install.sh --help for usage."
      exit 1
      ;;
  esac
done

if [[ -z "$MODE" ]]; then
  echo "Error: specify --project, --global, or --target <path>"
  echo "Run ./install.sh --help for usage."
  exit 1
fi

# ── Resolve target directory ─────────────────────────────────────────────────

case "$MODE" in
  project)
    TARGET_DIR="$(cd "${PROJECT_PATH:-.}" && pwd)/.claude"
    ;;
  global)
    TARGET_DIR="${HOME}/.claude"
    ;;
  custom)
    # TARGET_DIR already set
    ;;
esac

# ── Validate source ─────────────────────────────────────────────────────────

for cmd in "${COMMANDS[@]}"; do
  if [[ ! -f "${SCRIPT_DIR}/commands/${cmd}.md" ]]; then
    echo "Error: missing commands/${cmd}.md in source directory (${SCRIPT_DIR})"
    exit 1
  fi
done

if [[ ! -f "${SCRIPT_DIR}/hooks/intercept-trigger.py" ]]; then
  echo "Error: missing hooks/intercept-trigger.py"
  exit 1
fi

if [[ ! -f "${SCRIPT_DIR}/scripts/trigger.py" ]]; then
  echo "Error: missing scripts/trigger.py"
  exit 1
fi

# ── Check for python3 ────────────────────────────────────────────────────────

if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required for hook and trigger scripts."
  exit 1
fi

# ── Install ──────────────────────────────────────────────────────────────────

COMMANDS_DIR="${TARGET_DIR}/commands/mg"
SUPPORT_DIR="${TARGET_DIR}/cc-regression-test"

echo "Installing cc-regression-test to: ${TARGET_DIR}"

# Commands
mkdir -p "$COMMANDS_DIR"
for cmd in "${COMMANDS[@]}"; do
  cp "${SCRIPT_DIR}/commands/${cmd}.md" "${COMMANDS_DIR}/${cmd}.md"
done
echo "  Commands → ${COMMANDS_DIR}/"

# Supporting files
mkdir -p "${SUPPORT_DIR}/hooks" "${SUPPORT_DIR}/scripts"
cp "${SCRIPT_DIR}/hooks/intercept-trigger.py" "${SUPPORT_DIR}/hooks/"
cp "${SCRIPT_DIR}/scripts/trigger.py" "${SUPPORT_DIR}/scripts/"
chmod +x "${SUPPORT_DIR}/hooks/intercept-trigger.py"
chmod +x "${SUPPORT_DIR}/scripts/trigger.py"
echo "  Hooks    → ${SUPPORT_DIR}/hooks/"
echo "  Scripts  → ${SUPPORT_DIR}/scripts/"

# ── Resolve paths ────────────────────────────────────────────────────────────

HOOKS_ABSOLUTE="${SUPPORT_DIR}/hooks"
SCRIPTS_ABSOLUTE="${SUPPORT_DIR}/scripts"
SOURCE_ABSOLUTE="${SCRIPT_DIR}"

echo "  Resolving placeholders in command files ..."
for cmd in "${COMMANDS[@]}"; do
  cmd_file="${COMMANDS_DIR}/${cmd}.md"
  sed -i "s|{HOOKS_DIR}|${HOOKS_ABSOLUTE}|g" "$cmd_file"
  sed -i "s|{SCRIPTS_DIR}|${SCRIPTS_ABSOLUTE}|g" "$cmd_file"
  sed -i "s|{SOURCE_DIR}|${SOURCE_ABSOLUTE}|g" "$cmd_file"
done

# ── Merge hook into settings.json ────────────────────────────────────────────

SETTINGS_FILE="${TARGET_DIR}/settings.json"
HOOK_CMD="python3 ${HOOKS_ABSOLUTE}/intercept-trigger.py"

echo "  Merging hook config into ${SETTINGS_FILE} ..."

python3 - "$SETTINGS_FILE" "$HOOK_CMD" <<'PYEOF'
import json
import sys

settings_path = sys.argv[1]
hook_cmd = sys.argv[2]

try:
    with open(settings_path) as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    settings = {}

hooks = settings.setdefault("hooks", {})
pre_tool = hooks.setdefault("PreToolUse", [])

# Hook format: {"matcher": "Bash", "hooks": [{"type": "command", "command": "..."}]}
new_entry = {
    "matcher": "Bash",
    "hooks": [{"type": "command", "command": hook_cmd}]
}

# Check if already present (check inside hooks[].command)
already = any(
    isinstance(h, dict)
    and any(
        isinstance(hk, dict) and hk.get("command") == hook_cmd
        for hk in h.get("hooks", [])
    )
    for h in pre_tool
)

if not already:
    pre_tool.append(new_entry)
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    print("    Hook entry added.")
else:
    print("    Hook entry already present.")
PYEOF

# ── Update manifest ──────────────────────────────────────────────────────────
TOOL_SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "${TOOL_SOURCE_DIR}/../install/scripts/mg-install-lib.py" \
  update-manifest \
  --target "$(dirname "$TARGET_DIR")" \
  --tool "$(basename "$TOOL_SOURCE_DIR")" \
  --source "$TOOL_SOURCE_DIR"

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "Done. Installed:"
echo ""
echo "  Commands:"
for cmd in "${COMMANDS[@]}"; do
  echo "    ${COMMANDS_DIR}/${cmd}.md"
done
echo ""
echo "  Supporting files:"
echo "    ${SUPPORT_DIR}/hooks/intercept-trigger.py"
echo "    ${SUPPORT_DIR}/scripts/trigger.py"
echo ""
echo "  Hook config:"
echo "    ${SETTINGS_FILE}"
echo "    Matcher: Bash"
echo "    Command: ${HOOK_CMD}"
echo ""
echo "Invoke with:"
echo "  /mg:cc-regression-test"
echo ""
echo "Note: If this is a fresh install, restart Claude Code for the hook to take effect."
