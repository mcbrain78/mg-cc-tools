# Resumable Workflow

---
name: mg:resumable-workflow
description: Run a dynamic investigation — decompose, research, verify, summarize — as a resumable main-session loop that survives a session death and picks up where it stopped
argument-hint: "<task> [--run-dir <path>] [--force]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Agent
  - AskUserQuestion
---

<objective>
Answer a substantial question by running a **dynamic multi-agent investigation**:
decompose the task into questions, research them in parallel, adversarially verify the
findings, assess what is still missing, and loop until the investigation stops learning
anything new. Then summarize from what survived verification.

Every step is **durable**. Findings go to disk as they are produced and the loop's state
is re-derived from that disk state at the top of every round, so a run that dies —
context limit, usage limit, crash — resumes by re-typing the same command. Nothing is
redone; completed steps cost one Bash call each.

The loop is driven **here, in the main session**, not by the `Workflow` tool. That is
deliberate: the orchestrator needs Bash and the filesystem to own durable state, and a
`Workflow` script has neither. It is also what this repo already measured as cheaper —
cost scales with agent **count**, and the runtime does not share context between agents,
so nothing amortizes a shared corpus except reading it once yourself.
</objective>

<context>
Arguments: $ARGUMENTS
</context>

## Step 1 — Bind the run

Parse `$ARGUMENTS`: the non-flag remainder is the **task text**; `--run-dir <path>` and
`--force` are optional. If the task text is empty, print this and stop:

```
Usage: /mg:resumable-workflow <task> [--run-dir <path>] [--force]

  <task>       What to investigate. The same text always resolves to the same run,
               so re-typing this command is how you resume.
  --run-dir    Resume a specific run directory (use when you reworded the task).
  --force      Start a new run even if a near-identical one exists.
```

Then run:

`python3 {MG_INSTALL_SCRIPTS_DIR}/run_state.py resolve --task "<task text>" [--run-dir <path>] [--force]`

Store from its JSON: `run_dir`, `digest_path`, `summary_path`, `status`, `round`,
`all_complete`. Every path it emits is absolute — hand those absolute paths to agents,
never relative ones; a subagent's working directory is not guaranteed.

**If it exits 1**, it is refusing to merge two runs into one ledger — either the
`--run-dir` belongs to a different task, or a near-identical run already exists. Show
its message and stop. Do not pass `--force` on the user's behalf: adopting the wrong run
dir silently mixes two investigations.

If `status` is `resumed`, say so before doing anything else: report the round it is
resuming at and how many questions are already answered. The user needs to know they are
continuing, not starting.

## Step 2 — Digest (once per run)

Spawn ONE **digest** agent with the instructions at `{MG_INSTALL_AGENTS_DIR}/digest.md`,
step id `digest`, and the sources the task names. It skips itself if already done, so run
it unconditionally.

This is the run's cost lever: every agent afterwards reads its output instead of the
corpus. Do not skip it even for a small task — two agents reading the same three files
already costs more than one digest.

## Step 3 — The round loop

Rounds `M = <round from resolve>` upward, to a cap of **20**. Each round:

### 3.0 Read the state

`python3 {MG_INSTALL_SCRIPTS_DIR}/run_state.py status <run_dir>`

Note `questions_total` — call it `Q_before`. This JSON is your **only** knowledge of the
run. Never carry a finding, a question, or a payload from a previous round in your own
context; re-read it here.

### 3.1 Decompose

Spawn ONE **decompose** agent (`{MG_INSTALL_AGENTS_DIR}/decompose.md`), step id
`decompose-r<M>`. Give it the task text, the absolute `digest_path`, and — on rounds
after the first — the absolute path to the previous round's assess payload
(`handoff-assess-r<M-1>.md` in the run dir) plus the text of any finding the majority
rule refuted last round.

### 3.2 Research

Re-run `status`. For every id in `pending`, spawn a **research** agent
(`{MG_INSTALL_AGENTS_DIR}/research.md`) with that id as both the step id and the
question, plus the absolute `digest_path`.

**Batch up to 8 agents per message** — multiple Agent calls in a single message run
concurrently. Wait for a batch, then send the next. Do not spawn more than 8 at once.

### 3.3 Verify

