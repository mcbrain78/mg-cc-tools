# Render-Reliability A/B Test

Run each prompt in a **fresh Claude Code session** (so prior context doesn't taint results). Each produces the same target-menu content; we compare which pattern the LLM echoes faithfully.

Ground truth output (10 lines):

```
Target project:

  [1] ai-stock-ranker
  [2] external-tools
  [3] mg-cc-tools
  [4] road-runner
  [5] senovo-test
  [6] Enter path manually

Type a number or project name:
```

After each run, check the assistant's response text (NOT the Bash tool output — that's collapsed). The response should contain all 10 lines above, in order, unmodified.

---

## Prompt A — Verbatim-tag pattern (current approach)

```
You are acting as the mg-cc-tools installer.

Run this command:

    python3 /home/mcbrain/mg_projects/mg-cc-tools/install/scripts/test-render.py --mode verbatim --source /home/mcbrain/mg_projects/mg-cc-tools

The output is wrapped in <verbatim>...</verbatim> tags. You MUST reproduce EVERY line between the tags exactly as-is in your response text. Do not drop, truncate, reformat, or summarize ANY line. Bash tool output is collapsed in the UI and invisible to the user; your response text is the ONLY way they see this content.

After echoing, wait for my reply.
```

---

## Prompt B — JSON-extract pattern (proposed approach)

```
You are acting as the mg-cc-tools installer.

Run this command:

    python3 /home/mcbrain/mg_projects/mg-cc-tools/install/scripts/test-render.py --mode json --source /home/mcbrain/mg_projects/mg-cc-tools

The output is a single-line JSON object with two fields:
- "display": a string containing the content to show the user (may contain \n for newlines)
- "lines": the expected number of lines in the rendered content

Parse the JSON. Print the VALUE of the "display" field as your response text, preserving all newlines exactly as stored. Do not wrap in code fences, do not prefix, do not summarize. Before you finish, verify your response contains at least `lines` lines — if not, re-print.

After echoing, wait for my reply.
```

---

## What to check

For each prompt, verify the assistant's user-facing response:

- [ ] Contains the header line `Target project:`
- [ ] Contains a blank line after the header
- [ ] Contains all 6 numbered options, in order
- [ ] Contains a blank line after option [6]
- [ ] Contains the trailing prompt `Type a number or project name:`
- [ ] No extra wrapping (no ```code fences```, no `<verbatim>` tags leaked, no summary text)

Record results so we know which pattern to adopt for the full install.md rewrite.
