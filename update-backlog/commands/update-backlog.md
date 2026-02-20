# Update Backlog Command

Scans `.planning/` directory for deferred items and synchronizes them to `BACKLOG.md`. Uses a layered detection approach (structural, semantic, LLM classification) to identify backlog candidates, deduplicates against existing items, and presents changes for user approval.

**Reference:** See `.planning/phases/08-update-backlog-skill/08-CONTEXT.md` for implementation decisions.

---

## Step 1: Mode Selection

**Ask user:** "Full scan or incremental? (full/incremental)"

### Full Mode

Scan all `.md` files in `.planning/` directory regardless of modification time.

Use when:
- First time running the skill
- BACKLOG.md doesn't exist yet
- User wants to catch everything

### Incremental Mode

Only scan files modified after the last scan timestamp.

**Finding last scan timestamp:**
1. Read BACKLOG.md header
2. Look for: `Last scan: YYYY-MM-DD HH:MM`
3. If found: Use that timestamp to filter files
4. If not found: Fall back to full scan

**Checking file modification times:**

Use this exact command (replace TIMESTAMP with actual value):
```bash
# IMPORTANT: Use paths WITHOUT ./ prefix - must match find output format
find .planning -name "*.md" -type f \
  ! -path ".planning/BACKLOG.md" \
  ! -path ".planning/todos/*" \
  -newermt "TIMESTAMP"
```

Example:
```bash
find .planning -name "*.md" -type f \
  ! -path ".planning/BACKLOG.md" \
  ! -path ".planning/todos/*" \
  -newermt "2026-02-01 19:28"
```

### BACKLOG.md Missing

If `.planning/BACKLOG.md` does not exist:
- Default to full scan
- Create the file with standard structure after scan completes
- Note to user: "BACKLOG.md doesn't exist. Running full scan and will create it."

### Timestamp Recording

At scan start, record the current timestamp for later:
```
SCAN_TIMESTAMP=$(date +"%Y-%m-%d %H:%M")
```

This timestamp will be written to BACKLOG.md header after changes are confirmed.

---

## Step 2: File Discovery

### Find All Planning Files

Use Glob tool to discover all markdown files:
```
Pattern: .planning/**/*.md
Path: [project root]
```

### Exclusions

Exclude from scanning:
- `.planning/BACKLOG.md` - Target file, not source
- `.planning/todos/**` - Tracked by GSD todo planner, integrated into GSD workflows

**Important:** The `.planning/todos/` directory is managed separately by GSD's built-in todo tracking. Items there should NOT appear in BACKLOG.md as they would create duplicate tracking.

### Incremental Filtering

For incremental mode, use `-newermt` to filter by modification time:
```bash
# IMPORTANT: Use paths WITHOUT ./ prefix - must match find output format
find .planning -name "*.md" -type f \
  ! -path ".planning/BACKLOG.md" \
  ! -path ".planning/todos/*" \
  -newermt "LAST_SCAN_TIMESTAMP"
```

Replace `LAST_SCAN_TIMESTAMP` with the value from BACKLOG.md header (e.g., "2026-02-01 19:28").

### User Feedback

Present discovery results:
- "Found {N} files to scan..."
- For incremental: "Found {N} files modified since {LAST_SCAN_TIMESTAMP}..."

---

## Step 3: Scanning and Detection

Use a layered approach to identify backlog candidates. Start with high-confidence structural patterns, then semantic markers, then fall back to LLM/user classification for ambiguous cases.

### Layer 1 - Structural Detection (HIGH confidence)

Known sections that contain backlog items. When found, extract all items within.

**Section patterns to scan:**
| Section Name | Typically Found In | Item Type |
|--------------|-------------------|-----------|
| `## Deferred Ideas` | CONTEXT.md files | Feature / Improvement |
| `## Out of Scope` | PROJECT.md, REQUIREMENTS.md | Feature |
| `## Issues Deferred` | ROADMAP.md files | Bug / Issue |
| `## Future Requirements` | REQUIREMENTS.md | Feature |
| `## Deferred` | Any planning file | Mixed |