Re-run `status`. For every finding in `unverified`, spawn **verify** agents
(`{MG_INSTALL_AGENTS_DIR}/verify.md`), one per lens:

- Default **two** lenses: `correctness` and `sources`. Step ids `v-<finding-id>-correctness`
  and `v-<finding-id>-sources`.
- **Only if those two disagree**, spawn a third — `scope`, or `repro` where reproducing
  the reasoning is the real question — as the tie-break.

Two-plus-tie-break rather than three-always is a deliberate cost bound: verification is
where agent count explodes, and a unanimous pair needs no third opinion. Batch these the
same way, up to 8 per message.

### 3.4 Apply the majority rule

From `status`, for each finding: **refuted** when `refuted > verdicts / 2`, otherwise
**confirmed**. You own this rule; the script only counts. Keep the refuted ids — 3.1
feeds them to next round's decompose so the question behind them gets re-asked.

### 3.5 Assess

Spawn ONE **assess** agent (`{MG_INSTALL_AGENTS_DIR}/assess.md`), step id `assess-r<M>`,
with the task text, the absolute `digest_path`, the current `status` JSON, and the
absolute paths of this round's research payloads (`handoff-<question-id>.md`).

### 3.6 Close the round

Re-run `status` and take `questions_total` as `Q_after`. Then:

`python3 {MG_INSTALL_SCRIPTS_DIR}/run_state.py round <run_dir> --new-questions <Q_after - Q_before>`

### 3.7 Branch

On the one-line summaries and the `status` JSON alone — you hold no round content:

- **`dry_rounds >= 2` and `all_complete` is true** → converged. Go to Step 4.
- **`M` reaches 20** → stop at cap. Go to **On round cap**.
- Otherwise → increment `M` and start the next round at 3.0. Carry nothing forward.

## Step 4 — Summarize

Spawn ONE **summarize** agent (`{MG_INSTALL_AGENTS_DIR}/summarize.md`), step id
`summary`, with the task text, the `status` JSON, the absolute `summary_path`, the
absolute `digest_path`, the confirmed/refuted split from 3.4, and the absolute paths of
the research payloads.

Then report to the user:

- The path to `summary.md`, and its headline answer — read **only** the `## Answer`
  section to quote it.
- Scale: rounds run, questions asked, findings confirmed vs refuted.
- **What was reused vs computed** on this invocation, if it was a resume. A resumed run
  that reports nothing looks like a run that did nothing.
- Anything `abandoned`, and any `corrupt_lines` in the ledger.

## State discipline (load-bearing)

- **The orchestrator is a thin router.** It runs `status`, spawns agents with absolute
  paths, and reads back one-line summaries. It never reads a research payload, a verify
  payload, or a digest. That is what holds main-session context flat across 20 rounds —
  and it is what makes the run resumable, because context that was never held cannot be
  lost.
- **The ledger on disk is the state.** Pending work is pending because the ledger says
  so. Never filter a question or finding using memory of a previous round.
- **Agents own their own skip check.** Every agent claims its step first and returns
  immediately if it is done, so re-spawning a completed step is safe and cheap. You do
  not need to pre-filter — but you should still only spawn what `pending` and
  `unverified` list, because a skipped agent still costs a spawn.
- **Payload files are `handoff-*`.** The script derives these names, and the prefix is
  deliberate: a subagent `Write` to a `findings`/`report`-named file trips a Claude Code
  guard that pushes the content back into the response instead of to disk, which would
  break the step. Never rename them.
- **If compacted mid-loop**, resume from disk: `resolve` again with the same task, take
  `round` from its output, and continue at 3.0. The interrupted round simply re-runs and
  its completed steps skip.
- **Do not downgrade agent models.** Verification quality is the termination signal — a
  false confirmation ends the loop on a wrong answer. Let agents inherit the session
  model.

## On round cap

Twenty rounds without converging means genuine churn — usually a task too broad to
settle, or an assess agent manufacturing gaps. Do not summarize as if converged. Report
honestly: the last round's gap list (its path, not its contents), what kept growing (the
`new_questions` per round from the ledger), the current confirmed/refuted counts. Then
offer the user three options: **re-run** for another batch of rounds (state is on disk,
so it continues), **summarize the partial** (Step 4, with the cap noted in the report),
or **narrow the task** and start a fresh run.
