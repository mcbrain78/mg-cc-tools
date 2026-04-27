---
name: edit-on
description: Re-enable Edit/Write tools (disable edit guard)
argument-hint: "[<instruction>]"
allowed-tools: Bash
---

**IMPORTANT: Run these two commands as SEPARATE sequential tool calls. Do NOT combine them in a single parallel message — the second call's hook must see the first call's output in the transcript.**

Step 1 — Run the edit guard emitter to re-enable edits:

```
python3 "{MG_INSTALL_EMIT_EDIT_GUARD_SCRIPT}" ON
```

Step 2 — After step 1 completes, trigger a statusline bridge update:

```
echo "Statusline Update: EDITS ON"
```

Edit/Write tools are now enabled.

**Next action:** $ARGUMENTS

If the user provided instructions above, follow them. If no instructions were given (empty or blank), ask the user what they would like to do next — do not assume.