**Item patterns within sections:**
| Pattern | Meaning | Action |
|---------|---------|--------|
| `- [ ]` | Unchecked todo | Candidate |
| `- **Name**:` | Named item | Candidate |
| `- Name (v2)` or `(later)` | Deferred marker | Candidate |
| `- [x]` | Completed | Skip (not a candidate) |

### Layer 2 - Semantic Detection (MEDIUM confidence)

When text contains these markers in context, flag as potential backlog item.

**High confidence markers:**
- "deferred to v2"
- "deferred to future"
- "deferred"
- "out of scope"
- "future phase"
- "not implementing"
- "excluded from milestone"

**Medium confidence markers (need context check):**
- "later"
- "TBD"
- "maybe"
- "could"
- "might add"

For medium confidence: Read surrounding context to determine if it describes a backlog candidate vs just conversational text.

### Layer 3 - LLM Classification (LOW confidence, for ambiguous cases)

When text doesn't match structural patterns or semantic markers but seems like it might be a backlog item:

**Prompt user:**
```
Is this a backlog item?

[text snippet]
Source: {filename} > {section}

(yes/no)
```

Accept user's response and classify accordingly.

### Item Extraction Format

For each detected item, capture:

```yaml
description: "The item text (cleaned, may be summarized for long items)"
source: "filename.md > Section Name"
type: Bug | Feature | Improvement | Tech Debt | Other
area: UI | pipeline | database | tooling | workflow | system | other
confidence: HIGH | MEDIUM | LOW
context: "Why this matters - problem statement or user need (1-2 sentences)"
history:
  - "YYYY-MM-DD: Captured from {source} during scan"
```

**Field definitions:**

| Field | Required | Description |
|-------|----------|-------------|
| description | Yes | The item text (cleaned, may be summarized) |
| source | Yes | Where item came from (file > section) |
| type | Yes | Bug, Feature, Improvement, Tech Debt, Other |
| area | Yes | UI, pipeline, database, tooling, workflow, system, other |
| confidence | Yes | HIGH, MEDIUM, LOW (detection confidence) |
| context | Yes | Why this matters (1-2 sentences) |
| history | Yes | Dated events (captured, discussed, deferred, etc.) |

**Type classification guidance:**
- **Bug:** Something broken that needs fixing
- **Feature:** New functionality not yet implemented
- **Improvement:** Enhancement to existing functionality
- **Tech Debt:** Code quality, refactoring, cleanup
- **Other:** Doesn't fit above categories

**Area inference:**
- Infer from file path, section context, or item keywords
- When unclear, default to `other`

### Context Extraction

When extracting items, also capture surrounding context to populate the `context` field:

1. **Read surrounding text** (1-2 paragraphs before/after the item)
2. **Look for "why" indicators:**
   - Rationale explanations ("because...", "since...", "to enable...")
   - Problem statements ("currently...", "the issue is...", "users need...")
   - User needs ("would allow...", "enables...", "supports...")
3. **Synthesize context** (1-2 sentences explaining the "why")
4. **If context is unclear:** Prompt user:
   ```
   What's the context for this item?
   [item description]

   (Enter 1-2 sentences or press enter to skip)
   ```

**History initialization:**
- For new items: Single entry `"YYYY-MM-DD: Captured from {source} during scan"`
- History is append-only — events are added over time (discussed, deferred, partially implemented, etc.)

---

## Step 4: Deduplication

After collecting all candidates from scanning, deduplicate before adding to BACKLOG.md.

### Deduplication Strategy

**1. Exact Match**
- Same description text (case-insensitive, whitespace-normalized)
- Action: Merge into single item
- Keep first source found, combine all sources in attribution
- Example: `source: "CONTEXT.md > Deferred Ideas, REQUIREMENTS.md > Out of Scope"`

