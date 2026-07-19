# Non-Goals — GSD Fork as Single Source, Deployed via mg:install

Explicit scope exclusions that must persist across review rounds. Do **not** re-propose these in `mg:spec-improve` or later refinement — they were considered and deliberately excluded.

- **Wrapping or using GSD's `install.js`.** It bakes in the patch-backup/reapply ceremony being retired, requires a build step for hooks (`hooks/dist/` empty + git-ignored), only targets the cwd for local installs, and writes a nondeterministic manifest timestamp. The concept commits to a purpose-built installer (D3). `install.js` may be consulted as a *reference* only.

- **Symlink or global-install consumption model.** Per-project, git-tracked real copies are retained (D4). Do not re-propose `~/.claude/get-shit-done` symlinks or per-project symlinks to the fork.

- **Folding `mg-gsd-wrappers` into the fork.** The `/mg:` GSD command wrappers stay a separate tool (D6), to keep this change's scope contained.

- **Replicating GSD's local-patch backup/reapply.** No `gsd-local-patches/`, no manifest backup, no `/gsd:reapply-patches` — that mechanism is the retired ceremony, not a feature to port.

- **GSD Bug 8 (`add-phase` under-writes milestone surfaces).** A separate fix, excluded at scope selection. It belongs in its own concept, not here — though it will be *implemented in the fork* under this concept's dev model.
