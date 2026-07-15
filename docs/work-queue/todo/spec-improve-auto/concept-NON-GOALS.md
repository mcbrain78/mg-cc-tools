# Non-Goals for concept.md

- No changes to mg:spec-improve review behavior — it remains the manual path by design; it inherits only the shared improve_files.py hardening plus the minimal Setup resume branch that hardening forces (guard failure → paths → resume or --fresh).
- No concept-spec-template changes — specifically no scope↔verification link syntax to make coverage checking deterministic.
- No spec-create-milestone consumption of concept-IMPLEMENTER-NOTES.md — the sidecar is advisory for the implementer in this version.
- No divergence detection for hand-edits to the original during discussion pauses — same exposure exists in spec-improve today.
- No token budget mechanism — cost is accepted at this leverage point; the round cap is the only brake.
- No analysis tooling for run history — history/ is raw material; hindsight analysis (gate tuning, churn review) stays ad-hoc.