**2. Near Match (>90% semantic similarity AND same topic)**
- Very similar wording describing the same thing
- Action: Prompt user
```
These items seem similar. Merge them?

1. [first item text]
   Source: {source1}

2. [second item text]
   Source: {source2}

(yes/no)
```
- If yes: Merge as above
- If no: Keep both as separate items

**3. Partial Overlap (different scope but related)**
- Items touch the same area but describe different work
- Action: Keep both as separate items
- Optionally note relationship if helpful

### Merge Behavior

When merging duplicate items:
- **Date:** Keep earliest captured date (if both have dates), otherwise use today
- **Sources:** Combine: `"source_a > Section, source_b > Section"`
- **Type priority:** Bug > Feature > Improvement > Tech Debt > Other (keep higher priority)
- **Confidence:** Keep highest confidence level
- **Description:** Keep more complete description, or merge if complementary

### Cross-Reference with Existing BACKLOG.md

Before adding new items, check against existing BACKLOG.md:

1. Read existing BACKLOG.md items (parse by BKLOG-NNN IDs)
2. For each new candidate:
   - **Exact match with existing:** Skip (already in backlog)
   - **Similar to existing:** Prompt user: "This seems similar to BKLOG-{NNN}. Is it a duplicate? (yes/no)"
   - **No match:** Add as new item

### ID Generation

**Sequential IDs that never repeat:**

1. Parse existing BACKLOG.md to find all `BKLOG-NNN` patterns
2. Find the highest number: `max_id = max(all NNN values)`
3. New items get sequential IDs starting from `max_id + 1`
4. Format: `BKLOG-XXX` (zero-padded to 3 digits)

**Rules:**
- Never reuse IDs, even if an item is removed
- If BACKLOG.md is empty or doesn't exist: Start at BKLOG-001
- Example: If highest existing is BKLOG-012, next new item is BKLOG-013

### Collected Items Storage

After deduplication, organize items into categories:

```yaml
new_items:
  - id: BKLOG-013
    description: "..."
    source: "..."
    type: Feature
    area: pipeline
    confidence: HIGH

duplicate_items:
  - description: "..."
    matched_existing: BKLOG-005
    source: "..."

ambiguous_items:
  - description: "..."
    source: "..."
    user_decision: "yes"  # or "no" if rejected
```

This structure feeds into Step 5 (Implementation Detection).

---

## Step 5: Implementation Detection

Identify BACKLOG.md items that have been implemented and should be removed.

### Detection Approach (in order of confidence)

#### Layer 1 - Requirements Tracing (HIGH confidence)

Read `.planning/REQUIREMENTS.md` traceability table to identify completed items.

**Process:**
1. Parse the traceability table in REQUIREMENTS.md
2. Look for rows where the `Traces To` column references a BKLOG-XXX ID
3. Check the `Status` column for that row

**Detection rule:**
- If item ID (BKLOG-XXX) appears in traceability table with `Status: Complete` -> Item is implemented, propose removal

**Example:**
```markdown
| Req ID | Description | Traces To | Status |
|--------|-------------|-----------|--------|
| UPDT-03 | Remove implemented items | BKLOG-012 | Complete |
```
-> BKLOG-012 has "Status: Complete" in traceability -> propose removal

#### Layer 2 - Phase Verification (MEDIUM confidence)

Check phase VERIFICATION.md files for criteria that match backlog items.

**Process:**
1. Find all VERIFICATION.md files: `.planning/phases/*/VERIFICATION.md`
2. For each existing BACKLOG.md item:
   - Search VERIFICATION.md success criteria for semantic match
   - Look for description overlap or explicit ID references

**Detection rule:**
- If item description matches a verified success criterion -> Item is likely implemented

**Prompt user for confirmation:**
```
BKLOG-XXX appears to match verified criterion in Phase N:
  - Criterion: "[criterion text]"
  - Status: Verified

Remove this item? (yes/no)
```

