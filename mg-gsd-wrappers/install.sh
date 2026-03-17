#!/usr/bin/env bash
set -euo pipefail

# ── GSD Wrappers — Installer ────────────────────────────────────────────────
#
# Installs the mg:discuss-milestone, mg:discuss-phase, mg:plan-phase, and
# mg:execute-phase commands into a Claude Code configuration.
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

COMMANDS=(
  discuss-milestone
  discuss-phase
  plan-phase
  execute-phase
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

SNAPSHOT_FILE="discuss-methodology.snapshot.md"
if [[ ! -f "${SCRIPT_DIR}/references/${SNAPSHOT_FILE}" ]]; then
  echo "Error: missing references/${SNAPSHOT_FILE} in source directory (${SCRIPT_DIR})"
  exit 1
fi

PATCH_FILE="discuss-phase-check-remaining.md"
PATCH_SOURCE="${REPO_DIR}/gsd-patches/patches/${PATCH_FILE}"
if [[ ! -f "$PATCH_SOURCE" ]]; then
  echo "Error: missing gsd-patches/patches/${PATCH_FILE} in repo (${REPO_DIR})"
  exit 1
fi

# ── Check for python3 ──────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required. Install it and re-run."
  exit 1
fi

# ── Install ──────────────────────────────────────────────────────────────────

COMMANDS_DIR="${TARGET_DIR}/commands/mg"

echo "Installing gsd-wrappers to: ${TARGET_DIR}"

# Commands
mkdir -p "$COMMANDS_DIR"
for cmd in "${COMMANDS[@]}"; do
  cp "${SCRIPT_DIR}/commands/${cmd}.md" "${COMMANDS_DIR}/${cmd}.md"
done
echo "  Commands → ${COMMANDS_DIR}/"

# Copy methodology snapshot alongside commands
cp "${SCRIPT_DIR}/references/${SNAPSHOT_FILE}" "${COMMANDS_DIR}/${SNAPSHOT_FILE}"
SNAPSHOT_ABSOLUTE="${COMMANDS_DIR}/${SNAPSHOT_FILE}"
echo "  Snapshot → ${SNAPSHOT_ABSOLUTE}"

# ── Resolve placeholders ────────────────────────────────────────────────────

echo "  Resolving {METHODOLOGY_SNAPSHOT} in discuss-milestone.md ..."
cmd_file="${COMMANDS_DIR}/discuss-milestone.md"
if grep -q '{METHODOLOGY_SNAPSHOT}' "$cmd_file" 2>/dev/null; then
  sed -i "s|{METHODOLOGY_SNAPSHOT}|${SNAPSHOT_ABSOLUTE}|g" "$cmd_file"
fi

# ── Copy patch to gsd-patches source ────────────────────────────────────────

PATCHES_SOURCE_DIR="${REPO_DIR}/gsd-patches/patches"
if [[ -d "$PATCHES_SOURCE_DIR" ]]; then
  echo "  Patch already in source: ${PATCHES_SOURCE_DIR}/${PATCH_FILE}"
else
  echo "  Warning: gsd-patches/patches/ not found at ${PATCHES_SOURCE_DIR}"
fi

# Also copy patch to installed gsd-patches if they exist
INSTALLED_PATCHES="${TARGET_DIR}/gsd-patches"
if [[ -d "$INSTALLED_PATCHES" ]]; then
  cp "$PATCH_SOURCE" "${INSTALLED_PATCHES}/${PATCH_FILE}"
  echo "  Patch → ${INSTALLED_PATCHES}/${PATCH_FILE}"
else
  echo "  Note: gsd-patches not installed at ${TARGET_DIR}. Run gsd-patches/install.sh to install patches."
fi

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "Done. Installed:"
echo ""
echo "  Commands:"
for cmd in "${COMMANDS[@]}"; do
  echo "    ${COMMANDS_DIR}/${cmd}.md"
done
echo ""
echo "  Snapshot:"
echo "    ${SNAPSHOT_ABSOLUTE}"
echo ""
echo "  Patch (source):"
echo "    ${PATCHES_SOURCE_DIR}/${PATCH_FILE}"
if [[ -d "$INSTALLED_PATCHES" ]]; then
echo ""
echo "  Patch (installed):"
echo "    ${INSTALLED_PATCHES}/${PATCH_FILE}"
fi
echo ""
echo "Invoke with:"
echo "  /mg:discuss-milestone [milestone-name]  ← batch all phase discussions"
echo "  /mg:discuss-phase <phase-number>        ← deviation-aware discuss"
echo "  /mg:plan-phase <phase-number>           ← deviation-aware plan"
echo "  /mg:execute-phase <phase-number>        ← deviation-flagging execute"
echo ""
echo "Prerequisite: GSD must be installed. Run /mg:apply-gsd-patches to apply the --check-remaining patch."
