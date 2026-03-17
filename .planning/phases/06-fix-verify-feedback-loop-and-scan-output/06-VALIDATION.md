---
phase: 6
slug: fix-verify-feedback-loop-and-scan-output
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-17
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via `python3 -m pytest`) |
| **Config file** | `pyproject.toml` (minimal -- name, version, dev deps) |
| **Quick run command** | `python3 -m pytest create-docs/scripts/tests/ -x` |
| **Full suite command** | `python3 -m pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest create-docs/scripts/tests/ -x`
- **After every plan wave:** Run `python3 -m pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | add-verify-finding | unit | `python3 -m pytest create-docs/scripts/tests/test_add_verify_finding.py -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | add-verify-finding reject | unit | `python3 -m pytest create-docs/scripts/tests/test_add_verify_finding.py -x` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | list-verify-findings filter | unit | `python3 -m pytest create-docs/scripts/tests/test_list_verify_findings.py -x` | ❌ W0 | ⬜ pending |
| 06-01-04 | 01 | 1 | list-verify-findings summary | unit | `python3 -m pytest create-docs/scripts/tests/test_list_verify_findings.py -x` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | write-scan-output validate | unit | `python3 -m pytest create-docs/scripts/tests/test_write_scan_output.py -x` | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 1 | write-scan-output reject | unit | `python3 -m pytest create-docs/scripts/tests/test_write_scan_output.py -x` | ❌ W0 | ⬜ pending |
| 06-xx-xx | xx | 2 | install.sh includes scripts | smoke | manual -- `./create-docs/install.sh --project /tmp/test-install` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `create-docs/scripts/tests/test_add_verify_finding.py` — stubs for add-verify-finding validation
- [ ] `create-docs/scripts/tests/test_list_verify_findings.py` — stubs for list-verify-findings filtering/summary
- [ ] `create-docs/scripts/tests/test_write_scan_output.py` — stubs for write-scan-output validation

*Existing infrastructure (pytest, pyproject.toml, conftest patterns) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| install.sh includes new scripts | install coverage | Requires shell execution + file system inspection | Run `./create-docs/install.sh --project /tmp/test-install` and verify scripts exist in `.claude/create-docs/scripts/` |
| Verifier agent 2-step workflow | agent rewrite | LLM prompt behavior, not deterministic | Run `/mg:create-docs-verify` on road-runner and verify findings JSON + report are both produced |
| Generate 3-tier approval flow | feedback loop | Interactive UX with AskUserQuestion | Run `/mg:create-docs-generate` in update mode with findings present and verify all 3 tiers appear |
| Router findings-aware state | router update | End-to-end pipeline state detection | Run `/mg:create-docs` after verify has produced findings and verify router suggests re-running generate |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
