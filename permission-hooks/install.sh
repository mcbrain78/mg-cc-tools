#!/usr/bin/env bash
set -euo pipefail

# ── Permission Hooks — Installer ────────────────────────────────────────────
#
# Installs the permission-guard hook into a Claude Code configuration.
# Copies files only — does NOT edit settings.json.
# Post-install.md handles settings.json registration via subagent.
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=()

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
    # TARGET_DIR already set — derive PROJECT_ROOT if target is a .claude dir
    if [[ "$TARGET_DIR" == */.claude ]]; then
      PROJECT_ROOT="$(cd "$(dirname "$TARGET_DIR")" && pwd)"
    else
      PROJECT_ROOT=""
    fi
    ;;
esac

# ── Validate source ─────────────────────────────────────────────────────────

if [[ ! -f "${SCRIPT_DIR}/hooks/permission-guard.py" ]]; then
  echo "Error: missing hooks/permission-guard.py"
  exit 1
fi

if [[ ! -f "${SCRIPT_DIR}/scripts/emit-context.py" ]]; then
  echo "Error: missing scripts/emit-context.py"
  exit 1
fi

if [[ ! -f "${SCRIPT_DIR}/scripts/emit-edit-guard.py" ]]; then
  echo "Error: missing scripts/emit-edit-guard.py"
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

# Hook file
mkdir -p "${SUPPORT_DIR}/hooks"
cp "${SCRIPT_DIR}/hooks/permission-guard.py" "${SUPPORT_DIR}/hooks/"
chmod +x "${SUPPORT_DIR}/hooks/permission-guard.py"
echo "  Hooks    → ${SUPPORT_DIR}/hooks/"

# Scripts
mkdir -p "${SUPPORT_DIR}/scripts"
cp "${SCRIPT_DIR}/scripts/emit-context.py" "${SUPPORT_DIR}/scripts/"
cp "${SCRIPT_DIR}/scripts/emit-edit-guard.py" "${SUPPORT_DIR}/scripts/"
chmod +x "${SUPPORT_DIR}/scripts/emit-context.py"
chmod +x "${SUPPORT_DIR}/scripts/emit-edit-guard.py"
echo "  Scripts  → ${SUPPORT_DIR}/scripts/"

# Commands
mkdir -p "${COMMANDS_DIR}"
cp "${SCRIPT_DIR}/commands/edit-on.md" "${COMMANDS_DIR}/"
cp "${SCRIPT_DIR}/commands/edit-off.md" "${COMMANDS_DIR}/"
cp "${SCRIPT_DIR}/commands/auto-approve.md" "${COMMANDS_DIR}/"
echo "  Commands → ${COMMANDS_DIR}/ (edit-on.md, edit-off.md, auto-approve.md)"

# ── Resolve placeholders ────────────────────────────────────────────────────

echo "  Resolving placeholders ..."

# Hook file: {MG_INSTALL_PROJECT_ROOT}
hook_file="${SUPPORT_DIR}/hooks/permission-guard.py"
sed -i "s|{MG_INSTALL_PROJECT_ROOT}|${PROJECT_ROOT}|g" "$hook_file"

# Command files: {MG_INSTALL_EMIT_EDIT_GUARD_SCRIPT}
EMIT_EDIT_GUARD_ABS="${SUPPORT_DIR}/scripts/emit-edit-guard.py"
for cmd_file in "${COMMANDS_DIR}/edit-on.md" "${COMMANDS_DIR}/edit-off.md"; do
  if [[ -f "$cmd_file" ]]; then
    sed -i "s|{MG_INSTALL_EMIT_EDIT_GUARD_SCRIPT}|${EMIT_EDIT_GUARD_ABS}|g" "$cmd_file"
  fi
done

# Command file: {MG_INSTALL_EMIT_CONTEXT_SCRIPT}
EMIT_CONTEXT_ABS="${SUPPORT_DIR}/scripts/emit-context.py"
sed -i "s|{MG_INSTALL_EMIT_CONTEXT_SCRIPT}|${EMIT_CONTEXT_ABS}|g" "${COMMANDS_DIR}/auto-approve.md"

# ── Clean up stale files ───────────────────────────────────────────────────

# Clean up stale command from v1.0
STALE_CMD="${COMMANDS_DIR}/install-permission-hooks.md"
if [[ -f "$STALE_CMD" ]]; then
  rm "$STALE_CMD"
  echo "  Removed stale: install-permission-hooks.md"
fi

# Clean up stale underscore-named commands (renamed to hyphenated in v2.1)
for stale in "edit_on.md" "edit_off.md"; do
  if [[ -f "${COMMANDS_DIR}/${stale}" ]]; then
    rm "${COMMANDS_DIR}/${stale}"
    echo "  Removed stale: ${stale}"
  fi
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
echo "  Hook:"
echo "    ${SUPPORT_DIR}/hooks/permission-guard.py"
if [[ -n "$PROJECT_ROOT" ]]; then
  echo "    PROJECT_ROOT: ${PROJECT_ROOT}"
else
  echo "    PROJECT_ROOT: (empty — falls back to cwd from hook event)"
fi
echo ""
echo "Next step:"
echo "  Post-install subagent will register the hook in settings.json"
