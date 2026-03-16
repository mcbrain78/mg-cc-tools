# Phase 5: Verify, Notes Command & Router - Research

**Researched:** 2026-03-16
**Domain:** LLM command authoring (markdown instruction prompts), Python script CLI tools, pipeline state management
**Confidence:** HIGH

## Summary

Phase 5 implements three commands that complete the create-docs pipeline: the verify command (`/mg:create-docs-verify`), the notes command (`/mg:add-docs`), and the router (`/mg:create-docs`). All three commands are markdown instruction prompt files following the established mg-cc-tools pattern. No new Python scripts are needed -- all required scripts exist from Phase 1 (add-note.py, classify-note.py, check-references.py). The verifier agent definition also exists from Phase 2. The work is writing the command .md files that orchestrate existing infrastructure, plus verifying the install.sh handles them (it already does -- the COMMANDS array already includes all three commands).

The primary technical challenge is the verify command, which orchestrates six distinct quality checks and must coordinate the verifier agent's use of LSP for symbol verification (instead of the regex-based `_symbol_exists_in_project()` in check-references.py). The router follows the established codebase-health router pattern exactly. The add-docs command is the simplest -- it calls two existing scripts (add-note.py, classify-note.py) and presents results.

**Primary recommendation:** Follow the codebase-health exemplar patterns precisely. The router command mirrors `codebase-health/commands/codebase-health.md`, the verify command mirrors `codebase-health/commands/codebase-health-verify.md`, and the add-docs command is a lightweight standalone. No new scripts, agents, or install.sh changes are needed.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Reference Integrity Check (VFY-01): File path verification uses check-references.py (Phase 1). Symbol verification uses LSP tool (go-to-definition) in the verify agent instead of regex-based _symbol_exists_in_project(). check-references.py acts as reference extractor only.
- Cross-Doc Consistency (VFY-02): Terms must match glossary definitions. Architecture descriptions must match developer guide descriptions.
- Diataxis Mixing Detection (VFY-03): Flag sections where content type mismatches declared DIATAXIS type.
- Completeness Check (VFY-04): Major code components have documentation for each relevant audience.
- Example Validity (VFY-05): Code examples are syntactically valid.
- Link Integrity (VFY-06): Internal markdown links between docs resolve.
- Verify Output (VFY-07): Output to .mg/docs/docs-verify-report.md with issues categorized by severity.
- Router Command (CMD-01): /mg:create-docs detects pipeline state (no docs, existing docs, partial scan) and routes. Same pattern as /mg:codebase-health.
- Verify Command (CMD-04): /mg:create-docs-verify is read-only. Cross-reference check, Diataxis mixing detection, completeness audit. Agent doc quality: YAML frontmatter valid, file paths in SYSTEM_MAP.md exist, convention rules reference real patterns.
- Add-Docs Command (CMD-05): /mg:add-docs "note" is standalone. Writes inbox only. Note stored in .mg/docs/notes-inbox.json with unique ID, raw text, timestamp, context. Auto-classified with confidence. User sees classification immediately and can correct. Notes carry GSD phase context.
- Verify report includes glossary inconsistency flags from Phase 4's reconciliation pass.
- Agents receive file paths only, read files themselves.
- /mg:add-docs lives inside create-docs/ tool directory -- deployed by same install script.
- Tool installs to .claude/create-docs/ -- verify and router commands reference scripts at .claude/create-docs/scripts/.
- Road-runner validation baked into phase success criteria -- full pipeline must run end-to-end on ../road-runner.

### Claude's Discretion
- Verify report format and severity categorization (critical, warning, info)
- How verify step presents re-generation options to user
- Add-docs classification correction UX (how the user corrects auto-classification)
- Router state detection heuristics (how to distinguish "partial scan" from "complete scan")
- Whether add-docs should support batch note ingestion
- How backlog integration is triggered (automatic suggestion vs manual)

