# GSD Fork as Single Source, Deployed via mg:install

## Situation

GSD is maintained as a personal fork at `external-tools/mg-gsd-fork/` — a git repo with its own test suite (`tests/`, run via `node scripts/run-tests.cjs`). It is deployed into each consuming project as an **independent real copy** under `.claude/` (four areas: `get-shit-done/` ~96 files, `commands/gsd/` 32, `agents/` 12, `hooks/` 3). There is no global install; workflows invoke the CLI project-relatively (`node "./.claude/get-shit-done/bin/gsd-tools.cjs"`). Targets are **git-tracked** — the running GSD version is part of how each repo works.

Two layers of local modification sit on top of upstream GSD today:

- **`.cjs` core patches (Bug 1–7)** — committed *in the fork*, and byte-identical across the fork and every install (verified: 0 `.cjs` files differ).
- **`gsd-patches/` overlays** — 8 anchor/replace patches applied *per-target after install* via `/mg:apply-gsd-patches`, designed to survive `/gsd:update`. Three modify workflow `.md` files (discuss-phase, plan-phase, execute-phase); three modify hook `.js` files (context-monitor, statusline ×2); the rest touch statusline/context config. These exist only in the installed copies, **not** in the fork.

The historical dev flow was **backwards**: edit GSD in mg-cc-tools' *installed* copy, then hand-copy the files back into the fork. Edits made this way never run against the fork's test suite (which lives outside `get-shit-done/` and is never installed).

## Problem

1. **Edits bypass the test suite.** Because the suite lives only in the fork and editing happens in installed copies, changes ship with zero test coverage, and the manual copy-back-to-fork step is error-prone.

2. **The patch overlay system is distribution overhead the owner no longer needs.** `gsd-patches` made sense when GSD was third-party and local changes had to survive upstream updates. As the sole owner of the fork, the reinstall-then-reapply-patches ceremony is pure friction — and a clean reinstall *collides* with the patch-modified state (GSD "discovers" locally-patched files and backs them up), which becomes messy.

3. **GSD's own `install.js` is unsuitable as a clean-deploy mechanism.** Research (`bin/install.js`, cited findings) shows it:
   - bakes in the exact patch-backup/reapply ceremony being retired (`saveLocalPatches` → `gsd-local-patches/` + "run `/gsd:reapply-patches`");
   - installs **zero hooks** from a plain git checkout — `hooks/dist/` is empty and git-ignored, requiring `npm run build:hooks` first;
   - only targets the current working directory for local installs (`--local`; `--config-dir` is rejected with it);
   - writes a **nondeterministic timestamp** into `gsd-file-manifest.json`, churning a git-tracked target on every install;
   - emits **bare-relative** hook command strings that would regress the target's current `$CLAUDE_PROJECT_DIR`-anchored wiring;
   - silently replaces a malformed `settings.json` (user-settings loss).

## Solution

### Overview

Make the fork the single source of truth, edited directly (with its tests). Fold the `gsd-patches` overlays into the fork and retire the patch system entirely. Deploy the fork into targets via a new **`gsd-fork` external tool** inside `mg:install` (following the existing `devils-advocate` external-tool convention), backed by a **purpose-built, deterministic, non-interactive installer**. The result: a clean fork install always lands correctly into a git-tracked target — one normal install action, no patch step, no collision with prior state.

### Fork as source of truth

- All GSD changes — `.cjs`, workflows, agents, hooks, statusline — go directly into `external-tools/mg-gsd-fork`.
- Loop: edit → `node scripts/run-tests.cjs` green → commit in the fork.
- The "edit install → copy to fork" flow is retired.

### Fold overlays, then retire gsd-patches

- Fold the 8 `gsd-patches/patches/*` overlays into the fork:
  - **Workflows:** `discuss-phase` (`--check-remaining`, ~+40 lines), `plan-phase` (key-findings, ~+14), `execute-phase` (key-findings + pyright-gate, ~+140).
  - **Hooks/config:** `context-monitor-session-dir`, `statusline-edit-guard`, `statusline-context-cache` — anchor/replace edits applied to the fork's `hooks/gsd-context-monitor.js` and `hooks/gsd-statusline.js`.
- These include the customizations behind the target's current `$CLAUDE_PROJECT_DIR`-anchored hook wiring — once folded, the fork carries them natively.
- Retire `gsd-patches/` (the tool, the patches, and `/mg:apply-gsd-patches`). No reapply step ever again.
- `mg-gsd-wrappers` stays **separate** — not folded in — to keep complexity down.

### `gsd-fork` external tool in mg:install

