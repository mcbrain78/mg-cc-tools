# resumable-workflow — handover

**Status: PAUSED 2026-09-02**, at the owner's request — the need for the command is
itself under review. Nothing is broken or half-applied: the source is committed, the
full test suite is green, and the installer validates. It is simply not finished being
*proven*, and it is installed nowhere.

Do not resume by reading the code first. Read **"What has never run"** below; it is the
whole reason this is parked rather than done.

---

## What it is

`/mg:resumable-workflow <task>` runs a dynamic multi-agent investigation as a
**main-session loop**: decompose the task into questions, research them in parallel,
adversarially verify the findings, assess what is still missing, and repeat until the
investigation stops learning anything new — then summarize from what survived
verification.

Every step is durable. Agents write their own output to disk and the loop re-derives its
entire state from a ledger at the top of each round, so a run that dies to a context or
usage limit resumes by **re-typing the same command** — the task text hashes to the same
run directory.

Run state lives at `.mg/resumable-workflow/runs/<slug>-<hash8>/`.

## Why it does not use the built-in `Workflow` tool

Two reasons, and only the first is airtight:

1. **Durability (decisive).** A `Workflow` script has no filesystem access and no tool
   access — only the subagents it spawns have tools — and `resumeFromRunId` is
   **same-session only**, replaying a runtime-held journal. So a Workflow-based run
   cannot survive the session ending, which is the entire point of this tool.
2. **Cost (weaker than it first appears).** `AUTO2-DESIGN.md:28` records a Workflow
   orchestrator in this repo measuring **16.5M tokens / 2 rounds / 77 agents on a
   62-line fixture, never converging**, with a caching probe (`wf_7640160e-133`) proving
   the runtime does **not** cross-agent-cache context, so fan-out cannot amortize a
   shared corpus.

**Correction that must not be re-introduced:** it is *not* established that the
main-session loop is cheaper. `EFFICIENCY-DESIGN.md` measures exactly one architecture —
the Workflow drain — and contains no main-session figures at all; its planned A/B had
both arms inside the drain and never ran. `AUTO2:28`'s "~10× too expensive" appears
nowhere in the document it cites. An earlier draft of `commands/resumable-workflow.md`
claimed the loop was "measured cheaper"; that clause was found and removed by the tool
running on itself. What is supported: *the Workflow drain measured 16.5M and never
converged*, and *the runtime shares no context between agents*.

## What is built

```
resumable-workflow/
├── tool.toml                       python3 preflight; detect .claude/resumable-workflow/scripts/
├── install.sh                      three modes; validated by mg-install-lib.py validate
├── commands/resumable-workflow.md  the loop (256 lines)
├── agents/                         digest, decompose, research, verify, assess, summarize
└── scripts/run_state.py            the ledger (838 lines) + 781 lines of tests
```

Commits, oldest first:

| Commit | What |
|---|---|
| `242b45d` | the durable run-state ledger |
| `5f6aada` | the loop, agents, installer |
| `bea24c9` | `digest_path` pointed at a file that was never created |
| `1330d1c` | four defects the tool found in itself |
| `d9892f6` | bound the verification fan-out (batching + agent ceiling) |
| `e5f1181` | default the ceiling to 50 |

`run_state.py` subcommands: `resolve`, `add`, `claim`, `complete`, `fail`, `reap`,
`round`, `status`. Stdlib only, hand-rolled flag parsing (house style, keeps the 0/1
exit contract), one JSON object on stdout. Invoked as bare `python3` — no venv.

## What is verified

- **78 unit tests** over the ledger; **2589** full-repo suite green; `ruff` clean.
- `install.sh` validated by the repo's own `mg-install-lib.py validate` in **both**
  `--project` (relative placeholders) and `--target` (absolute) modes.
- **Script-level resume**: a fabricated mid-run ledger resumes at the correct round,
  lists only the unresearched question as pending and only the unverified finding, and
  skips completed steps returning their prior summaries. A reworded task
  (`audit the WIDGET auth flow` vs `Audit the widget auth flow`) resolves to the same
  run.
- **Convergence rule** fires correctly on `dry_rounds >= 2` + `all_complete`.
- **One real round** on the tool's own source: digest → decompose → 6 research agents,
  all with live agents. It found six defects in the tool (see below).
- **Fan-out reduction measured** on the real shape: 141 → 21 agents a round.

## What has never run — read this first

- **No run has ever converged.** The **verify**, **assess** and **summarize** stages
  have *never executed with live agents*. Only digest, decompose and research have.
- **`assess` is the highest-risk unexercised component.** It drives termination: a
  completeness critic that manufactures gaps prevents convergence forever, and one that
  gives up early ends the run on a false clean. Its behaviour is entirely unknown.
