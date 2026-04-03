---
name: edit_off
description: Block Edit/Write tools (enable edit guard)
allowed-tools: Bash
---

Run the edit guard emitter to block edits:

```
python3 {EMIT_EDIT_GUARD_SCRIPT} OFF
```

Edit/Write tools are now blocked. You are in discussion mode — focus on analysis, design, and conversation. Do not attempt to edit or write files until the user runs `/mg:edit_on`.
