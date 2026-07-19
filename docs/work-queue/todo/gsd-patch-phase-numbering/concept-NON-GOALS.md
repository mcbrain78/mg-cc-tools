# Non-Goals — GSD ROADMAP Writer Consolidation & Marker System

These are explicit scope exclusions for this concept. They were considered and deliberately ruled out. They must **persist across review rounds** — do not re-propose them in `mg:spec-improve` or downstream planning without a new decision that overturns the cited rationale.

- **Full render-from-model** (a `roadmap.json` / expanded-frontmatter source of truth that regenerates all ROADMAP prose). Ruled out in D1: it fights GSD upstream's own direct-`.md` writers — notably `complete-milestone`, which deletes and recreates the file — on every fork re-sync; high blast radius against a tracked fork.

- **Percent unification / phase-based percent.** Ruled out in D4: `percent` is plan-based in three computations (`state.cjs:344`, `roadmap.cjs:212`, `commands.cjs:416`); an unplanned (0-plan) phase doesn't change it, and premature-close is guarded by `disk_status`, not percent. Unifying to phase-based would be a three-site breaking change that makes `/gsd:progress` and `state json` disagree and churns the value on every `update-progress`. **Do not "make percent consistent."**

- **Auto-heal / heuristic marker auto-detection on write.** Ruled out in D2: three checklist dialects coexist in real files and defeat bold/non-bold detection; the ROADMAP is LLM-authored and rewritten at milestone boundaries, so per-write auto-detection turns any miss into per-command corruption. Markers are **authored** (templates + workflow), validated on write, and migrated once under supervision — never inferred at write time.

- **Legacy-regex fallback path.** Ruled out in D3: writers hard-require markers. Do not add a "fall back to the old behavior if unmarked" branch — that keeps the fragile path alive and defeats the consolidation.

- **Fixing the 8 pre-existing test failures.** They were resolved separately (the suite is now green). Not part of this concept.

- **Markers in archived `milestones/*.md`.** Those are frozen byte-snapshots (`milestone.cjs:139`); leaving them untouched is correct.

- **Migrating external / non-controlled GSD installs.** Only the ~4 controlled projects are migrated via the one-shot `roadmap ensure-markers` pass.
