# Documentation Style Guide

Writing conventions for `/mg:auto-doc` generated documentation. Writer agents reference this guide at generation time to ensure consistent, audience-appropriate output.

## 1. Universal Conventions

These rules apply to all documentation regardless of audience.

### Voice and Tense

- **Active voice.** "The scanner reads the config file" not "The config file is read by the scanner."
- **Present tense.** "This function returns a list" not "This function will return a list."
- **Second person for instructions.** "You can configure..." or imperative "Configure..." -- never "The user should configure..."

### Language

- No marketing language. Avoid "powerful", "seamless", "elegant", "blazing fast."
- No filler phrases. Cut "it should be noted that", "in order to", "as a matter of fact."
- Version-independent phrasing. "The current implementation" not "As of v1.2" unless version-specific behavior is the point.
- Prefer concrete over abstract. "Returns an empty list" not "Returns an appropriate default."

### Structure

- One idea per paragraph. If a paragraph covers two concepts, split it.
- Lead with the conclusion. State what something does before explaining how.
- Use parallel structure in lists. All items should follow the same grammatical pattern.

### Terminology

- Use the project's own terminology consistently. If the codebase calls it a "finding", don't call it an "issue" or "result."
- Define terms on first use. Bold the term and follow with the definition.
- Maintain a glossary (GLOSSARY.md) for cross-audience terminology.

## 2. Audience-Specific Conventions

### End-Users

**Goal:** Help users accomplish tasks without needing to understand internals.

- **Plain language.** Avoid jargon. If a technical term is unavoidable, define it inline.
- **Task-oriented structure.** Organize by what users want to do, not by system architecture.
- **Scannable format.** Use numbered steps for procedures, bullet lists for options, tables for comparisons.
- **No implementation details.** Users don't need to know which library handles auth -- they need to know how to log in.
- **Expected results.** After each step, state what the user should see.
- **Error guidance.** For common mistakes, include a "Troubleshooting" callout near the relevant step.

**Example structure:**
```
## Installing the Tool

1. Open your terminal.
2. Run the install command:
   ```bash
   bash install.sh --project
   ```
3. You should see: "Installation complete. 5 commands installed."
```

### Developers

**Goal:** Help developers understand, extend, and integrate with the codebase.

- **Code-first.** Show the example before the explanation. Developers scan for code blocks.
- **Stripe/Twilio style.** Short prose, rich code samples, progressive disclosure (overview first, details in linked sections).
- **Technical depth welcome.** Explain algorithms, data flow, design decisions. Don't oversimplify.
- **Link to source.** Reference specific files and functions. Use relative paths: `scripts/lib/json_io.py`.
- **Type signatures matter.** Include parameter types, return types, and exception types.
- **Show edge cases.** Document what happens with empty input, missing files, invalid data.

**Example structure:**
```
## json_io.load_json

```python
data = load_json("path/to/file.json", default={})
```

Loads and parses a JSON file. Returns `default` if the file doesn't exist.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str` | -- | Path to JSON file |
| `default` | `Any` | `None` | Fallback if file not found |

**Returns:** Parsed JSON data (`dict`, `list`, etc.) or `default`.

**Raises:** `json.JSONDecodeError` if file exists but contains invalid JSON.
```

### Agents (LLM Consumers)

**Goal:** Provide unambiguous, machine-optimized context for LLM agents.

- **Explicit over implicit.** State constraints directly: "MUST use absolute paths" not "paths should be absolute."
- **YAML frontmatter.** Include structured metadata at the top of each document (tool name, purpose, allowed operations).
- **Absolute paths.** Always use absolute paths for file references. Relative paths are ambiguous across working directories.
- **No ambiguity.** If a field can be null, say so. If a behavior depends on context, enumerate the cases.
- **Structured over prose.** Prefer tables, lists, and code blocks over paragraphs. Agents parse structured content more reliably.
- **Action-oriented.** "Run `python3 script.py --flag`" not "You might want to run the script."
- **Constraint blocks.** Group constraints together with clear labels (MUST, SHOULD, MUST NOT).

**Example structure:**
```
---
tool: add-note
purpose: Append documentation note to inbox
inputs: --inbox, --text
outputs: Updated notes-inbox.json
---

## Behavior

- MUST write atomically (temp file + os.replace)
- MUST generate sequential NOTE-NNN IDs
- MUST NOT modify existing notes
- Returns exit code 0 on success, 1 on failure
```

### DevOps

**Goal:** Enable operators to deploy, monitor, and troubleshoot the system.

- **Runbook structure.** Organize by scenario: symptom, cause, fix.
- **Copy-paste ready.** Every command should be runnable as-is. No `<placeholder>` without explaining what to substitute.
- **Include expected output.** After each command, show what success and failure look like.
- **Environment awareness.** Specify which environment (dev, staging, prod) each procedure applies to.
- **Prerequisite checklist.** Start each procedure with what must be true before starting.
- **Rollback steps.** For destructive operations, include how to undo.

**Example structure:**
```
## Symptom: Scan Fails with "Permission Denied"

**Cause:** The scripts directory lacks execute permissions.

**Fix:**
```bash
chmod +x .claude/auto-doc/scripts/*.py
```

**Expected output:** No output on success. Verify with:
```bash
ls -la .claude/auto-doc/scripts/
# Should show -rwxr-xr-x for .py files
```

