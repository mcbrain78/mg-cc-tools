#!/usr/bin/env bash
set -euo pipefail

# ── Create Context — Installer ──────────────────────────────────────────────
#
# Installs the mg:create-context command into a Claude Code configuration.
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=(
  create-context
  prepare-context
)

# ── Parse arguments ──────────────────────────────────────────────────────────

TARGET_DIR=""
MODE=""

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

SNAPSHOT_FILE="context-template.snapshot"
if [[ ! -f "${SCRIPT_DIR}/commands/${SNAPSHOT_FILE}" ]]; then
  echo "Error: missing commands/${SNAPSHOT_FILE} in source directory (${SCRIPT_DIR})"
  exit 1
fi

# ── Check for python3 ──────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required. Install it and re-run."
  exit 1
fi

# ── Install ──────────────────────────────────────────────────────────────────

COMMANDS_DIR="${TARGET_DIR}/commands/mg"

echo "Installing create-context to: ${TARGET_DIR}"

mkdir -p "$COMMANDS_DIR"
for cmd in "${COMMANDS[@]}"; do
  cp "${SCRIPT_DIR}/commands/${cmd}.md" "${COMMANDS_DIR}/${cmd}.md"
done

# Copy template snapshot alongside command
cp "${SCRIPT_DIR}/commands/${SNAPSHOT_FILE}" "${COMMANDS_DIR}/${SNAPSHOT_FILE}"

# Resolve {TEMPLATE_SNAPSHOT} placeholder in command file
SNAPSHOT_ABSOLUTE="${COMMANDS_DIR}/${SNAPSHOT_FILE}"
cmd_file="${COMMANDS_DIR}/create-context.md"
if grep -q '{TEMPLATE_SNAPSHOT}' "$cmd_file" 2>/dev/null; then
  sed -i "s|{TEMPLATE_SNAPSHOT}|${SNAPSHOT_ABSOLUTE}|g" "$cmd_file"
fi

echo "  Commands → ${COMMANDS_DIR}/"
echo "  Snapshot → ${SNAPSHOT_ABSOLUTE}"

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
echo "  Snapshot:"
echo "    ${SNAPSHOT_ABSOLUTE}"
echo ""
echo "Invoke with:"
echo "  /mg:create-context <phase-number> <source-file-path>"
echo "  /mg:prepare-context <start>-<end> <source-file-path>"
echo ""
echo "Prerequisite: GSD must be installed (uses .claude/get-shit-done/templates/context.md)"