### Deferred Ideas (OUT OF SCOPE)
- Backlog integration as automated pipeline step (BKL-01) -- v2 requirement, manual for now
- Real-time sync via file watchers or CI hooks -- out of scope
- Custom document template authoring UI -- out of scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VFY-01 | Reference integrity: file paths, symbol names, commands verified against codebase | check-references.py extracts references; verify agent uses LSP for symbol verification, filesystem for file paths |
| VFY-02 | Cross-doc consistency: terms match glossary, descriptions match across audiences | Verifier agent reads GLOSSARY.md and cross-checks terminology across all generated docs |
| VFY-03 | Diataxis mixing detection: flag tutorial in reference docs, explanation in how-to | Verifier agent reads DIATAXIS HTML comments and checks content against declared type |
| VFY-04 | Completeness: major code components have docs for each relevant audience | Verifier agent compares source_material_index from docs-scan.json against generated docs |
| VFY-05 | Example validity: code examples are syntactically valid | Verifier agent checks fenced code blocks: Python compile(), JSON parse, bash heuristics |
| VFY-06 | Link integrity: internal markdown links between docs resolve | Verifier agent resolves relative links and heading anchors; skips external URLs |
| VFY-07 | Output as docs-verify-report.md with issues by severity | Verify command writes structured report to .mg/docs/docs-verify-report.md |
| CMD-01 | /mg:create-docs router detects pipeline state and routes | Router command follows codebase-health.md pattern with docs-pipeline-specific state checks |
| CMD-04 | /mg:create-docs-verify checks reference integrity, consistency, Diataxis, completeness | Verify command orchestrates verifier agent, check-references.py, and presents report |
| CMD-05 | /mg:add-docs captures note with auto-classification | Add-docs command calls add-note.py then classify-note.py and presents results |
</phase_requirements>

## Standard Stack

### Core

| Component | Location | Purpose | Why Standard |
|-----------|----------|---------|--------------|
| check-references.py | create-docs/scripts/ | Extract file paths and symbol names from markdown | Phase 1 script, tested (8 tests), used as reference extractor for VFY-01 |
| add-note.py | create-docs/scripts/ | Atomic append to notes-inbox.json | Phase 1 script, tested (8 tests), used by CMD-05 |
| classify-note.py | create-docs/scripts/ | Keyword-based audience classification | Phase 1 script, tested (11 tests), used by CMD-05 |
| verifier.md | create-docs/agents/ | Verifier agent with 6-check process | Phase 2 agent definition, already defines VFY-01 through VFY-06 checks |
| install.sh | create-docs/ | Deployment with sed path resolution | Already includes all 5 commands in COMMANDS array, handles sed for all placeholders |

### Supporting

| Component | Location | Purpose | When to Use |
|-----------|----------|---------|-------------|
| lib/json_io.py | create-docs/scripts/lib/ | Atomic JSON load/save | Used by add-note.py and classify-note.py internally |
| schema.md | create-docs/references/ | docs-scan.json data contract | Read by verify command for completeness checking |
| .docs.config.json | create-docs/references/ | Default pipeline config | Read by router for audience/docs_dir detection |
| codebase-health.md | codebase-health/commands/ | Router pattern exemplar | Reference for CMD-01 state detection logic |
| codebase-health-verify.md | codebase-health/commands/ | Verify pattern exemplar | Reference for CMD-04 orchestration structure |

### No New Dependencies Needed

All required infrastructure exists. Phase 5 creates/updates zero Python scripts and zero agent definitions. The work is entirely in writing three command .md files (the instruction prompts).

## Architecture Patterns

### File Layout (what Phase 5 modifies)

```
create-docs/
  commands/
    create-docs.md          # CMD-01: Router -- FILL STUB
    create-docs-verify.md   # CMD-04: Verify -- FILL STUB
    add-docs.md             # CMD-05: Notes -- FILL STUB
    create-docs-scan.md     # (exists, no changes)
    create-docs-generate.md # (exists, no changes)
  agents/
    verifier.md             # (exists from Phase 2, no changes needed)
  scripts/
    check-references.py     # (exists from Phase 1, no changes needed)
    add-note.py             # (exists from Phase 1, no changes needed)
    classify-note.py        # (exists from Phase 1, no changes needed)
  install.sh                # (exists, already handles all 5 commands)
```

### Pattern 1: Router State Detection (CMD-01)

**What:** Detect where the user is in the scan-generate-verify pipeline and route to the correct next step.
**When to use:** The `/mg:create-docs` command.
**Reference:** `codebase-health/commands/codebase-health.md` (lines 20-132)

