# New Milestone Gate

---
name: mg:new-milestone-gsd
description: Gate for /gsd:new-milestone - shows backlog status and offers update
argument-hint: "[milestone name]"
allowed-tools:
  - Read
  - Bash
  - Skill
---

<objective>
Gate milestone creation with backlog review. Shows current backlog status and offers three options: update the backlog first, proceed directly to new milestone creation, or cancel.
</objective>

<context>
Load milestone name from `$ARGUMENTS` if provided. This will be preserved in the final instructions so the user can pass it to `/gsd:new-milestone`.

**Reference:**
- `.planning/BACKLOG.md` - File to parse for status
- `/mg:update-backlog` - Skill to invoke for backlog updates
- `/gsd:new-milestone` - Target skill to delegate to after gate passes
</context>

## Step 1: Validate

Check if BACKLOG.md exists:

```bash
test -f .planning/BACKLOG.md && echo "exists" || echo "missing"
```

**If missing:**

Display this message and exit the skill immediately (do not continue to Step 2):

```
---

No BACKLOG.md found.

**Action required:** Run `/mg:update-backlog` to create and populate the backlog.

---
```

**If exists:** Continue to Step 2.

## Step 2: Parse and Display Status

Read `.planning/BACKLOG.md` and extract the status information.

### Parsing Logic

1. Read BACKLOG.md
2. Find line matching `**Total items:**` pattern
3. Extract counts: `Triaged: N | Ideas: N | Won't Do: N`
4. Find `**Last updated:**` line
5. Extract and format date (e.g., "2026-02-01 19:28" -> "Feb 1")

### Display Format

Present the status header in this format:

```
--- BACKLOG ---
3 Triaged | 9 Ideas | 3 Won't Do
Last updated: Feb 1
---
```

Then display: "How would you like to proceed?"

## Step 3: Route by Choice

Present options to user:

1. **Update backlog** - Run /mg:update-backlog first
2. **Proceed to new milestone** - Go directly to /gsd:new-milestone
3. **Cancel** - Exit without action

---

### Option 1: Update backlog

Ask: "Full scan or incremental? (full/incremental)"

Then invoke the update-backlog skill:

```
Use Skill tool:
- skill: "mg:update-backlog"
```

After completion, display:

```
---

Backlog updated.

**Next:** Run `/clear` then `/gsd:new-milestone [name]`

---
```

Include the milestone name from `$ARGUMENTS` if it was provided (e.g., "Run `/clear` then `/gsd:new-milestone v3`").

**If update-backlog encounters errors:** Show the error but still offer to proceed to /gsd:new-milestone.

---

### Option 2: Proceed to new milestone

Display instructions (do not invoke the skill directly):

```
---

**Next:** Run `/clear` then `/gsd:new-milestone [name]`

---
```

Include the milestone name from `$ARGUMENTS` if it was provided.

---

### Option 3: Cancel

Display:

```
---

Cancelled.

Run `/clear` and then: `/mg:new-milestone-gsd` or `/gsd:new-milestone`

---
```

<success_criteria>
- [ ] BACKLOG.md existence validated (or error shown if missing)
- [ ] Status header displayed with accurate counts
- [ ] User selected one of three options
- [ ] Selected option executed correctly:
  - Update: /mg:update-backlog invoked, then instructions shown
  - Proceed: Instructions shown for /gsd:new-milestone
  - Cancel: Cancellation message shown
- [ ] Milestone name preserved in instructions (if provided)
</success_criteria>