- **The batched verifier's quality is unmeasured.** See "the fan-out trade" below.
- **No cross-session drill.** Resume has only been exercised in the session that wrote
  the code — which masks a broken re-derivation, because the model still holds the state
  in context. It must be driven from a fresh `claude -p`.
- **The default ceiling makes convergence unreachable out of the box.** 50 agents ≈ two
  rounds at the measured shape (~21/round); converging needs at least three, two of them
  dry. Any real run must pass `--max-agents` (≈120 for a six-question task) or use a
  narrower task. This is deliberate — the operator chooses the budget — but it means
  "just run it" will stop on the ceiling.

## The measurement that should drive future decisions

Research agents produce a **mean of 11 findings per question** — observed 9, 11, 13, 15,
16, 29 across six questions on a real task. The design had implicitly assumed 2–3.

Any design that fans out per *finding* is therefore ~11× more expensive than it looks.
This single number is why verification is batched, and it should be re-measured on a
different task before anything else is tuned.

## Design decisions not worth re-litigating

Each of these was arrived at the hard way; the rationale is in the code comments and the
commit messages.

- **The ledger record is the done-marker, never file existence.** A payload on disk may
  have been truncated by a kill mid-write. A payload with no `complete` record is redone
  and overwritten — safe only because a step's sole durable effect is its own payload.
- **Ids are content slugs, never positional.** An index-derived id names a different item
  once the set shrinks, so `claim` would skip work never done. Slugs also make `add`
  idempotent, which is what lets decomposition re-run every round without duplicating
  research.
- **All loop state is derived, never stored** — round number from closed-round markers,
  dry count from their `new_questions`, and `new_questions` itself from the question
  records' `round` tag. A stored counter loses a round on one side of a crash or the
  other; see defect 2 below for what that cost.
- **Appends are single `os.write`s of pre-encoded bytes under `flock`**, and the fold
  tolerates unparseable lines while reporting `corrupt_lines`. `_append` also closes an
  unterminated final line before appending — without that, one torn write silently
  swallows every later record.
- **`complete` is terminal in the fold**, by record precedence rather than line order, so
  a zombie agent from an interrupted session cannot reopen a finished step and overwrite
  a good payload.
- **Payload files are `handoff-*`, derived by the script.** A subagent `Write` to a
  `findings`/`report`-named file trips a Claude Code guard that returns the content in
  the response instead of writing it, breaking the step. Deriving the name in code means
  a prompt cannot get it wrong.
- **The orchestrator never reads a payload.** It runs `status`, spawns agents with
  absolute paths, and reads back one-line summaries. That is what holds main-session
  context flat across 20 rounds — and context never held cannot be lost to a compaction.
- **`status` carries text, not just ids.** An id is a slug truncated at 40 chars, so the
  loop cannot recover a question or a refuted finding from one, and it may not read
  payloads. Findings also carry their parent `question`, which is what makes batching
  possible.
- **The agent ceiling is cumulative across invocations, and `summary` is exempt.**
  Per-turn counting is the flaw that makes the built-in `budget` unenforceable across
  sessions. The exemption exists because the loop's response to exhausting its allowance
  is to summarize what it has — refusing that claim would deadlock the run and discard
  every agent already paid for to save one.

## What the tool found when run on itself

Worth preserving as evidence that dogfooding pays here: one round on its own source
surfaced six defects, two proven by execution rather than reading. All are fixed.

1. **`digest_path` mismatch** — `resolve` emitted `<run_dir>/digest.md` while
   `claim digest` sent the agent to `handoff-digest.md`, so every downstream agent was
   pointed at a file that is never created. Caught by the *digest stage itself*, before
   any research ran. The existing test missed it because `endswith("digest.md")` is true
   of `handoff-digest.md`.
2. **False dry round** — if a session died between decompose's first `add` and the
   `round` call, the re-run computed `Q_after − Q_before = 0`, because the total it read
   already included the dead attempt's questions. Two such rounds satisfied
   `dry_rounds >= 2` and converged a run that never had a dry round — on a tool whose
   whole purpose is surviving interruptions. Reproduced by driving a real
   interrupted-resume cycle.
3. **Orphaned claims stranded the run** — a verify agent that recorded its verdict and
   then died left a step in neither `pending` nor `unverified` while keeping
   `open_steps` non-empty, pinning `all_complete` False forever. Fixed with `reap`.
4. **Unbounded agent count** — see the fan-out section.
5. **Refuted-finding text was unobtainable** — step 3.1 required text `status` did not
   emit and that no permitted source could supply.
6. **Question text never reached research agents** — `pending` gave ids only while the
   prompt promised the question. (The orchestrator hit this live and worked around it by
   reading the ledger, violating its own state discipline without noticing.)

## The fan-out trade, and the options not taken

Per-round cost is `3 + N + L·N·F` (questions × lenses × findings-per-question). `F` was
the term nobody had bounded, and at a measured mean of 11 it dominated: per-finding
verification cost **141–207 agents for a six-question round**, against the built-in
Workflow tool's entire 1000-agent lifetime cap, in round one of twenty.

