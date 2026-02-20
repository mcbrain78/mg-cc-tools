#!/usr/bin/env bash
set -euo pipefail

# ── Codebase Health Pipeline — Installer ──────────────────────────────────────
#
# Installs the three codebase-health commands and their supporting files into
# a Claude Code project or global configuration.
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
#
# What it does:
#   1. Copies command files to <target>/commands/mg/
#   2. Copies supporting files (agents, references) to <target>/codebase-health/
#   3. Resolves all relative paths in command files to absolute paths,
#      so the LLM can find agent instructions and schema at runtime.
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=(
  codebase-health
  codebase-health-scan
  codebase-health-verify
  codebase-health-implement
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
      echo "  --global     Install into ~/.claude/"
      echo "  --target     Install into a custom .claude/ directory"
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

if [[ ! -f "${SCRIPT_DIR}/references/schema.md" ]]; then
  echo "Error: missing references/schema.md"
  exit 1
fi

if [[ ! -d "${SCRIPT_DIR}/agents" ]]; then
  echo "Error: missing agents/ directory"
  exit 1
fi

if [[ ! -d "${SCRIPT_DIR}/scripts" ]]; then
  echo "Error: missing scripts/ directory"
  exit 1
fi

# ── Check for python3 ──────────────────────────────────────────────────────

if command -v python3 &>/dev/null; then
  PYTHON_VERSION="$(python3 --version 2>&1)"
  echo "  python3 found: ${PYTHON_VERSION}"
else
  echo "  Warning: python3 not found. The circular-deps and unused-deps scanners"
  echo "  will fall back to LLM-only analysis (slower, uses more context)."
  echo "  Install Python 3.8+ for optimal performance."
fi

# ── Install ───────────────────────────────────────────────────────────────────

COMMANDS_DIR="${TARGET_DIR}/commands/mg"
SUPPORT_DIR="${TARGET_DIR}/codebase-health"

echo "Installing codebase-health pipeline to: ${TARGET_DIR}"

# Commands
echo "  Commands → ${COMMANDS_DIR}/"
mkdir -p "$COMMANDS_DIR"
for cmd in "${COMMANDS[@]}"; do
  cp "${SCRIPT_DIR}/commands/${cmd}.md" "${COMMANDS_DIR}/${cmd}.md"
done

# Supporting files
echo "  Agents   → ${SUPPORT_DIR}/agents/"
echo "  Schema   → ${SUPPORT_DIR}/references/"
echo "  Scripts  → ${SUPPORT_DIR}/scripts/"
if [[ -d "$SUPPORT_DIR" ]]; then
  rm -rf "$SUPPORT_DIR"
fi
mkdir -p "${SUPPORT_DIR}/agents" "${SUPPORT_DIR}/references" "${SUPPORT_DIR}/scripts/lib"
cp "${SCRIPT_DIR}"/agents/*.md "${SUPPORT_DIR}/agents/"
cp "${SCRIPT_DIR}/references/schema.md" "${SUPPORT_DIR}/references/"
cp "${SCRIPT_DIR}"/scripts/*.py "${SUPPORT_DIR}/scripts/"
cp "${SCRIPT_DIR}"/scripts/lib/*.py "${SUPPORT_DIR}/scripts/lib/"
chmod +x "${SUPPORT_DIR}/scripts/"*.py

# Global default config (all install modes)
echo "  Defaults  → ${SUPPORT_DIR}/references/.health-scan.config.json"
cat > "${SUPPORT_DIR}/references/.health-scan.config.json" <<'CONFIGEOF'
{
  "scanner_model": "sonnet",
  "verifier_model": "sonnet",
  "implementer_model": "sonnet"
}
CONFIGEOF

# ── Resolve paths ─────────────────────────────────────────────────────────────
#
# Replace relative placeholders with absolute paths so the LLM can find them
# at runtime without knowing the command file's directory.

SCHEMA_ABSOLUTE="${SUPPORT_DIR}/references/schema.md"
CONFIG_ABSOLUTE="${SUPPORT_DIR}/references/.health-scan.config.json"
AGENTS_ABSOLUTE="${SUPPORT_DIR}/agents"
SCRIPTS_ABSOLUTE="${SUPPORT_DIR}/scripts"

echo "  Resolving paths in command files ..."
for cmd in "${COMMANDS[@]}"; do
  cmd_file="${COMMANDS_DIR}/${cmd}.md"
  # Resolve schema reference (all three commands)
  if grep -q 'references/schema.md' "$cmd_file" 2>/dev/null; then
    sed -i "s|references/schema.md|${SCHEMA_ABSOLUTE}|g" "$cmd_file"
  fi
  # Resolve global config reference (scan, verify, implement)
  if grep -q '{GLOBAL_CONFIG}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{GLOBAL_CONFIG}|${CONFIG_ABSOLUTE}|g" "$cmd_file"
  fi
done

# Resolve agent references in the scanner (all agents/ paths)
SCAN_FILE="${COMMANDS_DIR}/codebase-health-scan.md"
if grep -q 'agents/' "$SCAN_FILE" 2>/dev/null; then
  sed -i "s|agents/|${AGENTS_ABSOLUTE}/|g" "$SCAN_FILE"
fi

# Resolve agent references in the implementor (agents/implementor.md only)
IMPL_FILE="${COMMANDS_DIR}/codebase-health-implement.md"
if grep -q 'agents/implementor.md' "$IMPL_FILE" 2>/dev/null; then
  sed -i "s|agents/implementor.md|${AGENTS_ABSOLUTE}/implementor.md|g" "$IMPL_FILE"
fi

# Resolve {SCRIPTS_DIR} placeholder in agent files
echo "  Resolving {SCRIPTS_DIR} in agent files ..."
for agent_file in "${SUPPORT_DIR}/agents/"*.md; do
  if grep -q '{SCRIPTS_DIR}' "$agent_file" 2>/dev/null; then
    sed -i "s|{SCRIPTS_DIR}|${SCRIPTS_ABSOLUTE}|g" "$agent_file"
  fi
done

# Resolve {SCRIPTS_DIR} placeholder in command files (for script calls)
echo "  Resolving {SCRIPTS_DIR} in command files ..."
for cmd_file in "${COMMANDS_DIR}/"*.md; do
  if grep -q '{SCRIPTS_DIR}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{SCRIPTS_DIR}|${SCRIPTS_ABSOLUTE}|g" "$cmd_file"
  fi
done

# ── Scaffold project .health-scan config ─────────────────────────────────────
#
# For --project installs, also create .health-scan/ with config files in the
# project root. These override the global defaults. Skip files that already
# exist to preserve user edits.

if [[ -n "$PROJECT_ROOT" ]]; then
  HEALTH_DIR="${PROJECT_ROOT}/.health-scan"
  mkdir -p "$HEALTH_DIR"
  echo "  Config    → ${HEALTH_DIR}/"

  # Project config (overrides global defaults)
  CONFIG_FILE="${HEALTH_DIR}/.health-scan.config.json"
  if [[ ! -f "$CONFIG_FILE" ]]; then
    cat > "$CONFIG_FILE" <<'CONFIGEOF'
{
  "scanner_model": "sonnet",
  "verifier_model": "sonnet",
  "implementer_model": "sonnet"
}
CONFIGEOF
    echo "    Created .health-scan.config.json (defaults)"
  else
    echo "    .health-scan.config.json already exists — kept"
  fi

  # Default ignore (empty)
  IGNORE_FILE="${HEALTH_DIR}/.health-ignore"
  if [[ ! -f "$IGNORE_FILE" ]]; then
    touch "$IGNORE_FILE"
    echo "    Created .health-ignore (empty)"
  else
    echo "    .health-ignore already exists — kept"
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "Done. Installed:"
echo ""
echo "  Commands:"
for cmd in "${COMMANDS[@]}"; do
  echo "    ${COMMANDS_DIR}/${cmd}.md"
done
echo ""
echo "  Supporting files:"
echo "    ${SUPPORT_DIR}/references/schema.md"
echo "    ${SUPPORT_DIR}/references/.health-scan.config.json  (global defaults)"
echo "    ${SUPPORT_DIR}/agents/ ($(ls "${SUPPORT_DIR}/agents/" | wc -l) files)"
echo "    ${SUPPORT_DIR}/scripts/ ($(ls "${SUPPORT_DIR}/scripts/"*.py | wc -l) scripts + lib/)"
if [[ -n "$PROJECT_ROOT" ]]; then
echo ""
echo "  Project config (overrides global defaults):"
echo "    ${HEALTH_DIR}/.health-scan.config.json"
echo "    ${HEALTH_DIR}/.health-ignore"
fi
echo ""
echo "Invoke with:"
echo "  /mg:codebase-health              ← start here (guides you through the pipeline)"
echo "  /mg:codebase-health-scan         ← step 1: scan"
echo "  /mg:codebase-health-verify       ← step 2: verify"
echo "  /mg:codebase-health-implement    ← step 3: implement"
