---
name: edit-off
description: Block Edit/Write tools (enable edit guard)
allowed-tools: Bash
---

**IMPORTANT: Run these two commands as SEPARATE sequential tool calls. Do NOT combine them in a single parallel message — the second call's hook must see the first call's output in the transcript.**

Step 1 — Run the edit guard emitter to block edits:

```
python3 /home/mcbrain/mg_projects/mg-cc-tools/.claude/permission-hooks/scripts/emit-edit-guard.py OFF
```

Step 2 — After step 1 completes, trigger a statusline bridge update:

```
echo "Statusline Update: EDITS OFF"
```

Edit/Write tools are now blocked. You are in discussion mode — focus on analysis, design, and conversation. Do not attempt to edit or write files until the user runs `/mg:edit-on`.
