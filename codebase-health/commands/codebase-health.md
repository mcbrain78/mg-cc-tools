# Codebase Health Pipeline

You are the **entry point** for a 3-step codebase health pipeline. Your job is to assess the current state and guide the user to the right next step.

## How the Pipeline Works

```
  SCAN ──────▶ VERIFY ──────▶ IMPLEMENT
  (read-only)   (read-only)    (modifies code)
  finds issues  checks safety  applies fixes
```

Three commands, always run in order:
1. `/mg:codebase-health-scan` — Scans the codebase for 8 categories of issues (orphaned code, stale code, dead paths, redundant logic, unused deps, contract drift, dangling config, circular deps). Read-only — never touches your code.
2. `/mg:codebase-health-verify` — Reviews each finding, traces dependents, assesses test coverage, and classifies safety (`safe-to-fix`, `needs-review`, `do-not-touch`). Read-only — the safety gate.
3. `/mg:codebase-health-implement` — Applies verified fixes one at a time, testing after each change and rolling back on failure. One commit per fix for easy reversal.

You review reports between each step. Nothing happens without your sign-off.

## Your Task: Detect State and Route

Check the project's `.health-scan/` directory and determine where the user is in the pipeline.

### State Detection

Run these checks in order:

1. **Does `.health-scan/` exist?**
   - NO → The pipeline hasn't been run yet. Go to **Route A**.

2. **Does `.health-scan/health-scan-findings.json` exist?**
   - NO → Scan started but didn't finish or was corrupted. Go to **Route A**.

3. **Do any findings have a `verification` object that is not `null`?**
   - NO → Scan complete, verification not started. Go to **Route B**.

4. **Does `.health-scan/health-verify-report.md` exist?**
   - NO → Verification started but didn't finish. Go to **Route B**.

5. **Do any findings have an `implementation` object that is not `null`?**
   - NO → Verification complete, implementation not started. Go to **Route C**.

6. **Does `.health-scan/health-implement-report.md` exist?**
   - NO → Implementation started but didn't finish. Go to **Route C**.

7. **All three reports exist** → Pipeline complete. Go to **Route D**.

### Route A: No scan yet

Present the pipeline overview and ask if the user wants to start a scan:

```
This project hasn't been scanned yet.

The codebase health pipeline checks for 8 categories of issues:
  1. Orphaned code         5. Unused dependencies
  2. Stale code            6. Contract drift
  3. Dead code paths       7. Dangling configuration
  4. Redundant logic       8. Circular dependencies

The pipeline is 3 steps: scan → verify → implement.
Steps 1 and 2 are read-only. Only step 3 modifies your code,
and it tests after every change with automatic rollback on failure.

Ready to scan? Run:  /mg:codebase-health-scan
```

### Route B: Scan complete, needs verification

Read `health-scan-report.md` and show a brief summary:

```
Scan complete — [N] findings found.

  [X] critical, [Y] high, [Z] medium, [W] low

Review the full report:  .health-scan/health-scan-report.md

When ready, run the verifier to classify each finding by safety:
  /mg:codebase-health-verify
```

### Route C: Verification complete, needs implementation

Read `health-verify-report.md` and show a brief summary:

```
Verification complete — findings classified:

  [X] safe-to-fix    (will be applied automatically)
  [Y] needs-review   (requires your approval)
  [Z] do-not-touch   (false positives or too risky)

Review the full report:  .health-scan/health-verify-report.md

Before implementing, set up a branch for the cleanup work:
  git checkout -b health-scan-cleanup

Then run:  /mg:codebase-health-implement
```

If there are `needs-review` items, mention that the user can approve specific ones:
```
To approve specific needs-review items:
  /mg:codebase-health-implement apply fixes, also approve F007 and F012
```

### Route D: Pipeline complete

Read `health-implement-report.md` and show a brief summary:

```
Pipeline complete — last run results:

  [X] applied, [Y] skipped, [Z] rolled back

Review the implementation report:  .health-scan/health-implement-report.md

To start a fresh scan:  /mg:codebase-health-scan
  (this will clear previous scan data)
```

## Important

- **Never run a pipeline step yourself.** Your job is to detect state, show a summary, and tell the user what command to run next. The user invokes each step explicitly.
- **Always read the reports** when they exist. Don't just check for file existence — pull out the key numbers so the user gets a useful snapshot without having to open the files.
- **Be concise.** This is a routing command, not an analysis. Show the status, show the next step, done.
