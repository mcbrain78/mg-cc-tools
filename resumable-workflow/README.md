# resumable-workflow

> **Status: PAUSED, and not proven.** The source is committed and the tests are green,
> but **no run has ever converged** — the verify, assess and summarize stages have never
> executed with live agents. Do not treat this as a working tool yet.
>
> Read [`docs/work-queue/todo/resumable-workflow/HANDOVER.md`](../docs/work-queue/todo/resumable-workflow/HANDOVER.md)
> before using or continuing it.

`/mg:resumable-workflow <task>` runs a dynamic multi-agent investigation as a
main-session loop — decompose the task into questions, research them in parallel,
adversarially verify the findings, assess what is still missing, repeat until the
investigation stops learning, then summarize from what survived verification.

Every step is durable: agents write their output to disk and the loop re-derives its
state from a ledger each round, so a run that dies to a context or usage limit resumes
by **re-typing the same command**. It deliberately does not use the built-in `Workflow`
tool, whose script has no filesystem access and whose resume is same-session only.

## Layout

| Path | Role |
|---|---|
| `commands/resumable-workflow.md` | the loop; the orchestrator only routes |
| `agents/` | digest, decompose, research, verify, assess, summarize |
| `scripts/run_state.py` | the ledger — `resolve`, `add`, `claim`, `complete`, `fail`, `reap`, `round`, `status` |

Run state lives at `.mg/resumable-workflow/runs/<slug>-<hash8>/`.

## Two things to know before running it

- **The default agent ceiling (50) will stop a real task before it converges.** A round
  costs about `3 + N + 2N` agents, so a six-question round is ~21, while converging needs
  at least three rounds. Pass `--max-agents 120` or use a narrow task.
- **Re-typing the same task text resumes that run.** The text hashes to the run
  directory, so a reworded task starts a new run — `resolve` refuses a near-identical
  sibling unless you pass `--run-dir` to resume it or `--force` to fork.

## Development

```bash
python3 -m pytest resumable-workflow/ --tb=short -q --no-header
ruff check resumable-workflow/
```
