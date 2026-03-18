# Patch: execute-phase-pyright-gate

## Meta
- **Target:** get-shit-done/workflows/execute-phase.md
- **Description:** Adds a pyright type-check gate after all waves complete, before the verifier runs. Errors are auto-fixed by a subagent; persistent failures are reported as warnings.

## Modifications

### 1. Add pyright gate step after aggregate_results

Inserts a new `<step name="typecheck_gate">` between `aggregate_results` and `close_parent_artifacts`. The gate runs pyright, and if errors are found, spawns an executor subagent to fix them. If errors persist after the fix attempt, they are reported as warnings but do not block phase completion.

**Anchor:**
```
<step name="close_parent_artifacts">
**For decimal/polish phases only (X.Y pattern):** Close the feedback loop by resolving parent UAT and debug artifacts.
```

**Replace with:**
```
<step name="typecheck_gate">
Run pyright type-check gate after all plans complete but before verification.

**Prerequisites:** Only run if project has a `pyrightconfig.json` at repo root.

```bash
if [ -f pyrightconfig.json ]; then
  PYRIGHT_ERRORS=$(source .venv/bin/activate 2>/dev/null; pyright --outputjson 2>/dev/null | python3 -c "
import sys, json
d = json.load(sys.stdin)
errs = d.get('generalDiagnostics', [])
print(len(errs))
for e in errs[:20]:
    f = e.get('file','?'); r = e.get('range',{}).get('start',{}); ln = r.get('line',0)
    print(f'{f}:{ln}: {e.get(\"message\",\"\")}')
" 2>/dev/null)
  ERROR_COUNT=$(echo "$PYRIGHT_ERRORS" | head -1)
fi
```

**If `pyrightconfig.json` not found or `ERROR_COUNT` is 0:** Log `Pyright: clean` and proceed to next step.

**If errors found:**

1. Report:
   ```
   ## Pyright: {ERROR_COUNT} type error(s) found

   {Error details from PYRIGHT_ERRORS, lines 2+}
   ```

2. Spawn a fix agent:
   ```
   Task(
     subagent_type="gsd-executor",
     model="{executor_model}",
     prompt="
       <objective>
       Fix {ERROR_COUNT} pyright type errors introduced during phase {phase_number}.
       </objective>

       <instructions>
       1. Run: source .venv/bin/activate && pyright
       2. Fix each error with minimal, targeted changes (correct types, add imports, narrow types).
       3. Do NOT refactor unrelated code or add unnecessary type: ignore comments.
       4. After fixing, re-run pyright to confirm zero errors.
       5. Commit all fixes in a single commit:
          fix({phase_number}): resolve pyright type errors
       </instructions>

       <files_to_read>
       - ./CLAUDE.md (Project instructions)
       - ./pyrightconfig.json (Type check configuration)
       </files_to_read>

       <success_criteria>
       - [ ] pyright reports 0 errors
       - [ ] All fixes committed
       </success_criteria>
     "
   )
   ```

3. After fix agent completes, re-run pyright to verify:
   ```bash
   REMAINING=$(source .venv/bin/activate 2>/dev/null; pyright --outputjson 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['summary']['errorCount'])" 2>/dev/null || echo "0")
   ```

4. **If 0 remaining:** `Pyright: {ERROR_COUNT} errors fixed` — proceed.
5. **If errors persist:** Report as warning but do NOT block:
   ```
   ## ⚠ Pyright: {REMAINING} type error(s) remain after auto-fix

   These will be caught by CI on PR. Consider fixing manually.
   ```
   Proceed to next step.
</step>

<step name="close_parent_artifacts">
**For decimal/polish phases only (X.Y pattern):** Close the feedback loop by resolving parent UAT and debug artifacts.
```