**Chosen (C):** one verify agent per *(question, lens)* — it takes every unverified
finding of that question and records a verdict per finding. Removes `F` from the
dominant term: **141 → 21 agents**, measured, with nothing discarded. Zero change to the
ledger model. Also the right axis, since nothing shares context between agents: one
agent checking eleven related claims reads the digest once where eleven read it eleven
times.

**Its cost, unmeasured:** a batched verifier splits attention across ~11 claims instead
of attacking one. `verify.md` mitigates by requiring claim-by-claim work and preferring
`fail` over rubber-stamping a long tail, but **whether verdict quality actually holds up
has not been tested.** If it does not, these were the runners-up:

- **A — cap findings per question at ~5.** Simplest; enforceable deterministically in
  `add`. Rejected because it discards real findings and the *research* agent picks what
  to drop, blind, before verification has any say.
- **B — record all findings, verify only the top-K per round.** No information loss, and
  the summary can honestly say "45 recorded, 25 verified". Rejected for now as the most
  machinery: it needs a ranking mechanism and `all_complete` must learn a *deferred*
  state.

**Also added (D):** a cumulative lifetime agent ceiling, enforced in `claim` as well as
in the loop's prose — a runaway is exactly when prose is not followed. Refusing at claim
time cannot un-spawn an agent but stops it working, degrading a runaway from N expensive
agents to N that return after one Bash call.

## Where to continue, in order

1. **Run it once to convergence.** Everything below is speculation until this happens.
   Use a genuinely narrow task and `--max-agents 120`. Watch specifically: does `assess`
   ever return zero gaps, and at which round? If it thrashes, the loop cannot terminate
   and the design needs more determinism — learn that cheaply, before tuning anything
   else. This mirrors how `spec-improve-auto` was validated (`AUTO2-DESIGN.md`, "validate
   the load-bearing bet").
2. **Cross-session resume drill.** Fabricate a mid-run ledger, then drive the command
   from a fresh `claude -p` so the model holds no state. Assert it resumes at the right
   round, re-researches nothing, and that folded state has exactly one `complete` per
   step. Assert on *folded state*, not raw line counts — a re-claimed step legitimately
   changes those.
3. **Measure the batched verifier.** Run both shapes over the same finding set and
   compare verdicts. If batching materially degrades quality, adopt A or B above.
4. **Decide whether `F` needs a bound of its own.** Batching removed findings-per-question
   from the *verify* term, but research agents still record unboundedly many, which
   inflates the assess input and the summary. A soft cap enforced in `add` is a one-line
   change if it turns out to matter.
5. **Harden the prose-only bounds.** The 20-round cap and the batch-of-8 are instructions
   an LLM follows, not enforced limits. The agent ceiling now backstops the blast radius,
   but the round cap in particular is re-armable simply by re-invoking.
6. **Decide the scale escape hatch** (deferred by decision). Main-session batching is
   right to roughly 100–150 steps per run; past that, the per-batch barriers and
   accumulating one-line returns cost more than the Workflow sandbox's friction, and the
   answer is a main-session loop that delegates a single wide stage to a `Workflow` call
   used purely as a parallel-map — keeping resume logic where the tools are. Not built.
7. **Usage gating and cron auto-resume** (dropped by decision, to keep resume manual).
   The machinery is generic and already exists at `spec/scripts/spec_checks.py`
   `cmd_usage_gate` — it reads the real `/usage` cost-free and emits a one-shot cron
   string. If revived, note the repo's mirroring convention: that parser is duplicated in
   `permission-hooks/scripts/usage-read.py` rather than shared, and has already taken two
   bug-fix commits.

## Operational notes for whoever picks this up

- **Never install it automatically.** Repo practice is to commit source and stop; a bare
  `install.sh` is only half of `/mg:install` and skips `settings.json`.
- **Tests must use `tmp_path` only.** `pyproject.toml` sets `-n auto` (pytest-xdist), so
  a shared on-disk fixture dir races across workers.
- **Test imports use `sys.path.insert` + `import run_state`** (the
  `permission-hooks/scripts/tests/` pattern). Spec's package-path style is unavailable —
  `resumable-workflow` is not a valid Python identifier.
- **Agents must not run destructive commands.** During the dogfood run, a research
  agent's demo script deleted every file under the shared scratch tree, taking the
  digest, the ledger and four payloads with it. The repo was untouched. `research.md`
  and `verify.md` now ban `rm`/`mv`/truncating redirects outside their own payload and
  require `${VAR:?}` bracing on any variable-rooted path. Keep that guardrail in any new
  agent file.
- The tool is **not** listed in the repo `README.md`, which covers only 4 of 14 tools and
  is stale generally.
