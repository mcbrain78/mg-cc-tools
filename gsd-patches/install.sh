#!/usr/bin/env bash
set -euo pipefail

# ── GSD Patches — Installer ─────────────────────────────────────────────────
#
# Installs the mg:apply-gsd-patches command and patch definitions into a
# Claude Code configuration.
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=(
  apply-gsd-patches
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

if [[ ! -d "${SCRIPT_DIR}/patches" ]]; then
  echo "Error: missing patches/ directory"
  exit 1
fi

# ── Install ──────────────────────────────────────────────────────────────────

COMMANDS_DIR="${TARGET_DIR}/commands/mg"
PATCHES_DIR="${TARGET_DIR}/gsd-patches"

echo "Installing gsd-patches to: ${TARGET_DIR}"

# Commands
mkdir -p "$COMMANDS_DIR"
for cmd in "${COMMANDS[@]}"; do
  cp "${SCRIPT_DIR}/commands/${cmd}.md" "${COMMANDS_DIR}/${cmd}.md"
done
echo "  Commands → ${COMMANDS_DIR}/"

# Patch definitions
if [[ -d "$PATCHES_DIR" ]]; then
  rm -rf "$PATCHES_DIR"
fi
mkdir -p "$PATCHES_DIR"
cp "${SCRIPT_DIR}"/patches/*.md "$PATCHES_DIR/"
echo "  Patches  → ${PATCHES_DIR}/"

# ── Resolve paths ────────────────────────────────────────────────────────────

PATCHES_ABSOLUTE="$PATCHES_DIR"

echo "  Resolving {PATCHES_DIR} in command files ..."
for cmd in "${COMMANDS[@]}"; do
  cmd_file="${COMMANDS_DIR}/${cmd}.md"
  if grep -q '{PATCHES_DIR}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{PATCHES_DIR}|${PATCHES_ABSOLUTE}|g" "$cmd_file"
  fi
done

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "Done. Installed:"
echo ""
echo "  Commands:"
for cmd in "${COMMANDS[@]}"; do
  echo "    ${COMMANDS_DIR}/${cmd}.md"
done
echo ""
echo "  Patches:"
for patch in "${PATCHES_DIR}"/*.md; do
  echo "    ${patch}"
done
echo ""
echo "Invoke with:"
echo "  /mg:apply-gsd-patches <project-name-or-path>"
