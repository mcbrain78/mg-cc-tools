# Auto-Doc v2 — Deterministic Extraction + Three-Pass Writer Architecture

## Situation

Auto-doc v1.2 generate pipeline works end-to-end. 12 docs, 73 sections, ~32k words on road-runner. The `calls` field now threads through the full generate pipeline, and verify can check parameter names deterministically.

Writer agents use Serena (LSP) for source file exploration per v1.2's efficiency improvements. The scan produces per-audience view files so writers don't re-parse the full `docs-scan.json`.

## Complication

A full generate + verify cycle on road-runner exposed **6 systemic issues** responsible for the majority of findings:

1. **API function signatures are pervasively wrong (35 findings)** — SYSTEM_MAP and QUICK_REFERENCE have incorrect signatures that contradict each other AND the codebase.
2. **Table/schema counts are wrong and inconsistent (6 findings)** — "18 tables" vs actual 19-21, "15 tables" vs actual 16.
3. **DevOps procedures lack expected output (11 findings)** — destructive commands with no verification.
4. **Agent MUST constraints lack consequences (7 findings)** — no "what breaks" explanations.
5. **Test factory function signatures are wrong (6 findings)** — `make_income_statement(ticker=...)` but actual takes only `db`.
6. **FinanceMetrics code snippet is structurally wrong (1 finding)** — shows nonexistent `id` PK and `traceability` column.

These fall into two categories:

- **42 findings (issues 1, 2, 5, 6): wrong facts** — the writer agent inferred from context instead of reading from source.
- **24 findings (issues 3, 4): convention non-compliance** — the writer agent ignored structural expectations (expected output after commands, consequences for MUST constraints).

### Why more instructions won't fix this

Each writer agent has a large instruction set across 7 sections (Role, Inputs, Documents, Process, Conventions, Output, Principles). The agent runs as a subagent with CC system prompt, Serena instructions, and CLAUDE.md layered on top. By section 8 of 12 in a loop, attention has degraded — the agent cuts corners, inferring signatures instead of reading them.

The instruction to self-verify (Process substeps d-f: rollback verification, command output verification, placeholder check) was also ignored for some sections. The conventions that were violated exist in the prompt — they were just too far from the point of generation to hold attention. Adding more instructions to fix instruction non-compliance is a losing strategy.

### The architectural problem

The v1.2 writer agent has three competing concerns in a single pass:

1. **Structural extraction** — read source files, capture exact signatures, count tables, find usage patterns. Mechanical and deterministic.
2. **Accurate prose** — transcribe facts correctly into documentation. Requires attention to detail.
3. **Document coherence** — progressive explanation, consistent depth, no redundancy, transitions. Requires holistic document awareness.

These compete for the same attention budget. The agent's reasoning tokens are split between "what should I read next via Serena," "is this signature correct," and "does this section flow from the previous one." No concern gets full attention.

Removing extraction (concern 1) into a deterministic phase helps, but leaves concerns 2 and 3 competing. A per-document writer with correct facts in the input can still transcribe them incorrectly by section 6-7, especially when simultaneously managing coherence across sections.

Serena works well for the scan phase where the agent needs *selective* discovery — "is this file relevant?" — using shallow reads. But for extraction, the need is different: read *everything* about the mapped symbols at full depth. That's not a progressive discovery task, it's a bulk extraction task. An LLM choosing what to read next adds decision overhead and creates opportunities to skip things. A deterministic script that parses all mapped files exhaustively doesn't skip anything.

## Solution

Four changes that fully decompose the competing concerns:

1. **Deterministic extraction phase** (Pass 0) — eliminates concern 1 entirely.
2. **Per-section writers** (Pass 1) — each agent handles one section with narrow scope, ensuring accurate transcription of facts.
3. **Per-document coherence editors** (Pass 2) — each agent handles one document, focusing solely on flow and coherence.
4. **Cross-document reconciliation** (Pass 3) — catches contradictions across documents within an audience.

Template PATTERN markers bring structural conventions inline with generation, addressing the 24 convention findings in Pass 1.

### Why scan stays as-is

Analysis of the road-runner scan transcript shows the scan agents already work efficiently: 77% of Serena calls are `get_symbols_overview` (shallow), only 2% are `include_body` (deep), and the deep reads were for content extraction after mapping decisions were already made. The mapping decisions themselves relied only on symbol names, kinds, and docstrings — all available from shallow reads.

