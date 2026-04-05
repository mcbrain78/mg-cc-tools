#!/usr/bin/env bash
set -euo pipefail

# ── Devil's Advocate — Installer ───────────────────────────────────────────
#
# Installs the devils-advocate skill from the external-tools archive.
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
# ───────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── External archive location ─────────────────────────────────────────────

ARCHIVE_NAME="notmanas-claude-code-skills-devils-advocate"
SKILL_PATH="skills/devils-advocate"
EXTERNAL_DIR="${REPO_DIR}/../external-tools/${ARCHIVE_NAME}"

# ── Parse arguments ───────────────────────────────────────────────────────

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

# ── Resolve target directory ──────────────────────────────────────────────

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

# ── Validate external archive ────────────────────────────────────────────

SOURCE_DIR="${EXTERNAL_DIR}/${SKILL_PATH}"

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Error: external archive not found at: ${SOURCE_DIR}"
  echo ""
  echo "Clone it with:"
  echo "  cd ${REPO_DIR}/../external-tools"
  echo "  git clone --depth 1 https://github.com/notmanas/claude-code-skills.git ${ARCHIVE_NAME}"
  exit 1
fi

if [[ ! -f "${SOURCE_DIR}/SKILL.md" ]]; then
  echo "Error: SKILL.md not found in ${SOURCE_DIR}"
  exit 1
fi

# ── Install ───────────────────────────────────────────────────────────────

DEST_DIR="${TARGET_DIR}/skills/devils-advocate"

echo "Installing devils-advocate to: ${DEST_DIR}"

mkdir -p "$DEST_DIR"
cp -r "${SOURCE_DIR}/"* "$DEST_DIR/"

echo "  Skill files → ${DEST_DIR}/"

# ── Update manifest ──────────────────────────────────────────────────────

TOOL_SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "${TOOL_SOURCE_DIR}/../install/scripts/mg-install-lib.py" \
  update-manifest \
  --target "$(dirname "$TARGET_DIR")" \
  --tool "$(basename "$TOOL_SOURCE_DIR")" \
  --source "$TOOL_SOURCE_DIR"

# ── Summary ──────────────────────────────────────────────────────────────

echo ""
echo "Done. Installed:"
echo ""
echo "  ${DEST_DIR}/SKILL.md"
echo "  ${DEST_DIR}/references/ai-blind-spots.md"
echo "  ${DEST_DIR}/references/blind-spots.md"
echo "  ${DEST_DIR}/references/questioning-frameworks.md"
echo ""
echo "Invoke with:"
echo "  /devils-advocate"
