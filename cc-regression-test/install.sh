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
#   Post-install.md handles settings.json merge via subagent.
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

# The shared settings.json hook merge. Deployed into the target rather than
# called from source, because the command file that uses it runs at runtime in
# the target project and cannot see the mg-cc-tools source tree.
MERGE_HOOK_SRC="${SCRIPT_DIR}/../install/scripts/merge-hook-entry.py"
if [[ ! -f "$MERGE_HOOK_SRC" ]]; then
  echo "Error: missing install/scripts/merge-hook-entry.py"
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
cp "$MERGE_HOOK_SRC" "${SUPPORT_DIR}/scripts/"
chmod +x "${SUPPORT_DIR}/hooks/intercept-trigger.py"
chmod +x "${SUPPORT_DIR}/scripts/trigger.py"
chmod +x "${SUPPORT_DIR}/scripts/merge-hook-entry.py"
echo "  Hooks    → ${SUPPORT_DIR}/hooks/"
echo "  Scripts  → ${SUPPORT_DIR}/scripts/"

# ── Resolve paths ────────────────────────────────────────────────────────────
#
# In --project mode, emit relative paths for the installed hooks/scripts so the
# regression test is portable across clones.
# {MG_INSTALL_SOURCE_DIR} intentionally stays absolute even in project mode: it
# points to the mg-cc-tools source tree (outside .claude/) and is only read by
# the regression test's dev-only sync-check against the source repo. The sync
# check is not portable by design.

if [[ "$MODE" == "project" ]]; then
  HOOKS_PATH=".claude/cc-regression-test/hooks"
  SCRIPTS_PATH=".claude/cc-regression-test/scripts"
  SETTINGS_PATH=".claude/settings.json"
else
  HOOKS_PATH="${SUPPORT_DIR}/hooks"
  SCRIPTS_PATH="${SUPPORT_DIR}/scripts"
  SETTINGS_PATH="${TARGET_DIR}/settings.json"
fi
SOURCE_ABSOLUTE="${SCRIPT_DIR}"

echo "  Resolving placeholders in command files ..."
for cmd in "${COMMANDS[@]}"; do
  cmd_file="${COMMANDS_DIR}/${cmd}.md"
  sed -i "s|{MG_INSTALL_HOOKS_DIR}|${HOOKS_PATH}|g" "$cmd_file"
  sed -i "s|{MG_INSTALL_SCRIPTS_DIR}|${SCRIPTS_PATH}|g" "$cmd_file"
  sed -i "s|{MG_INSTALL_SOURCE_DIR}|${SOURCE_ABSOLUTE}|g" "$cmd_file"
  # merge-hook-entry.py needs the install mode and the settings path resolved at
  # install time: the command runs in the target and cannot re-derive either.
  sed -i "s|{MG_INSTALL_MODE}|${MODE}|g" "$cmd_file"
  sed -i "s|{MG_INSTALL_SETTINGS}|${SETTINGS_PATH}|g" "$cmd_file"
done

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
echo "Invoke with:"
echo "  /mg:cc-regression-test"
echo ""
echo "Next step:"
echo "  Post-install subagent will merge hook entry into settings.json"
