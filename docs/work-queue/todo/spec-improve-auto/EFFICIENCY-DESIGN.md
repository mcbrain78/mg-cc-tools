# `mg:spec-improve-auto` — Token-Efficiency Design Note

**Status:** design / proposal (nothing implemented). Supersedes the concept's stance that cost is a non-goal — the user has re-prioritized: the drain is "too expensive," and per-round cost must come down.

**Grounding:** every number below is *measured* from the first real drain run (run `wf_fae45c30-1c5`, 2 closed rounds, 77 agents, on the 62-line `scratchpad/p6-fixture`) and a dedicated caching probe (`wf_7640160e-133`) — not estimated. Reproduce with `scratchpad/token_report.py <transcript-dir>`.

---

## 1. The measured baseline

2 rounds · 77 agents · 62-line fixture → **~16.5M tokens raw**, of which **~1.2M is output**. Weighted by Opus list pricing (input 1×, **output 5×**, cache-write 1.25×, cache-read 0.1×):

| Bucket | Raw tokens | $-weight | Share of $ | What it is |
|---|--:|--:|--:|---|
| **cache_create** | 8.84M | ×1.25 | **~52%** | Each agent establishes its *own* context (system + role prompt + files it reads/inlines) |
| **output** | 1.21M | ×5 | **~28%** | Reasoning + edits — priciest per token |
| cache_read | 24.64M | ×0.1 | ~12% | Re-reads *within* an agent's own turns — already cheap |
| fresh input | 1.77M | ×1 | ~8% | — |

**Approx cost: ~$100 for 2 rounds** at Opus list pricing on a *trivial* fixture. A full 10-round run is plausibly $300–500+; a real 200–500-line spec (bigger contexts, more atoms) is multiples of that.

Cost by role (billed weight, from `token_report.py`): **fixer 19% · decision-taker 18% · researcher 12% · prose-extract 11% · readers 7% · judges 6%** · round-close relays + tally + macro-ids + dedup + apply ≈ the rest. The heavy hitters are **multi-turn reasoning agents** (fixer/decision-taker/researcher each rack up millions of cache-read tokens across many turns). **Note:** the per-atom verify swarm had *not run yet* at 2 rounds — the run was still in macro/decision work — so verifier cost is not in this baseline but will be a wide swarm once reached.

---

## 2. Two empirical findings that constrain the design

**Finding A — caching is already well-exploited.** 70% of all input context is cache-reads (0.1×). The prompt-cache lever is largely spent; don't chase it.

**Finding B — the runtime does NOT cross-agent-cache an inlined prefix.** The probe warmed a ~15K-token byte-identical prefix on one agent, then ran 3 more with the *same* prefix:

```
agent      cache_CREATE   cache_READ
A (cold)      55,088            0
B/C/D (warm)  43,288       11,800   ← each re-created 79%; only the shared system/tools block (~21%) was reused
```

The identical prefix sits in the *user* message, past the runtime's cache breakpoint (which covers only the agentType's system/tools block). So inlining the doc as a "shared prefix" gets re-established per agent anyway. **This kills the "keep many small agents, share their context via caching" lever.** Combined with Finding A + the 52% cache_create share, the conclusion is forced:

> **Per-agent cost is intrinsic to the *number* of agents and the *size* of each agent's context. The only ways down are: fewer agents, smaller per-agent context, and cheaper per-token.**

---

## 3. The reframe (design principle)

The first run showed fixes *stick* (0 finding-id re-emergence round-over-round) while new issues surface each round — quality here is **iteration-bound**, not single-pass-bound (this is *why* manual `spec-improve` needs 10–20 passes). That flips the usual calculus:

- **Cost-efficiency and quality are aligned, not opposed.** A cheaper/faster loop buys *more passes per budget*, and more passes is where quality actually comes from. Cheapening a role is *reallocating* budget from per-pass precision to more passes — not sacrificing accuracy.
- **Optimization target: maximize quality-per-dollar-to-convergence.** Make the loop as cheap/fast as possible *down to the convergence floor*.
- **The floor is the risk.** Iteration only lifts quality if each pass is net-positive (fixes > new errors) **and** the gate can still reliably call a round "dry." Below some per-pass accuracy, you thrash to round-cap instead of converging. That floor is unknown — it's the convergence bet, now with a cost axis.

