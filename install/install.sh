#!/usr/bin/env bash
set -euo pipefail

# ── Install Command — Bootstrap Installer ──────────────────────────────────
#
# Self-installs the /mg:install command into a Claude Code configuration.
# This is the ONLY install.sh that does NOT update the manifest — mg-cc-tools
# itself is the source repo and does not need a manifest entry.
#
# Usage:
#   ./install.sh --project [<dir>]  Install into project's .claude/ (default: cwd)
#   ./install.sh --global           Install globally into ~/.claude/
#   ./install.sh --target <path>    Install into a custom .claude/ directory
# ──────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

COMMANDS=(
  install
)

# ── Read display fence from config ───────────────────────────────────────────

DISPLAY_CONFIG="${SCRIPT_DIR}/display.toml"
if [[ ! -f "$DISPLAY_CONFIG" ]]; then
  echo "Error: missing display config at ${DISPLAY_CONFIG}"
  exit 1
fi

FENCE=$(python3 -c "
import sys, tomllib
with open('${DISPLAY_CONFIG}', 'rb') as f:
    print(tomllib.load(f).get('fence', ''))
" 2>/dev/null)

case "$FENCE" in
  codeblock|verbatim) ;;
  *)
    echo "Error: invalid or missing 'fence' in ${DISPLAY_CONFIG} (got: '${FENCE}')"
    echo "       expected 'codeblock' or 'verbatim'"
    exit 1
    ;;
esac

RULE_FILE="${SCRIPT_DIR}/display-rules/${FENCE}.md"
if [[ ! -f "$RULE_FILE" ]]; then
  echo "Error: missing display rule at ${RULE_FILE}"
  exit 1
fi

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

# ── Install ──────────────────────────────────────────────────────────────────

COMMANDS_DIR="${TARGET_DIR}/commands/mg"

echo "Installing mg:install to: ${TARGET_DIR}"
echo "  Display fence: ${FENCE} (from $(basename "$DISPLAY_CONFIG"))"

mkdir -p "$COMMANDS_DIR"
for cmd in "${COMMANDS[@]}"; do
  cp "${SCRIPT_DIR}/commands/${cmd}.md" "${COMMANDS_DIR}/${cmd}.md"
done

# Substitute {DISPLAY_RULE} placeholder with the rule file's contents.
# Python is cleaner than sed for multi-line file-to-string substitution.
python3 -c "
import sys
with open('${RULE_FILE}') as f:
    rule = f.read().rstrip('\n')
out = '${COMMANDS_DIR}/install.md'
with open(out) as f:
    text = f.read()
if '{DISPLAY_RULE}' not in text:
    sys.exit('Error: {DISPLAY_RULE} placeholder missing from ' + out)
text = text.replace('{DISPLAY_RULE}', rule)
with open(out, 'w') as f:
    f.write(text)
"

echo "  Commands -> ${COMMANDS_DIR}/"

# NOTE: No manifest update here. mg-cc-tools is the source repo — it does not
# need a manifest entry for itself. See Pitfall 7 in RESEARCH.md.

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "Done. Installed:"
echo ""
echo "  Commands:"
for cmd in "${COMMANDS[@]}"; do
  echo "    ${COMMANDS_DIR}/${cmd}.md"
done
echo ""
echo "New machine setup:"
echo "  cd mg-cc-tools"
echo "  ./install/install.sh --project    # bootstrap the installer"
echo "  # Then use /mg:install interactively for everything else"
