# Phase 24: Writer Orient-Write Integration - Research

**Researched:** 2026-04-02
**Domain:** LLM agent prompt design, Python CLI extension, markdown command orchestration
**Confidence:** HIGH

## Summary

Phase 24 integrates the orient-write loop (Phase 22's `next-heading.py`) and refined templates (Phase 23's `prepare-templates` pipeline) into the live documentation generation flow. There are three deliverables: (1) rewrite `devops-writer.md` to use a two-phase orient-then-write loop driven by `next-heading.py`, (2) extend `generate-setup.py` to detect refined templates and include them in its JSON output, and (3) modify `auto-doc-generate.md` to route refined-template-capable writers through a different Agent prompt that passes the refined template path.

All Python infrastructure is already built. `next-heading.py` (Phase 22) parses refined templates, emits orient/write/done JSON responses, and manages state. `write-section.py` already accepts `--section` and `--parent` arguments compatible with `next-heading.py`'s `heading_path` convention. The refined templates exist at `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` with `<!-- REFINED: date, scan: date -->` metadata comments. No new Python scripts are needed -- this phase modifies two markdown files and extends one Python script.

The key architectural insight is that the devops-writer transforms from a template-reading agent that decides its own heading structure into a script-driven agent that receives one heading at a time. The writer never decides what headings to create -- it receives orient responses (with source files to read), then write responses (with PURPOSE and EXAMPLE for each heading), and emits content via `write-section.py` after each write response. This is the same "script controls ordering, LLM controls actions" pattern proven by `next-section.py` in the verify pipeline.

**Primary recommendation:** Split into three plans: (1) extend `generate-setup.py` with refined template detection and stale warning logic, (2) rewrite `devops-writer.md` for the orient-write loop, (3) update `auto-doc-generate.md` for refined template routing and differential writer prompt construction.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Writer agent prompt rewritten for two-phase per-section processing
- **Initialization (once per document):** Read project model, glossary, style guide -- lightweight orientation context, then enter the heading loop
- **Per `##` section -- Orient phase:** Receive orient response from next-heading.py (heading outline + source files). Read the source files for this `##` section. The heading outline tells the writer "what am I reading for" -- it knows the upcoming subsections before reading source code
- **Per heading -- Write phase:** Receive write response from next-heading.py (PURPOSE + EXAMPLE for this heading). Write content matching the PURPOSE, using the format from the EXAMPLE. Emit content + refs via write-section.py (with `--parent` for child headings). Call next-heading.py for the next heading
- Source files are read once per `##` section -- the write loop works from already-loaded context. Additional source reading per heading is optional
- The writer never decides what headings to create -- that's the template's job. It never worries about document-level structure -- that's the heading outline. It focuses entirely on reading source code and writing good prose with accurate refs
- The writer calls next-heading.py in the sequence: orient -> write x N -> orient -> write x N -> done
- Writer splits `heading_path` from next-heading.py on `/`: last segment becomes `--section` argument, everything before becomes `--parent` argument
- For `##`-level headings (no `/` in path), `--parent` is omitted
- Check for refined templates before spawning writers: if `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` exists -> pass refined template path to writer agent prompt
- If refined template not found -> fall back to generic template (backward compatible, current behavior)
- Print a warning if refined templates are stale: scan date newer than refined date from `<!-- REFINED: -->` metadata
- generate-setup.py extended to detect refined templates for each audience/document
- Includes a `refined_templates` dict in JSON output mapping audience/document to the refined template path (or null if not found)
- Generate command uses this dict to decide which writer prompt to construct
- The refined template completely replaces the generic template for the writer -- the writer sees only the refined template, not both
- Generic templates remain as input to the refiner (Phase 23), not the writer
- Only `devops-writer.md` is rewritten in this phase -- all other writers unchanged
- `glossary-writer.md` and `overview-writer.md` explicitly excluded
- The generate command's refined template detection must be non-breaking: projects without refined templates continue working exactly as before

### Claude's Discretion
- How the devops-writer prompt structures the orient phase source reading (full file reads vs symbol overview reads)
- Whether the writer prompt includes explicit instructions for each response type or a single unified loop instruction
- How the generate command constructs different writer prompts for refined vs generic template paths
- Error handling in the writer when next-heading.py returns unexpected responses
- How stale template detection compares dates (parse `<!-- REFINED: -->` metadata vs scan file timestamp vs scan metadata)
- Test strategy for end-to-end verification -- real road-runner run vs synthetic test fixtures

