#!/usr/bin/env bash
set -euo pipefail

# -- Create-Docs Pipeline -- Installer ----------------------------------------
#
# Installs the create-docs tool and its supporting files into a Claude Code
# project or global configuration.
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
#
# What it does:
#   1. Copies command files to <target>/commands/mg/
#   2. Copies supporting files (scripts, references, agents) to <target>/create-docs/
#   3. Resolves all relative paths in command files to absolute paths,
#      so the LLM can find scripts, agents, and references at runtime.
#   4. (--project only) Scaffolds .mg/docs/ workspace with config, inbox, scan-logs.
# ------------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=(
  create-docs
  create-docs-scan
  create-docs-generate
  create-docs-verify
  add-docs
)

# -- Parse arguments -----------------------------------------------------------

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
      if [[ $# -lt 2 ]]; then
        echo "Error: --target requires a path argument"
        exit 1
      fi
      TARGET_DIR="$2"
      shift 2
      ;;
    -h|--help)
      echo "Usage: ./install.sh [--project [<dir>] | --global | --target <path>]"
      echo ""
      echo "  --project [<dir>]  Install into <dir>/.claude/ (default: current directory)"
      echo "  --global           Install into ~/.claude/"
      echo "  --target <path>    Install into a custom .claude/ directory"
      echo ""
      echo "Invoke with:"
      echo "  /mg:create-docs           <- router (guides you through the pipeline)"
      echo "  /mg:create-docs-scan      <- step 1: scan"
      echo "  /mg:create-docs-generate  <- step 2: generate"
      echo "  /mg:create-docs-verify    <- step 3: verify"
      echo "  /mg:add-docs              <- capture notes"
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

# -- Resolve target directory --------------------------------------------------

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

# -- Validate source -----------------------------------------------------------

echo "Validating source files ..."

for cmd in "${COMMANDS[@]}"; do
  if [[ ! -f "${SCRIPT_DIR}/commands/${cmd}.md" ]]; then
    echo "Error: missing commands/${cmd}.md in source directory (${SCRIPT_DIR})"
    exit 1
  fi
done

if [[ ! -d "${SCRIPT_DIR}/commands" ]]; then
  echo "Error: missing commands/ directory in ${SCRIPT_DIR}"
  exit 1
fi

if [[ ! -d "${SCRIPT_DIR}/scripts" ]]; then
  echo "Error: missing scripts/ directory in ${SCRIPT_DIR}"
  exit 1
fi

if [[ ! -d "${SCRIPT_DIR}/scripts/lib" ]]; then
  echo "Error: missing scripts/lib/ directory in ${SCRIPT_DIR}"
  exit 1
fi

if [[ ! -d "${SCRIPT_DIR}/references" ]]; then
  echo "Error: missing references/ directory in ${SCRIPT_DIR}"
  exit 1
fi

if [[ ! -f "${SCRIPT_DIR}/references/schema.md" ]]; then
  echo "Error: missing references/schema.md"
  exit 1
fi

if [[ ! -f "${SCRIPT_DIR}/references/style-guide.md" ]]; then
  echo "Error: missing references/style-guide.md"
  exit 1
fi

if [[ ! -f "${SCRIPT_DIR}/references/.docs.config.json" ]]; then
  echo "Error: missing references/.docs.config.json"
  exit 1
fi

if [[ ! -d "${SCRIPT_DIR}/references/templates" ]]; then
  echo "Error: missing references/templates/ directory in ${SCRIPT_DIR}"
  exit 1
fi

# -- Check for python3 ---------------------------------------------------------

if command -v python3 &>/dev/null; then
  PYTHON_VERSION="$(python3 --version 2>&1)"
  echo "  python3 found: ${PYTHON_VERSION}"
else
  echo "Error: python3 is required. Documentation scripts need Python 3.8+."
  exit 1
fi

# -- Install -------------------------------------------------------------------

COMMANDS_DIR="${TARGET_DIR}/commands/mg"
SUPPORT_DIR="${TARGET_DIR}/create-docs"

echo "Installing create-docs pipeline to: ${TARGET_DIR}"

# Commands
echo "  Commands -> ${COMMANDS_DIR}/"
mkdir -p "$COMMANDS_DIR"
for cmd in "${COMMANDS[@]}"; do
  cp "${SCRIPT_DIR}/commands/${cmd}.md" "${COMMANDS_DIR}/${cmd}.md"
done

# Supporting files
echo "  Scripts    -> ${SUPPORT_DIR}/scripts/"
echo "  References -> ${SUPPORT_DIR}/references/"
echo "  Agents     -> ${SUPPORT_DIR}/agents/"

mkdir -p "${SUPPORT_DIR}/scripts/lib"
mkdir -p "${SUPPORT_DIR}/references"
mkdir -p "${SUPPORT_DIR}/agents"

# Copy scripts
for py_file in "${SCRIPT_DIR}"/scripts/*.py; do
  if [[ -f "$py_file" ]]; then
    cp "$py_file" "${SUPPORT_DIR}/scripts/"
  fi
done

# Copy scripts/lib
for py_file in "${SCRIPT_DIR}"/scripts/lib/*.py; do
  if [[ -f "$py_file" ]]; then
    cp "$py_file" "${SUPPORT_DIR}/scripts/lib/"
  fi
done

# Copy references
cp "${SCRIPT_DIR}/references/schema.md" "${SUPPORT_DIR}/references/"
cp "${SCRIPT_DIR}/references/style-guide.md" "${SUPPORT_DIR}/references/"
cp "${SCRIPT_DIR}/references/.docs.config.json" "${SUPPORT_DIR}/references/"

# Copy templates (recursive -- preserves audience subdirectory structure)
echo "  Templates  -> ${SUPPORT_DIR}/references/templates/"
cp -r "${SCRIPT_DIR}/references/templates" "${SUPPORT_DIR}/references/"

# Copy agents (if any exist -- Phase 2 adds them)
if ls "${SCRIPT_DIR}"/agents/*.md &>/dev/null 2>&1; then
  cp "${SCRIPT_DIR}"/agents/*.md "${SUPPORT_DIR}/agents/"
fi

# Make scripts executable
chmod +x "${SUPPORT_DIR}/scripts/"*.py

# -- Resolve paths -------------------------------------------------------------
#
# Replace relative placeholders with absolute paths so the LLM can find them
# at runtime without knowing the command file's directory.

SCHEMA_ABS="${SUPPORT_DIR}/references/schema.md"
STYLE_GUIDE_ABS="${SUPPORT_DIR}/references/style-guide.md"
CONFIG_ABS="${SUPPORT_DIR}/references/.docs.config.json"
AGENTS_ABS="${SUPPORT_DIR}/agents"
SCRIPTS_ABS="${SUPPORT_DIR}/scripts"
TEMPLATES_ABS="${SUPPORT_DIR}/references/templates"

echo "  Resolving path placeholders in command files ..."
for cmd in "${COMMANDS[@]}"; do
  cmd_file="${COMMANDS_DIR}/${cmd}.md"
  if [[ ! -f "$cmd_file" ]]; then
    continue
  fi
  # Resolve schema reference
  if grep -q 'references/schema.md' "$cmd_file" 2>/dev/null; then
    sed -i "s|references/schema.md|${SCHEMA_ABS}|g" "$cmd_file"
  fi
  # Resolve style guide reference
  if grep -q 'references/style-guide.md' "$cmd_file" 2>/dev/null; then
    sed -i "s|references/style-guide.md|${STYLE_GUIDE_ABS}|g" "$cmd_file"
  fi
  # Resolve global config placeholder
  if grep -q '{GLOBAL_CONFIG}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{GLOBAL_CONFIG}|${CONFIG_ABS}|g" "$cmd_file"
  fi
  # Resolve scripts dir placeholder
  if grep -q '{SCRIPTS_DIR}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{SCRIPTS_DIR}|${SCRIPTS_ABS}|g" "$cmd_file"
  fi
  # Resolve templates dir placeholder
  if grep -q '{TEMPLATES_DIR}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{TEMPLATES_DIR}|${TEMPLATES_ABS}|g" "$cmd_file"
  fi
  # Resolve agents/ prefix (bare path reference to agent files)
  # Only match agents/ followed by a lowercase letter -- real agent files use
  # lowercase names (e.g., agents/verifier.md). Audience-category paths like
  # agents/SYSTEM_MAP.md use uppercase and must NOT be rewritten.
  if grep -q 'agents/[a-z{]' "$cmd_file" 2>/dev/null; then
    sed -i 's|agents/\([a-z{]\)|'"${AGENTS_ABS}"'/\1|g' "$cmd_file"
  fi
done

# Resolve placeholders in agent files (Phase 2 adds agents)
echo "  Resolving path placeholders in agent files ..."
for agent_file in "${SUPPORT_DIR}/agents/"*.md; do
  if [[ ! -f "$agent_file" ]]; then
    continue
  fi
  if grep -q 'references/schema.md' "$agent_file" 2>/dev/null; then
    sed -i "s|references/schema.md|${SCHEMA_ABS}|g" "$agent_file"
  fi
  if grep -q 'references/style-guide.md' "$agent_file" 2>/dev/null; then
    sed -i "s|references/style-guide.md|${STYLE_GUIDE_ABS}|g" "$agent_file"
  fi
  if grep -q '{GLOBAL_CONFIG}' "$agent_file" 2>/dev/null; then
    sed -i "s|{GLOBAL_CONFIG}|${CONFIG_ABS}|g" "$agent_file"
  fi
  if grep -q '{SCRIPTS_DIR}' "$agent_file" 2>/dev/null; then
    sed -i "s|{SCRIPTS_DIR}|${SCRIPTS_ABS}|g" "$agent_file"
  fi
  if grep -q '{TEMPLATES_DIR}' "$agent_file" 2>/dev/null; then
    sed -i "s|{TEMPLATES_DIR}|${TEMPLATES_ABS}|g" "$agent_file"
  fi
done

# -- Scaffold project workspace ------------------------------------------------
#
# For --project installs, create .mg/docs/ with default config, empty inbox,
# and scan-logs directory. Skip if .mg/docs/ already exists to preserve
# user customizations.

if [[ -n "$PROJECT_ROOT" ]]; then
  DOCS_WORKSPACE="${PROJECT_ROOT}/.mg/docs"

  if [[ -d "$DOCS_WORKSPACE" ]]; then
    echo "  Scaffolding: .mg/docs/ already exists -- skipping (preserving existing config)"
  else
    echo "  Scaffolding -> ${DOCS_WORKSPACE}/"
    mkdir -p "${DOCS_WORKSPACE}/scan-logs"

    # Project-local config (copy of global defaults for user to customize)
    cp "${SCRIPT_DIR}/references/.docs.config.json" "${DOCS_WORKSPACE}/.docs.config.json"
    echo "    Created .docs.config.json (defaults -- customize as needed)"

    # Empty notes inbox
    echo '{"notes": []}' > "${DOCS_WORKSPACE}/notes-inbox.json"
    echo "    Created notes-inbox.json (empty inbox)"

    # scan-logs directory already created above
    echo "    Created scan-logs/ directory"
  fi
fi

# -- Update manifest -----------------------------------------------------------
TOOL_SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "${TOOL_SOURCE_DIR}/../install/scripts/mg-install-lib.py" \
  update-manifest \
  --target "$(dirname "$TARGET_DIR")" \
  --tool "$(basename "$TOOL_SOURCE_DIR")" \
  --source "$TOOL_SOURCE_DIR"

# -- Summary -------------------------------------------------------------------

CMD_COUNT="${#COMMANDS[@]}"
SCRIPT_COUNT=$(find "${SUPPORT_DIR}/scripts" -maxdepth 1 -name "*.py" -type f | wc -l)
TEMPLATE_COUNT=$(find "${SUPPORT_DIR}/references/templates" -name "*.template.md" -type f 2>/dev/null | wc -l)
AGENT_COUNT=$(find "${SUPPORT_DIR}/agents" -name "*.md" -type f 2>/dev/null | wc -l)

echo ""
echo "Done. Installed create-docs to ${TARGET_DIR}/"
echo ""
echo "  Commands:    ${CMD_COUNT} command files -> .claude/commands/mg/"
echo "  Scripts:     ${SCRIPT_COUNT} scripts -> .claude/create-docs/scripts/"
echo "  References:  schema.md, style-guide.md, .docs.config.json -> .claude/create-docs/references/"
echo "  Templates:   ${TEMPLATE_COUNT} templates -> .claude/create-docs/references/templates/"
echo "  Agents:      ${AGENT_COUNT} agent definitions -> .claude/create-docs/agents/"
if [[ -n "$PROJECT_ROOT" ]]; then
  if [[ -d "${PROJECT_ROOT}/.mg/docs" ]]; then
    echo "  Scaffolded:  .mg/docs/ (config, inbox, scan-logs)"
  fi
fi
echo ""
echo "Invoke with:"
echo "  /mg:create-docs              <- start here (guides you through the pipeline)"
echo "  /mg:create-docs-scan         <- step 1: scan"
echo "  /mg:create-docs-generate     <- step 2: generate"
echo "  /mg:create-docs-verify       <- step 3: verify"
echo "  /mg:add-docs                 <- capture documentation notes"
