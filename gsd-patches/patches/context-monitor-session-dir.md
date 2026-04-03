# Patch: context-monitor-session-dir

## Meta
- **Target:** hooks/gsd-context-monitor.js
- **Description:** Migrates context monitor from flat /tmp/ files to session directory structure. Updates metrics path and warned path to use /tmp/claude-code/mg-session-{session}/.

## Modifications

### 1. Update path comment

**Anchor:**
```
// 1. The statusline hook writes metrics to /tmp/claude-ctx-{session_id}.json
```

**Replace with:**
```
// 1. The statusline hook writes metrics to /tmp/claude-code/mg-session-{session_id}/context-bridge.json
```

### 2. Replace metrics path with session directory

Replace flat tmpDir paths with session directory structure. Remove unused `os` require.

**Anchor:**
```
const fs = require('fs');
const os = require('os');
const path = require('path');
```

**Replace with:**
```
const fs = require('fs');
const path = require('path');
```

**Anchor:**
```
    const tmpDir = os.tmpdir();
    const metricsPath = path.join(tmpDir, `claude-ctx-${sessionId}.json`);
```

**Replace with:**
```
    const sessionDir = path.join('/tmp/claude-code', `mg-session-${sessionId}`);
    const metricsPath = path.join(sessionDir, 'context-bridge.json');
```

### 3. Replace warned path with session directory

**Anchor:**
```
    const warnPath = path.join(tmpDir, `claude-ctx-${sessionId}-warned.json`);
```

**Replace with:**
```
    const warnPath = path.join(sessionDir, 'context-warned.json');
```