**If this doesn't resolve it:** Check that the `.mg/docs/` workspace directory is writable by the current user.
```

## 3. Diataxis Classification

Documentation falls into four types. Each audience tends toward different types, but any audience may need any type.

### Tutorial

Step-by-step learning experience. The reader follows along to build understanding.

- **Audience affinity:** End-users (getting started), Developers (onboarding)
- **Structure:** Sequential steps with a concrete goal
- **Tone:** Guided, patient, encouraging
- **Key rule:** Never assume prior knowledge within the tutorial's scope

### How-To Guide

Practical steps to accomplish a specific task. The reader already has context.

- **Audience affinity:** DevOps (runbooks), End-users (task guides)
- **Structure:** Prerequisites, numbered steps, expected result
- **Tone:** Direct, efficient
- **Key rule:** Stay focused on one task. Link to explanations rather than embedding them.

### Reference

Technical description of the system's machinery. Factual and complete.

- **Audience affinity:** Developers (API docs), Agents (system maps)
- **Structure:** Organized by the system's structure (modules, endpoints, fields)
- **Tone:** Precise, neutral, comprehensive
- **Key rule:** Describe what IS, not what to DO. No opinions or recommendations.

### Explanation

Discussion of concepts, design decisions, and context. Helps the reader understand WHY.

- **Audience affinity:** Developers (architecture decisions), DevOps (system design context)
- **Structure:** Topic-driven, with connections between concepts
- **Tone:** Conversational but technical
- **Key rule:** Provide context and reasoning, not instructions.

## 4. Section Conventions

### Opening

Every section starts with a **context sentence** that tells the reader what this section covers and why it matters. Never jump straight into details.

Good: "The scanner builds a project model by analyzing source files and git history. This model drives all downstream documentation generation."

Bad: "The project_model field contains tech_stack, entry_points, components, and infrastructure."

### Closing

End each section with a **what's next pointer** when there is a logical next step:

- "See [Configuration](#configuration) to customize which audiences are enabled."
- "The scanner uses this model during the gap analysis step (next section)."

Omit the pointer for terminal sections (glossary entries, API field descriptions).

### Optional Content

Mark optional sections with a clear indicator:

```markdown
> **Note:** This section only applies if GSD integration is enabled in `.docs.config.json`.
```

Do not hide critical information in optional callouts.

## 5. Formatting Standards

### Headings

- **H1 (`#`)**: Document title only. One per file.
- **H2 (`##`)**: Major sections.
- **H3 (`###`)**: Subsections.
- **H4 (`####`)**: Rarely needed. If you need H4, consider restructuring.
- Never skip heading levels (H2 followed by H4).

### Code Blocks

- Always include a language tag: ` ```python `, ` ```bash `, ` ```json `.
- Use `bash` for shell commands, `console` for shell sessions with output.
- Keep code blocks self-contained. The reader should be able to copy and run them.
- Add a brief comment above non-obvious code blocks explaining what they demonstrate.

### Admonitions

Use blockquote-based admonitions with bold labels:

```markdown
> **Note:** Supplementary information that adds context.

> **Warning:** Something that could cause problems if ignored.

> **Important:** Critical information the reader must not miss.
```

### Links

- Use relative links within the same document set: `[Style Guide](./style-guide.md)`.
- Use descriptive link text: `[configuration reference](./config.md)` not `[click here](./config.md)`.
- When linking to source code, include the file path: `[json_io.py](scripts/lib/json_io.py)`.

### Tables

- Use tables for structured comparisons, parameter lists, and field descriptions.
- Always include a header row.
- Align columns for readability in the source markdown (optional but preferred).
- Keep cell content concise. Use footnotes or separate sections for lengthy descriptions.

## 6. Quality Checks

These checks prevent common issues caught during verification.

### Heading-Content Alignment
Before closing a section, re-read the heading. If the heading says "Configuration" but the content only lists file paths with no configuration instructions, rewrite to match.

### Consistent Section Depth
Sections at the same heading level should have comparable depth. If one peer section is 3 sentences and another is 3 paragraphs, expand the thin one or condense the long one.

### Verify Cross-References
Search for "see below", "as described above", "the following section" — verify the target exists in the document. If not, rewrite without the dangling reference.

### No Internal Contradictions
Scan for conflicting statements: version requirements, naming, parameter types, ordering. If two claims could conflict, verify against source material.

### No Placeholder Content
Remove all: TODOs, `{placeholder}` tokens, `TBD`, leftover template comments (`<!-- PURPOSE:`, `<!-- EXAMPLE:`, `<!-- AUDIENCE:`), `lorem ipsum`.

## 7. Reference Naming by Audience

Code entities named in prose create verifiable anchors for the ref system. The density of naming varies by audience — devops names functions when they tell operators where to look; end-user docs rarely name internal code at all.

| Audience | Naming Density | What to Name | What NOT to Name |
|----------|---------------|--------------|------------------|
| Developer/Agent | High | Functions, classes, modules, parameters, types | — |
| DevOps | Medium | Config files, env vars, service units, DB objects, CLI tools, flow names. Functions/classes when they tell the operator where to look. | Full signatures, parameter types, internal implementation patterns |
| End-user | Low | Flow names, config paths the user interacts with | Internal functions, classes, modules |
| Glossary | Map-level | The specific code entity each term maps to | — |

### DevOps Naming Examples

**Good:** "The `classify_severity()` function assigns severity based on change magnitude: `info` (below 1%), `warning` (1-5%), `critical` (above 5%)."

**Bad:** "Drift detection classifies severity into three levels." (no verifiable anchor — if the writer read `classify_severity` during orient, the function name must appear in prose or the ref must be omitted)

**Bad:** "`classify_severity(changed_fields: dict[str, FieldDiff]) -> Severity` iterates..." (too much implementation detail for devops — full signatures belong in developer docs)

---

*This style guide is referenced by writer agents during documentation generation. Updates to these conventions affect all future document generation runs.*
