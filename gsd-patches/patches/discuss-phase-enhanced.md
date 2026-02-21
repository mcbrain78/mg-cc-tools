# Patch: discuss-phase-enhanced

## Meta
- **Target:** get-shit-done/workflows/discuss-phase.md
- **Description:** Adds option recommendations and auto-deepen loop to discuss-phase questioning

## Modifications

### 1. Add recommendation behavior

Adds inline reasoning about the best option, marks it "(Recommended)", and places it first.

**Anchor:**
```
2. **Ask 4 questions using AskUserQuestion:**
   - header: "[Area]" (max 12 chars — abbreviate if needed)
   - question: Specific decision for this area
   - options: 2-3 concrete choices (AskUserQuestion adds "Other" automatically)
   - Include "You decide" as an option when reasonable — captures Claude discretion
```

**Replace with:**
```
2. **Ask 4 questions using AskUserQuestion:**
   - header: "[Area]" (max 12 chars — abbreviate if needed)
   - question: Specific decision for this area
   - options: 2-3 concrete choices (AskUserQuestion adds "Other" automatically)
   - Include "You decide" as an option when reasonable — captures Claude discretion
   - **Recommend an option:** Before presenting each question, internally reason about
     which option best fits the phase context, user's prior answers, and common patterns
     for this domain. Mark the recommended option with "(Recommended)" suffix and place
     it as option #1. Present remaining options in their natural order after it.
```

### 2. Add auto-deepen loop

Replaces the static continuation check with a self-assessment loop. The user always retains control — the LLM's assessment only determines which option is recommended and how the question is framed.

**Anchor:**
```
3. **After 4 questions, check:**
   - header: "[Area]" (max 12 chars)
   - question: "More questions about [area], or move to next?"
   - options: "More questions" / "Next area"

   If "More questions" → ask 4 more, then check again
   If "Next area" → proceed to next selected area
   If "Other" (free text) → interpret intent: continuation phrases ("chat more", "keep going", "yes", "more") map to "More questions"; advancement phrases ("done", "move on", "next", "skip") map to "Next area". If ambiguous, ask: "Continue with more questions about [area], or move to the next area?"
```

**Replace with:**
```
3. **After 4 questions, self-assess then check with user:**

   Before presenting the continuation choice, internally evaluate:
   - Are there meaningful implementation decisions for this area I haven't surfaced yet?
   - Would probing deeper reveal questions the user hasn't considered?
   - Have prior answers opened new ambiguities that deserve follow-up?

   **If you identify more meaningful questions to ask:**
   - header: "[Area]" (max 12 chars)
   - question: "I have more questions about [area]. Continue discussing, or move on?"
   - options: "Continue discussing (Recommended)" / "Move to next area"
   If user continues → ask up to 4 more questions, then self-assess again (repeat this loop).
   If user moves on → proceed to next selected area.

   **If satisfied that coverage is sufficient:**
   - header: "[Area]" (max 12 chars)
   - question: "I think we've covered [area] well. Move on, or dig deeper?"
   - options: "Move to next area (Recommended)" / "More questions"
   If user moves on → proceed to next selected area.
   If user wants more → ask up to 4 more questions, then self-assess again.

   If "Other" (free text) → interpret intent: continuation phrases ("chat more", "keep going", "yes", "more") map to asking more questions; advancement phrases ("done", "move on", "next", "skip") map to proceeding to next area. If ambiguous, ask: "Continue with more questions about [area], or move to the next area?"
```
