# CC Regression Test

---
name: mg:cc-regression-test
description: Regression test suite for Claude Code features (hooks, interactive prompts)
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
  - Glob
---

<objective>
Run a regression test suite that validates core Claude Code features still work correctly.
Tests hook interception (PreToolUse hooks fire and prompt the user) and AskUserQuestion
(presents options and waits for actual user selection instead of auto-approving).
</objective>

<context>
Scripts directory: {MG_INSTALL_SCRIPTS_DIR}
Hooks directory: {MG_INSTALL_HOOKS_DIR}
Source directory: {MG_INSTALL_SOURCE_DIR}
</context>

<process>

## Step 0: Source Sync Check

Before running tests, verify that installed files are in sync with the source repository.

```bash
# Compare installed vs source for hooks and scripts
INSTALLED_HOOKS_MD5=$(cd "{MG_INSTALL_HOOKS_DIR}" && md5sum *.py 2>/dev/null | sort)
SOURCE_HOOKS_MD5=$(cd "{MG_INSTALL_SOURCE_DIR}/hooks" && md5sum *.py 2>/dev/null | sort)
INSTALLED_SCRIPTS_MD5=$(cd "{MG_INSTALL_SCRIPTS_DIR}" && md5sum *.py 2>/dev/null | sort)
SOURCE_SCRIPTS_MD5=$(cd "{MG_INSTALL_SOURCE_DIR}/scripts" && md5sum *.py 2>/dev/null | sort)
```

**If all identical:** Log `Files in sync.` and proceed to Step 1.

**If different:** Determine what changed:
- Compare hooks: which files are new, modified, or orphaned
- Compare scripts: which files are new, modified, or orphaned

Report:
```
--- CC Regression Test Sync Check ---

Source: {MG_INSTALL_SOURCE_DIR}

Hooks:
  New:      [list or "none"]
  Modified: [list or "none"]
  Orphaned: [list or "none"]

Scripts:
  New:      [list or "none"]
  Modified: [list or "none"]
  Orphaned: [list or "none"]
```

Ask via AskUserQuestion:
- header: "Sync"
- question: "Installed cc-regression-test files are out of sync with source. Sync now?"
- options:
  - "Sync now" — "Copy files from source and re-merge hooks into settings.json, then stop"
  - "Continue stale" — "Run tests with currently installed files"

**If "Sync now":**

1. Copy all source files:
```bash
cp "{MG_INSTALL_SOURCE_DIR}/hooks/"*.py "{MG_INSTALL_HOOKS_DIR}/"
cp "{MG_INSTALL_SOURCE_DIR}/scripts/"*.py "{MG_INSTALL_SCRIPTS_DIR}/"
chmod +x "{MG_INSTALL_HOOKS_DIR}/"*.py "{MG_INSTALL_SCRIPTS_DIR}/"*.py
```

2. Re-merge hook config into settings.json. The settings path is resolved at install time into
   `{MG_INSTALL_SETTINGS}`, so there is nothing to derive here.

Run:
```bash
python3 {MG_INSTALL_SCRIPTS_DIR}/merge-hook-entry.py \
  --settings {MG_INSTALL_SETTINGS} \
  --install-mode {MG_INSTALL_MODE} \
  --hook-rel-path .claude/cc-regression-test/hooks/intercept-trigger.py \
  --hook-abs-path {MG_INSTALL_HOOKS_DIR}/intercept-trigger.py \
  --matcher Bash
```

This is the same shared script the install step uses, so a sync run and an install now agree
on the command form and on what counts as a change. It prints ADDED, REWROTE or UNCHANGED.
Report whichever it prints -- in particular, do NOT report a fresh registration on UNCHANGED.
A REWROTE here means duplicates left by the previous scheme were collapsed: install time wrote
a relative command path while this command wrote an absolute one, so neither recognised the
other and every sync run appended one more entry.