#### Layer 3 - Semantic Matching (LOW confidence)

Check SUMMARY.md files from completed phases for accomplishment matches.

**Process:**
1. Find all SUMMARY.md files: `.planning/phases/*/*-SUMMARY.md`
2. Read the "Accomplishments" or "What was built" sections
3. For each BACKLOG.md item, check if description matches any accomplishment

**Detection rule:**
- If item matches SUMMARY.md accomplishment content -> Item may be implemented

**Prompt user with evidence:**
```
BKLOG-XXX may be implemented based on Phase N summary:
  - Accomplishment: "[accomplishment text]"

Remove this item? (yes/no)
```

### Handling Partial Implementations

When checking implementation status, user may indicate work is not fully complete.

**If user responds "partial" or indicates partial implementation:**

1. Prompt: "What remains to be done?"
2. Capture user's response
3. Update item description with partial marker:
   ```
   [Partial] Original description - Remaining: [user's input]
   ```
4. Keep item in BACKLOG.md with updated description
5. Mark as `partial_items` category (not for removal)

### Detection Results Storage

After implementation detection, categorize items:

```yaml
implemented_items:
  - id: BKLOG-012
    reason: "Requirements tracing - Status: Complete in REQUIREMENTS.md"
    evidence: "UPDT-03 traces to BKLOG-012"

partial_items:
  - id: BKLOG-005
    original_description: "Redesign version timeline..."
    updated_description: "[Partial] Redesign version timeline - Remaining: mobile layout, dark mode"

uncertain_items:
  - id: BKLOG-003
    checked_with: "user"
    user_response: "no"  # User said not to remove
```

These results feed into Step 6 (Preview Changes).

---

## Step 6: Preview Changes

Present all proposed changes in a PR-style diff format for user review.

### Change Categories

Collect all changes from previous steps:

1. **Additions** (`new_items` from Step 4) - New items detected in planning files
2. **Removals** (`implemented_items` from Step 5) - Items confirmed as implemented
3. **Updates** (`partial_items` from Step 5) - Items with updated descriptions

### PR-Style Diff Format

Present changes using +/-/~ symbols like a code diff:

```markdown
## Proposed BACKLOG.md Changes

### Additions (+{N} items)
+ [BKLOG-013] New feature description | type: Feature | area: UI | source: 08-CONTEXT.md > Deferred Ideas
+ [BKLOG-014] Tech debt item | type: Tech Debt | area: pipeline | source: 02-RESEARCH.md > Future Work
+ [BKLOG-015] Bug discovered | type: Bug | area: database | source: 05-SUMMARY.md > Issues

### Removals (-{N} items)
- [BKLOG-012] Central backlog management | Reason: Implemented in Phase 7 (REQUIREMENTS.md traceability)

### Updates (~{N} items)
~ [BKLOG-003] [Partial] Original description - Remaining: X, Y | Reason: Partially implemented

### Summary
- New items: {N}
- Removed: {N}
- Updated: {N}
- Unchanged: {N}
```

### No Changes Scenario

If no changes detected after scanning:

**Display:**
```
No changes to BACKLOG.md. All items are current.
```

**Action:**
- Skip Steps 7 and 8 (no confirmation or write needed)
- Update "Last scan:" timestamp only (run abbreviated Step 8)

---

## Step 7: Confirmation

Allow user to approve, reject, or selectively accept proposed changes.

### Confirmation Prompt

After displaying the preview, prompt user:

```
Accept all? Or review individually? (all/individual/cancel)
```

### Option: "all"

Proceed to Step 8 (Write Changes) with all proposed changes.

No further interaction needed.

### Option: "individual"

Present each change one at a time for user decision.

**For additions:**
```
Add [BKLOG-XXX] [description]?
Source: [source attribution]
Type: [type] | Area: [area]

(yes/no/edit)
```

