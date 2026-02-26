#!/usr/bin/env bash
set -euo pipefail

# ── Data Provider Field Mapping — Installer ─────────────────────────────────
#
# Installs the map-fields-research command and supporting scripts into
# a Claude Code project or global configuration.
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
#
# What it does:
#   1. Copies command file to <target>/commands/mg/
#   2. Copies Python scripts to <target>/data-provider/scripts/
#   3. Copies reference files to <target>/data-provider/references/
#   4. Copies DESIGN.md to <target>/data-provider/
#   5. Resolves {SCRIPTS_DIR} in the command file to absolute paths
#   6. (--project only) Scaffolds .mg/data-provider/ work directory
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=(
  map-fields-research
)

# ── Parse arguments ───────────────────────────────────────────────────────────

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

# ── Resolve target directory ──────────────────────────────────────────────────

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

# ── Validate source ──────────────────────────────────────────────────────────

for cmd in "${COMMANDS[@]}"; do
  if [[ ! -f "${SCRIPT_DIR}/commands/${cmd}.md" ]]; then
    echo "Error: missing commands/${cmd}.md in source directory (${SCRIPT_DIR})"
    exit 1
  fi
done

if [[ ! -d "${SCRIPT_DIR}/scripts" ]]; then
  echo "Error: missing scripts/ directory"
  exit 1
fi

if [[ ! -d "${SCRIPT_DIR}/references" ]]; then
  echo "Error: missing references/ directory"
  exit 1
fi

# ── Check for python3 ────────────────────────────────────────────────────────

if command -v python3 &>/dev/null; then
  PYTHON_VERSION="$(python3 --version 2>&1)"
  echo "  python3 found: ${PYTHON_VERSION}"
else
  echo "  Warning: python3 not found. The scripts require Python 3.10+."
  echo "  Install Python before using the pipeline."
fi

# ── Install ───────────────────────────────────────────────────────────────────

COMMANDS_DIR="${TARGET_DIR}/commands/mg"
SUPPORT_DIR="${TARGET_DIR}/data-provider"

echo "Installing data-provider field mapping to: ${TARGET_DIR}"

# Commands
echo "  Commands   → ${COMMANDS_DIR}/"
mkdir -p "$COMMANDS_DIR"
for cmd in "${COMMANDS[@]}"; do
  cp "${SCRIPT_DIR}/commands/${cmd}.md" "${COMMANDS_DIR}/${cmd}.md"
done

# Scripts
echo "  Scripts    → ${SUPPORT_DIR}/scripts/"
mkdir -p "${SUPPORT_DIR}/scripts"
cp "${SCRIPT_DIR}"/scripts/*.py "${SUPPORT_DIR}/scripts/"
chmod +x "${SUPPORT_DIR}/scripts/"*.py

# References
echo "  References → ${SUPPORT_DIR}/references/"
mkdir -p "${SUPPORT_DIR}/references"
cp "${SCRIPT_DIR}"/references/*.md "${SUPPORT_DIR}/references/"

# Design doc
echo "  Design     → ${SUPPORT_DIR}/DESIGN.md"
cp "${SCRIPT_DIR}/DESIGN.md" "${SUPPORT_DIR}/DESIGN.md"

# ── Resolve paths ─────────────────────────────────────────────────────────────
#
# Replace {SCRIPTS_DIR} placeholder with absolute path so the LLM can find
# the Python scripts at runtime.

SCRIPTS_ABSOLUTE="${SUPPORT_DIR}/scripts"

echo "  Resolving {SCRIPTS_DIR} in command files ..."
for cmd in "${COMMANDS[@]}"; do
  cmd_file="${COMMANDS_DIR}/${cmd}.md"
  if grep -q '{SCRIPTS_DIR}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{SCRIPTS_DIR}|${SCRIPTS_ABSOLUTE}|g" "$cmd_file"
  fi
done

# ── Scaffold project work directory ──────────────────────────────────────────
#
# For --project installs, create .mg/data-provider/ with the standard
# directory structure and seed the input files.

if [[ -n "$PROJECT_ROOT" ]]; then
  WORK_DIR="${PROJECT_ROOT}/.mg/data-provider"
  echo "  Work dir   → ${WORK_DIR}/"

  mkdir -p "${WORK_DIR}/input" "${WORK_DIR}/tasks" "${WORK_DIR}/output"

  # Copy field reference template (don't overwrite if exists)
  if [[ ! -f "${WORK_DIR}/input/00-field-reference.md" ]]; then
    cp "${SCRIPT_DIR}/references/00-field-reference.md" "${WORK_DIR}/input/00-field-reference.md"
    echo "    Created input/00-field-reference.md (template)"
  else
    echo "    input/00-field-reference.md already exists — kept"
  fi

  # Create empty providers.txt if missing
  if [[ ! -f "${WORK_DIR}/input/providers.txt" ]]; then
    cat > "${WORK_DIR}/input/providers.txt" <<'EOF'
SimFin
Financial Modeling Prep
Alpha Vantage
Polygon
Tiingo
EOF
    echo "    Created input/providers.txt (default providers)"
  else
    echo "    input/providers.txt already exists — kept"
  fi

  # Copy README and DESIGN (don't overwrite)
  if [[ ! -f "${WORK_DIR}/README.md" ]]; then
    cp "${SCRIPT_DIR}/README.md" "${WORK_DIR}/README.md"
    echo "    Created README.md"
  else
    echo "    README.md already exists — kept"
  fi

  if [[ ! -f "${WORK_DIR}/DESIGN.md" ]]; then
    cp "${SCRIPT_DIR}/DESIGN.md" "${WORK_DIR}/DESIGN.md"
    echo "    Created DESIGN.md"
  else
    echo "    DESIGN.md already exists — kept"
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "Done. Installed:"
echo ""
echo "  Command:"
for cmd in "${COMMANDS[@]}"; do
  echo "    ${COMMANDS_DIR}/${cmd}.md"
done
echo ""
echo "  Supporting files:"
echo "    ${SUPPORT_DIR}/scripts/ ($(ls "${SUPPORT_DIR}/scripts/"*.py | wc -l) scripts)"
echo "    ${SUPPORT_DIR}/references/ ($(ls "${SUPPORT_DIR}/references/"*.md | wc -l) files)"
echo "    ${SUPPORT_DIR}/DESIGN.md"
if [[ -n "$PROJECT_ROOT" ]]; then
echo ""
echo "  Project work directory:"
echo "    ${WORK_DIR}/input/00-field-reference.md"
echo "    ${WORK_DIR}/input/providers.txt"
echo "    ${WORK_DIR}/tasks/              (empty — run generate.py to populate)"
echo "    ${WORK_DIR}/output/             (empty — run summarize.py to populate)"
fi
echo ""
echo "Usage:"
echo "  1. Edit .mg/data-provider/input/providers.txt with your provider names"
echo "  2. python ${SCRIPTS_ABSOLUTE}/generate.py        # create task files"
echo "  3. /mg:map-fields-research                        # run research pipeline"
echo "  4. python ${SCRIPTS_ABSOLUTE}/summarize.py        # generate report"