The codebase-health router checks state in order:
1. Does `.mg/health-scan/` exist? NO -> Route A (no scan)
2. Does findings JSON exist? NO -> Route A
3. Are findings verified? NO -> Route B
4. Does verify report exist? NO -> Route B
5. Does implement report exist? NO -> Route C
6. All complete -> Route D

**Adapted for create-docs pipeline:**
1. Does `.mg/docs/` workspace exist? NO -> Route A (fresh start)
2. Does `.mg/docs/docs-scan.json` exist? NO -> Route A (scan needed)
3. Does `{docs_dir}` (from config, default `docs/auto-doc/`) contain any `.md` files? NO -> Route B (scan done, generation needed)
4. Does `.mg/docs/docs-verify-report.md` exist? NO -> Route C (generation done, verify needed)
5. All three exist -> Route D (pipeline complete, offer re-run options)

**Additional state: update mode detection.**
- If docs exist AND scan data exists -> check if scan data is newer than docs (mode = "update")
- If docs exist but no scan data -> offer re-scan or verify-only

**Router never runs steps itself.** It detects state, shows summary, tells user which command to run next.

### Pattern 2: Verify Command Orchestration (CMD-04)

**What:** Read-only verification that spawns the verifier agent and presents a structured report.
**When to use:** The `/mg:create-docs-verify` command.
**Reference:** `codebase-health/commands/codebase-health-verify.md` (full file)

The verify command:
1. Loads context (config, scan data, docs directory)
2. Verifies prerequisites exist (docs-scan.json, generated docs)
3. Runs check-references.py for file path extraction (deterministic)
4. Spawns verifier agent via Task tool for the 6 quality checks
5. Agent uses LSP for symbol verification (not the regex in check-references.py)
6. Writes docs-verify-report.md
7. Presents results with severity summary
8. Suggests re-generation for flagged sections

**Key difference from codebase-health verify:** The docs verify command does NOT need the batch/subagent parallelization pattern. Codebase-health verifies individual findings (can be dozens). Docs verify runs 6 sequential checks across all docs. A single verifier agent instance handles all checks.

### Pattern 3: Add-Docs Command (CMD-05)

**What:** Lightweight standalone command that captures a note and auto-classifies it.
**When to use:** The `/mg:add-docs "note"` command.

Flow:
1. Extract note text from user's command arguments
2. Detect context: active file (if available), GSD phase (if .planning/ exists)
3. Call add-note.py to append to notes-inbox.json
4. Call classify-note.py to auto-classify (audience, document, section, confidence)
5. Display classification to user
6. Ask if user wants to correct the classification (AskUserQuestion)
7. If corrected, update the note's classification in inbox

This is the simplest command -- no subagents, no pipeline state, no prerequisites beyond the .mg/docs/ workspace existing.

### Pattern 4: Command File Structure

All three commands follow the established YAML frontmatter + markdown instruction format:

```markdown
---
name: mg:{command-name}
description: {brief description}
allowed-tools: {tool list}
---

# {Command Title}

{Role description}

## Before You Start
{Prerequisites and context loading}

## Process
{Step-by-step instructions}

## Important Principles
{Constraints and rules}
```

The existing stubs already have frontmatter. The allowed-tools are already set:
- `create-docs.md`: Bash, Read, Write, Glob, Grep
- `create-docs-verify.md`: Bash, Read, Write, Glob, Grep, Task
- `add-docs.md`: Bash, Read, Write

**Note on add-docs:** The stub's `allowed-tools` lacks `AskUserQuestion`. If classification correction UX is desired (Claude's discretion item), `AskUserQuestion` should be added.

### Anti-Patterns to Avoid

