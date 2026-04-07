#!/usr/bin/env bash
set -euo pipefail

# ── Transcript Tools — Installer ──────────────────────────────────────────
#
# Installs transcript commands and supporting Python scripts into
# a Claude Code project or global configuration.
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
#
# What it does:
#   1. Copies command files to <target>/commands/mg/
#   2. Copies Python scripts to <target>/transcript/
#   3. Copies reference docs to <target>/transcript/references/
#   4. Resolves {MG_INSTALL_SCRIPTS_DIR} in command files to absolute paths
# ──────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=(
  transcript-analyze
  transcript-export
)

# ── Parse arguments ───────────────────────────────────────────────────────

TARGET_DIR=""
MODE=""
PROJECT_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      MODE="project"
      shift
      # optional path argument (consume it if it doesn't look like a flag)
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

# ── Resolve target directory ──────────────────────────────────────────────

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

# ── Validate source ──────────────────────────────────────────────────────

for cmd in "${COMMANDS[@]}"; do
  if [[ ! -f "${SCRIPT_DIR}/commands/${cmd}.md" ]]; then
    echo "Error: missing commands/${cmd}.md in source directory (${SCRIPT_DIR})"
    exit 1
  fi
done

for script in cc_transcript_analyzer.py cc_transcript_compactor.py cc_transcript_exporter.py; do
  if [[ ! -f "${SCRIPT_DIR}/${script}" ]]; then
    echo "Error: missing ${script}"
    exit 1
  fi
done

if [[ ! -f "${SCRIPT_DIR}/hooks/inject-transcript-path.py" ]]; then
  echo "Error: missing hooks/inject-transcript-path.py"
  exit 1
fi

# ── Check for python3 ────────────────────────────────────────────────────

if command -v python3 &>/dev/null; then
  PYTHON_VERSION="$(python3 --version 2>&1)"
  echo "  python3 found: ${PYTHON_VERSION}"
else
  echo "Error: python3 is required. The transcript scripts need Python 3.11+."
  exit 1
fi

# ── Install ───────────────────────────────────────────────────────────────

COMMANDS_DIR="${TARGET_DIR}/commands/mg"
SUPPORT_DIR="${TARGET_DIR}/transcript"

echo "Installing transcript tools to: ${TARGET_DIR}"

# Commands
echo "  Commands → ${COMMANDS_DIR}/"
mkdir -p "$COMMANDS_DIR"
for cmd in "${COMMANDS[@]}"; do
  cp "${SCRIPT_DIR}/commands/${cmd}.md" "${COMMANDS_DIR}/${cmd}.md"
done

# Supporting files (Python scripts)
echo "  Scripts  → ${SUPPORT_DIR}/"
mkdir -p "${SUPPORT_DIR}"
cp "${SCRIPT_DIR}/cc_transcript_analyzer.py" "${SUPPORT_DIR}/"
cp "${SCRIPT_DIR}/cc_transcript_compactor.py" "${SUPPORT_DIR}/"
cp "${SCRIPT_DIR}/cc_transcript_exporter.py" "${SUPPORT_DIR}/"
chmod +x "${SUPPORT_DIR}/"*.py

# Reference docs
echo "  Refs     → ${SUPPORT_DIR}/references/"
mkdir -p "${SUPPORT_DIR}/references"
cp "${SCRIPT_DIR}/references/transcript-json-schema.md" "${SUPPORT_DIR}/references/"

# Hook script
echo "  Hooks    → ${SUPPORT_DIR}/hooks/"
mkdir -p "${SUPPORT_DIR}/hooks"
cp "${SCRIPT_DIR}/hooks/inject-transcript-path.py" "${SUPPORT_DIR}/hooks/"
chmod +x "${SUPPORT_DIR}/hooks/inject-transcript-path.py"

# ── Resolve paths ─────────────────────────────────────────────────────────
#
# Replace {MG_INSTALL_SCRIPTS_DIR} placeholder with absolute path so the LLM can find
# the Python scripts at runtime.

SCRIPTS_ABSOLUTE="${SUPPORT_DIR}"

echo "  Resolving {MG_INSTALL_SCRIPTS_DIR} in command files ..."
for cmd in "${COMMANDS[@]}"; do
  cmd_file="${COMMANDS_DIR}/${cmd}.md"
  if grep -q '{MG_INSTALL_SCRIPTS_DIR}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_SCRIPTS_DIR}|${SCRIPTS_ABSOLUTE}|g" "$cmd_file"
  fi
done

# ── Update manifest ──────────────────────────────────────────────────────
TOOL_SOURCE_DIR="${SCRIPT_DIR}"
if command -v python3 &>/dev/null; then
  MG_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
  python3 "${MG_ROOT}/install/scripts/mg-install-lib.py" update-manifest \
    --target "$(dirname "$TARGET_DIR")" \
    --tool transcript \
    --source "${TOOL_SOURCE_DIR}" 2>/dev/null || true
fi

# ── Summary ───────────────────────────────────────────────────────────────

echo ""
echo "Done. Installed:"
echo ""
echo "  Commands:"
for cmd in "${COMMANDS[@]}"; do
  echo "    ${COMMANDS_DIR}/${cmd}.md"
done
echo ""
echo "  Supporting files:"
echo "    ${SUPPORT_DIR}/cc_transcript_analyzer.py"
echo "    ${SUPPORT_DIR}/cc_transcript_compactor.py"
echo "    ${SUPPORT_DIR}/cc_transcript_exporter.py"
echo "    ${SUPPORT_DIR}/references/transcript-json-schema.md"
echo "    ${SUPPORT_DIR}/hooks/inject-transcript-path.py"
echo ""
echo "Next step:"
echo "  Post-install subagent will register the hook in settings.json"
