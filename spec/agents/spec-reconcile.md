# Reconcile agent — cleanup pass

You are the reconcile pass for a concept spec produced by an autonomous multi-round
loop. Your job is a **presentation-only** cleanup so the artifact reads as if a careful
human wrote it in one sitting — NOT to change any decision, mechanism, number, or design
content. When in doubt, leave it.

You edit the working copy at `{absolute WORKING path}` **directly**. This is the one
place a reconcile-time agent is the writer — the per-round "propose-only, applier is sole
writer" rule does not apply to you, because you perform a bulk whole-document transform
rather than a targeted edit.

## Mode

The orchestrator hands you `MODE: full` or `MODE: cleanup-only`.

- **`full`** — the finalize run. The design is settled and the loop is over. Do all four
  fixes below.
- **`cleanup-only`** — a mid-loop maintenance run between rounds. **Skip fix 1
  (renumbering) entirely.** Every prior `[decision-take]` and `[fix]` line in the
  changelog names decisions by number, and so do the `Governs` lines the reviewer uses as
  its skip-list; renumbering mid-loop would silently re-point all of them at different
  decisions. Do fixes 2–4, which only remove text that no longer describes the document.
  In `cleanup-only`, `reconcile-audit` is a **read-only report**: numbering gaps it names
  are expected mid-loop and are not yours to close. It must still show **zero dangling
  `Dn` / `ODn` references** — if your own edits created one, fix that.

## What to fix (only these)

1. **Decision numbering** *(`MODE: full` only — skip in `cleanup-only`)*. Renumber the `### Dn:` decision headings so they are
   contiguous `1..N` in document order, and update EVERY reference to a decision to
   match — the `## Decision Index`, cross-references inside other decisions, and any
   mention in Situation / Problem / Solution / Scope / Verification. A reference is a
   bare `Dn` token (e.g. "see D7", "per D3"). Build the old→new map FIRST, then apply it
   everywhere in one consistent sweep. If the headings are already contiguous and in
   order, do not renumber.
2. **Stale range / count references.** Fix references that name a stale range or count —
   e.g. a decision body that says "D1–D10" when the spec now defines D1–D13, or "the
   thirteen decisions" when there are twelve. Make them match what the spec actually
   contains.
3. **Reversal / draft-history narrative.** Remove sentences describing states the final
   doc no longer holds — "reversed from the as-drafted rule", "an earlier draft did X —
   rejected", "changed this round from Y". State the settled decision plainly. This
   loses no audit trail: the round-by-round evolution is preserved in `history/run-*/`.
   KEEP genuine "rejected alternative" rationale that explains WHY the settled choice
   beats an alternative — that is design content, not draft history.
4. **Context / Problem duplication.** Where a decision's `Context:` preamble merely
   restates what the `## Problem` section already says, trim it to what is specific to
   that decision. Do not delete context that adds decision-specific framing.

## What NOT to touch

- Any design decision, mechanism, table/column name, cadence, number, or trade-off.
- Section structure and headings other than decision renumbering.
- The `### Dn:` decision TITLES (only their numbers may change).
- Anything you are unsure about — leave it, and note it in your summary.

## Procedure

1. Run the deterministic audit and read it:
   `{MG_INSTALL_SCRIPTS_DIR}/improve_files.py reconcile-audit {absolute WORKING path}`
   It reports numbering gaps / duplicates / out-of-order headings and any dangling
   `Dn` / `ODn` references.
2. Read the working copy. Apply the fixes your `MODE` allows with `Edit` — 1–4 under
   `full`, 2–4 under `cleanup-only`. For renumbering, apply the old→new map to every
   occurrence (headings + all references) so nothing is left dangling.
3. Re-run `reconcile-audit`.
   - Under `MODE: full` it MUST end `"clean": true` (contiguous numbering, zero dangling
     references). If not, fix exactly what it names and repeat. Do not stop until clean —
     renumbering is your one destructive edit and this audit is its guard.
   - Under `MODE: cleanup-only` it must report **zero dangling `Dn` / `ODn` references**.
     Numbering gaps and out-of-order headings are expected mid-loop: report them in your
     summary, do not close them.
4. If a `Dn` / `ODn` reference is dangling because the target genuinely no longer exists
   (e.g. a leftover "see OD3" after the Open Decisions were removed at finalize), rewrite
   the sentence to stand on its own — never invent a target to satisfy the audit.

## Return (one line to the orchestrator)

Return **exactly one line and nothing else** — the orchestrator holds only this summary
and independently re-runs the audit + exit exam:

`RECONCILED <mode> — renumbered <k> decisions (<old→new, or "none">); stripped <s> stale/history spans; deduped <c> contexts; <lines removed> lines; audit clean.`

Under `MODE: cleanup-only` say `renumbered 0 (skipped — cleanup-only)`, and if the audit
named numbering gaps, end with `; numbering gaps left for finalize: <list>` instead of
`audit clean`.

If you changed nothing: `RECONCILED <mode> — nothing to clean; audit clean.`
