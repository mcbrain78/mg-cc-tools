# Patch: statusline-edit-guard

## Meta
- **Target:** hooks/gsd-statusline.js
- **Description:** Adds edit guard badge to statusline. Reads bridge file written by permission-guard.py and shows lock/pencil icon with state. Requires statusline-context-cache patch (for sessionDir).

## Modifications

### 1. Add edit guard badge before output

Read the edit guard bridge file and prepend a badge to the statusline output. Shows red lock when edits are OFF, dim pencil when ON. No badge if bridge file doesn't exist (permission-hooks not installed).

**Anchor:**
```
    // Output
    const dirname = path.basename(dir);
    if (task) {
      process.stdout.write(`${gsdUpdate}\x1b[2m${model}\x1b[0m │ \x1b[1m${task}\x1b[0m │ \x1b[2m${dirname}\x1b[0m${ctx}`);
    } else {
      process.stdout.write(`${gsdUpdate}\x1b[2m${model}\x1b[0m │ \x1b[2m${dirname}\x1b[0m${ctx}`);
    }
```

**Replace with:**
```
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
        // No bridge file yet (permission-hooks not active) — show nothing
      }
    }

    // Output
    const dirname = path.basename(dir);
    if (task) {
      process.stdout.write(`${editBadge}${gsdUpdate}\x1b[2m${model}\x1b[0m │ \x1b[1m${task}\x1b[0m │ \x1b[2m${dirname}\x1b[0m${ctx}`);
    } else {
      process.stdout.write(`${editBadge}${gsdUpdate}\x1b[2m${model}\x1b[0m │ \x1b[2m${dirname}\x1b[0m${ctx}`);
    }
```
