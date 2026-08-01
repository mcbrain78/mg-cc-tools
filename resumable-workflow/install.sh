#!/usr/bin/env bash
set -euo pipefail

# ── Resumable Workflow — Installer ────────────────────────────────────────────
#
# Installs the mg:resumable-workflow command into a Claude Code configuration.
#
# Commands:
#   mg:resumable-workflow    Dynamic investigation loop that survives a session death
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=(
  resumable-workflow
)

# Agent instruction files spawned by the command at runtime (handed to a subagent
# by absolute path). They get the same placeholder pass as the command files —
# each one calls run_state.py itself.
AGENTS=(
  digest
  decompose
  research
  verify
  assess
  summarize
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

for agent in "${AGENTS[@]}"; do
  if [[ ! -f "${SCRIPT_DIR}/agents/${agent}.md" ]]; then
    echo "Error: missing agents/${agent}.md in source directory (${SCRIPT_DIR})"
    exit 1
  fi
done

if [[ ! -f "${SCRIPT_DIR}/scripts/run_state.py" ]]; then
  echo "Error: missing scripts/run_state.py in source directory (${SCRIPT_DIR})"
  exit 1
fi

# ── Check for python3 ────────────────────────────────────────────────────────
#
# tool.toml preflight only runs under /mg:install, so a direct install.sh needs
# its own check. run_state.py is stdlib-only — no venv required.
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 is required. Install it and re-run."
  exit 1
fi

# ── Install ──────────────────────────────────────────────────────────────────

COMMANDS_DIR="${TARGET_DIR}/commands/mg"

echo "Installing resumable-workflow to: ${TARGET_DIR}"

# Commands
mkdir -p "$COMMANDS_DIR"
for cmd in "${COMMANDS[@]}"; do
  cp "${SCRIPT_DIR}/commands/${cmd}.md" "${COMMANDS_DIR}/${cmd}.md"
done
echo "  Commands → ${COMMANDS_DIR}/"

# Scripts (the *.py glob deliberately excludes tests/)
SCRIPTS_DIR="${TARGET_DIR}/resumable-workflow/scripts"
mkdir -p "$SCRIPTS_DIR"
cp "${SCRIPT_DIR}/scripts/"*.py "$SCRIPTS_DIR/"
chmod +x "$SCRIPTS_DIR/"*.py
echo "  Scripts → ${SCRIPTS_DIR}/"

# Agents
AGENTS_DIR="${TARGET_DIR}/resumable-workflow/agents"
mkdir -p "$AGENTS_DIR"
for agent in "${AGENTS[@]}"; do
  cp "${SCRIPT_DIR}/agents/${agent}.md" "${AGENTS_DIR}/${agent}.md"
done
echo "  Agents → ${AGENTS_DIR}/"

# Run directories are created lazily by `run_state.py resolve` under the
# project's .mg/, so nothing is scaffolded here.

# ── Resolve placeholders ─────────────────────────────────────────────────────
#
# In --project mode, emit relative paths so the installed command works in any
# clone of the target project. In --global/--target mode the tool files live at a
# fixed absolute location, so absolute paths are baked in.

if [[ "$MODE" == "project" ]]; then
  SCRIPTS_PATH=".claude/resumable-workflow/scripts"
  AGENTS_PATH=".claude/resumable-workflow/agents"
else
  SCRIPTS_PATH="${SCRIPTS_DIR}"
  AGENTS_PATH="${AGENTS_DIR}"
fi

for cmd in "${COMMANDS[@]}"; do
  cmd_file="${COMMANDS_DIR}/${cmd}.md"
  [[ -f "$cmd_file" ]] || continue

  sed -i "s|{MG_INSTALL_SCRIPTS_DIR}|${SCRIPTS_PATH}|g" "$cmd_file"
  sed -i "s|{MG_INSTALL_AGENTS_DIR}|${AGENTS_PATH}|g" "$cmd_file"
done

# Agent files call run_state.py themselves, so they get the same substitution.
for agent in "${AGENTS[@]}"; do
  agent_file="${AGENTS_DIR}/${agent}.md"
  [[ -f "$agent_file" ]] || continue

  sed -i "s|{MG_INSTALL_SCRIPTS_DIR}|${SCRIPTS_PATH}|g" "$agent_file"
  sed -i "s|{MG_INSTALL_AGENTS_DIR}|${AGENTS_PATH}|g" "$agent_file"
done
echo "  Placeholders resolved"

# Fail loudly rather than shipping a command that points at a literal placeholder.
LEFTOVER=$(grep -l "{MG_INSTALL_" \
  "${COMMANDS_DIR}/resumable-workflow.md" \
  "${AGENTS_DIR}"/*.md 2>/dev/null || true)
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
echo "  Agents:"
for agent in "${AGENTS[@]}"; do
  echo "    ${AGENTS_DIR}/${agent}.md"
done
echo "  Scripts:"
echo "    ${SCRIPTS_DIR}/run_state.py"
echo ""
echo "Invoke with:"
echo "  /mg:resumable-workflow <task>"
echo ""
echo "Re-typing the same task resumes that run — state lives in .mg/resumable-workflow/runs/"
