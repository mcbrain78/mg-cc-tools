# mg-cc-tools

## What This Is

A collection of Claude Code slash commands under the `mg:` namespace, distributed as self-contained tool subdirectories with their own install scripts, command files, agents, scripts, and references. Each tool is invoked as `/mg:<tool-name>` after installation into a target project's `.claude/` directory (or `~/.claude/` for global).

The flagship tools shipped in v1.1:

- **`/mg:auto-doc`** family — audience-segmented documentation generator with a 5-step pipeline (scan → prepare-templates → generate → auditv2 → fix), 13 document types across 4 audiences, recursive section XML, reference manifests verified by LSP.
- **`/mg:install`** — unified installer for all tools in the collection, with tool.toml-driven discovery, atomic manifest tracking, two-stage installs (install.sh + post-install.md subagent), and three install patterns (copy-only, copy+configure, execute-only).
- **`/mg:transcript-analyze`** + `/mg:transcript-export` — paginated CLI for navigating Claude Code session exports up to 75MB+, with autonomous investigation mode.
- **GSD extension tools** (`/mg:execute-phase`, `/mg:plan-phase`, `/mg:discuss-phase`, `/mg:discuss-milestone`) — wrappers around the get-shit-done workflow.
- **Smaller tools** — `/mg:auto-approve`, `/mg:edit-on`/`/mg:edit-off`, `/mg:cc-regression-test`, `/mg:spec-*` family, `/mg:install`, etc.

## Core Value

A library of well-tested, self-contained Claude Code slash commands that compose into substantial workflows (documentation, installation, session analysis, GSD execution). Each tool follows the same pattern (install.sh + commands/ + agents/ + scripts/ + references/) so contributors can add new tools without learning new conventions, and users can install/update them through a single unified installer.

## Current State (post-v1.1)

**Shipped:** v1.1 (2026-05-04) — 24 phases over 69 days, 64 plans, 652 commits, ~156k LOC excluding planning docs. See `.planning/MILESTONES.md` and `.planning/milestones/v1.1-MILESTONE-AUDIT.md`.

**Active tools** (12+ installable):
- auto-doc, install, transcript, codebase-health, gsd-patches, mg-gsd-wrappers, permission-hooks, cc-regression-test, devils-advocate, debug-triage, update-backlog, new-milestone-gsd, create-context, data-provider, export-session

**Tech stack:** Python 3.11+ (tomllib floor), Bash for install scripts, Markdown for command/agent prompts, YAML frontmatter, JSON for data contracts. uv for dev environment. pytest for tests, ruff for linting.

**Architecture invariants:**
- Self-contained tool pattern (no cross-tool dependencies)
- Install-time path resolution via `{MG_INSTALL_*}` placeholders sed-replaced by install.sh
- All deterministic logic in Python (`scripts/*.py`); .md files are LLM instruction prompts
- All data flows through files (`--input`/`--output`), never through shell args
- Atomic JSON I/O via `lib/json_io.py` (`fcntl.flock` + `tempfile` + `os.replace`)

## Requirements

### Validated (v1.1)

All v1.1 active requirements shipped. See `.planning/milestones/v1.1-REQUIREMENTS.md` for the full traceability table. High-level capabilities:

- ✓ `/mg:auto-doc` 5-step pipeline (scan/prepare-templates/generate/auditv2/fix) — v1.1
- ✓ 13 audience-segmented document types across 4 audiences — v1.1
- ✓ 6 writer agents (4 audience + glossary + overview) using orient-write protocol — v1.1
- ✓ Reference manifest system with LSP `documentSymbol` verification — v1.1
- ✓ Recursive section XML with per-heading emission and round-trip fidelity — v1.1
- ✓ Template refiner pipeline producing project-specific refined templates — v1.1
- ✓ Incremental scan mode with git diff scoping — v1.1
- ✓ End-user functional-first restructure with interface detection — v1.1
- ✓ `/mg:install` unified installer with tool.toml discovery — v1.1
- ✓ Atomic manifest tracking with concurrent-safe writes — v1.1
- ✓ Two-stage install (install.sh + post-install.md subagent) — v1.1
- ✓ Three install patterns (copy-only, copy+configure, execute-only) — v1.1
- ✓ `/mg:transcript-analyze` paginated CLI + autonomous investigation slash command — v1.1

### Active (v1.2 candidates)

(No v1.2 milestone planned yet. Cleanup items from v1.1 audit can be folded in or addressed independently.)

- [ ] `install/install.sh` missing `update-manifest` self-call (1-line fix)
- [ ] Delete orphaned `auto-doc/references/templates/SCRIPT_README.template.md`
- [ ] Revise misleading "That's verify's job" phrasing in `auto-doc/commands/auto-doc-auditv2.md`
- [ ] Add `tool.toml` + `install.sh` to `export-session/` so installer can discover it
- [ ] Nyquist compliance for the 23 phases marked `nyquist_compliant: false` (only Phase 12 is compliant)
- [ ] (TBD) v1.2 milestone theme — see `/gsd:new-milestone`

