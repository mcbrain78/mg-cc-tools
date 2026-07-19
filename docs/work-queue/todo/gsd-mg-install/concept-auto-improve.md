# GSD Fork as Single Source, Deployed via mg:install

## Situation

GSD is maintained as a personal fork at `external-tools/mg-gsd-fork/` — a git repo with its own test suite (`tests/`, run via `node scripts/run-tests.cjs`). It is deployed into each consuming project as an **independent real copy** under `.claude/` (four areas: `get-shit-done/` ~96 files, `commands/gsd/` 32, `agents/` 12, `hooks/` 3). There is no global install; workflows invoke the CLI project-relatively (`node "./.claude/get-shit-done/bin/gsd-tools.cjs"`). Targets are **git-tracked** — the running GSD version is part of how each repo works.

Two layers of local modification sit on top of upstream GSD today:

- **`.cjs` core patches (Bug 1–7)** — committed *in the fork*, and byte-identical across the fork and every install (verified: 0 `.cjs` files present in both trees differ).
- **`gsd-patches/` overlays** — 8 anchor/replace patches applied *per-target after install* via `/mg:apply-gsd-patches`, designed to survive `/gsd:update`. Five modify workflow `.md` files (discuss-phase ×2, plan-phase, execute-phase ×2); three modify hook `.js` files (context-monitor, statusline ×2). These exist only in the installed copies, **not** in the fork.

The historical dev flow was **backwards**: edit GSD in mg-cc-tools' *installed* copy, then hand-copy the files back into the fork. Edits made this way never run against the fork's test suite (which lives outside `get-shit-done/` and is never installed — with one stray exception, `get-shit-done/test/status-bug7.test.cjs`, which sits *inside* the deployable tree; it gets relocated as part of this work, see Scope).

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
- The fork is **fully independent** of upstream GSD — no upstream merges (D9). Its `.md` files are converted once from upstream's portable `$HOME/.claude` form to the project-local `./.claude` form and committed, so installs are verbatim copies with no path derivation.
- Loop: edit → `node scripts/run-tests.cjs` green → commit in the fork.
- One stray test file sits inside the deployable tree — `get-shit-done/test/status-bug7.test.cjs`, the only non-deployable file there. It moves to the fork's top-level `tests/`, where `scripts/run-tests.cjs` auto-discovers `*.test.cjs` files (its default gsd-tools path is adjusted for the new location), and `get-shit-done/test/` is deleted. This keeps installer requirement 1's wipe-and-recopy verbatim — no exclusion logic, and no test file lands git-tracked in every target.
- The "edit install → copy to fork" flow is retired.

### Fold overlays, then retire gsd-patches

- Fold the 8 `gsd-patches/patches/*` overlays into the fork:
  - **Workflows (5):** `discuss-phase-check-remaining` (~+40 lines), `discuss-phase-enhanced` (option recommendations + auto-deepen loop), `plan-phase-key-findings` (~+14), `execute-phase-key-findings` and `execute-phase-pyright-gate` (~+140 combined).
  - **Hooks (3):** `context-monitor-session-dir`, `statusline-edit-guard`, `statusline-context-cache` — anchor/replace edits applied to the fork's `hooks/gsd-context-monitor.js` and `hooks/gsd-statusline.js`.
- These include the customizations behind the target's current `$CLAUDE_PROJECT_DIR`-anchored hook wiring — once folded, the fork carries them natively.
- Retire `gsd-patches/` (the tool, the patches, and `/mg:apply-gsd-patches`). No reapply step ever again.
- `mg-gsd-wrappers` stays **separate** — not folded in — to keep complexity down.

### Remove GSD's self-update machinery

- Delete from the fork: `commands/gsd/update.md`, `commands/gsd/reapply-patches.md`, `get-shit-done/workflows/update.md`, and `hooks/gsd-check-update.js` — plus the now-dead update-available badge branch in `hooks/gsd-statusline.js` (it reads the cache `gsd-check-update` wrote).
- Updates flow exclusively through `/mg:install <target> gsd-fork` (D8). In targets, `commands/gsd/` wipe-and-recopy drops the two command files automatically; the installer removes the legacy hook file and `settings.json` entry (requirements 5 and 9).

### `gsd-fork` external tool in mg:install

