#!/usr/bin/env bash
set -euo pipefail

# ── Spec — Installer ──────────────────────────────────────────────────────────
#
# Installs the mg:spec-* commands into a Claude Code configuration.
#
# Commands:
#   mg:spec-draft            Formalize ideas into concept specs
#   mg:spec-improve          Iterative subagent-review improvement
#   mg:spec-improve-auto     Autonomous main-session review+fix loop
#   mg:spec-create-context   Convert concept spec to GSD CONTEXT.md
#   mg:spec-create-milestone Project a frozen concept spec into a GSD milestone
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
  spec-improve-auto
  spec-create-context
  spec-create-milestone
  spec-prepare-context
  spec-gsd-phases
  spec-help
)

REFERENCES=(
  concept-spec-template.md
  context-template.snapshot
  requirements-template.snapshot
)

# Agent instruction files spawned by commands at runtime (handed to a subagent by
# path). They get the same placeholder pass as the command files.
AGENTS=(
  spec-reconcile
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

for agent in "${AGENTS[@]}"; do
  if [[ ! -f "${SCRIPT_DIR}/agents/${agent}.md" ]]; then
    echo "Error: missing agents/${agent}.md in source directory (${SCRIPT_DIR})"
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

# Agents
AGENTS_DIR="${TARGET_DIR}/spec/agents"
mkdir -p "$AGENTS_DIR"
for agent in "${AGENTS[@]}"; do
  cp "${SCRIPT_DIR}/agents/${agent}.md" "${AGENTS_DIR}/${agent}.md"
done
echo "  Agents → ${AGENTS_DIR}/"

# Retire the drain workflow from prior installs (spec-improve-auto is now a
# main-session loop — no Workflow script).
rm -rf "${TARGET_DIR}/spec/workflows"

# References
REFS_DIR="${TARGET_DIR}/spec/references"
mkdir -p "$REFS_DIR"
for ref in "${REFERENCES[@]}"; do
  cp "${SCRIPT_DIR}/references/${ref}" "${REFS_DIR}/${ref}"
done
echo "  References → ${REFS_DIR}/"

# ── Resolve placeholders ─────────────────────────────────────────────────────
#
# In --project mode, emit relative paths so the installed commands work in any
# clone of the target project. In --global/--target mode the tool files live at
# a fixed absolute location, so absolute paths are baked in.

if [[ "$MODE" == "project" ]]; then
  SNAPSHOT_PATH=".claude/spec/references/context-template.snapshot"
  REQ_SNAPSHOT_PATH=".claude/spec/references/requirements-template.snapshot"
  TEMPLATE_PATH=".claude/spec/references/concept-spec-template.md"
  SCRIPTS_PATH=".claude/spec/scripts"
  RECONCILE_AGENT_PATH=".claude/spec/agents/spec-reconcile.md"
else
  SNAPSHOT_PATH="${REFS_DIR}/context-template.snapshot"
  REQ_SNAPSHOT_PATH="${REFS_DIR}/requirements-template.snapshot"
  TEMPLATE_PATH="${REFS_DIR}/concept-spec-template.md"
  SCRIPTS_PATH="${SCRIPTS_DIR}"
  RECONCILE_AGENT_PATH="${AGENTS_DIR}/spec-reconcile.md"
fi

for cmd in "${COMMANDS[@]}"; do
  cmd_file="${COMMANDS_DIR}/${cmd}.md"
  [[ -f "$cmd_file" ]] || continue

  sed -i "s|{MG_INSTALL_TEMPLATE_SNAPSHOT}|${SNAPSHOT_PATH}|g" "$cmd_file"
  sed -i "s|{MG_INSTALL_REQUIREMENTS_SNAPSHOT}|${REQ_SNAPSHOT_PATH}|g" "$cmd_file"
  sed -i "s|{MG_INSTALL_CONCEPT_TEMPLATE}|${TEMPLATE_PATH}|g" "$cmd_file"
  sed -i "s|{MG_INSTALL_SCRIPTS_DIR}|${SCRIPTS_PATH}|g" "$cmd_file"
  sed -i "s|{MG_INSTALL_RECONCILE_AGENT}|${RECONCILE_AGENT_PATH}|g" "$cmd_file"
done

# Agent files get the same script-path substitution the commands get — they call
# improve_files.py themselves.
for agent in "${AGENTS[@]}"; do
  agent_file="${AGENTS_DIR}/${agent}.md"
  [[ -f "$agent_file" ]] || continue

  sed -i "s|{MG_INSTALL_SCRIPTS_DIR}|${SCRIPTS_PATH}|g" "$agent_file"
done
echo "  Placeholders resolved"

# Fail loudly rather than shipping a command that points at a literal placeholder.
LEFTOVER=$(grep -l "{MG_INSTALL_" "${COMMANDS_DIR}"/spec-*.md "${AGENTS_DIR}"/*.md 2>/dev/null || true)
if [[ -n "$LEFTOVER" ]]; then
  echo "Error: unresolved {MG_INSTALL_*} placeholders remain in:"
  echo "$LEFTOVER" | sed 's/^/    /'
  exit 1
fi

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
echo "  Agents:"
for agent in "${AGENTS[@]}"; do
  echo "    ${AGENTS_DIR}/${agent}.md"
done
echo ""
echo "Invoke with:"
echo "  /mg:spec-draft [<source-file-path>]"
echo "  /mg:spec-improve <file-path>"
echo "  /mg:spec-improve-auto <file-path>"
echo "  /mg:spec-create-context <phase-number> <source-file-path>"
echo "  /mg:spec-create-milestone <version> <spec-path>"
echo "  /mg:spec-prepare-context <start>-<end> <source-file-path>"
echo "  /mg:spec-gsd-phases <source-file-path>"
echo "  /mg:spec-help"
echo ""
echo "Prerequisite: GSD must be installed (uses .planning/ROADMAP.md)"