- New `gsd-fork/` tool dir in mg-cc-tools: `tool.toml` + `install.sh`.
- `tool.toml` marks it `[external]` with the source as a **relative path from the mg-cc-tools root** (`../external-tools/mg-gsd-fork`), matching the `devils-advocate` convention (external source lives in the `external-tools/` sibling).
- `mg:install` deploys it like any other tool. The `gsd` preflight check (mg-install-lib.py:135), today a "install upstream GSD yourself" prerequisite, flips to being **satisfied by co-installing `gsd-fork`**.
- mg-cc-tools' own `.claude/get-shit-done` becomes a normal `mg:install` target sourced from the fork — inverting the old flow.

### Purpose-built installer

Because `install.js` is unsuitable, the `gsd-fork` installer is written from scratch (using install.js only as a behavioral reference), split as a thin `install.sh` (arg parsing, target resolution) over a Python helper that does the deterministic work (D7). It must:

1. **Wipe-and-recopy** `get-shit-done/` and `commands/gsd/` (stale-safe — removed source files disappear from the target).
2. Clear `agents/gsd-*.md`, then copy the fork's agents.
3. Copy the 3 hooks **directly from the fork's top-level `hooks/`** — bypassing the empty `hooks/dist/` and its build step.
4. Write `VERSION`, `CHANGELOG.md`, and `package.json` (`{"type":"commonjs"}`).
5. **Path-rewrite** copied `.md` (`~`/`$HOME`/global `.claude` → the target's `./.claude` form).
6. **Idempotently wire `settings.json`** — SessionStart→`gsd-check-update`, PostToolUse→`gsd-context-monitor`, statusLine→`gsd-statusline` — byte-matching the existing `$CLAUDE_PROJECT_DIR`-anchored form (`${CLAUDE_PROJECT_DIR:-.}` for statusLine), existence-guarded against duplicates, merging into (never clobbering) existing user settings.
7. Be **deterministic**: re-installing an unchanged fork produces an **empty git diff** in the target (no manifest timestamp, no sidecar churn).
8. Run **non-interactively** and target an **arbitrary project directory**.
9. **Not** replicate GSD's local-patch backup/reapply (`gsd-local-patches/`, manifest backup, `/gsd:reapply-patches`) — that is the retired ceremony.

## Design Decisions

### D1: Fork is the single source of truth, edited directly

**Choice:** All GSD changes go into `external-tools/mg-gsd-fork` and are edited there; the "edit install → copy to fork" flow is retired.

**Why:** The test suite lives only in the fork, so edits made anywhere else ship untested. The `.cjs` core is already byte-identical fork↔installs, so there is no divergence to reconcile. The fork uses portable `$HOME/.claude` paths that an installer derives to project-local form — editing source and deriving is the correct direction; editing the derived artifact and back-porting is not.

**Alternatives rejected:** Edit the installed copy then copy to the fork — no tests, backwards path direction, manual and error-prone.

### D2: Retire gsd-patches; fold overlays into the fork

**Choice:** Fold the 8 overlays into the fork and remove the `gsd-patches` tool and `/mg:apply-gsd-patches`.

**Why:** The patch system existed to keep local changes alive across third-party upstream updates. As sole owner of the fork, that need is gone, and the reinstall-then-reapply cycle both adds friction and collides with the patch-modified install state.

### D3: Roll our own installer — do not wrap `install.js`

**Choice:** Write a purpose-built `gsd-fork` installer; use `install.js` only as a reference.

**Why:** `install.js` bakes in the patch-backup/reapply ceremony being retired; requires a build step for hooks (`hooks/dist/` is empty and git-ignored); only targets the cwd for local installs; writes a nondeterministic manifest timestamp that churns a git-tracked target; and emits bare-relative hook wiring that regresses the current `$CLAUDE_PROJECT_DIR` form. Each is a real blocker against the "installs cleanly, deterministically, into a git-tracked target" bar.

**Alternatives rejected:** A thin wrapper around `install.js` — would perpetuate the patch ceremony and still require a build step, cwd gymnastics, and post-hoc de-churning.

### D4: Keep the installed GSD git-tracked

**Choice:** Each target continues to track its `.claude` GSD copy in git.

**Why:** The running GSD version is part of how each repo works and reads. **Implication:** the installer must be deterministic (D3) — a no-op re-install must yield an empty diff, or tracking becomes noise.

### D5: Settings wiring uses the `$CLAUDE_PROJECT_DIR` mg convention, owned by the installer

**Choice:** The installer wires `settings.json` (SessionStart, PostToolUse, statusLine) using the `$CLAUDE_PROJECT_DIR`-anchored command form, and owns those entries.

**Why:** `$CLAUDE_PROJECT_DIR` is the established mg-wide convention — the `permission-hooks` tool already uses it for its own entries — and it is more robust than `install.js`'s bare-relative form (which breaks when Claude Code's cwd is not the project root). The `gsd-patches` overlays modify the hook *files*, not the settings *entries*, so once `install.js` is dropped no existing tool owns these entries; the `gsd-fork` installer takes ownership. It byte-matches the existing form (`$CLAUDE_PROJECT_DIR` for the two hooks, `${CLAUDE_PROJECT_DIR:-.}` for statusLine) so git-tracked targets don't churn.

