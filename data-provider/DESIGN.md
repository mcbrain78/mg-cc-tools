# Data Provider Field Mapping — Design

## Problem

We need to map 25 UCR scoring fields to data provider APIs. Previous attempts
used broad-sweep analysis: one agent maps all fields for a provider in a single
pass, then a separate verification pass checks the results. This consistently
failed because:

1. **Hallucinated field availability** — The agent reads API documentation and
   infers mappings, but docs are incomplete or ambiguous. Fields get marked as
   available when they aren't.
2. **Too much surface area** — Mapping 25 fields × N providers in one pass means
   errors compound. A wrong assumption about one endpoint cascades into incorrect
   mappings for related fields.
3. **Verification discovers problems instead of preventing them** — The process
   creates optimistic mappings first, then tries to verify. Every verification
   round uncovers new issues, leading to multiple cycles of rework.

We spent 2+ days iterating on provider mapping docs without converging on a
reliable result.

## Design Decisions

### 1. Adversarial agent pair (researcher + verifier)

Instead of one agent doing research and self-checking, two agents with different
roles evaluate each mapping:

- **Researcher**: Optimistic. Searches for docs, finds endpoints, proposes mappings.
- **Verifier**: Skeptical. Independently fetches the same documentation URL and
  confirms or rejects every claim.

The verifier has explicit instructions to reject if anything is uncertain. This
catches the most common failure mode: the researcher finding a plausible-looking
field that doesn't actually exist in the API response.

### 2. One task file per (field, provider) pair

Each combination is an atomic unit of work with its own file. This gives:

- **Isolation**: A bad result for one field doesn't contaminate others.
- **Resumability**: If a session crashes, completed tasks are preserved.
- **Inspectability**: You can read any task file and see exactly what happened.
- **Parallelism**: Independent tasks can run concurrently.

### 3. File-based state, not in-memory

Task state (pending/researched/verified/inconclusive) lives in the task files
themselves. Python scripts handle all file reads and writes. Agents never edit
files directly.

Why: Agent context windows reset between sessions. File state persists. Scripts
are deterministic — they can't hallucinate a status change.

### 4. Python scripts for file operations, agents only for reasoning

| Layer | Handled by | Why |
|-------|-----------|-----|
| File generation, parsing, status updates | Python scripts | Deterministic, testable, no LLM variance |
| API doc research, claim verification | AI agents | Requires web search, reading comprehension, judgment |

This separation means the mechanical parts can't go wrong (wrong format, lost
data, corrupted files), and the agents focus purely on what they're good at.

### 5. Per-field iteration, not per-provider

We process all providers for field #1, then all providers for field #2, etc.
Not all fields for provider A, then provider B.

Why: The user cares about coverage per field ("can anyone supply Revenue YoY?").
Processing field-first answers that question immediately. If a field is hard to
source from any provider, you know on day one — not after mapping 24 other fields.

### 6. Binary outcomes: DIRECT, DERIVABLE, or NONE

No SUBSTITUTE category. Previous attempts used SUBSTITUTE ("similar but different
definition") which created ambiguity — is it close enough? Does the difference
matter? Every SUBSTITUTE required a judgment call that kept shifting.

Binary is clearer: the provider either has it (directly or via computable raw
inputs) or it doesn't. This eliminates the largest source of tail-chasing.

### 7. Max 2 rounds, then inconclusive

If the researcher proposes a mapping and the verifier rejects it, the researcher
gets one retry with the rejection feedback. If the second attempt also fails,
the task is marked inconclusive for manual review.

Why: Without a hard cap, the loop could run indefinitely on ambiguous cases.
Inconclusive is an honest answer — it means "we couldn't confirm this from
public docs" which is useful information in itself.

### 8. Evidence URL required

Every accepted mapping must cite the exact documentation URL. The verifier
independently fetches this URL to confirm. This forces grounding in actual
docs rather than the agent's training data, which may be outdated.

## Agent Prompt Design

### Researcher prompt

Key instructions that make it reliable:

- "Find EXAMPLE/SAMPLE JSON RESPONSES" — pushes the agent toward concrete
  evidence rather than field description tables
- "Verify you are looking at the LATEST API version" — providers change APIs;
  the agent's training data may reference deprecated endpoints
- "DO NOT use SUBSTITUTE" — removes the tempting escape hatch
- Structured output format with specific fields — makes parsing deterministic

### Verifier prompt

Key instructions that make it effective:

- "WebFetch the EXACT evidence URL" — forces independent verification, not
  trusting the researcher's summary
- "Be skeptical" section with specific rejection criteria — sets the bar high
- "If you cannot find the claimed field in an actual example response, REJECT" —
  the single most important instruction; prevents accepting fields that are
  described in docs but not in actual responses

### Retry prompt

When a researcher retries after rejection, the rejection reason is appended:
"PREVIOUS ATTEMPT REJECTED. Reason: {reason}. Please try a different approach."

This steers the researcher away from repeating the same mistake.

## Architecture

```
User invokes:
  generate.py         → creates 125 task files in tasks/
  /mg:map-fields-research  → orchestrates research+verification
  summarize.py        → produces coverage report in output/

Orchestrator (Claude command):
  reads pending tasks via status.py
  spawns researcher subagents (up to N parallel)
  parses structured output
  spawns verifier subagents
  updates task files via status.py
  handles retry loop

Scripts (Python, no LLM):
  generate.py    — template × fields × providers → task files
  status.py      — list/read/update task state
  summarize.py   — task files → coverage matrix + detail tables
```

## Known Limitations

- **No API keys**: We rely on published documentation, not actual API calls.
  If docs don't include example JSON responses, the mapping cannot be confirmed.
  Some providers have sparse or JS-rendered docs that WebFetch can't read well.

- **Training data lag**: Agents may reference outdated API versions from their
  training data. The "verify latest version" instruction mitigates this but
  doesn't eliminate it. The evidence URL requirement lets the user spot-check.

- **WebFetch reliability**: Some API doc sites are single-page apps that don't
  render via simple HTTP fetch. This may cause false NONE results.

- **Verifier false negatives**: A skeptical verifier may reject valid mappings
  if the docs page is poorly structured. These show up as inconclusive and
  need manual review.

## Future Improvements

Ideas considered but deferred:

- **API key validation**: Actually call the API for a known ticker and confirm
  the field exists in the response. Would eliminate all doc-parsing ambiguity.
- **Different models per role**: E.g., opus for researcher (better at finding
  information), haiku for verifier (cheaper, different perspective). Currently
  both use the same model for simplicity.
- **Confidence scoring**: Instead of binary accept/reject, the verifier could
  assign a confidence score. Deferred because binary is simpler to act on.
- **Cross-field learning**: If provider X has quarterly revenue (field #1),
  it probably has annual revenue too (fields #4, #5). Currently each task is
  independent. Cross-field inference could reduce redundant research.
- **Provider ranking**: After all fields are mapped, automatically rank
  providers by coverage + historical depth + cost. Currently the summary
  report presents data but doesn't recommend.