### Deferred Ideas (OUT OF SCOPE)
- Stale writer modernization -- end-user-writer, developer-writer, agent-writer need separate format updates before they can use the orient-write loop
- Glossary and overview writer changes -- these writers don't benefit from the orient-write loop
- Parallel heading writes -- sequential loop is simpler and sufficient
- Automatic prepare-templates invocation from generate -- remains a separate manual command
- Merge mode for refined templates -- overwrite only
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| OWI-01 | The devops-writer agent processes documents in a two-phase orient-then-write loop: orient once per `##` section to load source context, then write each heading within that section | Rewrite devops-writer.md Process section; orient phase reads source files from next-heading.py orient response, write phase emits per heading via write-section.py |
| OWI-02 | The generate command detects refined templates at the project-level path and uses them when present, falling back to generic templates when no refined template exists | Extend generate-setup.py to include `refined_templates` dict; generate command checks dict to decide writer prompt construction |
| OWI-03 | The generate command prints a warning when a refined template is stale relative to the latest scan | generate-setup.py parses `<!-- REFINED: ... scan: DATE -->` metadata and compares against scan file's `scan_date`; stale entries flagged in JSON output |
| OWI-04 | The writer produces content for every heading in the template, skipping none and inventing none -- it never decides what headings to create or manages document-level structure | Writer loop is driven entirely by next-heading.py responses; each write response triggers exactly one write-section.py call; done response terminates the loop |
| OWI-05 | When a refined template is present, the writer sees only the refined template, not the generic template | Generate command passes refined template path to writer prompt; generic template path omitted entirely when refined is available |
| OWI-06 | Content quality and reference accuracy of the orient-write pipeline are at least as good as the previous generation approach | Verification requirement -- manual or end-to-end test comparing output quality |
| OWI-07 | Only devops-writer is modified in this phase; all other writers, including glossary-writer and overview-writer, are unchanged | Locked scope constraint; generate command's fallback logic ensures non-devops writers receive generic templates as before |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| auto-doc/scripts/next-heading.py | Phase 22 | Script-gated heading iterator | Already built; emits orient/write/done JSON responses from refined template |
| auto-doc/scripts/write-section.py | Existing | Per-heading emission with `--section` and `--parent` | Already supports nested heading paths; writer calls it after each write response |
| auto-doc/scripts/generate-setup.py | Existing | Generate pipeline setup | Extended with refined template detection; JSON output consumed by generate command |
| auto-doc/scripts/get-section-sources.py | Existing | Per-section source file lookup | Writer MAY still use this for additional source lookup beyond orient response |
| lib/json_io.py | Existing | Atomic JSON load/save | Used by generate-setup.py for refined template metadata parsing |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| argparse | stdlib | CLI argument parsing | generate-setup.py extension |
| re | stdlib | Regex for `<!-- REFINED: -->` parsing | Stale template detection in generate-setup.py |
| os.path | stdlib | File existence checks | Refined template detection |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| generate-setup.py extension | Separate detect-refined-templates.py | Unnecessary; generate-setup.py already produces all runtime metadata for the generate command |
| Stale detection in Python | Stale detection in generate command prompt | Python is deterministic and testable; prompt-level date comparison is fragile |

## Architecture Patterns

### Recommended Approach

No new files. Three existing files are modified:

```
auto-doc/
├── agents/
│   └── devops-writer.md       # REWRITE: orient-write loop replacing template-reading approach
├── commands/
│   └── auto-doc-generate.md   # MODIFY: refined template routing in Stage 2 writer prompts
└── scripts/
    └── generate-setup.py      # EXTEND: refined_templates dict + stale warnings in JSON output
```

### Pattern 1: Script-Driven Writer Loop (devops-writer.md)

**What:** Writer agent follows a loop driven by next-heading.py instead of parsing the template itself.

**When to use:** When refined templates exist and the writer supports the orient-write pattern.

**Loop structure:**
```
1. Initialize: Read project model, glossary, style guide
2. For each document:
   a. First call to next-heading.py -> orient response
   b. LOOP:
      - If orient: read source files listed in response, note heading outline
      - If write: generate content for this heading using PURPOSE/EXAMPLE,
                  emit via write-section.py with --section and --parent derived from heading_path,
                  call next-heading.py for next response
      - If done: exit loop
```