- **Do not modify check-references.py.** The LSP decision means symbol verification moves to the agent level. check-references.py stays as-is (the `_symbol_exists_in_project()` function remains but is not called by the verify pipeline -- the agent uses LSP instead). Modifying the script would break its 8 passing tests for no benefit.
- **Do not create new scripts for verify checks.** The 6 verification checks (reference integrity, cross-doc, diataxis, completeness, example validity, link integrity) are all LLM judgment tasks performed by the verifier agent. Only file path checking uses the Python script.
- **Do not modify install.sh.** The COMMANDS array already includes all 5 commands. The sed resolution loop already handles `{SCRIPTS_DIR}`, `references/schema.md`, `references/style-guide.md`, `{GLOBAL_CONFIG}`, `{TEMPLATES_DIR}`, and `agents/` prefix. No new placeholders are needed.
- **Do not modify the verifier agent.** The verifier.md from Phase 2 already defines the complete 6-check process with severity categories, output format, and principles. The verify command orchestrates it; it does not redefine it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| File path validation | Custom file walking/checking | check-references.py --docs-dir --project-root | Already handles backtick paths, code blocks, URL exclusion, directory refs |
| Symbol validation | Regex-based symbol search | LSP tool (go-to-definition) via verifier agent | LSP handles inheritance, re-exports, decorators, cross-module imports |
| Note storage | Custom JSON append logic | add-note.py --inbox --text [--phase] [--file] | Atomic writes, sequential IDs, context capture |
| Note classification | Custom keyword matching | classify-note.py --text [--note-id --inbox] | Audience detection, confidence scoring, inbox update |
| Pipeline state detection | Custom state machine | Filesystem checks (same as codebase-health router) | Check file existence in order: workspace -> scan data -> docs -> verify report |
| Verify report format | Custom template engine | Markdown string construction in verify command | The verifier agent writes the report following the template in its agent definition |

**Key insight:** Phase 5 is an orchestration phase, not an infrastructure phase. All the infrastructure was built in Phases 1-2. The value is in the command prompts that wire the pieces together correctly.

## Common Pitfalls

### Pitfall 1: Confusing Extractor vs. Verifier Role for check-references.py

**What goes wrong:** The command tries to use check-references.py's `_symbol_exists_in_project()` for symbol verification, conflicting with the LSP decision.
**Why it happens:** The script already has symbol verification built in. It is tempting to use it directly.
**How to avoid:** The verify command should call check-references.py with `--docs-dir` and `--project-root` to get the reference extraction output (file paths and symbol names with their locations). Then pass only the extracted symbols to the verifier agent, which uses LSP to check them. File path results from the script can be used directly (filesystem checks are deterministic).
**Warning signs:** The verify command invokes check-references.py and treats its symbol `status: broken` results as final. The script's symbol check is regex-based and will miss valid symbols (re-exports, decorators, etc.).

### Pitfall 2: Router Confusing "Existing Docs but No Scan" State

**What goes wrong:** Router detects docs in `docs/auto-doc/` but finds no `docs-scan.json`, and does not know whether to suggest scan or re-scan.
**Why it happens:** User may have manually created docs, or deleted scan data.
**How to avoid:** When docs exist but scan data does not exist, the router should treat this as "update mode needing a scan" -- suggest running `/mg:create-docs-scan` which will detect mode = "update" from the existing docs.
**Warning signs:** Router sends user to generate step when no scan data exists.

### Pitfall 3: Verify Command Missing AskUserQuestion Tool

**What goes wrong:** The verify command wants to present re-generation suggestions interactively but lacks the tool.
**Why it happens:** The stub's `allowed-tools` includes Task but not AskUserQuestion.
**How to avoid:** The verify command's current allowed-tools (Bash, Read, Write, Glob, Grep, Task) are sufficient. Re-generation suggestions should be presented as text output, not interactive prompts. The user decides whether to run `/mg:create-docs-generate` after reviewing the report. This matches codebase-health-verify which presents results and suggests next steps without interactive approval.
**Warning signs:** Trying to add interactive approval flow to the verify step.

### Pitfall 4: Add-Docs Not Detecting GSD Phase Context

**What goes wrong:** Notes are added without GSD phase context even when .planning/ exists.
**Why it happens:** The add-docs command does not check for .planning/STATE.md.
**How to avoid:** The add-docs command should check for `.planning/STATE.md`, extract the current phase name, and pass it as `--phase` to add-note.py. This is a simple file existence check + read.
**Warning signs:** All notes have `context.phase: null` despite running in a GSD-managed project.

### Pitfall 5: Verifier Agent Not Receiving LSP Instructions