**Role-by-role cheapening policy (load-bearing):**

- **Cheapen aggressively — self-correcting or mechanical:** readers, atom-verifiers, prose-extractors, aggregators, all relay/marshal agents. A miss here re-surfaces in a later pass's fresh read, or is deterministic transcription.
- **Keep sharp — locked-in / consequential:** the **decision-taker** and **block-gate** especially. A wrongly auto-taken decision writes a D-block *and* the dedup pass then suppresses re-judging it — so a cheap error there can persist unseen. Either keep these at full accuracy, **or** add a re-open path so a later pass can revisit a taken decision. The 3-judge gate is a middle case (majority voting gives some robustness; validate before cheapening).

---

## 4. Lever catalog

Ranked by (impact × safety). Impact tags: 💰 token cost, ⏱ wall-clock, ⚠ accuracy risk.

| # | Lever | 💰 | ⏱ | ⚠ | Notes |
|---|---|:--:|:--:|:--:|---|
| 1 | **Merge the round-close relay chain** (part1/2/3 + coverage + churn + archive → 1 agent) | ✅ | ✅✅ | none | Pure mechanical script sequencing. **12 of the 77 agents** were round-close relays across 2 rounds — collapsing them cuts serial critical-path depth *and* cache_create with zero reasoning to degrade. **First implementation.** |
| 2 | **Code-digest pre-pass** | ✅ | ✅ | low | One agent reads all cited code once, emits a compact digest; downstream agents consume the digest instead of each re-reading the files. Shrinks every downstream agent's context (smaller cache_create) even though it isn't cross-agent *shared*. Directly attacks "everyone re-analyzes the same code." |
| 3 | **Batch bounded work** (N atoms per verifier; 1 prose-extractor not 2) | ✅ | ✅¹ | validate | Fewer agents → fewer context establishments. Keep **per-item verdicts with evidence** inside one context (10 individual atom-checks, not one holistic impression) to preserve the accuracy the ledger's coverage accounting depends on. ¹Wall-clock win only when the fan-out is *over* the concurrency cap (7 here); batching a within-cap fan-out serializes it → *slower*. |
| 4 | **Model tiering** (see §5) | ✅✅ | ✅ | validate | Biggest $ lever. Haiku 4.5 is **5× cheaper** than Opus; Sonnet 5 ~1.7×. Apply per the role policy; validate fidelity/accuracy first. |
| 5 | **Lower `effort` on bounded roles** | ✅ | ✅ | low | Cuts output tokens (the 28% slice). Stays on Opus. Safe for genuinely mechanical/bounded work. (Note: not combinable with Haiku — Haiku 4.5 rejects `effort`.) |
| 6 | **Section-slice reader/verifier context** | ✅ | — | low-med | Give an agent only its atom's section, not the whole doc. Atoms are section-anchored, so mostly safe; some cross-section context lost. |
| — | ~~Inlined shared prefix~~ | — | — | — | **Dead** (Finding B — runtime won't share it). |
| — | ~~Fewer rounds~~ | — | — | — | Not a knob — rounds are iteration-inherent (user-confirmed). |

**Not reachable through the Workflow tool, but noted for a future architecture:** the **Batches API** gives a flat **50%** discount and the drain's parallel swarms (verifiers) are latency-tolerant within a round — an ideal fit. But `agent()` spawns individual sessions, not batch requests, so this is only available if the orchestration moves off the Workflow tool (the `drain_state.py` direction we've otherwise ruled out). Flag, don't pursue now.

---

## 5. Model tiering (in scope per user)

Pricing (per 1M tokens): Opus 4.8 `claude-opus-4-8` **$5/$25** · Sonnet 5 `claude-sonnet-5` **$3/$15** (0.6×) · Haiku 4.5 `claude-haiku-4-5` **$1/$5** (0.2×). Workflow `agent()` takes the friendly name in `model:` (`'opus'|'sonnet'|'haiku'`).

