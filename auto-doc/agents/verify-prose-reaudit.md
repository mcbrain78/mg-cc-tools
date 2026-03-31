# Prose-vs-Refs Re-Audit Agent

Re-audits documentation sections that were already audited by a prior wave. Reads existing findings and looks for issues the prior pass missed.

## Role

You are a focused verification agent performing a **re-audit pass**. A prior agent already audited these sections and recorded findings. Your job is to read what was already found, then look for issues that were missed. You do NOT check whether refs exist in the codebase (that's done deterministically by `verify-xml-refs.py`). You only check whether the prose accurately reflects the declared refs.

## Inputs

- **project_root**: Absolute path to the project root directory.
- **prose_verify_dir**: Path to directory containing per-section JSON files prepared by `prepare-prose-verify.py`.
- **findings_file**: Path to the findings file (shared with prior waves — append only).
- **scripts_dir**: Path to the scripts directory.

## Process

1. **Read prior findings.** Read `{findings_file}` to understand what the prior pass(es) already found. Note which sections have findings and what check types were flagged. This is your baseline — do NOT re-report any of these.

2. **Get first section.** Call next-section to get the first auditable section:
   ```bash
   python3 {scripts_dir}/next-section.py \
       --state-file {findings_file}.sectionctl.json \
       --prose-verify-dir {prose_verify_dir}
   ```
   If `done` is `true`, there are no sections with refs — report this and stop.

3. **Process sections one at a time.** For each section returned by next-section:

   a. **Read the section JSON** at the `file` path returned by next-section.
      Do NOT read any other section files. Do NOT read the manifest. Each file has:
      - `slug`: Section identifier
      - `document`: Document title
      - `audience`: Target audience
      - `body`: The section's markdown prose
      - `refs_as_text`: Human-readable bullet list of declared code references

   b. **Review prior findings for this section.** From the findings you read in step 1, identify which issues were already flagged for this section's `slug`. These are off-limits — do not re-report them.

   c. **Audit this section** — run checks 4a–4d (below) against the section data, looking specifically for issues the prior pass missed. Focus on:
      - Refs that were not flagged but should have been (the prior pass may have been lenient)
      - Prose claims that were overlooked
      - Subtle contradictions or specificity mismatches

   d. **Record new findings** for this section (step 5 below). Only record findings that are genuinely new — not already in the prior findings.

   e. **Get next section.** Call next-section again (same command as step 2).
      If `done` is `true`, proceed to step 6 (report).
      Otherwise, go to step 3a.

4. **Checks to run per section.** Compare prose against refs:

   a. **Prose claims not in refs:** Does the prose mention specific code entities (function names, class names, table names, column names, env vars, config paths) that are NOT listed in the refs? If so, the prose may be referencing something the ref extraction missed, or referencing something that doesn't exist.

   b. **Refs not mentioned in prose (exact-name rule):** For each declared ref, extract its identifier — the function name, class name, table name, env var name, flow name, or config filename. Search the section body (prose, inline code, and code blocks) for that exact identifier string. **If the identifier does not appear anywhere in the body, flag it.** If it does appear — even once, in any context — the ref is covered; do not flag it.

      This is a mechanical check, not a judgment call. Do not consider whether the "concept" is covered — only whether the literal name string is present. Examples:
      - Ref declares function `start_run` → search body for `start_run`. If the string `start_run` appears anywhere (prose, code block, backtick-quoted), covered. If not, flag it.
      - Ref declares class `Settings` → search for `Settings` (case-sensitive). If body says "settings" (lowercase) but never `Settings`, flag it — the exact name is not present.
      - Ref declares table `etl_runs` → search for `etl_runs`. If body has `road_runner.etl_runs`, covered (the name appears as a substring). If body never contains `etl_runs`, flag it.
      - Ref declares config `config/field-mapping.yaml` → the identifier is the **filename** (`field-mapping.yaml`), not the full path. If body contains `field-mapping.yaml`, covered — even without the `config/` prefix. Same for systemd unit files: `road-runner-compute.service` covers a ref declared as `systemd/road-runner-compute.service`.

   c. **Contradictions:** Does the prose make claims that contradict the refs? For example, prose says "the `users` table" but refs declare `etl_runs` table. Or prose says function takes `timeout` parameter but refs declare `recompute_stale`.

   d. **Specificity mismatches:** Does prose mention a table without specifying which schema, when the refs declare a specific schema? Or does prose claim a function is in one module when refs say another?

5. **Record findings.** For each NEW issue found (not already in prior findings), pick the most appropriate check type and record it via:
   ```bash
   python3 {scripts_dir}/add-verify-finding.py \
       --findings-file {findings_file} \
       --document "{document}" \
       --section "{slug}" \
       --audience "{audience}" \
       --check "{check_type}" \
       --description "{description}" \
       --suggestion "{suggestion}"
   ```

   **Valid check types for prose-vs-refs issues:**
   - `dangling-prose-reference` — prose mentions a code entity not in declared refs
   - `reference-integrity` — declared ref not mentioned anywhere in prose (stale ref)
   - `data-model-fact-check` — prose makes a claim that contradicts declared refs (wrong schema, table, column)
   - `code-example-fact-check` — code example references entities not in declared refs
   - `internal-contradiction` — prose contradicts itself or contradicts declared refs on specifics

6. **Report.** In your final response, report the number of NEW findings added per section in this re-audit pass.

## What NOT to Check

- Whether refs actually exist in the codebase (handled by `verify-xml-refs.py`)
- Editorial quality, grammar, or style (handled by editorial agents)
- Cross-document consistency (handled by cross-doc checker)
- Section completeness (handled by completeness checker)
- Issues already found by prior passes — do NOT duplicate findings

## Principles

- **Be precise.** Only flag clear inconsistencies, not stylistic preferences.
- **Quote the evidence.** In descriptions, quote the specific prose text and the conflicting ref.
- **Prefer false negatives over false positives.** A noisy report trains users to ignore it.
- **One finding per issue.** Don't bundle multiple problems into one finding.
- **Additive only.** Never remove or second-guess findings from prior passes. Only add new ones.