- New `gsd-fork/` tool dir in mg-cc-tools: `tool.toml` + `install.sh`.
- `tool.toml` marks it `[external]` using the **existing key set** (`archive`, `repo`, `path` — `read_tool_toml` rejects unknown keys): `archive = "mg-gsd-fork"` names the source directory under the `external-tools/` sibling, `repo` records upstream provenance. Per the `devils-advocate` convention, the library treats `[external]` values as documentary; `install.sh` composes the actual source path as `../external-tools/<archive>` relative to the mg-cc-tools root. No library schema change.
- `mg:install` deploys it like any other tool, with two small library changes:
  - **Preflight co-selection** — the `gsd` check (mg-install-lib.py:135), today a `path_exists {target}/.claude/get-shit-done` probe with an "install upstream GSD yourself" fix message, flips to being **satisfied by `gsd-fork`**: `run_preflight` (:547) already receives the selected tool names, so the check passes when the path exists *or* `gsd-fork` is in the same selection (preflight runs once, before anything installs, so path-existence alone would spuriously fail a combined fresh install). The fix message becomes "co-install gsd-fork".
  - **Install-order hoist** — install order today is simply the selection order (`get_install_plan`, :1580, preserves the given list; no dependency ordering exists anywhere). `get_install_plan` hoists `gsd-fork` to the front of the plan, so within a run it installs before any tool declaring `required = ["gsd"]` — otherwise a mid-run failure could leave gsd-dependent tools installed into a GSD-less target.
- mg-cc-tools' own `.claude/get-shit-done` becomes a normal `mg:install` target sourced from the fork — inverting the old flow.

### Purpose-built installer

Because `install.js` is unsuitable, the `gsd-fork` installer is written from scratch (using install.js only as a behavioral reference), split as a thin `install.sh` (arg parsing, target resolution) over a Python helper that does the deterministic work (D7). It must:

1. **Wipe-and-recopy** `get-shit-done/` and `commands/gsd/` (stale-safe — removed source files disappear from the target).
2. Clear `agents/gsd-*.md`, then copy the fork's agents.
3. Copy the 2 hooks (`gsd-context-monitor.js`, `gsd-statusline.js`) **directly from the fork's top-level `hooks/`** — bypassing the empty `hooks/dist/` and its build step. (`gsd-check-update.js` is removed from the fork — D8.)
4. Write `get-shit-done/VERSION` (the fork's version string, taken from the fork's `package.json`) and `.claude/package.json` (`{"type":"commonjs"}`) — the locations current installs already use. VERSION is informational only: its sole programmatic consumer, `gsd-check-update`, is removed (D8). No `CHANGELOG.md`: current installs carry none, and adding one would put a new git-tracked file into every target with no consumer.
5. **Idempotently wire `settings.json`** — PostToolUse→`gsd-context-monitor` and statusLine→`gsd-statusline`; **no SessionStart entry** (the update check is removed — D8) — emitting one canonical form: a `$CLAUDE_PROJECT_DIR`-anchored command for the hook, `${CLAUDE_PROJECT_DIR:-.}` for statusLine. Existing targets disagree on form (bare-relative, `$CLAUDE_PROJECT_DIR`, `${CLAUDE_PROJECT_DIR:-.}` all occur in the wild), so the installer **normalizes**: it recognizes any prior GSD entry variant and replaces it in place — never appending a duplicate — and removes the legacy `SessionStart→gsd-check-update` entry, while merging into (never clobbering) existing user settings. First install on a legacy-form target produces a one-time normalization diff; from then on the entries are stable. If `settings.json` exists but is not valid JSON, the installer **aborts with a non-zero exit and writes nothing** — never the silent file replacement `install.js` performs.
6. Be **deterministic**: re-installing an unchanged fork produces an **empty git diff** in the target (no manifest timestamp, no sidecar churn).
7. Run **non-interactively** and target an **arbitrary project directory**.
8. **Not** replicate GSD's local-patch backup/reapply (`gsd-local-patches/`, manifest backup, `/gsd:reapply-patches`) — that is the retired ceremony.
9. **Remove legacy residue** from the target: delete `.claude/gsd-file-manifest.json`, any `.claude/gsd-local-patches/` directory, and `.claude/hooks/gsd-check-update.js` (D8 — `hooks/` is shared with other tools, so it is not wipe-and-recopied and the file must be removed explicitly). Left behind, they are stale git-tracked metadata/code. This is migration cleanup (a one-time diff), distinct from requirement 8's "don't rebuild the mechanism".