- **yes**: Accept as-is, add to accepted list
- **no**: Reject, do not add this item
- **edit**: Allow user to modify description, type, or area
  - Prompt: "Enter new description (or press enter to keep): "
  - Prompt: "Enter type (Bug/Feature/Improvement/Tech Debt/Other or press enter to keep): "
  - Prompt: "Enter area (UI/pipeline/database/tooling/workflow/system/other or press enter to keep): "
  - After edits, add modified item to accepted list

**For removals:**
```
Remove [BKLOG-XXX] [description]?
Reason: [implementation evidence]

(yes/no)
```

- **yes**: Accept removal, add to accepted removals list
- **no**: Keep item in BACKLOG.md, do not remove

**For updates:**
```
Update [BKLOG-XXX] to:
  [new description with partial marker]
Reason: Partially implemented

(yes/no/edit)
```

- **yes**: Accept update as-is
- **no**: Keep original description unchanged
- **edit**: Allow user to modify the updated description

**After all items reviewed:**

Display summary of accepted vs rejected:
```
Accepted:
- {N} additions
- {N} removals
- {N} updates

Rejected:
- {N} additions
- {N} removals
- {N} updates

Proceed with accepted changes? (yes/no)
```

### Option: "cancel"

Abort without any changes to BACKLOG.md.

**Display:**
```
No changes made to BACKLOG.md.
```

**Action:**
- Exit skill immediately
- Do not update "Last scan:" timestamp (no successful scan completed)

### Confirmation Results Storage

Track what user approved and rejected:

```yaml
accepted_additions:
  - id: BKLOG-013
    description: "..."
    source: "..."
    type: Feature
    area: pipeline

accepted_removals:
  - id: BKLOG-012
    reason: "Implemented in Phase 7"

accepted_updates:
  - id: BKLOG-005
    old_description: "..."
    new_description: "[Partial] ..."

rejected_items:
  - id: BKLOG-014
    action: addition
    reason: "User rejected"
```

These results feed into Item Format Reference and Step 8 (Write Changes).

---

## Item Format Reference

Backlog items use a labeled sub-bullet format for rich context and history tracking.

### Example Item

