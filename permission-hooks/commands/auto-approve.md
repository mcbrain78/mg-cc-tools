---
name: auto-approve
description: Refresh permission auto-approval TTL (30 min)
allowed-tools: Bash
---

Run this command to refresh the auto-approval session:

```
python3 {MG_INSTALL_EMIT_CONTEXT_SCRIPT} AUTO-APPROVE 2>&1 || true
```

Auto-approval TTL has been refreshed. Permission prompts will be suppressed for the next 30 minutes.