### D6: Source the fork by relative path; keep mg-gsd-wrappers separate

**Choice:** The `gsd-fork` tool sources the fork via a relative path from the mg-cc-tools root (`../external-tools/mg-gsd-fork`); `mg-gsd-wrappers` is not folded into this work.

**Why:** The relative path matches the `devils-advocate` external convention and avoids machine-specific absolutes. Keeping the wrappers separate holds this change's scope down.

### D7: Installer is a thin `install.sh` over a Python helper

**Choice:** The `gsd-fork` installer is a thin `install.sh` (argument parsing, target resolution, invocation) that delegates the deterministic work — stale-safe copy, `.md` path-rewrite, idempotent `settings.json` merge — to a Python helper under `install/scripts/`.

**Why:** CLAUDE.md mandates that deterministic logic live in `scripts/*.py`, not embedded in shell/markdown; JSON-merge and path-rewriting are exactly that, and are error-prone in bash. mg-cc-tools already runs its install logic through `mg-install-lib.py`, so a Python helper is consistent and unit-testable.

**Alternatives rejected:** Pure-bash `cp`+`sed` (as `devils-advocate` uses) — adequate for a plain skill copy, but not for JSON-merge, path-rewrite, and orphan handling.

## Scope

### What gets built

- **Overlay fold** — apply the 8 `gsd-patches` overlays into the fork's workflow `.md` and hook `.js` files, committed in the fork.
- **`gsd-fork/` tool** in mg-cc-tools — `tool.toml` (`[external]`, relative source path) + a thin `install.sh` over a Python helper in `install/scripts/` (D7), implementing the 9 installer requirements above. This is the one non-trivial piece: stale-safe copy + path-rewrite + idempotent `settings.json` wiring.
- **`gsd` preflight flip** in `install/scripts/mg-install-lib.py` (:135) — from external prerequisite to satisfied-by-`gsd-fork`.
- **Retire `gsd-patches/`** — remove the tool directory, patches, and the `/mg:apply-gsd-patches` command.

### What does NOT get built

- **Wrapping or using GSD's `install.js`** — unsuitable (D3).
- **A symlink / global-install consumption model** — set aside; per-project tracked copies are retained (D4).
- **Folding `mg-gsd-wrappers` into the fork** — stays a separate tool (D6).
- **GSD's local-patch backup/reapply mechanism** — deliberately not replicated (D3).

## Open Items

None outstanding. The three items from the initial draft were resolved during discussion:

- **Installer implementation surface** → **D7** (thin `install.sh` over a Python helper). `post-install-configure.py` does no `settings.json` wiring today, so the installer owns settings wiring regardless — and per CLAUDE.md that logic belongs in Python.
- **Settings-wiring form / ownership** → **D5**. The `$CLAUDE_PROJECT_DIR` form is the established mg convention (matching `permission-hooks`); the `gsd-patches` overlays touch hook *files*, not settings *entries*, so the `gsd-fork` installer takes ownership and byte-matches the existing form.
- **Fold-set completeness** → **validated.** The 8 `gsd-patches` are the full local-customization set; the remaining fork↔install `.md` divergence is upstream/path drift (fork-ahead, PR-numbered commits — #841, #786, #644), which install-from-fork resolves. A per-file audit at fold time (see Verification) is the safeguard before deleting `gsd-patches`.

## Verification

- **Source edits are testable:** an edit in the fork, followed by `node scripts/run-tests.cjs`, runs against the suite and reports green/red.
- **Clean install:** `/mg:install <target> gsd-fork` into a fresh project produces `get-shit-done/`, `commands/gsd/`, `agents/`, `hooks/`, and a wired `settings.json`, non-interactively, with no prompts.
- **Determinism (the load-bearing check):** running the install twice on an unchanged fork produces an **empty `git diff`** in the target — no manifest timestamp, no `gsd-local-patches/` sidecar, no churn.
- **Patch system is gone:** after deploy, `gsd-patches` / `/mg:apply-gsd-patches` is never invoked, and folded customizations are present from the fork — e.g., `discuss-phase` accepts `--check-remaining`, and `settings.json` hooks use the `$CLAUDE_PROJECT_DIR` form.
- **Preflight:** the `gsd` check passes when `gsd-fork` is co-installed; the "install upstream GSD" fix message no longer appears.
- **Stale-safe:** a file removed from the fork is absent from the target after re-install (not orphaned).
- **Settings churn-free:** on an already-wired target, the installer's `settings.json` entries byte-match the existing `$CLAUDE_PROJECT_DIR` form — the entry lines produce no diff.
- **Fold-set audit:** before `gsd-patches` is deleted, a per-file check confirms the 8 patches are the only local customizations — remaining fork↔install `.md` divergence traces to upstream/path drift, not lost local edits.
