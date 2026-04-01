---
name: edit_on
description: Re-enable Edit/Write tools (disable edit guard)
argument-hint: "[<instruction>]"
allowed-tools: Bash
---

Run the edit guard emitter to re-enable edits:

```
python3 {EMIT_EDIT_GUARD_SCRIPT} ON
```

Edit/Write tools are now enabled.

**Next action:** $ARGUMENTS

If the user provided instructions above, follow them. If no instructions were given (empty or blank), ask the user what they would like to do next — do not assume.
