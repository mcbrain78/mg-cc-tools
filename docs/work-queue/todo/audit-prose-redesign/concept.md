# Audit Prose-vs-Refs Redesign

## Situation

The auto-doc audit pipeline (`/mg:auto-doc-audit`) runs after document generation to check prose-vs-refs consistency. Today it spawns 3 waves of LLM agents per document, each processing all sections sequentially — extracting entities from prose, cross-checking against declared refs, and making judgment calls in a single combined pass. A recent devops audit of 3 documents (57 sections total) consumed 671k tokens across 9 agent spawns and took 38 minutes.

The XML source format was recently refined to fine-grained sections (median 2,201 chars, max ~6,000 chars across 57 sections in the road-runner project), which means individual sections are well within LLM attention range.

The current pipeline performs two checks:
- **Check A (entity → ref):** Does each code entity mentioned in prose have a matching declared ref?
- **Check B (ref → body):** Does each declared ref's identifier appear somewhere in the section body?

Both checks are performed by LLM agents in every wave, even though Check B is a pure string search.

## Problem

1. **Token waste.** Every wave re-reads ALL sections, even clean ones. Waves 2-3 are more expensive than wave 1 because they also read a growing findings file. In the observed audit run, roughly 65% of per-wave tokens were spent on sections that produced no findings.

