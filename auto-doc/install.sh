#!/usr/bin/env bash
set -euo pipefail

# -- Auto-Doc Pipeline -- Installer --------------------------------------------
#
# Installs the auto-doc tool and its supporting files into a Claude Code
# project or global configuration.
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
#
# What it does:
#   1. Copies command files to <target>/commands/mg/
#   2. Copies supporting files (scripts, references, agents) to <target>/auto-doc/
#   3. Resolves all relative paths in command files to absolute paths,
#      so the LLM can find scripts, agents, and references at runtime.
#   4. (--project only) Scaffolds .mg/docs/ workspace with config, inbox, scan-logs.
# ------------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=(
  auto-doc
  auto-doc-scan
  auto-doc-generate
  auto-doc-update
  auto-doc-audit
  auto-doc-fix
  auto-doc-verify
  auto-doc-verify-mini
  auto-doc-verify-singledoc
  auto-doc-add
  auto-doc-script
  auto-doc-prepare-templates
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
      echo "  /mg:auto-doc              <- router (guides you through the pipeline)"
      echo "  /mg:auto-doc-scan         <- step 1: scan"
      echo "  /mg:auto-doc-generate     <- step 2: generate"
      echo "  /mg:auto-doc-update       <- fix findings + integrate notes"
      echo "  /mg:auto-doc-audit        <- lightweight ref integrity + prose audit"
      echo "  /mg:auto-doc-fix          <- fix audit findings (refs + prose)"
      echo "  /mg:auto-doc-verify       <- step 3: verify (full editorial)"
      echo "  /mg:auto-doc-verify-mini  <- step 3 alt: verify with Haiku editorial"
      echo "  /mg:auto-doc-verify-singledoc  <- step 3 alt: verify with self-driven Sonnet editorial"
      echo "  /mg:auto-doc-add          <- capture notes"
      echo "  /mg:auto-doc-script       <- generate README for a standalone script"
      echo "  /mg:auto-doc-prepare-templates <- refine templates with project-specific headings"
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
    TARGET_DIR="${MG_INSTALL_PROJECT_ROOT}/.claude"
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

# -- Migrate from create-docs (if present) ------------------------------------

COMMANDS_DIR="${TARGET_DIR}/commands/mg"
SUPPORT_DIR="${TARGET_DIR}/auto-doc"
MANIFEST_FILE="${TARGET_DIR}/mg-cc-tools.manifest.json"

if [[ -f "${COMMANDS_DIR}/create-docs.md" ]] || [[ -d "${TARGET_DIR}/create-docs" ]]; then
  echo "  Migrating: removing old create-docs installation ..."
  rm -f "${COMMANDS_DIR}/create-docs.md" \
        "${COMMANDS_DIR}/create-docs-scan.md" \
        "${COMMANDS_DIR}/create-docs-generate.md" \
        "${COMMANDS_DIR}/create-docs-verify.md" \
        "${COMMANDS_DIR}/add-docs.md"
  rm -rf "${TARGET_DIR}/create-docs"

  # Remove stale manifest entry
  if [[ -f "$MANIFEST_FILE" ]]; then
    python3 -c "
import json, sys
p = '$MANIFEST_FILE'
with open(p) as f: m = json.load(f)
if 'tools' in m: m['tools'].pop('create-docs', None)
with open(p, 'w') as f: json.dump(m, f, indent=2)
" 2>/dev/null || echo "  Warning: could not clean manifest (non-fatal)"
  fi
fi

# -- Install -------------------------------------------------------------------

echo "Installing auto-doc pipeline to: ${TARGET_DIR}"

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

