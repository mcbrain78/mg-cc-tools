#!/usr/bin/env bash
set -euo pipefail

# ── Permission Hooks — Installer ────────────────────────────────────────────
#
# Installs the permission-guard hook and management command into a Claude Code
# configuration. Copies files only — does NOT edit settings.json.
# Run /mg:install-permission-hooks after install to register the hook.
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=(
  install-permission-hooks
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
    PROJECT_ROOT="$(cd "${PROJECT_PATH:-.}" && pwd)"
    TARGET_DIR="${PROJECT_ROOT}/.claude"
    ;;
  global)
    PROJECT_ROOT=""
    TARGET_DIR="${HOME}/.claude"
    ;;
  custom)
    PROJECT_ROOT=""
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

if [[ ! -f "${SCRIPT_DIR}/hooks/permission-guard.py" ]]; then
  echo "Error: missing hooks/permission-guard.py"
  exit 1
fi

# ── Check for python3 ───────────────────────────────────────────────────────

if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required for the permission-guard hook."
  exit 1
fi

# ── Install ──────────────────────────────────────────────────────────────────

COMMANDS_DIR="${TARGET_DIR}/commands/mg"
SUPPORT_DIR="${TARGET_DIR}/permission-hooks"

echo "Installing permission-hooks to: ${TARGET_DIR}"

# Commands
mkdir -p "$COMMANDS_DIR"
for cmd in "${COMMANDS[@]}"; do
  cp "${SCRIPT_DIR}/commands/${cmd}.md" "${COMMANDS_DIR}/${cmd}.md"
done
echo "  Commands → ${COMMANDS_DIR}/"

# Hook file
mkdir -p "${SUPPORT_DIR}/hooks"
cp "${SCRIPT_DIR}/hooks/permission-guard.py" "${SUPPORT_DIR}/hooks/"
chmod +x "${SUPPORT_DIR}/hooks/permission-guard.py"
echo "  Hooks    → ${SUPPORT_DIR}/hooks/"

# ── Resolve placeholders ────────────────────────────────────────────────────

HOOKS_ABSOLUTE="${SUPPORT_DIR}/hooks"
SOURCE_ABSOLUTE="${SCRIPT_DIR}"

echo "  Resolving placeholders ..."

# Command file: {HOOKS_DIR} and {SOURCE_DIR}
for cmd in "${COMMANDS[@]}"; do
  cmd_file="${COMMANDS_DIR}/${cmd}.md"
  sed -i "s|{HOOKS_DIR}|${HOOKS_ABSOLUTE}|g" "$cmd_file"
  sed -i "s|{SOURCE_DIR}|${SOURCE_ABSOLUTE}|g" "$cmd_file"
done

# Hook file: {PROJECT_ROOT}
hook_file="${SUPPORT_DIR}/hooks/permission-guard.py"
sed -i "s|{PROJECT_ROOT}|${PROJECT_ROOT}|g" "$hook_file"

# ── Update manifest ──────────────────────────────────────────────────────────
TOOL_SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "${TOOL_SOURCE_DIR}/../install/scripts/mg-install-lib.py" \
  update-manifest \
  --target "$TARGET_DIR" \
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
echo "  Hook:"
echo "    ${SUPPORT_DIR}/hooks/permission-guard.py"
if [[ -n "$PROJECT_ROOT" ]]; then
  echo "    PROJECT_ROOT: ${PROJECT_ROOT}"
else
  echo "    PROJECT_ROOT: (empty — falls back to cwd from hook event)"
fi
echo ""
echo "Next step:"
echo "  Run /mg:install-permission-hooks to register the hook in settings.json"
echo ""
echo "Invoke with:"
echo "  /mg:install-permission-hooks"
