# Patch: statusline-context-cache

## Meta
- **Target:** hooks/gsd-statusline.js
- **Description:** Uses session directory for context cache/bridge files, adds edit guard badge, cleans up stale session dirs and legacy flat files.

## Modifications

### 1. Add session directory setup and migrate context cache

After `session` is extracted, set up a session directory and use it for all session-scoped temp files. Replaces flat `/tmp/claude-ctx-*` files with structured `/tmp/claude-code/mg-session-{session}/` directory.

**Anchor:**
```
    let remaining = data.context_window?.remaining_percentage;

    // Context window display (shows USED percentage scaled to usable context)
    // Claude Code reserves ~16.5% for autocompact buffer, so usable context
    // is 83.5% of the total window. We normalize to show 100% at that point.
    const AUTO_COMPACT_BUFFER_PCT = 16.5;
    let ctx = '';
    if (remaining != null) {
```

**Replace with:**
```
    // Session directory for all session-scoped temp files
    const sessionDir = session ? path.join('/tmp/claude-code', `mg-session-${session}`) : null;
    if (sessionDir) {
      try { fs.mkdirSync(sessionDir, { recursive: true }); } catch (e) {}
    }

    let remaining = data.context_window?.remaining_percentage;

    // Cache context window value to survive intermittent omissions from Claude Code
    const ctxCachePath = sessionDir ? path.join(sessionDir, 'context.json') : null;
    if (remaining != null && ctxCachePath) {
      try { fs.writeFileSync(ctxCachePath, JSON.stringify({ remaining, ts: Date.now() })); } catch (e) {}
    } else if (remaining == null && ctxCachePath) {
      try {
        const cached = JSON.parse(fs.readFileSync(ctxCachePath, 'utf8'));
        // Use cached value if less than 5 minutes old
        if (cached.remaining != null && (Date.now() - cached.ts) < 300000) remaining = cached.remaining;
      } catch (e) {}
    }

    // Cleanup stale session directories older than 1 week
    try {
      const ONE_WEEK = 7 * 24 * 60 * 60 * 1000;
      const now = Date.now();
      const ccDir = '/tmp/claude-code';
      if (fs.existsSync(ccDir)) {
        for (const d of fs.readdirSync(ccDir)) {
          if (d.startsWith('mg-session-')) {
            const dp = path.join(ccDir, d);
            try {
              if (now - fs.statSync(dp).mtimeMs > ONE_WEEK) fs.rmSync(dp, { recursive: true, force: true });
            } catch (e) {}
          }
        }
      }
    } catch (e) {}

    // One-time migration: clean up old flat files from /tmp/
    try {
      for (const f of fs.readdirSync(os.tmpdir())) {
        if (f.startsWith('claude-ctx-') && f.endsWith('.json')) {
          try { fs.unlinkSync(path.join(os.tmpdir(), f)); } catch (e) {}
        }
      }
    } catch (e) {}

    // Context window display (shows USED percentage scaled to usable context)
    // Claude Code reserves ~16.5% for autocompact buffer, so usable context
    // is 83.5% of the total window. We normalize to show 100% at that point.
    const AUTO_COMPACT_BUFFER_PCT = 16.5;
    let ctx = '';
    if (remaining != null) {
```

### 2. Update context bridge path

Replace the flat-file bridge path with the session directory path.

**Anchor:**
```
      if (session) {
        try {
          const bridgePath = path.join(os.tmpdir(), `claude-ctx-${session}.json`);
```

**Replace with:**
```
      if (sessionDir) {
        try {
          const bridgePath = path.join(sessionDir, 'context-bridge.json');
```