| Role | Model | Why | Validation before trusting |
|---|---|---|---|
| Atom-verifiers (bounded "does this claim hold?" checks) | **haiku** | Classification-shaped, self-correcting, the widest swarm → biggest 5× win | A/B verdict agreement vs Opus verifiers on a fixed atom set |
| Relay / marshal / tally / macro-ids / round-close scripts | **haiku** | Pure transcription + `uv run` | **Fidelity spike** (Gate-B style): does Haiku transcribe 100–160 verdict entries byte-faithfully? The `record-verdicts` count-assert already guards drops, but content fidelity needs checking |
| Prose-extractors, aggregators | **haiku / sonnet** | Bounded extraction; self-correcting | Extraction-completeness check vs Opus |
| Whole-doc readers, competitive-rewrite | **sonnet** | Real but bounded reasoning; ~1.7× win at Sonnet quality | Finding-quality A/B on the dry-run |
| Researcher | **sonnet / opus** | Feeds consequential takes | Keep opus until validated |
| **3-judge gate panel** | **opus** (or sonnet, validated) | Decides substantive/cosmetic + needs-user | Panel majority gives some robustness; validate a sonnet panel before switching |
| **Decision-taker, block-gate** | **opus** | **Locked-in** — errors persist through dedup suppression | Do not cheapen without a decision re-open path |
| Fixer / apply (edits the working copy) | **sonnet** | Bad edits self-correct (later readers catch them) | Watch for churn increase on the dry-run |

**Implementation caveats:** (a) Haiku 4.5 rejects the `effort` param — omit `effort` on Haiku agents. (b) Haiku is 200K context (fine for a spec + digest, not for pathological inputs). (c) Switching model per role is free in the Workflow model (`agent()` `model:` opt); there is no cache to invalidate across differently-typed agents (they don't share one anyway — Finding B).

---

## 6. Validation plan — the A/B convergence test

This doubles as the Phase-6 convergence dry-run we still owe. On a fixture with a **real fixed point** (a genuinely solid ~200-line spec + a few planted issues, so the gate *can* go dry):

1. **Baseline arm:** all-Opus drain → does it converge? in how many passes? total cost? final quality (planted issues fixed, no regressions)?
2. **Cheapened arm:** discovery/verification tiered to Haiku/Sonnet + batched, decisions kept Opus → does it *still* converge (even in more passes) at lower total cost and comparable final quality?

**Read-outs:** converged vs round-capped; pass count; total billed tokens (cost-per-converged-spec); finding-id stability (does cheapening add jitter that defeats below-bar memory / churn escalation?). If the cheapened arm converges cheaper → the reframe holds and this becomes the design. If it thrashes → we've found the floor, and back off the roles that broke it.

---

## 7. Implementation ordering

1. **Round-close relay merge** (§4 #1) — zero accuracy risk, immediate cache_create + wall-clock win. Ship first.
2. **Code-digest pre-pass** (§4 #2) — accuracy-preserving context shrink.
3. **Fidelity spike** for Haiku relays/verifiers (§5 validation) — cheap, gates the big tiering win.
4. **Tier** relays + verifiers to Haiku, readers to Sonnet (§5), guarded by (3).
5. **Batch** the verify sweep (§4 #3), per-item verdicts preserved.
6. **A/B convergence test** (§6) on a real-fixed-point fixture — the go/no-go for the whole cheapening thesis + the owed dry-run.

Each step is independently shippable and independently revertible (per-role model/effort is a one-line `agent()` opt; the round-close merge is a contained refactor). Nothing here touches the ledger, the sidecars, or the relay *contract* — only which model runs a role, how many agents a stage spawns, and how much context each carries.

---

## 8. Open questions / risks

- **The convergence floor is unmeasured.** The whole cheapening thesis rests on "cheaper passes still converge." Unknown until the A/B test — and baseline convergence itself isn't yet confirmed (the toy fixture never reached a dry gate).
- **Haiku transcription fidelity** for the high-volume `record-verdicts` marshal is the one place a cheap model could silently corrupt the ledger. The count-assert guards *drops*; per-entry content needs the spike.
- **Locked-in decisions** need either sustained Opus accuracy or a re-open mechanism before the decision path is cheapened at all.
- **Wall-clock ≠ cost.** Some levers cut tokens but not wall-clock (tiering a within-cap fan-out), and one can *raise* wall-clock (batching a within-cap fan-out). Keep the two axes separate when measuring.