(No path-rewrite step: the fork commits the project-local `./.claude` path form directly — D9.)

## Design Decisions

### D1: Fork is the single source of truth, edited directly

**Choice:** All GSD changes go into `external-tools/mg-gsd-fork` and are edited there; the "edit install → copy to fork" flow is retired.

**Why:** The test suite lives only in the fork, so edits made anywhere else ship untested. The `.cjs` core is already byte-identical fork↔installs, so there is no divergence to reconcile. Once the fork commits the project-local path form (D9), installed copies are verbatim replicas of the source — editing source and deploying copies is the correct direction; editing a deployed copy and back-porting is not.

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

**Choice:** The installer wires `settings.json` (PostToolUse, statusLine) using the `$CLAUDE_PROJECT_DIR`-anchored command form, and owns those entries.

**Why:** `$CLAUDE_PROJECT_DIR` is the established mg-wide convention — the `permission-hooks` tool already uses it for its own entries — and it is more robust than `install.js`'s bare-relative form (which breaks when Claude Code's cwd is not the project root). The `gsd-patches` overlays modify the hook *files*, not the settings *entries*, so once `install.js` is dropped no existing tool owns these entries; the `gsd-fork` installer takes ownership. The canonical emitted form is `$CLAUDE_PROJECT_DIR` for the PostToolUse hook and `${CLAUDE_PROJECT_DIR:-.}` for statusLine. The asymmetry follows Claude Code's documented contract: hooks are *guaranteed* `CLAUDE_PROJECT_DIR` in their environment, while the statusLine docs never mention the variable (the project dir arrives via stdin JSON there) — it is set in practice today, but a bare `$CLAUDE_PROJECT_DIR` would expand to empty if that undocumented behavior changed, breaking the statusline; `${CLAUDE_PROJECT_DIR:-.}` degrades to cwd-relative, upstream GSD's own project-install form. Existing targets are mutually inconsistent (mg-cc-tools' statusLine uses `$CLAUDE_PROJECT_DIR`, other targets use `${CLAUDE_PROJECT_DIR:-.}` or bare-relative commands), so byte-matching every target is impossible — instead the installer normalizes legacy variants to the canonical form on first install (a one-time, expected diff) and is churn-free thereafter.

### D6: Source the fork via the `[external]` archive convention; keep mg-gsd-wrappers separate

**Choice:** The `gsd-fork` tool declares its source with the existing `[external]` keys — `archive = "mg-gsd-fork"` (a directory name under the `external-tools/` sibling) plus `repo` for provenance — and `install.sh` composes the path as `../external-tools/<archive>` relative to the mg-cc-tools root. `mg-gsd-wrappers` is not folded into this work.

**Why:** This is exactly the `devils-advocate` convention: tool.toml's `[external]` values are documentary metadata (the library validates key *names* — an unknown key raises `ValueError` — but never reads the values), and the `../external-tools/` prefix lives in the tool's `install.sh`. Reusing the key set avoids machine-specific absolutes and requires no `_EXPECTED_KEYS` schema change. Keeping the wrappers separate holds this change's scope down.

### D7: Installer is a thin `install.sh` over a Python helper

**Choice:** The `gsd-fork` installer is a thin `install.sh` (argument parsing, target resolution, invocation) that delegates the deterministic work — stale-safe copy, idempotent `settings.json` merge, legacy-residue cleanup — to a Python helper under `install/scripts/`.

**Why:** CLAUDE.md mandates that deterministic logic live in `scripts/*.py`, not embedded in shell/markdown; JSON-merge is exactly that, and is error-prone in bash. mg-cc-tools already runs its install logic through `mg-install-lib.py`, so a Python helper is consistent and unit-testable.

**Alternatives rejected:** Pure-bash `cp`+`sed` (as `devils-advocate` uses) — adequate for a plain skill copy, but not for JSON-merge and orphan handling.

### D8: Remove GSD's self-update machinery from the fork

**Choice:** Delete `/gsd:update`, `/gsd:reapply-patches`, the `update.md` workflow, and the `gsd-check-update` hook from the fork, plus the statusline's update-available badge branch (which only reads the cache that hook wrote). The installer wires no SessionStart entry and removes the legacy entry and hook file from targets. Updates flow exclusively through `/mg:install <target> gsd-fork`.

**Why:** The machinery points at upstream npm. `gsd-check-update` compares the installed version against `npm view get-shit-done-cc version` — it would nag every session once upstream moves past the fork. `/gsd:update` runs `npx get-shit-done-cc`, i.e. upstream `install.js` with the entire retired ceremony (manifest timestamp, `gsd-local-patches/` backup, bare-relative hook wiring, reapply prompt) — a single invocation in any target clobbers a fork install. With the fork as single source and mg:install as the only deploy path, an in-target update surface has no legitimate use.

**Accepted limitation:** with the in-target nag gone, nothing signals that a target is behind the fork. `mg:install`'s status scan checksums the *tool directory* (`gsd-fork/` = tool.toml + install.sh), not the fork's content, so fork commits never flip the status table to "update" — updating each target is a deliberate, owner-initiated act. That is acceptable for a sole owner who deploys on his own cadence; no replacement signal is built (see What does NOT get built).

**Alternatives rejected:** Repointing `/gsd:update`/`gsd-check-update` at the fork — extra machinery to maintain for a nudge the sole owner doesn't need. Install-time exclusion (keep in fork, skip on copy) — leaves dead machinery in the source of truth and adds an exclusion list to the installer.

### D9: Fork is fully independent of upstream; commit the project-local path form

**Choice:** The fork no longer merges upstream GSD releases. Its `.md` files are converted once from upstream's portable `$HOME/.claude` paths to the project-local `./.claude` form and committed; the installer copies files verbatim, with no path-rewrite step.

**Why:** Upstream's portable-path form only earns its keep if upstream merges continue — it kept fork files textually close to upstream and pushed the project-local derivation to install time. With the fork fully independent (and the upstream update machinery removed — D8), that derivation step is pure overhead: committing the deployed form makes install a plain copy, shrinks the installer, and removes a whole class of rewrite bugs from the determinism contract (D4).

**Alternatives rejected:** Keep portable paths + install-time rewrite — preserves merge-friendliness the fork no longer needs, at the cost of a rewrite step that must itself be deterministic and tested.

## Scope

### What gets built

- **Overlay fold** — apply the 8 `gsd-patches` overlays into the fork's workflow `.md` and hook `.js` files, committed in the fork.
- **Update-machinery removal** — delete `commands/gsd/update.md`, `commands/gsd/reapply-patches.md`, `workflows/update.md`, `hooks/gsd-check-update.js`, and the statusline update badge from the fork (D8).
- **Path-form conversion** — one-time rewrite of the fork's `.md` files from `$HOME/.claude` to the project-local `./.claude` form, committed in the fork (D9).
- **Test relocation** — move `get-shit-done/test/status-bug7.test.cjs` (the only file in that directory) to the fork's top-level `tests/`, adjusting its default gsd-tools path for the new location, and delete `get-shit-done/test/` — so the wipe-and-recopy ships no test files. Committed in the fork.
- **`gsd-fork/` tool** in mg-cc-tools — `tool.toml` (`[external]` with `archive = "mg-gsd-fork"` per the devils-advocate convention — D6) + a thin `install.sh` over a Python helper in `install/scripts/` (D7), implementing the 9 installer requirements above. This is the one non-trivial piece: stale-safe copy + idempotent `settings.json` wiring.
- **`gsd` preflight flip + install-order hoist** in `install/scripts/mg-install-lib.py` — `run_preflight` (:547) passes the `gsd` check (:135) when `.claude/get-shit-done` exists *or* `gsd-fork` is selected in the same run; `get_install_plan` (:1580) hoists `gsd-fork` to the front of the plan so it installs before dependent tools; fix message updated to "co-install gsd-fork".
- **Retire `gsd-patches/`** — remove the tool directory, patches, and the `/mg:apply-gsd-patches` command.

### What does NOT get built

- **Wrapping or using GSD's `install.js`** — unsuitable (D3).
- **A symlink / global-install consumption model** — set aside; per-project tracked copies are retained (D4).
- **Folding `mg-gsd-wrappers` into the fork** — stays a separate tool (D6).
- **GSD's local-patch backup/reapply mechanism** — deliberately not replicated (D3).
- **Fork-staleness signaling** — no mechanism tells a target it is behind the fork (the status scan checksums the tool dir, not the fork — D8's accepted limitation). Updates are deliberate, owner-initiated `/mg:install` runs.

## Open Items

None outstanding. Resolved during discussion and review:

- **Upstream-merge model** → **D9** (fully independent). No upstream merges; the fork commits the project-local path form directly, and the installer's path-rewrite step is dropped. The upstream drift the fold-set item cites (PR-numbered commits) is historical — already-merged upstream work, not an ongoing flow.

- **Upstream update machinery** → **D8** (removed from the fork). `gsd-check-update` nagged against upstream npm; `/gsd:update` would run upstream `install.js` — the entire retired ceremony — and clobber a fork install. Updates flow exclusively through `/mg:install <target> gsd-fork`.

- **Installer implementation surface** → **D7** (thin `install.sh` over a Python helper). `post-install-configure.py` does no `settings.json` wiring today, so the installer owns settings wiring regardless — and per CLAUDE.md that logic belongs in Python.
- **Settings-wiring form / ownership** → **D5**. The `$CLAUDE_PROJECT_DIR` form is the established mg convention (matching `permission-hooks`); the `gsd-patches` overlays touch hook *files*, not settings *entries*, so the `gsd-fork` installer takes ownership and normalizes targets to the canonical form.
- **Fold-set completeness** → **validated.** The 8 `gsd-patches` are the full local-customization set; the remaining fork↔install `.md` divergence is upstream/path drift (fork-ahead, PR-numbered commits — #841, #786, #644), which install-from-fork resolves. A per-file audit at fold time (see Verification) is the safeguard before deleting `gsd-patches`.

## Verification

- **Source edits are testable:** an edit in the fork, followed by `node scripts/run-tests.cjs`, runs against the suite and reports green/red.
- **Clean install:** `/mg:install <target> gsd-fork` into a fresh project produces `get-shit-done/`, `commands/gsd/`, `agents/`, `hooks/`, and a wired `settings.json`, non-interactively, with no prompts.
- **Determinism (the load-bearing check):** running the install twice on an unchanged fork produces an **empty `git diff`** in the target — no manifest timestamp, no `gsd-local-patches/` sidecar, no churn.
- **Patch system is gone:** after deploy, `gsd-patches` / `/mg:apply-gsd-patches` is never invoked, and folded customizations are present from the fork — e.g., `discuss-phase` accepts `--check-remaining`, and `settings.json` hooks use the `$CLAUDE_PROJECT_DIR` form.
- **Preflight + ordering:** on a fresh target, co-selecting `gsd-fork` with a gsd-dependent tool passes preflight, and the install plan lists `gsd-fork` first; the "install upstream GSD" fix message no longer appears.
- **Stale-safe:** a file removed from the fork is absent from the target after re-install (not orphaned).
- **No test files shipped:** after the relocation, `get-shit-done/test/` is gone from the fork (and hence from targets), and `node scripts/run-tests.cjs` still discovers and passes `status-bug7.test.cjs` from `tests/`.
- **Legacy residue removed:** after install, `.claude/gsd-file-manifest.json` and `.claude/gsd-local-patches/` are absent from the target.
- **Update machinery gone:** after install, `commands/gsd/update.md` and `commands/gsd/reapply-patches.md` are absent (wipe-and-recopy drops them), `.claude/hooks/gsd-check-update.js` is absent, and `settings.json` contains no SessionStart GSD entry.
- **Settings normalization:** on a target with legacy-form entries (bare-relative or non-canonical `$CLAUDE_PROJECT_DIR` variants), the first install rewrites them to the canonical form exactly once — no duplicate hook entries are created — and a second install produces no `settings.json` diff.
- **Malformed settings fail-safe:** with an invalid-JSON `settings.json` in the target, the installer exits non-zero and the file is byte-identical to before the run.
- **Path form:** after the D9 conversion, no `$HOME/.claude` or `~/.claude` references remain in the fork's deployable `.md` files — installed copies are byte-identical to the fork.
- **Fold-set audit:** before `gsd-patches` is deleted, a per-file check confirms the 8 patches are the only local customizations — remaining fork↔install `.md` divergence traces to upstream/path drift, not lost local edits.
