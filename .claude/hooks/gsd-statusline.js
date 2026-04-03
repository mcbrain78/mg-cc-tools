#!/usr/bin/env node
// Claude Code Statusline - GSD Edition
// Shows: model | current task | directory | context usage

const fs = require('fs');
const path = require('path');
const os = require('os');

// Read JSON from stdin
let input = '';
// Timeout guard: if stdin doesn't close within 3s (e.g. pipe issues on
// Windows/Git Bash), exit silently instead of hanging. See #775.
const stdinTimeout = setTimeout(() => process.exit(0), 3000);
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  clearTimeout(stdinTimeout);
  try {
    const data = JSON.parse(input);
    const model = data.model?.display_name || 'Claude';
    const dir = data.workspace?.current_dir || process.cwd();
    const session = data.session_id || '';
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
      // Normalize: subtract buffer from remaining, scale to usable range
      const usableRemaining = Math.max(0, ((remaining - AUTO_COMPACT_BUFFER_PCT) / (100 - AUTO_COMPACT_BUFFER_PCT)) * 100);
      const used = Math.max(0, Math.min(100, Math.round(100 - usableRemaining)));

      // Write context metrics to bridge file for the context-monitor PostToolUse hook.
      // The monitor reads this file to inject agent-facing warnings when context is low.
      if (sessionDir) {
        try {
          const bridgePath = path.join(sessionDir, 'context-bridge.json');
          const bridgeData = JSON.stringify({
            session_id: session,
            remaining_percentage: remaining,
            used_pct: used,
            timestamp: Math.floor(Date.now() / 1000)
          });
          fs.writeFileSync(bridgePath, bridgeData);
        } catch (e) {
          // Silent fail -- bridge is best-effort, don't break statusline
        }
      }

      // Build progress bar (10 segments)
      const filled = Math.floor(used / 10);
      const bar = '█'.repeat(filled) + '░'.repeat(10 - filled);

      // Color based on usable context thresholds
      if (used < 50) {
        ctx = ` \x1b[32m${bar} ${used}%\x1b[0m`;
      } else if (used < 65) {
        ctx = ` \x1b[33m${bar} ${used}%\x1b[0m`;
      } else if (used < 80) {
        ctx = ` \x1b[38;5;208m${bar} ${used}%\x1b[0m`;
      } else {
        ctx = ` \x1b[5;31m💀 ${bar} ${used}%\x1b[0m`;
      }
    }

    // Current task from todos
    let task = '';
    const homeDir = os.homedir();
    // Respect CLAUDE_CONFIG_DIR for custom config directory setups (#870)
    const claudeDir = process.env.CLAUDE_CONFIG_DIR || path.join(homeDir, '.claude');
    const todosDir = path.join(claudeDir, 'todos');
    if (session && fs.existsSync(todosDir)) {
      try {
        const files = fs.readdirSync(todosDir)
          .filter(f => f.startsWith(session) && f.includes('-agent-') && f.endsWith('.json'))
          .map(f => ({ name: f, mtime: fs.statSync(path.join(todosDir, f)).mtime }))
          .sort((a, b) => b.mtime - a.mtime);

        if (files.length > 0) {
          try {
            const todos = JSON.parse(fs.readFileSync(path.join(todosDir, files[0].name), 'utf8'));
            const inProgress = todos.find(t => t.status === 'in_progress');
            if (inProgress) task = inProgress.activeForm || '';
          } catch (e) {}
        }
      } catch (e) {
        // Silently fail on file system errors - don't break statusline
      }
    }

    // GSD update available?
    let gsdUpdate = '';
    const cacheFile = path.join(claudeDir, 'cache', 'gsd-update-check.json');
    if (fs.existsSync(cacheFile)) {
      try {
        const cache = JSON.parse(fs.readFileSync(cacheFile, 'utf8'));
        if (cache.update_available) {
          gsdUpdate = '\x1b[33m⬆ /gsd:update\x1b[0m │ ';
        }
      } catch (e) {}
    }

    // Edit guard badge (reads bridge file written by permission-guard.py)
    let editBadge = '';
    if (sessionDir) {
      try {
        const guard = JSON.parse(fs.readFileSync(path.join(sessionDir, 'edit-guard.json'), 'utf8'));
        if (guard.state === 'OFF') {
          editBadge = '\x1b[31m\u{1F512} EDITS OFF\x1b[0m \u2502 ';
        } else {
          editBadge = '\x1b[2m\u270F\uFE0F EDITS ON\x1b[0m \u2502 ';
        }
      } catch (e) {
        // No bridge file yet — default to EDITS ON if permission-hooks are installed
        const hookPath = path.join(dir, '.claude', 'permission-hooks', 'hooks', 'permission-guard.py');
        if (fs.existsSync(hookPath)) {
          editBadge = '\x1b[2m\u270F\uFE0F EDITS ON\x1b[0m \u2502 ';
        }
      }
    }

    // Output
    const dirname = path.basename(dir);
    if (task) {
      process.stdout.write(`${editBadge}${gsdUpdate}\x1b[2m${model}\x1b[0m │ \x1b[1m${task}\x1b[0m │ \x1b[2m${dirname}\x1b[0m${ctx}`);
    } else {
      process.stdout.write(`${editBadge}${gsdUpdate}\x1b[2m${model}\x1b[0m │ \x1b[2m${dirname}\x1b[0m${ctx}`);
    }
  } catch (e) {
    // Silent fail - don't break statusline on parse errors
  }
});
