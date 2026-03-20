# Requirement Candidate Generator

Read the CONTEXT.md file provided as your argument.

For each locked decision in the `<decisions>` section, generate candidate requirements.
A requirement describes what becomes true or what the user/system can do — not how it's built.

For EACH candidate, output ONE line in this format:
```
N. [tag] Description (parent: #M if detail)
```

Where tag is one of:
- `capability` — a distinct user-observable feature or behavior
  (e.g., "running command X on input Y produces output Z")
- `constraint` — a cross-cutting rule that applies to multiple capabilities
  (e.g., "all output is plain text with no ANSI codes")
- `detail` — an implementation choice, internal mechanism, sub-behavior, or
  edge case that belongs to another candidate
  (e.g., "uses json.load() to parse input" is a detail of the command that loads it)

Be thorough — include everything from the decisions. Tagging handles the filtering.
Do NOT read or modify any files other than the context file. Output ONLY the numbered list.