**heading_path to write-section.py mapping:**
```
heading_path: "infrastructure-overview"
  -> --section infrastructure-overview (no --parent)

heading_path: "infrastructure-overview/deployment-topology"
  -> --section deployment-topology --parent infrastructure-overview

heading_path: "config-reference/environment-variables/required-variables"
  -> --section required-variables --parent config-reference/environment-variables
```

### Pattern 2: Refined Template Detection (generate-setup.py)

**What:** generate-setup.py checks for refined templates at `.mg/docs/templates/{audience}/{DOCUMENT}.template.md` and includes results in its JSON output.

**JSON output extension:**
```json
{
  "refined_templates": {
    "devops": {
      "OPERATIONS": {
        "path": "/abs/path/.mg/docs/templates/devops/OPERATIONS.template.md",
        "stale": false
      },
      "TROUBLESHOOTING": {
        "path": "/abs/path/.mg/docs/templates/devops/TROUBLESHOOTING.template.md",
        "stale": true
      }
    },
    "end-users": {
      "USER_GUIDE": null
    }
  },
  "stale_templates": ["devops/TROUBLESHOOTING"]
}
```

**Stale detection logic:**
1. Read the first 500 bytes of the refined template file
2. Parse `<!-- REFINED: {date}, scan: {scan_date} -->` with regex
3. Compare `scan_date` from the REFINED comment against `scan_date` from `docs-scan.json`
4. If scan file date is newer than refined template's scan date, mark as stale

### Pattern 3: Conditional Writer Prompt Construction (auto-doc-generate.md)

**What:** Generate command constructs different writer prompts depending on whether a refined template exists for the audience/document pair.

**Decision tree:**
```
For audience = devops:
  For each document in audience.documents:
    If refined_templates[audience][document] is not null:
      -> Pass refined template path + next-heading.py state file path to writer prompt
      -> Writer uses orient-write loop
    Else:
      -> Pass generic template path as before (existing behavior)
      -> Writer uses current per-heading emission pattern

For all other audiences:
  -> Always pass generic template path (unchanged behavior)
```

### Anti-Patterns to Avoid
- **Passing both refined and generic templates to the writer:** The writer must see exactly one template. Ambiguity about which takes precedence causes structural errors.
- **Writer deciding heading structure with refined templates:** The whole point of the orient-write loop is that the writer does not decide structure. If the writer reads the template directly, it may skip or invent headings.
- **Re-reading source files per heading:** Source files should be read once per `##` section during the orient phase. The write phase works from already-loaded context.
- **Breaking backward compatibility:** Projects without refined templates must continue working. The fallback to generic templates is essential.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Heading iteration | Manual template parsing in writer prompt | next-heading.py | Script ensures every heading is visited exactly once, in correct order |
| Section emission | Custom document assembly in writer | write-section.py with --section/--parent | Already handles state accumulation, nested sections, ref scoping |
| Template detection | Glob in generate command prompt | generate-setup.py Python extension | Deterministic, testable, avoids LLM filesystem interaction |
| Stale date comparison | Prompt-level date parsing | Python datetime comparison in generate-setup.py | String date comparison in LLM prompts is fragile |

**Key insight:** The writer agent's complexity is dramatically reduced by the orient-write loop. It no longer parses templates, decides structure, or manages section ordering. All of that is handled by scripts. The writer focuses entirely on: reading source code and writing good prose with accurate refs.

## Common Pitfalls

### Pitfall 1: Writer Breaks Loop on Unexpected Response
**What goes wrong:** next-heading.py returns an error or unexpected JSON; writer agent does not handle it gracefully and halts without emitting remaining sections.
**Why it happens:** Network issues, malformed state file, or template parsing edge cases.
**How to avoid:** Writer prompt must include explicit error handling: if next-heading.py returns non-zero exit code, log the error and continue calling with same args (state file tracks position). If JSON is malformed, retry once.
**Warning signs:** Writer completes with fewer sections than expected.

