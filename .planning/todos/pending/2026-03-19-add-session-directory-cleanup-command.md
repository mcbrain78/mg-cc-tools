---
created: 2026-03-19T09:31:15.564Z
title: Add session directory cleanup command
area: tooling
files: []
---

## Problem

Claude Code sessions generate large JSON files in project `temp/` or session directories. Over time these accumulate and consume disk space. There is no built-in way to prune old session data while retaining recent sessions.

The user wants a command that:
- Allows selecting how many days of session data to retain (e.g., keep last 7 days)
- Removes sessions older than the retention period
- Never deletes data without user confirmation
- Could be a standalone script or an `/mg:` slash command

## Solution

Build a cleanup utility (likely a Python script or slash command) that:
1. Scans the session directory for `.json` files
2. Parses timestamps from filenames or file metadata
3. Presents sessions grouped by age (e.g., "3 sessions from 7+ days ago, 12 from 3-7 days")
4. Asks the user for retention period (default: 7 days)
5. Removes files older than the retention cutoff
6. Reports what was removed and space reclaimed
