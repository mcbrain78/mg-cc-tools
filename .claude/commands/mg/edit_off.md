---
name: edit_off
description: Block Edit/Write tools (enable edit guard)
allowed-tools: Bash
---

Run the edit guard emitter to block edits:

```
python3 /home/mcbrain/mg_projects/mg-cc-tools/.claude/permission-hooks/scripts/emit-edit-guard.py OFF
```

Edit/Write tools are now blocked. You are in discussion mode — focus on analysis, design, and conversation. Do not attempt to edit or write files until the user runs `/mg:edit_on`.
