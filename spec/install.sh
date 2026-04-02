#!/usr/bin/env bash
set -euo pipefail

# ── Spec — Installer ──────────────────────────────────────────────────────────
#
# Installs the mg:spec-* commands into a Claude Code configuration.
#
# Commands:
#   mg:spec-draft            Formalize ideas into concept specs
#   mg:spec-improve          Iterative subagent-review improvement
#   mg:spec-create-context   Convert concept spec to GSD CONTEXT.md
#   mg:spec-prepare-context  Split multi-phase doc into per-phase files
#   mg:spec-gsd-phases       Analyze concept doc and create GSD phases
#   mg:spec-help             Show pipeline and usage guide
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=(
  spec-draft
  spec-improve
  spec-create-context
  spec-prepare-context
  spec-gsd-phases
  spec-help
)

REFERENCES=(
  concept-spec-template.md
  context-template.snapshot
)

# ── Parse arguments ───────────────────────────────────────────────────────────

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

# ── Resolve target directory ──────────────────────────────────────────────────

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

# ── Validate source ──────────────────────────────────────────────────────────

for cmd in "${COMMANDS[@]}"; do
  if [[ ! -f "${SCRIPT_DIR}/commands/${cmd}.md" ]]; then
    echo "Error: missing commands/${cmd}.md in source directory (${SCRIPT_DIR})"
    exit 1
  fi
done

for ref in "${REFERENCES[@]}"; do
  if [[ ! -f "${SCRIPT_DIR}/references/${ref}" ]]; then
    echo "Error: missing references/${ref} in source directory (${SCRIPT_DIR})"
    exit 1
  fi
done

# ── Check for python3 ────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required. Install it and re-run."
  exit 1
fi

# ── Migrate from create-context (if present) ─────────────────────────────────

COMMANDS_DIR="${TARGET_DIR}/commands/mg"
MANIFEST_FILE="${TARGET_DIR}/mg-cc-tools.manifest.json"

if [[ -f "${COMMANDS_DIR}/create-context.md" ]] || [[ -d "${TARGET_DIR}/create-context" ]]; then
  echo "  Migrating: removing old create-context installation ..."
  rm -f "${COMMANDS_DIR}/create-context.md" \
        "${COMMANDS_DIR}/prepare-context.md" \
        "${COMMANDS_DIR}/context-template.snapshot"
  rm -rf "${TARGET_DIR}/create-context"

  # Remove stale manifest entry
  if [[ -f "$MANIFEST_FILE" ]]; then
    python3 -c "
import json, sys
p = '$MANIFEST_FILE'
with open(p) as f: m = json.load(f)
if 'tools' in m: m['tools'].pop('create-context', None)
with open(p, 'w') as f: json.dump(m, f, indent=2)
" 2>/dev/null || echo "  Warning: could not clean manifest (non-fatal)"
  fi
fi

# ── Install ──────────────────────────────────────────────────────────────────

echo "Installing spec to: ${TARGET_DIR}"

# Commands
mkdir -p "$COMMANDS_DIR"
for cmd in "${COMMANDS[@]}"; do
  cp "${SCRIPT_DIR}/commands/${cmd}.md" "${COMMANDS_DIR}/${cmd}.md"
done
echo "  Commands → ${COMMANDS_DIR}/"

# Scripts
SCRIPTS_DIR="${TARGET_DIR}/spec/scripts"
mkdir -p "$SCRIPTS_DIR"
cp "${SCRIPT_DIR}/scripts/"*.py "$SCRIPTS_DIR/"
chmod +x "$SCRIPTS_DIR/"*.py
echo "  Scripts → ${SCRIPTS_DIR}/"

# References
REFS_DIR="${TARGET_DIR}/spec/references"
mkdir -p "$REFS_DIR"
for ref in "${REFERENCES[@]}"; do
  cp "${SCRIPT_DIR}/references/${ref}" "${REFS_DIR}/${ref}"
done
echo "  References → ${REFS_DIR}/"

# ── Resolve placeholders ─────────────────────────────────────────────────────

SNAPSHOT_ABSOLUTE="${REFS_DIR}/context-template.snapshot"
TEMPLATE_ABSOLUTE="${REFS_DIR}/concept-spec-template.md"

SCRIPTS_ABSOLUTE="${SCRIPTS_DIR}"

for cmd in "${COMMANDS[@]}"; do
  cmd_file="${COMMANDS_DIR}/${cmd}.md"
  [[ -f "$cmd_file" ]] || continue

  if grep -q '{TEMPLATE_SNAPSHOT}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{TEMPLATE_SNAPSHOT}|${SNAPSHOT_ABSOLUTE}|g" "$cmd_file"
  fi
  if grep -q '{CONCEPT_TEMPLATE}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{CONCEPT_TEMPLATE}|${TEMPLATE_ABSOLUTE}|g" "$cmd_file"
  fi
  if grep -q '{SCRIPTS_DIR}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{SCRIPTS_DIR}|${SCRIPTS_ABSOLUTE}|g" "$cmd_file"
  fi
done
echo "  Placeholders resolved"

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
echo "  References:"
for ref in "${REFERENCES[@]}"; do
  echo "    ${REFS_DIR}/${ref}"
done
echo ""
echo "Invoke with:"
echo "  /mg:spec-draft [<source-file-path>]"
echo "  /mg:spec-improve <file-path>"
echo "  /mg:spec-create-context <phase-number> <source-file-path>"
echo "  /mg:spec-prepare-context <start>-<end> <source-file-path>"
echo "  /mg:spec-gsd-phases <source-file-path>"
echo "  /mg:spec-help"
echo ""
echo "Prerequisite: GSD must be installed (uses .planning/ROADMAP.md)"