```markdown
- **[BKLOG-013] Redesign version timeline with clickable toggles**
  - Type: Feature
  - Area: UI
  - Captured: 2026-02-01
  - Source: PROJECT.md > Out of Scope
  - Context: Users need visual indication of which versions are selected. Current checkboxes are small and hard to hit on mobile.
  - History:
    - 2026-02-01: Captured from PROJECT.md during v2 milestone setup
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| Title | Yes | Main bullet text after ID (bold) |
| Type | Yes | Bug, Feature, Improvement, Tech Debt, Other |
| Area | Yes | UI, pipeline, database, tooling, workflow, system, other |
| Captured | Yes | Date item was added (YYYY-MM-DD) |
| Source | Yes | Where item came from (file > section) |
| Context | Yes | Why this matters (1-2 sentences) |
| History | Yes | Dated events list (captured, discussed, deferred, etc.) |

### Format Rules

1. **Main bullet:** Bold ID and title: `- **[BKLOG-XXX] Title**`
2. **Sub-bullets:** Labeled fields with consistent indentation (2 spaces)
3. **Context:** Problem statement or user need (1-2 sentences)
4. **History:** Nested bullet list under History field (4 spaces indent)
5. **Spacing:** Blank line between items for readability
6. **No horizontal rules** between items (standard bullet list)

### History Events

History tracks the item's lifecycle:
- `Captured from {source} during scan` - Initial addition
- `Discussed in planning session` - Mentioned but not prioritized
- `Deferred to v{N}` - Explicitly pushed to future milestone
- `Partially implemented - Remaining: X, Y` - Work started but incomplete
- `Triaged as {Bug/Feature}` - Classification changed
- `Linked to BKLOG-XXX` - Related to another item

---

## Step 8: Write Changes

Apply accepted changes to BACKLOG.md and update metadata.

### Prerequisites

Only execute if user confirmed changes (did not cancel in Step 7).

### Update Process

**1. Read current BACKLOG.md content:**
```
content = Read(.planning/BACKLOG.md)
```

**2. Parse into sections:**
- Header (metadata lines at top)
- Triaged section
- Ideas section
- Won't Do section

**3. Apply accepted changes:**

**For additions (insert new items):**
- Determine target section based on type:
  - Bug, Feature (with priority indicator) -> Triaged
  - Improvement, Tech Debt, Other -> Ideas
  - Items user classified as "Won't Do" -> Won't Do (with reason)
- Format item using labeled sub-bullets:
  ```markdown
  - **[BKLOG-XXX] Item Title**
    - Type: Feature
    - Area: UI
    - Captured: 2026-02-01
    - Source: PROJECT.md > Out of Scope
    - Context: Why this item matters. Problem statement or user need it addresses.
    - History:
      - 2026-02-01: Captured from PROJECT.md during v2 milestone setup
  ```
- Insert at end of appropriate section
- Blank line between items for readability

**For removals (delete items):**
- Find the main bullet line containing the BKLOG-XXX ID
- Remove entire item block (main bullet + all indented sub-bullets: Type, Area, Captured, Source, Context, History)
- Note: Item ID should not be reused (per ID generation rules)

**For updates (modify item content):**
- Find the line containing the BKLOG-XXX ID
- Replace description with updated text
- Keep ID, type, area, captured date, and source unchanged

**4. Update header metadata:**

Update "Last updated:" line:
```
Last updated: {today's date and time in YYYY-MM-DD HH:MM format}
```

Update "Last scan:" line:
```
Last scan: {SCAN_TIMESTAMP from Step 1}
```

Recalculate "Total items:" line:
```
**Total items:** {total} | Triaged: {triaged_count} | Ideas: {ideas_count} | Won't Do: {wont_do_count}
```

**5. Write to file:**

Use Write tool to update `.planning/BACKLOG.md` with modified content.

Display confirmation:
```
BACKLOG.md updated successfully.
```

### Section Placement Logic

| Item Type | Priority/Flag | Target Section |
|-----------|---------------|----------------|
| Bug | Any | Triaged |
| Feature | High priority | Triaged |
| Feature | Normal priority | Ideas |
| Improvement | Any | Ideas |
| Tech Debt | Any | Ideas |
| Other | Any | Ideas |
| Any | User: "Won't Do" | Won't Do |

### Completion Summary

After writing changes, display summary:

```markdown
## Backlog Update Complete

**Changes applied:**
- Added: {N} items
- Removed: {N} items
- Updated: {N} items

**BACKLOG.md stats:**
- Total items: {N}
- Triaged: {N}
- Ideas: {N}
- Won't Do: {N}

**Last scan timestamp recorded:** {SCAN_TIMESTAMP}

Note: No git commit was made. Run `git add .planning/BACKLOG.md && git commit -m "chore: update backlog"` if desired.
```

### Error Handling

**If BACKLOG.md doesn't exist when starting (Step 1):**
- Create it with standard header and empty sections
- Inform user: "Created new BACKLOG.md"
- Continue with normal flow

**Standard header template:**
```markdown
# Backlog

Last updated: {today's date and time}
Last scan: (not yet scanned)
Total items: 0 | Triaged: 0 | Ideas: 0 | Won't Do: 0

## Triaged

## Ideas

## Won't Do
```

**If parse error occurs:**
- Display error details
- Offer options:
  ```
  Failed to parse BACKLOG.md: [error details]

  Options:
  1. Create fresh BACKLOG.md (will lose existing content)
  2. Abort scan

  Choose: (1/2)
  ```
- If user chooses 1: Create fresh file, then add new items
- If user chooses 2: Exit skill without changes
