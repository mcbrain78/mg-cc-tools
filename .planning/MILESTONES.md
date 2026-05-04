# Milestones

## v1.1 milestone (Shipped: 2026-05-04)

**Phases completed:** 24 phases, 64 plans

**Timeline:** 2026-02-20 → 2026-04-30 (69 days)

**Stats:**
- 652 commits (198 with `feat`/`refactor` prefix)
- ~156k LOC (excluding `.planning/`, samples, test fixtures)
- Per-language: Python 78k, Markdown ~37k (excluding planning), Bash 2.7k, YAML 1.5k, TOML 161

**Key accomplishments:**

1. **`/mg:auto-doc` documentation pipeline** — scan → prepare-templates → generate → auditv2 → fix. 13 audience-segmented document types across 4 audiences (end-users, developers, agents, devops). Reference manifest system with LSP `documentSymbol` verification, recursive section XML, glossary reconciliation, incremental scan mode. (Phases 1-5, 12-17, 23-24)
2. **`/mg:install` unified installer** — tool.toml-driven discovery, atomic manifest tracking with fcntl.flock, two-stage install with post-install.md subagents, three install patterns (copy-only, copy+configure, execute-only). All deterministic logic in Python; install.md acts as thin orchestrator. (Phases 7, 8, 10, 11)
3. **`/mg:transcript-analyze`** — paginated CLI for navigating CC session exports up to 75MB+; slash command with autonomous investigation mode. Originally `session-analyzer/`, renamed to `transcript/` in stabilization. (Phase 9)
4. **Recursive section XML pipeline** — nested heading emission via `write-section.py --parent`, per-heading reference precision, round-trip fidelity through finalize/assemble/sync. (Phases 18-21)
5. **Reference manifest system** — replaced regex-based `check-references.py` with structured manifest: writers emit exact symbols + file paths, verified deterministically via filesystem and LSP `documentSymbol`. (Phase 14)
6. **End-user docs functional-first restructure** — interface detection in scan, 7-section USER_GUIDE template, `<!-- SYNTHESIZED -->` and `<!-- BOUNDARY -->` comment conventions. (Phase 15)

**Requirements:** 218 / 218 active satisfied (100%). 15 reqs intentionally removed in stabilization (commit `90fa640`); 1 req superseded by template-refiner architecture (DOC-04 → Phase 23). See `milestones/v1.1-REQUIREMENTS.md` for full traceability.

**Audit:** `passed` — see `milestones/v1.1-MILESTONE-AUDIT.md`.

**Remaining cleanup (carried into v1.2):**
- `install/install.sh` missing `update-manifest` self-call (1-line fix)
- Orphaned `auto-doc/references/templates/SCRIPT_README.template.md` (delete)
- Misleading "That's verify's job" phrasing in `auto-doc/commands/auto-doc-auditv2.md`
- REQUIREMENTS.md missing FIX-A1..A6, FIX-B1..B3 (Phase 6) and INST-01..INST-12 (Phase 7) traceability rows — only relevant if archive is amended
- `export-session/` has commands/scripts but no `tool.toml` (invisible to installer)
- 23 phases have `nyquist_compliant: false` in VALIDATION.md (only Phase 12 is compliant)

---