The scan's core job — "given a section PURPOSE, which source files are relevant?" — is genuinely semantic and needs LLM judgment. Serena provides an efficient way to do this through progressive discovery without reading entire files. The scan doesn't need to change.

The problem is what happens *after* scan: the writer agent re-reads the same files the scan already explored, but deeper. That's where the extraction phase comes in.

### Pass 0: Deterministic extraction (new script, no LLM)

A new Python script reads source files mapped to each section (from the scan's `source_material_index`) and extracts structured facts using the `griffe` library. This runs once before all writer agents and produces one JSON bundle per section.

**Script:** `auto-doc/scripts/extract-section-facts.py`

**Input:** scan data (all sections' source files) + project root.

**Output:** Per-section JSON bundles at `{TMP_DIR}/facts-{audience}-{document}-{section}.json`.

The script processes all sections in a single invocation to avoid re-parsing the same source file multiple times (a file can appear in multiple sections' `source_material_index`).

**Extraction backend — griffe:**

[Griffe](https://github.com/mkdocstrings/griffe) ("Signatures for entire Python programs") is a mature static analysis library from the mkdocstrings ecosystem. It parses Python source via `ast.parse()` — no runtime imports, no code execution — and produces a rich structured model of every symbol in a file.

Why griffe instead of custom AST walkers:
- Covers function signatures (params with types, defaults, kinds, return types), class bases, decorators, docstrings, class body assignments, module constants, async/sync, line numbers — all out of the box.
- Class body assignments (e.g., `ticker = Column(String(10), nullable=False)`) are stored as structured expression trees. `str(attr.value)` reconstructs the original source expression faithfully, without interpreting runtime semantics.
- Built-in JSON serialization (`obj.as_json()`).
- 601 KB core library, zero transitive dependencies. Well-maintained (81 releases, active development, backed by the mkdocstrings ecosystem).
- Eliminates 300-500 lines of custom AST walker code that would need testing and maintenance.

**Extraction scope — the static analysis line:** If griffe's static visitor surfaces it directly, extract it. If it requires understanding runtime semantics, don't. No framework-specific hacks. Griffe's default static analysis mode enforces this naturally — it parses source structure without evaluating it.

**What griffe provides:**

| Data | Griffe mechanism |
|---|---|
| Function/method signatures | `Parameters` model with types, defaults, `ParameterKind` (positional, keyword-only, etc.) |
| Return types | Annotation expressions on `Function` objects |
| Docstrings | Raw value + optional parsed sections (Google/NumPy/Sphinx styles) |
| Class definitions | Name, base classes as expressions, decorators with full expressions |
| Class body assignments | `Attribute` objects with `value` as structured `ExprCall` trees — `str(value)` gives the source expression |
| Module-level constants | `Attribute` objects with `kind=ATTRIBUTE` |
| Async vs sync | `labels={'async'}` on async functions |
| Decorators | `Decorator` objects, `str(d.value)` gives the full decorator expression |
| Line numbers | `lineno` / `endlineno` on every object |
| Imports | Tracked in `mod.imports` dict |

**What griffe does NOT provide (custom code needed):**

| Data | Approach |
|---|---|
| Call sites from test files | Small custom AST walker: find `ast.Call` nodes matching symbol names, extract kwargs |
| Counts (tables, classes, functions) | Computed from griffe output during facts bundle assembly |

**Class body assignments — raw expressions, not parsed types:**

For runtime constructs like ORM models, griffe captures the source expression as a structured tree:

```python
# Source
class FinanceMetrics(RoadRunnerBase):
    __tablename__ = "finance_metrics"
    ticker = Column(String(10), nullable=False)
    period_end_date = Column(Date, nullable=False)
```

```json
{
  "name": "FinanceMetrics",
  "kind": "class",
  "bases": ["RoadRunnerBase"],
  "docstring": "Computed financial metrics per ticker per period.",
  "body_assignments": [
    {"name": "__tablename__", "value": "\"finance_metrics\""},
    {"name": "ticker", "value": "Column(String(10), nullable=False)"},
    {"name": "period_end_date", "value": "Column(Date, nullable=False)"}
  ],
  "methods": [...]
}
```

The writer sees `Column(String(10), nullable=False)` — ground truth from the file, not a parsed interpretation. Griffe stores this as a structured `ExprCall` tree; `str()` on the value node reconstructs the source expression.

**Config file extraction (stdlib parsers, no LLM):**

| Source type | Method | What's captured |
|---|---|---|
| YAML/TOML | `tomllib` / `yaml` stdlib | Keys, structure, values |
| .env files | Line parsing | Variable names and example values |

**Non-Python source files (SQL, Dockerfile, shell, markdown):** Not extracted by the script. The per-section writer reads these directly via Read when they appear in a section's source file list. This is bounded (typically 0-2 non-Python files per section) and doesn't reintroduce split-attention because the per-section writer's scope is so narrow that there's almost nothing competing for attention.

**Clean cut for Python files:** Writers do not read Python source files. If the extraction missed something, the fix goes in the extraction script, not the writer. No "Read as fallback" escape hatch.

**Implementation:** The extraction script loads files via `griffe.visit()`, reshapes griffe's object model into the facts bundle schema, and adds call-site extraction as a small custom AST supplement. `lib/symbols.py`'s existing `extract_python_symbols()` and `extract_function_signatures()` remain available for use in verify and other scripts.

**Facts bundle schema:** The detailed per-section JSON schema (showing how symbols, usage_examples, counts, and config_facts compose into a bundle) will be defined during implementation planning. The class example above illustrates the representation approach; the full schema needs to account for all symbol kinds, nested classes, and cross-file usage examples.

### Pass 1: Per-section writers (accuracy)

One agent per section. Each gets a narrow scope: facts JSON for a few symbols, one template PURPOSE/EXAMPLE/PATTERN block, and 0-2 non-Python files. Job: write the section's prose from that small input.

**Why per-section works here (but was rejected in the earlier concept draft):**

The earlier rejection was based on per-section agents doing the *full* job — writing with coherence in mind. That concern is valid: isolated sections produce redundant content and inconsistent depth. The three-pass architecture resolves this by separating accuracy (Pass 1) from coherence (Pass 2). Per-section agents don't need to worry about how their section fits into the document — that's Pass 2's job.

The scope is so narrow that attention degradation and inference-over-reading can't happen — there's almost nothing competing for attention and almost nothing to get wrong.

**Input per writer agent:**
- Facts bundle for this section only
- Template PURPOSE, EXAMPLE, and PATTERN comments for this section only
- Style guide + glossary
- Standing notes for this section (if any)
- List of non-Python source files for this section (for direct Read)

**What the writer prompt contains:**
- Audience-specific conventions (writing style, not source reading)
- PATTERN type reference (what `command-then-output` and `constraint-with-consequence` mean)
- Instructions to emit section content and refs via `write-section.py`

**What's removed vs v1.2 writer prompts:**
- All Serena instructions
- Self-verification substeps
- Document/section looping
- "Source material over inference" principle (structurally enforced)
- Most "Do NOT" rules

**Agent overhead:** Per-section spawns more agents than per-document (73 vs ~12 for road-runner). Each agent pays fixed system prompt overhead. This is a known cost, accepted because the accuracy gain from narrow scope is the core improvement.

**Parallelism:** All per-section writers can run in parallel within an audience.

### Template PATTERN markers (used in Pass 1)

The 24 writing-quality findings (issues 3, 4) stem from conventions that were too far from the generation point to hold attention. The solution: bring structural expectations inline using `<!-- PATTERN: ... -->` markers in the templates, the same mechanism as the existing `<!-- PURPOSE: ... -->` and `<!-- EXAMPLE: ... -->` comments.

**Two patterns, covering the 24 findings:**

| Pattern | What it enforces | Where it appears |
|---|---|---|
| `<!-- PATTERN: command-then-output -->` | Every fenced `bash` block must be followed by expected output (success and failure) | DevOps template sections with CLI procedures |
| `<!-- PATTERN: constraint-with-consequence -->` | Every MUST/MUST NOT rule must include what breaks if violated | Agent template sections with constraint blocks |

**Why this works:** The diagnosis showed that instructions 70 lines from the generation point get ignored, but inline comments (PURPOSE, EXAMPLE) are followed reliably. PATTERN markers apply the same principle — the expectation is visible at the point of generation.

**Scoping:** Only two patterns. Don't turn every convention into a pattern — only the ones that were systematically ignored and represent structural expectations (not stylistic preferences). The writer prompt includes a short reference explaining what each PATTERN type means.

### Pass 2: Per-document coherence editors

One agent per document (~12 total). Reads all assembled sections of its document (output of Pass 1 finalization). Focuses solely on document coherence.

**Job:**
- Add transitions between sections
- Eliminate redundancy across sections
- Adjust depth for progressive explanation (don't re-explain a concept introduced in section 2 when referencing it in section 5)
- Add forward/back references between related sections
- Ensure consistent voice and terminology within the document

**Hard constraint:** May restructure prose and add connecting content. May NOT change any factual claim, signature, parameter name, count, or code example that came from Pass 1.

**Why this constraint is enforceable here (unlike v1.2 constraints):**

The v1.2 constraints failed under cognitive overload: 7 instruction sections, Serena tool calls, source navigation, 12-20 section loops, competing concerns. Pass 2 has none of that — it's one document in context, no tool calls needed, one job (coherence), one constraint (preserve facts), focused prompt. The failure conditions that caused v1.2's constraint violations don't apply.

**Input:** Assembled document markdown (all sections concatenated by `write-section.py --finalize`).

**Output:** Edited document written back to the same path.

### Pass 3: Cross-document reconciliation

One agent per audience. Reads all documents for its audience. Catches contradictions across documents.

**Why this is needed:** The v1.2 findings included inconsistencies like "18 tables" in ARCHITECTURE vs "15 tables" in QUICK_REFERENCE. Per-section writers (Pass 1) and per-document editors (Pass 2) can't catch these — each only sees one document. Glossary reconciliation already exists for terminology; this extends the concept to factual consistency.

**Job:**
- Flag contradictory facts across documents (different counts, conflicting parameter descriptions, inconsistent type signatures)
- Reconcile by choosing the version that matches the facts bundle (ground truth)
- Fix the contradicting document

**Input:** All documents for one audience + facts bundles (for ground truth reference).

**Output:** Corrected documents + reconciliation log.

### Data flow between passes

The orchestrator's main job is moving work between passes. The flow and the artifact at each boundary:

```
Pass 0: extract-section-facts.py
  → {TMP_DIR}/facts-{audience}-{document}-{section}.json  (one per section)

Pass 1: per-section writers
  reads: facts bundle + template PURPOSE/EXAMPLE/PATTERN + non-Python source files
  writes via: write-section.py (accumulates into per-audience state file)
  → write-section.py --finalize assembles into {docs_dir}/{audience}/{DOCUMENT}.md

Pass 2: per-document coherence editors
  reads: assembled document at {docs_dir}/{audience}/{DOCUMENT}.md
  writes: edited document back to the same path (in-place)

Pass 3: per-audience reconciliation
  reads: all documents for the audience + facts bundles (ground truth)
  writes: corrected documents in-place + reconciliation log
```

Each pass reads the output of the previous pass. Pass 1 uses `write-section.py` (the existing accumulation mechanism). Passes 2 and 3 operate on the assembled documents in-place — no intermediate paths needed since each pass fully completes before the next begins.

### Integration into generate command

The generate orchestrator changes from:

```
1. Prepare workspace
2. Glossary initial pass
3. Spawn 1 writer agent per audience (parallel) — each does all sections
4. Finalize per audience
5. Polish, reconcile, overview
```

To:

```
1. Prepare workspace
2. Glossary initial pass
3. Run extract-section-facts.py (deterministic, single invocation for all sections)
4. Pass 1: Spawn per-section writer agents (parallel within audience)
5. Finalize per audience (assemble sections into documents)
6. Pass 2: Spawn per-document coherence editors (parallel)
7. Pass 3: Spawn per-audience reconciliation agents (parallel)
8. Glossary reconcile, overview
```

### Refs and calls — correct by construction

The writer still emits refs per section — refs track what the writer actually referenced in its prose, not everything available in the facts bundle. What changes is correctness: since Python symbols come from the facts bundle (AST ground truth), the writer copies exact names and file paths rather than inferring them. For non-Python files read via Read, the writer tracks file paths as before. The result: refs accuracy improves without changing the mechanism.

## How this addresses each finding category

| Finding category | Count | Root cause | How v2 fixes it |
|---|---|---|---|
| Wrong API signatures | 35 | Writer inferred from context | Pass 0: signatures extracted by AST — ground truth. Pass 1: narrow scope prevents inference. |
| Wrong counts | 6 | Writer guessed quantities | Pass 0: counts computed deterministically. Pass 3: cross-doc reconciliation catches inconsistencies. |
| Wrong test factory signatures | 6 | Writer inferred params | Pass 0: test function signatures extracted by AST. |
| Wrong code snippet | 1 | Writer invented class fields | Pass 0: class body assignments captured as raw AST expressions. |
| Missing expected output | 11 | Convention ignored (too far from generation point) | Pass 1: `<!-- PATTERN: command-then-output -->` inline in template. |
| Missing MUST consequences | 7 | Convention ignored (same) | Pass 1: `<!-- PATTERN: constraint-with-consequence -->` inline in template. |
| Cross-doc contradictions | (subset of above) | No cross-doc check existed | Pass 3: reconciliation agent compares facts across documents. |

## Scope

**New files:**
- `auto-doc/scripts/extract-section-facts.py` — deterministic extraction script (griffe for Python, stdlib for config files, custom AST for call sites)
- `auto-doc/scripts/tests/test_extract_section_facts.py` — tests
- `auto-doc/agents/coherence-editor.md` — per-document coherence editing agent (Pass 2)
- `auto-doc/agents/cross-doc-reconciler.md` — cross-document reconciliation agent (Pass 3)

**Modified files:**
- `auto-doc/commands/auto-doc-generate.md` — three-pass orchestration, extraction step, per-section spawning
- `auto-doc/agents/{developer,end-user,devops,agent}-writer.md` — simplified to per-section scope, facts-based input, no Serena, no Python source reading
- `auto-doc/references/templates/devops/*.template.md` — add `<!-- PATTERN: command-then-output -->` markers
- `auto-doc/references/templates/agents/*.template.md` — add `<!-- PATTERN: constraint-with-consequence -->` markers

**Not changed:**
- Scan pipeline — already works well with Serena for progressive discovery; still produces `docs-scan.json`
- Verify pipeline — still consumes manifests; benefits from higher-quality refs without changes
- Schema (`docs-scan.json` contract unchanged)
- Style guide, glossary flow
- `write-section.py` — unchanged, still handles section accumulation and finalize

**Removed vs v1.2:**
- `doc-polisher.md` — replaced by the stronger coherence editor (Pass 2)

## Dependencies

- Python 3.11+ for `tomllib` (project already requires 3.11+); griffe requires 3.10+
- New dependency: `griffe` (601 KB core, zero transitive dependencies)

## Risks

| Risk | Mitigation |
|---|---|
| Extraction script complexity | Griffe handles the heavy lifting (signatures, classes, assignments); custom code limited to call-site detection and facts bundle assembly |
| Static analysis misses runtime constructs (SQLAlchemy Column, Pydantic Field) | Griffe's `Attribute.value` captures raw source expressions as structured trees — writer sees the actual code, not a parsed interpretation |
| Griffe dependency maintenance | Well-maintained (81 releases, active development, mkdocstrings ecosystem); lightweight (601 KB, zero transitive deps) |
| Per-section agent overhead (system prompt cost × 73) | Known cost, accepted for the accuracy gain from narrow scope |
| Pass 2 coherence editor could corrupt facts | Operates under focused conditions (one document, no tools, one job) unlike v1.2's overloaded context; tighten constraint if evidence of corruption emerges |
| Non-Python files read by per-section writer | Bounded to 0-2 files per section, known file list, no discovery; narrow scope prevents distraction |
| PATTERN markers could proliferate | Scoped to exactly 2 patterns covering the 24 observed findings; not a general mechanism |

## Verification

- Run generate on road-runner with v2 pipeline
- Compare verify findings against v1.2 baseline (66 findings)
- Spot-check: extracted facts match actual source (deterministic — should be 100%)
- Spot-check: per-section writer prose uses facts correctly
- Spot-check: coherence editor preserves factual claims while improving flow
- Spot-check: cross-doc reconciliation catches contradictory counts/signatures
- Spot-check: PATTERN markers produce expected output after commands and consequences for MUST constraints
- Compare token usage against v1.2 baseline