Report:
```
--- Files synced ---

Synced hooks and scripts from source.
Hook config verified in settings.json.

Please restart Claude Code to pick up hook changes, then re-run:

  /mg:cc-regression-test
```

**Stop here — do not proceed to tests.**

**If "Continue stale":** Proceed to Step 1 with installed files as-is.

## Step 1: Hook Interception Test

This test validates that PreToolUse hooks fire correctly and the user sees an approval prompt.

**Instructions:**

1. Announce: `Running Test 1: Hook interception...`

2. Run this command:
```bash
python3 {MG_INSTALL_SCRIPTS_DIR}/trigger.py
```

3. **What should happen:** The installed PreToolUse hook (`intercept-trigger.py`) detects this command, sleeps 10 seconds, then returns `permissionDecision: "ask"`. This means:
   - You (Claude) will be prompted by the hook to ask the user for approval
   - There will be a ~10 second delay before the prompt appears
   - The user must approve the command for it to execute

4. **After execution:** Check the output of trigger.py.

5. **Record result:**
   - **PASS** if: The hook fired (you were asked to get user approval before running the command), AND the trigger.py output contains `REGRESSION_TEST_TRIGGER_OK`
   - **FAIL** if: The command ran without any hook-triggered approval prompt, OR trigger.py output is missing/wrong

Store the result for the summary in Step 3.

## Step 2: AskUserQuestion Interactive Selection Test

This test validates that AskUserQuestion presents options to the user and waits for actual selection (doesn't auto-approve).

**Instructions:**

1. Announce: `Running Test 2: AskUserQuestion interactive selection...`

2. Call AskUserQuestion with:
   - header: "Regression test"
   - question: "CC Regression Test: Select Option B to pass this test."
   - options:
     - label: "Option A (wrong)" — description: "Test FAILS if this is selected — indicates possible auto-approve bug"
     - label: "Option B (correct)" — description: "Select this to PASS the test — proves interactive selection works"
     - label: "Option C (wrong)" — description: "Test FAILS if this is selected"

3. **Record result:**
   - **PASS** if: User's answer is "Option B (correct)"
   - **FAIL** if: Any other answer. Report what was received and why it indicates a problem:
     - Option A selected → "AskUserQuestion may be auto-approving the first option"
     - Option C selected → "Wrong option selected"
     - Empty/missing → "AskUserQuestion may not be waiting for user input"

Store the result for the summary in Step 3.

## Step 3: Report Results

Output the test results summary:

**If all tests passed:**
```
══════════════════════════════════════
  CC Regression Test Results
══════════════════════════════════════

Test 1: Hook interception ............. PASS
  - Hook fired on trigger.py command
  - 10s evaluation delay observed
  - User approval prompt appeared
  - trigger.py output: REGRESSION_TEST_TRIGGER_OK

Test 2: AskUserQuestion ............... PASS
  - User selected Option B as instructed
  - Interactive selection confirmed working

All tests passed (2/2)
══════════════════════════════════════
```

**If any test failed**, include failure details:
```
Test N: [name] ........................ FAIL
  - Expected: [what should have happened]
  - Got: [what actually happened]
  - Implication: [what this failure means for CC functionality]
```

And end with:
```
Tests passed: N/2
Tests failed: N/2

Failed tests indicate Claude Code features that may be broken.
══════════════════════════════════════
```

</process>

<important_notes>
- The hook interception test depends on the PreToolUse hook being registered in settings.json. If the hook doesn't fire, first check that settings.json contains the hook entry.
- The 10-second sleep in the hook is intentional — it simulates an evaluation delay and makes the hook's presence obvious to the user.
- Do NOT skip the AskUserQuestion call or substitute it with a different mechanism. The entire point is to test that AskUserQuestion works correctly.
- If the sync check finds files out of sync and the user chooses to sync, you MUST stop after syncing. Hook changes require a Claude Code restart to take effect.
</important_notes>
