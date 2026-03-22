---
phase: 13
slug: auto-doc-script
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-22
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via pyproject.toml) |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `python3 -m pytest auto-doc/scripts/tests/ --tb=short -q --no-header` |
| **Full suite command** | `python3 -m pytest --tb=short -q --no-header` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run smoke checks (file existence, grep for key content)
- **After every plan wave:** Run full install.sh integration test against temp directory
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | TBD | smoke | `head -5 auto-doc/commands/auto-doc-script.md` | Wave 0 | ⬜ pending |
| 13-01-02 | 01 | 1 | TBD | smoke | `grep -c 'PURPOSE:' auto-doc/references/templates/SCRIPT_README.template.md` | Wave 0 | ⬜ pending |
| 13-01-03 | 01 | 1 | TBD | smoke | `grep 'auto-doc-script' auto-doc/install.sh` | Wave 0 | ⬜ pending |
| 13-01-04 | 01 | 1 | TBD | integration | `bash auto-doc/install.sh --target /tmp/test-install/.claude && test -f /tmp/test-install/.claude/commands/mg/auto-doc-script.md` | Wave 0 | ⬜ pending |
| 13-01-05 | 01 | 1 | TBD | integration | `test -f /tmp/test-install/.claude/auto-doc/references/templates/SCRIPT_README.template.md` | Wave 0 | ⬜ pending |
| 13-01-06 | 01 | 1 | TBD | integration | `grep -v '{TEMPLATES_DIR}' /tmp/test-install/.claude/commands/mg/auto-doc-script.md` | Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

None — no test files needed. All validation is via smoke/integration checks against the delivered files themselves. The existing test infrastructure (`python3 -m pytest`) covers the broader auto-doc tool; this phase adds no Python code.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Command generates useful README for single script | TBD | LLM output quality — no deterministic test possible | Run `/mg:auto-doc-script <path>` on a sample script, review output |
| Command generates useful README for tool directory | TBD | LLM output quality — no deterministic test possible | Run `/mg:auto-doc-script <dir>` on a multi-file tool, review output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
