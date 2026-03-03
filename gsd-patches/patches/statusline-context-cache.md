# Patch: statusline-context-cache

## Meta
- **Target:** hooks/gsd-statusline.js
- **Description:** Caches last known context window value to temp file; falls back to cached value when Claude Code intermittently omits context_window data from statusline input. Cleans up stale cache files older than 1 week.

## Modifications

### 1. Add context window cache fallback

When `remaining_percentage` is null (Claude Code intermittently omits it), read the last known value from a session-scoped temp file. When it is present, cache it for future fallback. This ensures the context bar stays visible throughout the session.

**Anchor:**
```
    const remaining = data.context_window?.remaining_percentage;

    // Context window display (shows USED percentage scaled to 80% limit)
    // Claude Code enforces an 80% context limit, so we scale to show 100% at that point
    let ctx = '';
    if (remaining != null) {
```

**Replace with:**
```
    let remaining = data.context_window?.remaining_percentage;

    // Cache context window value to survive intermittent omissions from Claude Code
    const ctxCachePath = session ? path.join(os.tmpdir(), `claude-ctx-cache-${session}.json`) : null;
    if (remaining != null && ctxCachePath) {
      try { fs.writeFileSync(ctxCachePath, JSON.stringify({ remaining, ts: Date.now() })); } catch (e) {}
    } else if (remaining == null && ctxCachePath) {
      try {
        const cached = JSON.parse(fs.readFileSync(ctxCachePath, 'utf8'));
        // Use cached value if less than 5 minutes old
        if (cached.remaining != null && (Date.now() - cached.ts) < 300000) remaining = cached.remaining;
      } catch (e) {}
    }

    // Cleanup stale cache and bridge files older than 1 week
    try {
      const ONE_WEEK = 7 * 24 * 60 * 60 * 1000;
      const now = Date.now();
      for (const f of fs.readdirSync(os.tmpdir())) {
        if (f.startsWith('claude-ctx-') && f.endsWith('.json')) {
          const fp = path.join(os.tmpdir(), f);
          try {
            if (now - fs.statSync(fp).mtimeMs > ONE_WEEK) fs.unlinkSync(fp);
          } catch (e) {}
        }
      }
    } catch (e) {}

    // Context window display (shows USED percentage scaled to 80% limit)
    // Claude Code enforces an 80% context limit, so we scale to show 100% at that point
    let ctx = '';
    if (remaining != null) {
```