**What goes wrong:** The verifier agent from Phase 2 references `check-references.py --doc-file` for symbol checking instead of LSP.
**Why it happens:** The verifier.md was written before the LSP decision was finalized in the milestone discussion.
**How to avoid:** Check the existing verifier.md agent definition. If it instructs the agent to use `check-references.py --doc-file` for both file paths AND symbols, the verify command should override this in the Task prompt by explicitly instructing: "For symbol verification, use LSP go-to-definition instead of check-references.py's symbol results." The verify command's Task prompt controls the agent's behavior at runtime.
**Warning signs:** Looking at verifier.md (Phase 2), it does reference `{SCRIPTS_DIR}/check-references.py` for reference integrity. The command prompt must clarify the split: script for extraction, LSP for symbol verification.

### Pitfall 6: Verify Report Severity Model Inconsistency

**What goes wrong:** The verify report uses different severity levels than what the verifier agent expects.
**Why it happens:** The verifier agent from Phase 2 uses a 5-tier model (critical/high/medium/low/info) while the CONTEXT.md mentions (critical/warning/info) as a Claude's discretion item.
**How to avoid:** Use the 5-tier model from the existing verifier.md agent definition (critical/high/medium/low/info). This was already decided in Phase 2 and the agent is built around it. The CONTEXT.md discretion item for "severity categorization" should be resolved by keeping the existing 5-tier model.
**Warning signs:** Creating a new severity model that conflicts with the existing agent definition.

## Code Examples

### Router State Detection Logic (based on codebase-health.md pattern)

```markdown
## Your Task: Detect State and Route

Check the project state and determine pipeline position.

### State Detection

Run these checks in order:

1. **Does `.mg/docs/` directory exist?**
   - NO -> Route A (fresh start)

2. **Does `.mg/docs/docs-scan.json` exist?**
   - NO -> Route A (scan needed)

3. **Does `{docs_dir}` contain `.md` files?**
   (Read docs_dir from .mg/docs/.docs.config.json, default: docs/auto-doc)
   - NO -> Route B (scan done, generate next)

4. **Does `.mg/docs/docs-verify-report.md` exist?**
   - NO -> Route C (docs exist, verify next)

5. **All exist** -> Route D (pipeline complete)
```
Source: Adapted from codebase-health/commands/codebase-health.md lines 20-47

### Verify Command: check-references.py for Extraction, LSP for Symbols

```markdown
### Step 2: Reference Integrity (VFY-01)

#### 2a. Extract References

Run check-references.py to extract all file path and symbol references:
```bash
python3 {SCRIPTS_DIR}/check-references.py \
  --docs-dir <docs_dir> \
  --project-root <project_root> \
  --output <project_root>/.mg/docs/scan-logs/verify-refs.json
```

#### 2b. File Path Verification

From the script output, collect all entries where `type == "file_path"`.
The script already verified these against the filesystem:
- `status: "broken"` -> severity: **critical** (file does not exist)
- `status: "valid"` -> no issue

#### 2c. Symbol Verification (via LSP)

From the script output, collect all entries where `type == "symbol"`.
**Do NOT use the script's status for symbols.** Instead, for each symbol:
1. Use the LSP tool (go-to-definition) to check if the symbol resolves
2. If LSP resolves it -> valid (no issue)
3. If LSP cannot resolve it -> severity: **high** (symbol not found)
```
Source: CONTEXT.md locked decision + memory/project_lsp_symbol_verification.md

### Add-Docs Command: Script Invocation Pattern

```markdown
### Step 2: Add Note to Inbox

```bash
python3 {SCRIPTS_DIR}/add-note.py \
  --inbox <project_root>/.mg/docs/notes-inbox.json \
  --text "<user_note_text>" \
  --phase "<current_phase_or_empty>" \
  --file "<active_file_or_empty>"
```

### Step 3: Classify the Note

```bash
python3 {SCRIPTS_DIR}/classify-note.py \
  --text "<user_note_text>" \
  --note-id <note_id_from_step_2> \
  --inbox <project_root>/.mg/docs/notes-inbox.json