### Out of Scope

- Auto-push documentation to external hosting (GitHub Pages, ReadTheDocs) — deployment is outside tool scope
- Image/diagram generation — LLMs can't produce images; ASCII diagrams only
- Non-Markdown output formats (PDF, HTML) — Markdown is the universal format
- Real-time documentation sync (file watchers, CI hooks) — run-on-demand via slash commands
- Multi-language documentation (i18n) — English only

## Context

- v1.1 expanded the project from the original narrow `/mg:docs` focus (scan → generate → verify) into a broader tool collection including the install command family, session/transcript analyzer, and recursive XML pipeline.
- Two post-completion stabilization commits reshaped the codebase:
  - `d979a4b` (2026-04-07) — renamed `session-analyzer/` to `transcript/`
  - `90fa640` (2026-04-30) — pruned auto-doc to its final 5-command pipeline; removed router, notes subsystem, named verify checks, and `/mg:auto-doc-script` (15 reqs marked Removed in stabilization)
- Phase 5 and Phase 7 lack formal VERIFICATION.md but are user-verified out-of-band.
- Permissions architecture: `permission-hooks` provides PreToolUse hook configuration with rolling-TTL session context for human-gated auto-approval.

## Constraints

- **Self-contained tools:** No cross-tool dependencies within mg-cc-tools.
- **Install modes:** Every install.sh supports `--project`, `--global`, `--target` modes.
- **Path resolution:** All resource references use `{MG_INSTALL_*}` placeholders sed-replaced at install time.
- **Markdown for prompts; Python for logic:** No embedded Python in .md files.
- **Atomic JSON I/O:** All writes via `lib/json_io.py` to prevent partial-write corruption under concurrent access.
- **Python 3.11+:** Required for `tomllib` (used by mg-install-lib for tool.toml parsing).
- **Stdlib-only for install code:** No pip dependencies for `mg-install-lib.py` and related install scripts.
- **Auditv2 pipeline runs Wave 0 deterministic checks first** before any LLM extraction/resolution.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Markdown for agent docs (not JSON/YAML) | 15-16% more token-efficient than JSON; industry standard (CLAUDE.md, AGENTS.md) | ✓ Good — shipped as the writer agent convention |
| Diataxis classification system | Widely adopted framework; prevents content type mixing | ✓ Good — used in all writer agents and templates |
| Section-by-section generation → orient-write protocol | Research showed better quality than whole-document; orient-write further improved by separating context loading from writing | ✓ Good — orient-write is the v1.1 standard |
| 3-layer templates (classification + structural + exemplar) → refined templates | Generic templates supplemented by per-project refined templates with project-specific PURPOSE comments and EXAMPLE blocks | ✓ Good — Phase 23 template-refiner shipped |
| Reference manifest replacing regex-based check-references | Writers emit exact symbols + paths at generation time; verifier checks deterministically via filesystem and LSP `documentSymbol` | ✓ Good — Phase 14, eliminated false positives |
| Recursive section XML (Phases 18-21) | Earlier flat-section XML couldn't represent nested structure; refs leaked across sections | ✓ Good — round-trip fidelity confirmed |
| Notes subsystem | Captures operational knowledge during development | ⚠ Removed in stabilization — feature didn't earn its keep |
| Pipeline router (`/mg:auto-doc`) | State-detection routing to correct step | ⚠ Removed in stabilization — didn't add value over invoking step commands directly |
| Named verify checks (Diataxis mixing, completeness, link integrity, etc.) | Editorial-quality checks beyond reference integrity | ⚠ Removed in stabilization — auditv2 covers reference + prose, broader checks dropped |
| `/mg:auto-doc-script` standalone command | Single-script README generator separate from full pipeline | ⚠ Removed in stabilization — template kept as orphan |
| `tool.toml` for tool metadata | Enables `discover_tools()` without scanning install.sh; supports `[detect]`, `[post_install]`, `[preflight]` sections | ✓ Good — install command depends on this convention |
| Two-stage install (install.sh + post-install.md subagent) | Some tools need Claude Code intelligence for configuration (settings.json merges, patch application) | ✓ Good — permission-hooks, cc-regression-test, gsd-patches all use it |
| `install.md` as thin orchestrator | All deterministic logic in Python subcommands; LLM only echoes output, collects input, spawns agents | ✓ Good — Phase 11 refactor reduced 475-line state machine to 244-line orchestrator |
| Stdlib-only install code | No pip dependencies for the bootstrap path | ✓ Good — install works from clean system |
| Rename session-analyzer → transcript | Broader scope (analyze, export, session-file commands) | ✓ Good — d979a4b rename clean |

---
*Last updated: 2026-05-04 after v1.1 milestone completion*
