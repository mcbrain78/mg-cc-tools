# Field Mapping Pipeline

You orchestrate a pipeline that maps UCR scoring fields to data provider APIs.

## Work Directory

All files live under `.mg/data-provider/`. Scripts are at `{SCRIPTS_DIR}/`.
Agent instructions are at `{REFERENCES_DIR}/`.

## Step Selection

Ask the user which step to run using AskUserQuestion:

1. **Generate tasks** — Create task files from fields.yaml and providers.txt.
2. **Research** — Run adversarial researcher+verifier agents on pending tasks.
3. **Summarize** — Generate coverage report from completed tasks.
4. **Status** — Show current task status counts.

---

## Step: Generate tasks

```bash
python {SCRIPTS_DIR}/generate.py
```

Report the output.

---

## Step: Status

```bash
python {SCRIPTS_DIR}/status.py list --format summary
```

Report the output. Suggest Research if pending tasks exist, Summarize if all done.

---

## Step: Summarize

```bash
python {SCRIPTS_DIR}/summarize.py
```

Then display the report:
```bash
cat .mg/data-provider/output/coverage-report.md
```

---

## Step: Research

### Setup

Ask the user:
1. **Model**: sonnet (default), opus, haiku
2. **Parallel agents**: 3, 5 (default), 8

### Discover pending tasks

```bash
python {SCRIPTS_DIR}/status.py list --status pending --format summary
```

If no pending tasks, report "All tasks processed" and exit.

### Process tasks field by field

Group pending tasks by field number. Process one field at a time.

For each field, get its pending task filenames:
```bash
python {SCRIPTS_DIR}/status.py list --status pending --field-number {N} --format files
```

#### Spawn researchers

For each filename, spawn a background researcher agent:
- `subagent_type: "general-purpose"`
- `model: "<user's chosen model>"` — MUST be set explicitly
- `run_in_background: true` — MUST be set to avoid filling orchestrator context

**Researcher Task prompt** (replace TASK_FILE with the actual filename):
```
Read your instructions from {REFERENCES_DIR}/researcher-prompt.md
Your task file is: TASK_FILE
Replace every occurrence of TASK_FILE in the instructions with your actual filename.
```

Wait for all researchers to complete (you are notified automatically).

#### Check researcher results

```bash
python {SCRIPTS_DIR}/status.py list --field-number {N} --format files --status researched
```

- `researched` files → spawn verifiers
- `verified` files → done (NONE result, self-verified)
- `pending` files → researcher failed to write, mark inconclusive:
  ```bash
  python {SCRIPTS_DIR}/status.py update --file '<filename>' --status inconclusive
  ```

#### Spawn verifiers

For each `researched` file, spawn a background verifier agent (same settings as researcher).

**Verifier Task prompt** (replace TASK_FILE with the actual filename):
```
Read your instructions from {REFERENCES_DIR}/verifier-prompt.md
Your task file is: TASK_FILE
Replace every occurrence of TASK_FILE in the instructions with your actual filename.
```

Wait for all verifiers to complete.

#### Check verifier results

```bash
python {SCRIPTS_DIR}/status.py list --field-number {N} --format files --status pending
```

Any files still `pending` were rejected on first attempt. For each:
```bash
python {SCRIPTS_DIR}/status.py increment-iterations --file '<filename>'
```
Then spawn a NEW researcher (background) with prompt:
```
Read your instructions from {REFERENCES_DIR}/researcher-prompt.md
Your task file is: TASK_FILE
Replace every occurrence of TASK_FILE in the instructions with your actual filename.
PREVIOUS ATTEMPT REJECTED. Read the rejection_reason from the Verification section of your task file. Try a different approach.
```
Wait, then spawn a new verifier (background). This is the second and final round.

### Report progress

After each field completes:
```bash
python {SCRIPTS_DIR}/status.py list --field-number {N} --format summary
```

After all fields are processed:
```bash
python {SCRIPTS_DIR}/summarize.py
python {SCRIPTS_DIR}/status.py list --format summary
```

## Rules

- NEVER fabricate API documentation. If unsure, mark as NONE.
- ALWAYS use Python scripts for file operations. NEVER edit task files directly.
- ALWAYS use `run_in_background: true` for agents.
- ALWAYS set `model` explicitly on every Task call.
- Process one field at a time, then move to the next.
- Respect the parallelism limit.
- If an agent seems stuck, mark the task as inconclusive and move on.