2. **Deterministic work done by LLM.** Check B (does a declared ref's identifier appear in the section body?) is a literal string search: `if identifier in body`. The LLM performed this check with zero false positives and zero false negatives in the observed run — confirming it adds no judgment value. Running it across 3 waves for every section wastes tokens on work a script could do instantly.

## Solution

### Overview

Split the current combined extract-match-judge workload into three distinct phases: LLM extraction (wave 1), deterministic script clearing + Check B, and LLM resolution of only the uncleared remainder (waves 2+). Clean sections are never revisited after wave 1. Check B runs once in the script, not in the LLM.

### Wave 1 — Entity Extraction (LLM, per document)

One extraction agent per document, single pass through sections via `next-section.py`. For each section, the agent reads the prose body and extracts every code entity name — function names, table names, column names, file paths, env vars, CLI tools, flow names, enum values, etc. The agent writes each entity via `add-extracted-entity.py` with just the name and section link. It does NOT look at declared refs.

Output per document: `entities-{audience}-{DOCUMENT}.json` — a flat list of `{name, section}` pairs, deduplicated at write time.

### Script Step — Clearing + Check B (deterministic)

`clear-matched-entities.py` runs once per document after wave 1. It performs two operations:

**Clearing (Check A, partial):** For each section, match extracted entity names against declared ref identifiers for that section. A ref's identifier is its primary name field — `name` for code/flow/dep/ext/literal, `table` for db, basename for config `path`, `class` for enum, `value` for enum values. An entity clears if it exactly matches one ref identifier. Multiple matches (same name, different ref types) do not clear — the ambiguity goes to the LLM. Zero matches do not clear.

**Check B (ref → body):** For each declared ref in each section, check if its identifier string appears in the section body. If not found, emit a `reference-integrity` finding directly via `add-verify-finding.py`.

Output: `uncleared-{audience}-{DOCUMENT}.json` — only entities that did not clear, with their section links. A summary line to stderr: `"Extracted: 45, Cleared: 31, Uncleared: 14 across 8 sections"`.

The script also computes the list of affected sections (sections that have at least one uncleared entity) for wave 2 filtering.

### Waves 2+ — Resolution (LLM, per document)

One resolution agent per document, visiting only sections with uncleared entities via `next-section.py --sections-filter`. For each affected section, the agent reads the section body and its uncleared entities, then for each entity:

1. **Confirms** it is ref-worthy — not a Python builtin, SQL keyword, or noise.
2. **Maps** it by checking scan data (project model, database model) and searching the codebase to find where the entity comes from and what the correct ref should be.
3. **Emits** a finding via `add-verify-finding.py` with the correct ref in the suggestion field, or dismisses the entity as not ref-worthy.

The `waves=N` parameter on the audit command controls how many resolution passes run (default 2). Wave 1 (extraction) always runs once. Each resolution pass spawns a fresh agent that reads prior findings and the remaining uncleared list, looking for what previous passes missed or couldn't resolve.

### Pipeline Flow

```
Step 1: Setup (unchanged)
Step 2: verify-xml-refs.py (unchanged — refs → codebase)
Step 3: prepare-prose-verify.py (unchanged — creates per-section JSONs)
Step 4: Wave 1 — extraction agents (parallel per document)
Step 5: clear-matched-entities.py (per document, deterministic)
Step 6: Wave 2 — resolution agents (parallel per document, uncleared sections only)
Step 7: [Optional waves 3+] — resolution agents (remaining uncleared)
Step 8: Report
```

## Design Decisions

### D1: Entity extraction outputs names only, not typed refs

**Choice:** The extraction agent outputs flat `{name, section}` pairs, not structured ref dicts with type/schema/module fields.

**Why:** Typing the ref (is `get_db` a function, class, or flow?) requires judgment and context from the codebase. That judgment belongs in wave 2 where the agent resolves the entity against scan data and codebase. Extraction should be fast and mechanical — "list every code entity you see."

### D2: Clearing matches by exact name only

**Choice:** An entity clears if its name exactly matches one declared ref identifier for that section. Substring and fuzzy matches go to the LLM.

**Why:** Within a single section, the name space is small and almost always unambiguous. Exact matching is conservative — better to send a few extra items to wave 2 than to incorrectly clear an entity that refers to something different than the matched ref. Multiple exact matches (same name, different ref types) also don't clear — the ambiguity itself is worth reviewing.

### D3: Check B runs in the script, not the LLM

**Choice:** The clearing script performs Check B (ref identifier → body search) and emits `reference-integrity` findings directly.

**Why:** This check is a literal string search. It was the most reliably correct check the LLM performed (zero false positives/negatives in the observed audit run), confirming it adds zero judgment value. Running it in the script makes it instant, reproducible, and free of token cost.

### D4: Single-pass extraction (no internal loops)

**Choice:** The extraction agent processes all sections once, not in multiple loops.

**Why:** With fine-grained XML sections (median 2,201 chars, max ~6,000 chars), each section is well within attention range. The attention fatigue problem in the current system comes from the combined workload of extraction + cross-checking + judgment across 25+ sections. Pure extraction — "list every code entity you see" — is a much lighter cognitive task. If extraction misses an entity, wave 2 resolution agents can still discover it when investigating the section's uncleared items.

**Alternatives rejected:** Multi-pass extraction (3 internal loops). Would add token cost proportional to total sections x 2 extra passes, with diminishing returns given the reduced per-section workload.

### D5: LLM resolves entities, not the script

**Choice:** The resolution agent does all entity-to-source mapping (scan data, database model, codebase lookup). The clearing script does not attempt pre-resolution.

**Why:** Pre-resolving in the script risks false matches on common names like `status`, `id`, `name` that appear across many database tables, config keys, and modules. The LLM has section context to disambiguate — it knows the section is about drift warnings, so `status` means `data_drift_warnings.status`, not `etl_runs.status`. Deterministic lookup without context would produce noise.

### D6: Uncleared entities written to a separate file

**Choice:** The clearing script outputs `uncleared-{audience}-{DOCUMENT}.json` as a separate file, rather than annotating the entities file with `cleared: true/false` flags.

**Why:** The entities file is wave 1's complete output — a record of what was extracted. The uncleared file is a focused input for wave 2. Keeping them separate avoids mixing concerns, keeps the wave 2 agent's context lean, and makes it easy to inspect clearing behavior (both files side by side) when debugging or tuning.

## Scope

### What gets built

| Deliverable | Notes |
|---|---|
| `auto-doc/scripts/add-extracted-entity.py` | Append entity (name + section) to entities file. Dedup by `(name, section)` tuple on write. Follows `add-verify-finding.py` inline-mode CLI pattern. |
| `auto-doc/scripts/clear-matched-entities.py` | Per-section exact name matching + Check B. Inputs: entities file, prose-verify dir. Outputs: uncleared entities file + reference-integrity findings to findings file. |
| `auto-doc/agents/extract-prose-entities.md` | Extraction agent instructions. Single pass, next-section iteration, writes via `add-extracted-entity.py`. |
| `auto-doc/agents/resolve-prose-entities.md` | Resolution agent instructions. Visits only uncleared sections, confirms entities, maps against scan data / database model / codebase, emits findings via `add-verify-finding.py`. |
| `auto-doc/commands/auto-doc-audit.md` | Rewrite orchestrator flow: setup, verify-xml-refs, prepare, wave 1 extraction, script clearing, wave 2+ resolution, report. |
| `auto-doc/scripts/next-section.py` | Add `--sections-filter` flag to restrict iteration to a provided list of section paths. |

### What does NOT get built

- **Typed entity extraction** — outputting ref dicts with type/schema/module, not names. Typing is wave 2's job.
- **Script-based entity resolution** — pre-resolving entities against database model or scan data in the clearing script. Too noisy without section context (D5).
- **Changes to `verify-xml-refs.py`** — the deterministic ref-to-codebase checker is unchanged.
- **Changes to `prepare-prose-verify.py`** — section JSON preparation stays the same.
- **Changes to `add-verify-finding.py`** or findings format — output mechanism is reused as-is.
- **Changes to the verify pipeline (`auto-doc-verify`)** — audit and verify remain separate.
- **Multi-pass extraction** — no internal loops in the extraction agent (D4).

## Open Items

None — all items resolved during discussion.

## Verification

1. **Token reduction (post-implementation gauge).** After implementation, run the redesigned audit on a real project and compare total token usage against a baseline run of the old pipeline on the same project. The ~65% estimate from analysis is directional, not a target — actual reduction depends on clearing rate and project characteristics.

2. **Check B correctness.** Run the clearing script's Check B on road-runner OPERATIONS XML. Compare `reference-integrity` findings against the 7 that the LLM produced in the original audit. Should be identical or a strict subset (no false positives).

3. **Clearing rate.** After wave 1 extraction + clearing on road-runner devops, measure what percentage of extracted entities clear. Validates the "skip clean sections" premise — if clearing rate is very low, the token savings won't materialize.

4. **Finding parity.** Compare total findings (all types) from the redesigned audit against the original 163. The redesigned pipeline should find the same or more issues — never fewer, since it adds deterministic Check B that the LLM sometimes missed.

5. **`waves=N` parameter.** Run with `waves=1` and `waves=3`, verify that more resolution passes produce additional findings (diminishing returns expected).
