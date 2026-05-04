# Roadmap: mg-cc-tools

## Milestones

- ✅ **v1.1 milestone** — Phases 1-24 (shipped 2026-05-04) — see `milestones/v1.1-ROADMAP.md`

## Phases

<details>
<summary>✅ v1.1 milestone (Phases 1-24) — SHIPPED 2026-05-04</summary>

- [x] Phase 1: Foundation & Infrastructure (4/4 plans) — completed 2026-03-16
- [x] Phase 2: Templates & Agent Definitions (4/4 plans) — completed 2026-03-16
- [x] Phase 3: Scan Pipeline (2/2 plans) — completed 2026-03-16
- [x] Phase 4: Generate Pipeline (2/2 plans) — completed 2026-03-16
- [x] Phase 5: Verify, Notes Command & Router (2/2 plans) — completed 2026-03-17 *(work largely removed in stabilization)*
- [x] Phase 6: Fix Verify Feedback Loop & Scan Output (4/4 plans) — completed 2026-03-17
- [x] Phase 7: Install Command (4/5 plans, 07-05 SUMMARY missing but user-verified) — completed 2026-03-18
- [x] Phase 8: Install Tool Improvements (5/5 plans) — completed 2026-03-19
- [x] Phase 9: Session Analyzer → renamed to Transcript in stabilization (4/4 plans) — completed 2026-03-20
- [x] Phase 10: Renderer for Install Command (2/2 plans) — completed 2026-03-20
- [x] Phase 11: Add Tooling to Install Command (3/3 plans) — completed 2026-03-20
- [x] Phase 12: Auto Doc Rename & Cleanup (2/2 plans) — completed 2026-03-22
- [x] Phase 13: Auto Doc Script Command (1/1 plan) — completed 2026-03-22 *(removed in stabilization)*
- [x] Phase 14: Auto Doc Reference Manifest (3/3 plans) — completed 2026-03-22
- [x] Phase 15: Auto Doc End-User Quality (3/3 plans) — completed 2026-03-22
- [x] Phase 16: Auto Doc Incremental Scan (2/2 plans) — completed 2026-03-23
- [x] Phase 17: Auto Doc Generate Docs Improvements (2/2 plans) — completed 2026-03-24
- [x] Phase 18: Recursive Section XML Core (2/2 plans) — completed 2026-04-01
- [x] Phase 19: Nested Write-Section & Assembly (2/2 plans) — completed 2026-04-01
- [x] Phase 20: Recursive Pipeline Script Updates (2/2 plans) — completed 2026-04-01
- [x] Phase 21: Writer Agent Per-Heading Emission (2/2 plans) — completed 2026-04-01
- [x] Phase 22: Heading Iterator Script (1/1 plan) — completed 2026-04-02
- [x] Phase 23: Template Refiner Pipeline (2/2 plans) — completed 2026-04-02
- [x] Phase 24: Writer Orient-Write Integration (3/3 plans) — completed 2026-04-02

</details>

### 📋 v1.2 (Planned)

No phases planned yet. Run `/gsd:new-milestone` to start v1.2.

Cleanup candidates carried from v1.1 audit:
- `install/install.sh` missing `update-manifest` self-call (1-line fix)
- Delete orphaned `auto-doc/references/templates/SCRIPT_README.template.md`
- Revise misleading "That's verify's job" phrasing in `auto-doc/commands/auto-doc-auditv2.md`
- Add `tool.toml` + `install.sh` to `export-session/` for installer discovery
- Nyquist compliance for 23 phases marked `nyquist_compliant: false`

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation & Infrastructure | v1.1 | 4/4 | Complete | 2026-03-16 |
| 2. Templates & Agent Definitions | v1.1 | 4/4 | Complete | 2026-03-16 |
| 3. Scan Pipeline | v1.1 | 2/2 | Complete | 2026-03-16 |
| 4. Generate Pipeline | v1.1 | 2/2 | Complete | 2026-03-16 |
| 5. Verify, Notes Command & Router | v1.1 | 2/2 | Complete (mostly removed) | 2026-03-17 |
| 6. Fix Verify Feedback Loop | v1.1 | 4/4 | Complete | 2026-03-17 |
| 7. Install Command | v1.1 | 4/5 | Complete (user-verified) | 2026-03-18 |
| 8. Install Tool Improvements | v1.1 | 5/5 | Complete | 2026-03-19 |
| 9. Session Analyzer (→ Transcript) | v1.1 | 4/4 | Complete | 2026-03-20 |
| 10. Renderer for Install Command | v1.1 | 2/2 | Complete | 2026-03-20 |
| 11. Add Tooling to Install Command | v1.1 | 3/3 | Complete | 2026-03-20 |
| 12. Auto Doc Rename & Cleanup | v1.1 | 2/2 | Complete | 2026-03-22 |
| 13. Auto Doc Script | v1.1 | 1/1 | Complete (removed in stabilization) | 2026-03-22 |
| 14. Auto Doc Reference Manifest | v1.1 | 3/3 | Complete | 2026-03-22 |
| 15. Auto Doc End-User Quality | v1.1 | 3/3 | Complete | 2026-03-22 |
| 16. Auto Doc Incremental Scan | v1.1 | 2/2 | Complete | 2026-03-23 |
| 17. Auto Doc Generate Docs Improvements | v1.1 | 2/2 | Complete | 2026-03-24 |
| 18. Recursive Section XML Core | v1.1 | 2/2 | Complete | 2026-04-01 |
| 19. Nested Write-Section & Assembly | v1.1 | 2/2 | Complete | 2026-04-01 |
| 20. Recursive Pipeline Script Updates | v1.1 | 2/2 | Complete | 2026-04-01 |
| 21. Writer Agent Per-Heading Emission | v1.1 | 2/2 | Complete | 2026-04-01 |
| 22. Heading Iterator Script | v1.1 | 1/1 | Complete | 2026-04-02 |
| 23. Template Refiner Pipeline | v1.1 | 2/2 | Complete | 2026-04-02 |
| 24. Writer Orient-Write Integration | v1.1 | 3/3 | Complete | 2026-04-02 |

---
*Last updated: 2026-05-04 after v1.1 milestone completion. Full v1.1 phase details: `milestones/v1.1-ROADMAP.md`. v1.1 requirements (with 15 removed + 1 superseded): `milestones/v1.1-REQUIREMENTS.md`.*