### Pitfall 2: heading_path / write-section.py Argument Mismatch
**What goes wrong:** Writer splits heading_path incorrectly, passing wrong --section or --parent values to write-section.py.
**Why it happens:** Off-by-one in slash splitting, or forgetting to omit --parent for ## headings.
**How to avoid:** Document the exact splitting rule in the writer prompt with concrete examples. Include examples for all three levels (##, ###, ####).
**Warning signs:** write-section.py errors "parent section not found".

### Pitfall 3: State File Collision Between Documents
**What goes wrong:** Two documents in the same audience (e.g., OPERATIONS and TROUBLESHOOTING) use the same next-heading.py state file, corrupting each other's progress.
**Why it happens:** State file path not scoped to document name.
**How to avoid:** State file path must include both audience and document: `.mg/docs/tmp/heading-state-devops-OPERATIONS.json`. The generate command constructs this path per document.
**Warning signs:** Writer receives orient/write responses for wrong document.

### Pitfall 4: Stale Detection Date Format Mismatch
**What goes wrong:** Refined template has `scan: 2026-04-01` but scan file has `scan_date: "2026-04-01T14:30:00Z"`. String comparison fails because formats differ.
**Why it happens:** scan_date in docs-scan.json may be ISO 8601 with time, while REFINED comment uses date-only.
**How to avoid:** Parse both dates to date-only (YYYY-MM-DD) before comparison. Use `datestr[:10]` to extract date portion.
**Warning signs:** Stale warnings never trigger or always trigger.

### Pitfall 5: Refined Template Exists But Is Empty or Malformed
**What goes wrong:** next-heading.py parses an empty or malformed refined template and returns immediate done (0 headings). Writer emits no content for that document.
**Why it happens:** Refiner agent failed silently, or partial write left an incomplete file.
**How to avoid:** generate-setup.py should validate that refined templates have at least one `##` heading. If validation fails, treat as if refined template does not exist (fall back to generic).
**Warning signs:** Document generated with 0 sections.

### Pitfall 6: Non-Devops Writer Receives Refined Template Path
**What goes wrong:** end-user-writer or developer-writer receives a refined template path but does not understand the orient-write loop. It tries to read the template directly and gets confused by PURPOSE/EXAMPLE comments.
**Why it happens:** Generate command routing logic does not restrict refined template routing to devops only.
**How to avoid:** Generate command must check BOTH that a refined template exists AND that the audience is devops before using orient-write routing. For Phase 24, only devops-writer supports the orient-write loop.
**Warning signs:** Non-devops writers produce garbled output.

### Pitfall 7: Header File Not Passed on First Section
**What goes wrong:** Writer omits `--header-file` on the first `##` section of each document, resulting in documents without the ownership header and DIATAXIS/AUDIENCE comments.
**Why it happens:** Writer prompt does not clearly specify when to create and pass the header file.
**How to avoid:** Writer prompt must explicitly state: "Write the document header ONCE before the first write-section.py call for each document. Pass `--header-file` only on the first `##` section."
**Warning signs:** Assembled document missing `<!-- This file is auto-generated -->` header.

## Code Examples

### generate-setup.py Extension: Refined Template Detection

```python
# Source: Phase 24 design, extending existing generate-setup.py

def detect_refined_templates(project_root, audiences, scan_date):
    """Detect refined templates for each audience/document pair.

    Args:
        project_root: Absolute path to project root.
        audiences: Dict from get_enabled_audiences().
        scan_date: scan_date string from docs-scan.json.

    Returns:
        Tuple of (refined_templates dict, stale_templates list).
    """
    templates_base = os.path.join(project_root, ".mg", "docs", "templates")
    refined = {}
    stale = []

    for aud_name, aud_conf in audiences.items():
        refined[aud_name] = {}
        for doc in aud_conf.get("documents", []):
            path = os.path.join(templates_base, aud_name, f"{doc}.template.md")
            if os.path.isfile(path):
                is_stale = _check_stale(path, scan_date)
                refined[aud_name][doc] = {"path": path, "stale": is_stale}
                if is_stale:
                    stale.append(f"{aud_name}/{doc}")
            else:
                refined[aud_name][doc] = None

    return refined, stale


def _check_stale(template_path, current_scan_date):
    """Check if a refined template is stale relative to scan date.

    Reads first 500 bytes for the REFINED metadata comment.
    Compares scan date in REFINED comment against current_scan_date.
    """
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            head = f.read(500)
    except OSError:
        return True  # Can't read = treat as stale

    m = re.search(r'<!--\s*REFINED:.*?scan:\s*(\S+)', head)
    if not m:
        return True  # No REFINED comment = treat as stale

    refined_scan_date = m.group(1).rstrip(",").rstrip("-->").strip()[:10]
    current_date = current_scan_date[:10] if current_scan_date else ""

    return current_date > refined_scan_date
```

### devops-writer.md Loop Structure (Pseudocode)

```markdown
## Process

1. **Read context** -- Load project model, glossary, style guide (once per invocation).

2. **For each assigned document:**

   a. Write the document header to `{TMP_DIR}/header-devops-{DOCUMENT}.md`.

   b. Call next-heading.py for the first response:
      ```bash
      python3 {SCRIPTS_DIR}/next-heading.py \
        --state-file {TMP_DIR}/heading-state-devops-{DOCUMENT}.json \
        --template {REFINED_TEMPLATE_PATH} \
        --scan-file {project_root}/.mg/docs/docs-scan.json \
        --document {DOCUMENT}
      ```

   c. **LOOP** until done:
      - Parse the JSON response.
      - **If type = "orient":**
        - Note the heading_outline for context.
        - Read each source file from source_files (symbol overview for .py, full read for config).
        - Call next-heading.py again for the next response.
      - **If type = "write":**
        - Split heading_path on `/`: last segment = section_slug, rest = parent_path.
        - Generate content for this heading using PURPOSE guidance and EXAMPLE format.
        - Write content to temp file, write refs to temp JSON.
        - Call write-section.py with --section {section_slug} [--parent {parent_path}].
        - Pass --header-file ONLY on the very first ## section of the document.
        - Call next-heading.py again for the next response.
      - **If done = true:**
        - Log headings_processed count.
        - Exit loop for this document.

3. **Post-processing** -- Same as current: rollback verification, command output verification, placeholder check, propose glossary terms.
```

### auto-doc-generate.md Routing Logic

```markdown
### Stage 2: Write Audience Documents

For each audience in `audiences`:

  If audience is "devops" AND refined_templates[audience] has any non-null entries:
    For each document in audience.documents:
      If refined_templates[audience][document] is not null:
        Spawn Agent with orient-write prompt:
          - refined_template_path = refined_templates[audience][document].path
          - Includes next-heading.py loop instructions
          - Does NOT include generic template path
      Else:
        Spawn Agent with standard prompt (current behavior)
  Else:
    Spawn Agent with standard prompt (current behavior, unchanged)

  If stale_templates is non-empty:
    Print warning: "Warning: Refined templates may be stale (scan is newer): {list}"
    Print: "Run /mg:auto-doc-prepare-templates to refresh."
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Writer parses template, decides heading structure | Writer receives headings one-at-a-time from script | Phase 22-24 | Eliminates heading invention/skipping; guarantees template coverage |
| Generic templates only | Refined templates with project-specific headings | Phase 23-24 | More specific section structure; better source-to-section alignment |
| Writer reads all source files upfront | Source files loaded per ## section via orient phase | Phase 24 | Focused context per section; reduces irrelevant source material in LLM context |
| All writers use same template approach | devops-writer uses orient-write; others use legacy approach | Phase 24 | Incremental rollout; other writers updated in future phases |

**Deprecated/outdated:**
- devops-writer.md's current "read template, parse sections, emit per heading" pattern is replaced by the orient-write loop when refined templates are available
- The current pattern remains as fallback for projects without refined templates

## Open Questions

1. **Orient phase source reading strategy**
   - What we know: Current devops-writer uses `get_symbols_overview` for Python files and full Read for non-code files. The orient response provides source_files from scan's source_material_index.
   - What's unclear: Should the writer also call `get-section-sources.py` for additional source files not in the orient response, or is the orient response sufficient?
   - Recommendation: Orient response's source_files should be the primary source. Writer MAY call get-section-sources.py if the orient response has empty source_files for a section (defensive fallback). Keep current `get_symbols_overview` first / Read fallback pattern for the actual source reading.

2. **Writer prompt structure: unified loop vs explicit per-type instructions**
   - What we know: The writer needs to handle three response types (orient, write, done) in a loop.
   - What's unclear: Single instruction block covering all types vs separate numbered steps per type.
   - Recommendation: Use explicit per-type instructions (if orient -> do X, if write -> do Y, if done -> do Z). This is clearer for the LLM and matches the current step-by-step structure in devops-writer.md.

3. **Stale template date format in scan file**
   - What we know: `<!-- REFINED: {date}, scan: {scan_date} -->` uses a date string. The scan file has a `scan_date` field.
   - What's unclear: Exact format of scan_date in docs-scan.json (ISO 8601 with time? date only?).
   - Recommendation: Normalize both to YYYY-MM-DD (first 10 chars) before comparison. This handles both formats.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (via uv run) |
| Config file | pyproject.toml (existing) |
| Quick run command | `uv run pytest auto-doc/scripts/tests/test_generate_setup.py -x --tb=short -q` |
| Full suite command | `uv run pytest auto-doc/scripts/tests/ -x --tb=short -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OWI-01 | devops-writer orient-write loop | manual | N/A -- agent prompt change, tested via road-runner end-to-end | N/A |
| OWI-02 | generate-setup.py refined template detection | unit | `uv run pytest auto-doc/scripts/tests/test_generate_setup.py -x` | Exists, needs new tests |
| OWI-03 | Stale template warning | unit | `uv run pytest auto-doc/scripts/tests/test_generate_setup.py -x` | Exists, needs new tests |
| OWI-04 | Writer covers every heading | manual | N/A -- verified by comparing next-heading.py headings_processed against write-section.py section count | N/A |
| OWI-05 | Writer sees only refined template | manual | N/A -- verified by inspecting agent prompt construction in generate command | N/A |
| OWI-06 | Content quality comparison | manual | N/A -- side-by-side comparison of generated output | N/A |
| OWI-07 | Only devops-writer modified | unit/smoke | `uv run pytest auto-doc/scripts/tests/ -x --tb=short -q` -- full suite passes | Existing tests cover other writers |

### Sampling Rate
- **Per task commit:** `uv run pytest auto-doc/scripts/tests/test_generate_setup.py -x --tb=short -q`
- **Per wave merge:** `uv run pytest auto-doc/scripts/tests/ -x --tb=short -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] New test cases in `test_generate_setup.py` -- covers OWI-02: refined template detection (path exists -> included in output, path missing -> null, stale detection)
- [ ] New test cases in `test_generate_setup.py` -- covers OWI-03: stale template warning (scan date newer than REFINED scan date -> stale=true)

*(No new test files needed -- existing test_generate_setup.py is extended with new test classes)*

## Sources

### Primary (HIGH confidence)
- `auto-doc/scripts/next-heading.py` -- Phase 22 implementation, fully reviewed (orient/write/done response format, state management, heading_path convention)
- `auto-doc/scripts/write-section.py` -- Existing implementation, fully reviewed (--section, --parent args, state accumulation, finalize)
- `auto-doc/scripts/generate-setup.py` -- Existing implementation, fully reviewed (JSON output structure, workspace preparation, audience handling)
- `auto-doc/agents/devops-writer.md` -- Current writer agent, fully reviewed (216 lines, per-heading emission pattern, typed refs, source reading strategy)
- `auto-doc/commands/auto-doc-generate.md` -- Current generate command, fully reviewed (Stage 2 writer spawning pattern, Agent prompt construction)
- `auto-doc/agents/template-refiner.md` -- Phase 23 agent definition, fully reviewed (refined template format, REFINED metadata comment)
- `auto-doc/commands/auto-doc-prepare-templates.md` -- Phase 23 command, fully reviewed (output path convention, sequential agent spawning)

### Secondary (MEDIUM confidence)
- `auto-doc/scripts/tests/test_next_heading.py` -- 39 tests passing, validates orient/write/done response format
- `auto-doc/scripts/tests/test_generate_setup.py` -- 24 tests passing, validates JSON output structure
- Phase 22 RESEARCH.md -- design decisions for next-heading.py
- Phase 23 RESEARCH.md -- design decisions for template refiner pipeline

### Tertiary (LOW confidence)
- None. All findings are from direct code review of existing implementations.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All infrastructure already exists and is tested
- Architecture: HIGH - Pattern is proven by next-section.py in verify pipeline; heading_path convention validated by 39 passing tests
- Pitfalls: HIGH - Based on direct code review of all integration points

**Research date:** 2026-04-02
**Valid until:** 2026-05-02 (stable -- all dependencies are project-internal)