```

The script outputs classification JSON to stdout AND updates the note in the inbox.
```
Source: Existing scripts add-note.py and classify-note.py CLI interfaces

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Regex symbol search | LSP go-to-definition | Phase 5 design (CONTEXT.md) | Symbols resolved semantically, not textually |
| Per-finding parallelization (codebase-health) | Single agent for all checks (create-docs) | Phase 5 design | Simpler orchestration -- 6 checks not 12+ findings |

**Existing infrastructure that needs no changes:**
- verifier.md agent definition (Phase 2): Already defines all 6 checks
- check-references.py (Phase 1): Already extracts file paths and symbols from markdown
- add-note.py (Phase 1): Already handles atomic inbox append
- classify-note.py (Phase 1): Already handles keyword classification
- install.sh: Already includes all 5 commands and all sed placeholder resolutions

## Open Questions

1. **check-references.py --doc-file vs --docs-dir argument mismatch**
   - What we know: The verifier agent (verifier.md) references `--doc-file` but the actual script CLI uses `--docs-dir` (directory-level). The scan command was careful about this (noted as Pitfall 1 in create-docs-scan.md).
   - What's unclear: Whether the verify command should call check-references.py once with `--docs-dir` or iterate per doc file. Looking at the script, it takes `--docs-dir` and iterates internally.
   - Recommendation: Use `--docs-dir` to match the actual script interface. The verifier agent's `--doc-file` reference is from the Phase 2 stub and should be corrected in the verify command's Task prompt.

2. **AskUserQuestion for add-docs classification correction**
   - What we know: CONTEXT.md lists "classification correction UX" as Claude's discretion.
   - What's unclear: Whether to add AskUserQuestion to add-docs allowed-tools.
   - Recommendation: Yes, add AskUserQuestion. Present the classification, ask "Is this correct? If not, specify: audience, document, section". If user corrects, update the inbox entry directly via Write (the inbox is simple JSON). This is lightweight and matches the locked decision that "User sees classification immediately and can correct it."

3. **Whether check-references.py output format needs adaptation for verify**
   - What we know: The script outputs a flat list of issues with file, line, reference, type, status, message fields. The verify command needs to split these into file_path results (use directly) and symbol results (re-verify with LSP).
   - What's unclear: Whether the command should pre-filter or let the agent handle it.
   - Recommendation: The verify command should run check-references.py, save its output, then pass the output path to the verifier agent. The agent reads the JSON and handles the split (use file_path status as-is, re-verify symbols via LSP). This keeps the command orchestration clean and lets the agent apply judgment.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | pyproject.toml (project root) |
| Quick run command | `python3 -m pytest create-docs/scripts/tests/ -x -q` |
| Full suite command | `python3 -m pytest -x` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VFY-01 | check-references.py extracts file paths and symbols | unit | `python3 -m pytest create-docs/scripts/tests/test_check_references.py -x` | Yes (8 tests) |
| VFY-02 | Cross-doc consistency (glossary term matching) | manual-only | Agent-level LLM judgment | N/A -- LLM verification in agent |
| VFY-03 | Diataxis mixing detection | manual-only | Agent-level LLM judgment | N/A -- LLM verification in agent |
| VFY-04 | Completeness (scan data vs docs coverage) | manual-only | Agent-level LLM judgment | N/A -- LLM verification in agent |
| VFY-05 | Example validity (syntax checking) | manual-only | Agent-level LLM judgment | N/A -- LLM verification in agent |
| VFY-06 | Link integrity (markdown link resolution) | manual-only | Agent-level LLM judgment | N/A -- LLM verification in agent |
| VFY-07 | Verify report output format | manual-only | End-to-end road-runner validation | N/A -- command output validation |
| CMD-01 | Router state detection and routing | manual-only | End-to-end road-runner validation | N/A -- LLM command behavior |
| CMD-04 | Verify command orchestration | manual-only | End-to-end road-runner validation | N/A -- LLM command behavior |
| CMD-05 | add-note.py and classify-note.py integration | unit | `python3 -m pytest create-docs/scripts/tests/test_add_note.py create-docs/scripts/tests/test_classify_note.py -x` | Yes (19 tests) |

### Sampling Rate
- **Per task commit:** `python3 -m pytest create-docs/scripts/tests/ -x -q`
- **Per wave merge:** `python3 -m pytest -x`
- **Phase gate:** Full suite green + end-to-end road-runner pipeline validation