# Copy references (all .md, .yaml, and .json files, including dotfiles)
for ref_file in "${SCRIPT_DIR}"/references/*.md "${SCRIPT_DIR}"/references/*.yaml "${SCRIPT_DIR}"/references/*.json "${SCRIPT_DIR}"/references/.*.json; do
  [[ -f "$ref_file" ]] && cp "$ref_file" "${SUPPORT_DIR}/references/"
done

# Copy templates (recursive -- preserves audience subdirectory structure)
echo "  Templates  -> ${SUPPORT_DIR}/references/templates/"
cp -r "${SCRIPT_DIR}/references/templates" "${SUPPORT_DIR}/references/"

# Copy agents (if any exist -- Phase 2 adds them)
if ls "${SCRIPT_DIR}"/agents/*.md &>/dev/null 2>&1; then
  cp "${SCRIPT_DIR}"/agents/*.md "${SUPPORT_DIR}/agents/"
fi

# Clean up old agent files from prior installs (verify pipeline restructure)
rm -f "${SUPPORT_DIR}/agents/verifier.md" "${SUPPORT_DIR}/agents/editorial-reviewer.md"

# Make scripts executable
chmod +x "${SUPPORT_DIR}/scripts/"*.py

# -- Resolve paths -------------------------------------------------------------
#
# Replace relative placeholders with absolute paths so the LLM can find them
# at runtime without knowing the command file's directory.

CONFIG_ABS="${SUPPORT_DIR}/references/.docs.config.json"
AGENTS_ABS="${SUPPORT_DIR}/agents"
SCRIPTS_ABS="${SUPPORT_DIR}/scripts"
TEMPLATES_ABS="${SUPPORT_DIR}/references/templates"
CHECKS_ABS="${SUPPORT_DIR}/references/verify-checks.json"
TMP_ABS="${MG_INSTALL_PROJECT_ROOT}/.mg/docs/tmp"
EMIT_CONTEXT_ABS="${TARGET_DIR}/permission-hooks/scripts/emit-context.py"

echo "  Resolving path placeholders in command files ..."
for cmd in "${COMMANDS[@]}"; do
  cmd_file="${COMMANDS_DIR}/${cmd}.md"
  if [[ ! -f "$cmd_file" ]]; then
    continue
  fi
  # Auto-resolve all references/<file> paths to absolute
  for ref_match in $(grep -oP 'references/[a-zA-Z0-9._-]*\.(md|yaml|json)' "$cmd_file" 2>/dev/null | sort -u); do
    if [[ -f "${SUPPORT_DIR}/${ref_match}" ]]; then
      sed -i "s|${ref_match}|${SUPPORT_DIR}/${ref_match}|g" "$cmd_file"
    fi
  done
  # Resolve global config placeholder
  if grep -q '{MG_INSTALL_GLOBAL_CONFIG}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_GLOBAL_CONFIG}|${CONFIG_ABS}|g" "$cmd_file"
  fi
  # Resolve scripts dir placeholder
  if grep -q '{MG_INSTALL_SCRIPTS_DIR}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_SCRIPTS_DIR}|${SCRIPTS_ABS}|g" "$cmd_file"
  fi
  # Resolve templates dir placeholder
  if grep -q '{MG_INSTALL_TEMPLATES_DIR}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_TEMPLATES_DIR}|${TEMPLATES_ABS}|g" "$cmd_file"
  fi
  # Resolve tmp dir placeholder
  if grep -q '{MG_INSTALL_TMP_DIR}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_TMP_DIR}|${TMP_ABS}|g" "$cmd_file"
  fi
  # Resolve agents dir placeholder
  if grep -q '{MG_INSTALL_AGENTS_DIR}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_AGENTS_DIR}|${AGENTS_ABS}|g" "$cmd_file"
  fi
  # Resolve checks file placeholder
  if grep -q '{MG_INSTALL_CHECKS_FILE}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_CHECKS_FILE}|${CHECKS_ABS}|g" "$cmd_file"
  fi
  # Resolve emit-context script placeholder (permission-hooks cross-ref)
  if grep -q '{MG_INSTALL_EMIT_CONTEXT_SCRIPT}' "$cmd_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_EMIT_CONTEXT_SCRIPT}|${EMIT_CONTEXT_ABS}|g" "$cmd_file"
  fi
done

# Resolve placeholders in agent files (Phase 2 adds agents)
echo "  Resolving path placeholders in agent files ..."
for agent_file in "${SUPPORT_DIR}/agents/"*.md; do
  if [[ ! -f "$agent_file" ]]; then
    continue
  fi
  # Auto-resolve all references/<file> paths to absolute
  for ref_match in $(grep -oP 'references/[a-zA-Z0-9._-]*\.(md|yaml|json)' "$agent_file" 2>/dev/null | sort -u); do
    if [[ -f "${SUPPORT_DIR}/${ref_match}" ]]; then
      sed -i "s|${ref_match}|${SUPPORT_DIR}/${ref_match}|g" "$agent_file"
    fi
  done
  if grep -q '{MG_INSTALL_GLOBAL_CONFIG}' "$agent_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_GLOBAL_CONFIG}|${CONFIG_ABS}|g" "$agent_file"
  fi
  if grep -q '{MG_INSTALL_SCRIPTS_DIR}' "$agent_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_SCRIPTS_DIR}|${SCRIPTS_ABS}|g" "$agent_file"
  fi
  if grep -q '{MG_INSTALL_TEMPLATES_DIR}' "$agent_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_TEMPLATES_DIR}|${TEMPLATES_ABS}|g" "$agent_file"
  fi
  if grep -q '{MG_INSTALL_TMP_DIR}' "$agent_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_TMP_DIR}|${TMP_ABS}|g" "$agent_file"
  fi
  if grep -q '{MG_INSTALL_CHECKS_FILE}' "$agent_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_CHECKS_FILE}|${CHECKS_ABS}|g" "$agent_file"
  fi
  if grep -q '{MG_INSTALL_AGENTS_DIR}' "$agent_file" 2>/dev/null; then
    sed -i "s|{MG_INSTALL_AGENTS_DIR}|${AGENTS_ABS}|g" "$agent_file"
  fi
done

# -- Scaffold project workspace ------------------------------------------------
#
# For --project installs, create .mg/docs/ with default config, empty inbox,
# and scan-logs directory. Skip if .mg/docs/ already exists to preserve
# user customizations.

if [[ -n "$PROJECT_ROOT" ]]; then
  DOCS_WORKSPACE="${MG_INSTALL_PROJECT_ROOT}/.mg/docs"

  if [[ -d "$DOCS_WORKSPACE" ]]; then
    echo "  Scaffolding: .mg/docs/ already exists -- skipping (preserving existing config)"
  else
    echo "  Scaffolding -> ${DOCS_WORKSPACE}/"
    mkdir -p "${DOCS_WORKSPACE}/scan-logs" "${DOCS_WORKSPACE}/tmp"

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

# -- Post-install audit --------------------------------------------------------
#
# Verify that all source files were installed and all relative paths resolved.
# Warnings only -- does not block installation.

echo ""
echo "Running post-install audit ..."
AUDIT_WARNINGS=0

# 1. Source files not copied to target (skip tests/, __pycache__)
_check_copied() {
  local src_dir="$1" tgt_dir="$2" pattern="$3"
  for src_file in "${src_dir}"/${pattern}; do
    [[ -f "$src_file" ]] || continue
    local base
    base="$(basename "$src_file")"
    if [[ ! -f "${tgt_dir}/${base}" ]]; then
      echo "  WARNING: $(basename "$src_dir")/${base} exists in source but was not installed"
      AUDIT_WARNINGS=$((AUDIT_WARNINGS + 1))
    fi
  done
}

_check_copied "${SCRIPT_DIR}/commands" "$COMMANDS_DIR" "*.md"
_check_copied "${SCRIPT_DIR}/scripts" "${SUPPORT_DIR}/scripts" "*.py"
_check_copied "${SCRIPT_DIR}/scripts/lib" "${SUPPORT_DIR}/scripts/lib" "*.py"
_check_copied "${SCRIPT_DIR}/references" "${SUPPORT_DIR}/references" "*.md"
_check_copied "${SCRIPT_DIR}/references" "${SUPPORT_DIR}/references" "*.yaml"
_check_copied "${SCRIPT_DIR}/references" "${SUPPORT_DIR}/references" "*.json"
_check_copied "${SCRIPT_DIR}/references" "${SUPPORT_DIR}/references" ".*.json"
_check_copied "${SCRIPT_DIR}/agents" "${SUPPORT_DIR}/agents" "*.md"

# 2. Unresolved references/ paths in installed .md files
#    Uses negative lookbehind to skip resolved absolute paths (which contain /references/)
for md_file in "${COMMANDS_DIR}"/auto-doc*.md "${SUPPORT_DIR}/agents/"*.md; do
  [[ -f "$md_file" ]] || continue
  for match in $(grep -oP '(?<!/)references/[a-zA-Z0-9._-]+\.[a-z]+' "$md_file" 2>/dev/null | sort -u); do
    echo "  WARNING: unresolved reference path '${match}' in $(basename "$md_file")"
    AUDIT_WARNINGS=$((AUDIT_WARNINGS + 1))
  done
done

# 3. Unresolved install-time placeholders in installed .md files
#    Only checks placeholders that install.sh is responsible for resolving.
#    Runtime placeholders ({DOCUMENT}, {DOC_NAME}, etc.) are filled by the orchestrator.
INSTALL_PLACEHOLDERS='{MG_INSTALL_GLOBAL_CONFIG} {MG_INSTALL_SCRIPTS_DIR} {MG_INSTALL_TEMPLATES_DIR} {MG_INSTALL_TMP_DIR} {MG_INSTALL_AGENTS_DIR} {MG_INSTALL_CHECKS_FILE} {MG_INSTALL_EMIT_CONTEXT_SCRIPT}'
for md_file in "${COMMANDS_DIR}"/auto-doc*.md "${SUPPORT_DIR}/agents/"*.md; do
  [[ -f "$md_file" ]] || continue
  for placeholder in $INSTALL_PLACEHOLDERS; do
    if grep -qF "$placeholder" "$md_file" 2>/dev/null; then
      echo "  WARNING: unresolved install placeholder '${placeholder}' in $(basename "$md_file")"
      AUDIT_WARNINGS=$((AUDIT_WARNINGS + 1))
    fi
  done
done

if [[ "$AUDIT_WARNINGS" -gt 0 ]]; then
  echo "  ${AUDIT_WARNINGS} warning(s) -- new files may need install.sh updates"
else
  echo "  All checks passed."
fi

# -- Summary -------------------------------------------------------------------

CMD_COUNT="${#COMMANDS[@]}"
SCRIPT_COUNT=$(find "${SUPPORT_DIR}/scripts" -maxdepth 1 -name "*.py" -type f | wc -l)
TEMPLATE_COUNT=$(find "${SUPPORT_DIR}/references/templates" -name "*.template.md" -type f 2>/dev/null | wc -l)
AGENT_COUNT=$(find "${SUPPORT_DIR}/agents" -name "*.md" -type f 2>/dev/null | wc -l)

echo ""
echo "Done. Installed auto-doc to ${TARGET_DIR}/"
echo ""
echo "  Commands:    ${CMD_COUNT} command files -> .claude/commands/mg/"
echo "  Scripts:     ${SCRIPT_COUNT} scripts -> .claude/auto-doc/scripts/"
REF_COUNT=$(find "${SUPPORT_DIR}/references" -maxdepth 1 -type f | wc -l)
echo "  References:  ${REF_COUNT} reference files -> .claude/auto-doc/references/"
echo "  Templates:   ${TEMPLATE_COUNT} templates -> .claude/auto-doc/references/templates/"
echo "  Agents:      ${AGENT_COUNT} agent definitions -> .claude/auto-doc/agents/"
if [[ -n "$PROJECT_ROOT" ]]; then
  if [[ -d "${MG_INSTALL_PROJECT_ROOT}/.mg/docs" ]]; then
    echo "  Scaffolded:  .mg/docs/ (config, inbox, scan-logs)"
  fi
fi
echo ""
echo "Invoke with:"
echo "  /mg:auto-doc              <- start here (guides you through the pipeline)"
echo "  /mg:auto-doc-scan         <- step 1: scan"
echo "  /mg:auto-doc-generate     <- step 2: generate"
echo "  /mg:auto-doc-update       <- fix findings + integrate notes"
echo "  /mg:auto-doc-audit        <- lightweight ref integrity + prose audit"
echo "  /mg:auto-doc-fix          <- fix audit findings (refs + prose)"
echo "  /mg:auto-doc-verify       <- step 3: verify (full editorial)"
echo "  /mg:auto-doc-verify-mini  <- step 3 alt: verify with Haiku editorial"
echo "  /mg:auto-doc-verify-singledoc  <- step 3 alt: verify with Sonnet SendMessage editorial"
echo "  /mg:auto-doc-add          <- capture documentation notes"
echo "  /mg:auto-doc-script       <- generate README for a standalone script"
echo "  /mg:auto-doc-prepare-templates <- refine templates with project-specific headings"
