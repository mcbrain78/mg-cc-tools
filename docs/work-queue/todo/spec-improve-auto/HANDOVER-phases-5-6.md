# Handover — `mg:spec-improve-auto`, Phases 5 & 6

**Purpose:** resume the build of `mg:spec-improve-auto` in a **fresh session**. Phases 1–4 and both capability gates are done, committed, and green. This doc + the concept + the repo are everything you need for Phase 5 (registration/install) and Phase 6 (integration trials + the convergence dry-run).

## How to use this (fresh session, first 5 minutes)

1. Read the auto-loaded memory `project_spec_improve_auto_status` (the live resume anchor) and `project_spec_improve_auto_gate_a_findings` (3 non-obvious Workflow-tool facts).
2. Skim `git log --oneline -8` — the last 5 commits are this build (Phases 1a→4).
3. The design authority is `docs/work-queue/todo/spec-improve-auto/concept.md` (520 lines). The original plan is `~/.claude/plans/polymorphic-giggling-lightning.md`.
4. Start Phase 5 below. **Checkpoint after each phase** (atomic commit staging only that phase's files — never `git add -A`, there are pre-existing unrelated dirty files — plus update the status memory). No push unless the user asks.

---

## Where things stand — DONE (all committed on `main`)

| Phase | What | Commit |
|---|---|---|
| Gate A | Workflow capability spike — **GO** (Workflow tool validated: dynamic loops, conditional stages, computed fan-out, 40/40 scale, byte-identical relay) | (spike, no artifact) |
| Gate B | Ledger-fidelity spike — **GO** (span/hash/touched-section/reverse-marshal fidelity all confirmed with real agents) | (spike, no artifact) |
| 1a | `spec/scripts/improve_files.py` hardened (init guard + `--fresh`, `paths`, `append-note`/`note-ids`, `append-changelog`, `append-decision`/`update-decision`, `snapshot`, move-not-copy sidecar lifecycle, `next_run`) | `16fc211` |
| 1b | `spec/scripts/spec_checks.py` core (`structure`, `tally` +head-to-head, `block-gate`, `floor`, `briefing`, `decisions summary`) + minimal atom ledger | `300a420` |
| 2 | Full atom ledger (`atoms` group): `extract`, `merge`, `reanchor`, `mark-dirty`, `record-verdicts`, `coverage`, `radius`; lineage, churn | `c8922f2` |
| 3a | Ledger subcommands the drain needed: `atoms churn-check`, `atoms macro-ids`; `finding_atoms` in `decisions summary` | `cd40958` |
| 3b | `spec/workflows/spec-improve-auto.js` — the drain orchestrator (1378 lines) | `f6d7968` |
| 4 | `spec/commands/spec-improve-auto.md` — the outer-loop command | `9a3866c` |

**State:** 181 pytest tests green, `spec/` ruff-clean, `node --check` clean on the drain. **Both load-bearing bets (Workflow orchestration, ledger fidelity) are retired.** The remaining unfalsified bet is *convergence value* — whether finding-ids stay stable over many rounds so the loop converges rather than thrashes — which **only Phase 6's first real run falsifies** (see `project_spec_improve_auto_ledger`).

## The build map (file → what it is → key interface)

- **`spec/scripts/improve_files.py`** — all file ops (stdlib). `init`/`paths` emit the resolved-paths JSON the drain runs on; sidecar writers; `snapshot`; archival lifecycle. Tests: `spec/scripts/tests/test_improve_files.py` (51).
- **`spec/scripts/spec_checks.py`** — deterministic core + the atom ledger (stdlib + a subprocess into `milestone_checks.py` for `floor` only). CLI groups: top-level (`structure`/`tally`/`block-gate`/`floor`/`briefing`/`decisions`) and `atoms <sub>` (`extract`/`merge`/`reanchor`/`mark-dirty`/`record-verdicts`/`coverage`/`radius`/`churn-check`/`macro-ids`). Run `uv run spec/scripts/spec_checks.py` with no args for USAGE. Tests: `test_spec_checks.py`.
- **`spec/scripts/milestone_checks.py`** — pre-existing; **untouched**. `floor` wraps its `citations` check.
- **`spec/workflows/spec-improve-auto.js`** — the drain. Control-flow + inline prompts only; every deterministic value comes from a `spec_checks.py`/`improve_files.py` CLI call relayed as `script_output` and `JSON.parse`+validated before branching. Returns exactly `{status, rounds, fixed, below_bar}`. **Has never run end-to-end** — Phase 6 is its first real exercise.
- **`spec/commands/spec-improve-auto.md`** — the outer-loop command. `allowed-tools`: Bash, Read, AskUserQuestion, Workflow (no Edit/Write). Invokes the drain via `Workflow({scriptPath, args})`; branches on the return; derives briefing/scorecard command-side. **Uses the placeholder `{MG_INSTALL_WORKFLOWS_DIR}` which Phase 5 must wire into `install.sh`.**

**Drain args shape** (what the command passes / the drain parses, snake_case; camelCase tolerated):
`{ paths: <the whole init/paths JSON, path values absolutized>, scripts_dir, template_path, scratch_dir, run: <next_run>, overrides: [...], directives: [...] }`.

## Three Workflow-tool facts baked into the design (don't relitigate)

1. **`args` can arrive as a JSON string** — parse defensively: `const A = typeof args === 'string' ? JSON.parse(args) : (args||{})`. (Already in the drain.)
2. **`agent()` has no inline `tools` param** — per-role tool grants are via `agentType` (`general-purpose` = all tools for Bash/Edit roles; a read-only type like `Explore` for pure readers/verifiers).
3. **Marshal scratch files only under the threaded `scratch_dir`**, never the project tree.

## The build pattern that worked (reuse it)

Phases 3 & 4 were built via **dynamic workflows** (`Workflow` tool) to keep main-session context lean: **brief → write → 2–3 fresh-eyes reviews (parallel) → fix → validate**, returning only a compact summary. The persisted builder scripts are in the session's `workflows/scripts/` dir (not reusable cross-session, but the pattern is). The review stages caught real bugs both times — keep them. The Workflow tool is opt-in; this build has standing opt-in via the user's explicit requests ("use a dynamic workflow"). Confirm with the user before spawning large workflows.

---

## PHASE 5 — Registration + install (small, mechanical, self-validating)

**Authority:** concept §"Registration and installation" + §Scope "What gets built" (last three bullets). Three files, then one install test. Consider a dynamic workflow with the install-test as its validation stage — or just do it directly (it's small; read `spec/install.sh` first to confirm current line positions).

### 5.1 `spec/install.sh`
Mirror the existing `scripts`/`references` handling. Concretely:
- Add `spec-improve-auto` to the `COMMANDS=(...)` array (near the top, ~line 25).
- Add a **workflows copy step** next to the scripts copy (~line 159–163): validate the source `.js` exists (mirror the `for cmd/ref ... missing` validation loops ~line 103–115), then `WORKFLOWS_DIR="${TARGET_DIR}/spec/workflows"; mkdir -p "$WORKFLOWS_DIR"; cp "${SCRIPT_DIR}/workflows/"*.js "$WORKFLOWS_DIR/"`.
- In the placeholder-resolution block (~line 179–200): define `WORKFLOWS_PATH` alongside `SCRIPTS_PATH` — project mode → `.claude/spec/workflows`, else → `${WORKFLOWS_DIR}` — and add to the per-command `sed` loop: `sed -i "s|{MG_INSTALL_WORKFLOWS_DIR}|${WORKFLOWS_PATH}|g" "$cmd_file"`.
- Add an invoke-echo line in the summary (~line 224–231): `/mg:spec-improve-auto <file-path>`.
- **Convention (CLAUDE.md):** a new `{MG_INSTALL_*}` reference in a command file **requires** its `sed` replacement in `install.sh` — that's exactly this step. New `spec/scripts/*.py` are auto-globbed (no install change); only the `.js` needs the new copy step + placeholder.

### 5.2 `spec/commands/spec-help.md`
Add the `spec-improve-auto` listing (the "Commands" block; optionally the pipeline diagram). It's the autonomous sibling of `spec-improve`.

### 5.3 `spec/commands/spec-improve.md` — the inherited resume branch (D7)
Its Setup step must now handle the `improve_files.py init` **guard failure** (init now exits 1 if a working copy exists, a breaking change from Phase 1a): on exit 1 → run `paths` → AskUserQuestion **resume** (use existing working copy) vs **`--fresh`** (discard+restart). Document the inherited guard. This is *strictly safer* than today's silent reset — the review found `spec-improve` previously reset the working copy unconditionally. Do not change its review loop, cap, or approval flow.

### 5.4 Install test (self-validation)
`bash spec/install.sh --target <THROWAWAY-tmp-dir>` (e.g. `/tmp/…/p5-install`; **never** a real project path). Assert: the command lands with **all** placeholders substituted (grep the installed `.md` for a leftover literal `{MG_INSTALL_` → must be none, especially `{MG_INSTALL_WORKFLOWS_DIR}`); `spec-improve-auto.js` is under `<target>/.claude/spec/workflows/`; the `spec-help` listing shows the new row. Also re-run `uv run pytest spec/ -q` (still green) and `uv run ruff check spec/`.

### 5.5 Checkpoint
Commit (stage only `spec/install.sh`, `spec/commands/spec-help.md`, `spec/commands/spec-improve.md`). Update `project_spec_improve_auto_status` (Phase 5 → done, Phase 6 → next). Mark the Phase-5 task done.

---

## PHASE 6 — Integration trials + convergence dry-run (heavy; the drain's first real run)

**Authority:** concept §Verification (every bullet from "Gate panel trial" onward; the capstone is "**Convergence dry-run**"). This is the biggest remaining effort and needs a **full context budget** (that's why it's a fresh session).

### Headline: the drain has NEVER run end-to-end
Expect **real drain bugs** on the first run — logic that unit tests and static review couldn't catch. Budget for **iterative debugging**. Your diagnostic substrate is exactly what the design persists: after each round the drain writes `history/run-N/round-M.md` (working-copy snapshot) and `round-M-verdicts.json` (atom verdicts, findings, judge votes, tally). Read those to see what each round did. `git log` per-phase commits mean you can revert a bad drain edit cleanly.

### How to run it
1. Build a **small fixture concept spec** (~60–150 lines, template-conformant so `structure`/`floor` pass) with **planted issues** per the dry-run bullet:
   - macro: one **contradiction** + one **gap** (Phase H should fix these first);
   - micro: a **false claim** (cites code that doesn't say that) + a **mismatched example**;
   - a **below-threshold** decision-shaped issue (should auto-take, D-block written, `review_first`) and a **threshold-exceeding** one (should `block`).
   Put it at a throwaway path (e.g. `/tmp/…/p6-fixture/concept.md`) with a fake/minimal cited-code file so claim checks have something to read. **Never point the drain at a real project path.**
2. Install into a throwaway target (Phase 5's installer) OR invoke the drain directly with a hand-built args object. The cleanest end-to-end is: install → run `/mg:spec-improve-auto <fixture>` in that target. **This spawns dozens of agents** — it's the concept's `~40–160` first-sweep width. Confirm cost with the user before the first full run; consider a **reduced fixture** first (fewer atoms) to shake out mechanics cheaply.
3. Expected happy path: macro fixed in Phase H → micro fixed with changelog entries → below-threshold auto-taken → exits **`blocked`** on the threshold-exceeding decision → a **directive/override re-run** → **`converged`** with a briefing carrying all records; an override re-run re-drains only that decision's post-take radius.

### The trials (each validates a live behavior unit tests can't)
Gate panel trial · atomic-check trial (incl. the **unverifiable** verdict) · implementability-probe trial · exit-exam trial (planted evade-atomization flaw) · competitive-rewrite trial · structural-edit re-check trigger · decision dedup · gate memory · churn escalation · swarm shrinkage · and the capstone **convergence dry-run**. Some are assertable from the `history/` verdict logs of the dry-run; others want a focused fixture. You can orchestrate these as dynamic workflows too.

### The convergence bet (the thing Phase 6 exists to falsify)
Across the dry-run's rounds, check the `history/` record: do **finding-ids stabilize** round-over-round (so below-bar memory + churn escalation hold), or do they **jitter/thrash toward round-cap**? Stable → the ledger's load-bearing justification holds. Thrash on a should-converge spec → fire the D3 **no-ledger hybrid** fallback (a bounded redesign of the *finding-production* layer only; `spec_checks.py`/`improve_files.py`/the sidecars survive). See `project_spec_improve_auto_ledger`.

### Tracked residual to revisit here
`spec/workflows/spec-improve-auto.js` has one minor residual: a `findingId` JS **fallback** that sort/joins section paths for a finding with no pre-set id (the main macro path already uses the `atoms macro-ids` relay). If the dry-run exercises that fallback, route it through `macro-ids` too; otherwise leave it (defensive edge).

### Checkpoint
Commit any drain/script fixes the dry-run forced (atomic, per fix). If you add fixtures/tests, commit them. Update the status memory; mark Phase 6 done → the tool is complete. Then the tool can be installed and used on the next real concept spec (the ultimate acceptance test: a full run converges without a manual abort).

---

## Verification cheatsheet

```bash
uv run pytest spec/ --tb=short -q --no-header      # never pipe pytest (masks exit code)
uv run ruff check spec/                             # must stay clean (repo-wide `ruff check .` has PRE-EXISTING debt in transcript/ — not ours)
node --check spec/workflows/spec-improve-auto.js    # drain must parse
bash spec/install.sh --target /tmp/…/throwaway      # install test (Phase 5)
uv run spec/scripts/spec_checks.py                  # prints USAGE (all subcommands)
```

## Hard constraints (carry forward)
- **Checkpoint after every phase** — atomic commit (stage only that phase's files) + update the status memory. No push unless asked. (`feedback_checkpoint_after_each_phase`.)
- **`spec/` must stay ruff-clean and pytest-green.**
- **JS = control flow + prompts only**; all determinism in the Python CLIs. **No embedded Python/JS in `.md` files.**
- **Never point the drain or install at a real project path** — always throwaway tmp dirs.
- Stay on `main`; keep commits atomic. `.serena/project.yml` + `docs/work-queue/todo/{gsd-*,mg-*}` are pre-existing dirty/untracked — leave them.

## Pointers
- Design: `docs/work-queue/todo/spec-improve-auto/concept.md`
- Plan: `~/.claude/plans/polymorphic-giggling-lightning.md`
- Memories: `project_spec_improve_auto_status` (resume anchor), `project_spec_improve_auto_gate_a_findings` (Workflow facts), `project_spec_improve_auto_ledger` (the convergence bet), `feedback_swarm_design_philosophy`, `feedback_checkpoint_after_each_phase`, `feedback_fresh_eyes_review`.