### Wave 0 Gaps
None -- existing test infrastructure covers all scriptable behaviors. VFY-02 through VFY-06 are inherently LLM judgment tasks performed by the verifier agent and cannot be unit tested. The end-to-end road-runner validation (success criterion #4) serves as the integration test for the complete pipeline.

## Recommendations for Claude's Discretion Items

### Severity Categorization
Use the existing 5-tier model from verifier.md: **critical** (broken references, invalid links), **high** (missing symbols, structural Diataxis violations), **medium** (glossary inconsistencies, minor Diataxis mixing, broken heading anchors), **low** (example syntax warnings, undefined terms), **info** (suggestions, optimization opportunities).

### Re-generation Options Presentation
After presenting the verify report, suggest specific `/mg:create-docs-generate` usage rather than interactive approval. Example: "To fix critical and high issues, re-run `/mg:create-docs-generate` -- the staleness report from a fresh scan will cover the affected sections." This follows the codebase-health pattern where verify presents results and the user decides.

### Add-Docs Classification Correction UX
Use AskUserQuestion after displaying classification. Show the classification result, then ask: "Accept this classification? (yes / correct: audience=X, document=Y, section=Z)". If user provides corrections, update the note directly in inbox JSON. Keep it one round -- no multi-step correction wizard.

### Router State Detection Heuristics
Check in this order (ordered from "earliest" to "latest" pipeline state):
1. No `.mg/docs/` directory -> fresh start
2. No `docs-scan.json` -> scan needed
3. No docs in `docs_dir` -> generate needed
4. No `docs-verify-report.md` -> verify needed
5. All present -> complete; offer options (re-scan, re-verify, add notes)

For distinguishing "partial scan" from "complete scan": check if docs-scan.json has all expected top-level fields (project_model, source_material_index, gap_analysis). If any are missing, treat as incomplete scan.

### Batch Note Ingestion
Do not support batch ingestion for v1. The atomic append pattern of add-note.py handles one note at a time. Users can run `/mg:add-docs` multiple times. Batch support adds complexity (argument parsing, error handling per note) without proportional value.

### Backlog Integration
Present it as an informational suggestion at the end of the verify report: "Found N documentation gaps. Consider adding to .planning/BACKLOG.md." Do not auto-add. This keeps it manual per the v2 deferral while making the user aware.

## Sources

### Primary (HIGH confidence)
- **codebase-health/commands/codebase-health.md** -- Router pattern exemplar (read in full)
- **codebase-health/commands/codebase-health-verify.md** -- Verify pattern exemplar (read in full)
- **create-docs/agents/verifier.md** -- Phase 2 verifier agent definition (read in full)
- **create-docs/scripts/check-references.py** -- Phase 1 reference checker (read in full, 366 lines)
- **create-docs/scripts/add-note.py** -- Phase 1 note append script (read in full, 101 lines)
- **create-docs/scripts/classify-note.py** -- Phase 1 classification script (read in full, 162 lines)
- **create-docs/install.sh** -- Install script with all 5 commands in COMMANDS array (read in full, 344 lines)
- **create-docs/commands/create-docs-scan.md** -- Scan command for pipeline context (read in full)
- **create-docs/commands/create-docs-generate.md** -- Generate command for pipeline context (read in full)
- **create-docs/references/schema.md** -- docs-scan.json data contract (read in full)
- **create-docs/references/.docs.config.json** -- Default config (read in full)
- **memory/project_lsp_symbol_verification.md** -- LSP decision context (read in full)
- **All existing test files** -- 59 tests across 5 test files, all passing

### Secondary (MEDIUM confidence)
- **05-CONTEXT.md** -- Phase decisions from milestone discussion (comprehensive, covers all requirements)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all infrastructure exists and is tested; this phase writes command prompts only
- Architecture: HIGH -- three exemplar patterns exist in the codebase (router, verify, standalone command)
- Pitfalls: HIGH -- identified from direct code reading and pattern comparison against existing commands

**Research date:** 2026-03-16
**Valid until:** 2026-04-16 (stable -- infrastructure is frozen from Phases 1-2)
