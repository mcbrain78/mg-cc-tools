# Code Style and Conventions

## Python Style
- **Naming:** snake_case for functions and variables
- **Type hints:** Not consistently used — scripts are pragmatic CLI tools, not library code
- **Docstrings:** Brief one-liner docstrings when present (e.g. `"""Deduplicate by (file, lines tuple, category). Keeps first occurrence."""`)
- **Script pattern:** Each script uses `argparse` with a `main()` function and `if __name__ == "__main__": main()` guard
- **JSON I/O:** Shared helper functions (`load_json`, `save_json`) in `lib/json_io.py` within each tool
- **Output:** JSON to stdout for machine consumption, human-readable messages to stderr
- **No classes** in scripts — functional style with plain dicts and lists

## Command/Agent Files (.md)
- Markdown documents that serve as LLM instruction prompts
- Include YAML-style frontmatter (`name:`, `description:`, `allowed-tools:`)
- Reference supporting resources using relative placeholders that get sed-replaced at install time
- **Never embed Python code in .md files** — all deterministic logic goes in `scripts/*.py`

## Testing
- pytest with class-based test organization (e.g. `TestAddNoteBasic`, `TestAddNoteEdgeCases`)
- SCRIPT_PATH constant pointing to the script under test
- Tests run scripts via subprocess
- Never pipe pytest output — use `--tb=short -q --no-header` flags instead

## Project Conventions
- All commands use the `/mg:` namespace prefix
- Each tool is self-contained — no cross-tool dependencies
- Install scripts support three modes: `--project [<dir>]`, `--global`, `--target <path>`
- Install scripts validate that source files exist before copying
- Path placeholders in .md files must have corresponding `sed` replacements in `install.sh`
- Stay on current branch — don't check out new branches
- Keep commits atomic with clear messages
