export const meta = {
  name: "spec-improve-auto drain",
  description:
    "One autonomous drain run of the mg:spec-improve-auto pyramid: directive prelude, horizontal macro pass, atom decomposition, verification pyramid, exit exam. Control flow + prompts only — every deterministic computation is a uv-run script call made by an agent and relayed back.",
  phases: [
    { title: "Directive prelude", detail: "Apply carried overrides/directives to the working copy (directive runs only)." },
    { title: "Horizontal macro pass", detail: "Whole-document readers hunt gaps, disconnects, contradictions, simpler-whole-design; loop until a dry macro pass." },
    { title: "Atom decomposition", detail: "One-time full pass: extract mechanical atoms + merge two prose-extractor candidate sets into the ledger." },
    { title: "Verification pyramid", detail: "Per-round: verify dirty/unverified atoms, aggregate, gate, fix, decide, round-close; loop until coverage-complete + dry + no pending decision." },
    { title: "Exit exam", detail: "Fresh whole-document read; findings re-enter the pyramid, a clean exam converges the run." },
  ],
};

// ─────────────────────────────────────────────────────────────────────────────
// 0. ARGS + CONFIG  (gate finding: args may arrive as a JSON string)
// ─────────────────────────────────────────────────────────────────────────────
const A = (typeof args === "string") ? JSON.parse(args) : (args || {});

const PATHS = A.paths || {};
const SOURCE = PATHS.source;                 // <target> — the arg every script keys on
const DOC = PATHS.auto_improve;              // working copy — the doc every atoms subcmd reads
const LEDGER = PATHS.atoms;                  // concept-ATOMS.json
const DECISIONS = PATHS.decisions;           // concept-DECISIONS.json
const NOTES = PATHS.implementer_notes;       // concept-IMPLEMENTER-NOTES.md
const CHANGELOG = PATHS.changelog;           // concept-CHANGELOG.md
const NON_GOALS = PATHS.non_goals;           // concept-NON-GOALS.md
const HISTORY = PATHS.history_dir;

// arg-key aliases tolerated (brief uses camelCase; concept args JSON uses snake_case)
const SCRIPTS = A.scriptsDir || A.scripts_dir;
const TEMPLATE = A.templatePath || A.template_path;
const SCRATCH = A.scratchDir || A.scratch_dir;
const RUN = A.run;
const OVERRIDES = Array.isArray(A.overrides) ? A.overrides : [];
const DIRECTIVES = Array.isArray(A.directives) ? A.directives : [];

const SPEC_CHECKS = `uv run ${SCRIPTS}/spec_checks.py`;
const IMPROVE = `uv run ${SCRIPTS}/improve_files.py`;

// Termination + brake constants (thresholds the SCRIPTS own; here only for the JS's own agent-ceiling brake).
const ROUND_CAP = 10;          // phases H + P combined, per invocation (concept D4)
const AGENT_FLOOR = 900;       // static brake floor (~one round's headroom below the 1000 ceiling)
const AGENT_CEILING = 1000;    // Workflow lifetime agent ceiling — stay strictly under

// ─────────────────────────────────────────────────────────────────────────────
// 1. LOOP STATE  (D2/D10 — trivial control-flow state only; judgment lives in files)
// ─────────────────────────────────────────────────────────────────────────────
let roundIndex = 0;            // increments on every phase-H pass + phase-P round (phase-E reads do NOT)
let cumulativeAgents = 0;      // every agent() call, all classes — feeds the brake
let status = null;             // "converged" | "blocked" | "round-cap"
let fixed = 0;                 // auto-fixable findings applied (NOT decision-takes)
let belowBar = 0;             // below-bar findings appended to IMPLEMENTER-NOTES

let dirtySet = [];             // atom ids sizing next round's verifier swarm
let idTypeMap = {};            // atom id -> type (carried forward; sizes/labels verifiers without reading the ledger)
let idAnchorMap = {};          // atom id -> current anchor (section path)
let idLineageMap = {};         // atom id -> lineage id (for radius/churn)
let pendingDecisions = [];     // {decision_id, finding_atoms, macro} rebuilt from disk on continuation
let nullCallCarry = [];        // within-invocation record of failed/pending decision calls

// Churn escalation (Loop step 7) — set membership only; the >=2 thresholds are churn-check's (Python).
// Populated at every round close from `atoms churn-check`; consumed by the NEXT round's gate.
// Re-emergence is NOT a JS recollection (concept line 227-228): a finding present in the current gate
// IS the re-emergence, and the ledger-persisted escalation sets already encode fix_count/flip >=2.
let churnSets = { flip: new Set(), fix: new Set(), macros: new Set() };

// ─────────────────────────────────────────────────────────────────────────────
// 2. STRUCTURED-OUTPUT SCHEMAS
// ─────────────────────────────────────────────────────────────────────────────
const S_RELAY_SINGLE = {
  type: "object",
  properties: { notes: { type: "string" }, script_output: { type: "string" } },
  required: ["script_output"],
};
const S_RELAY_KEYED = {
  type: "object",
  properties: {
    notes: { type: "string" },
    script_output: {
      type: "array",
      items: {
        type: "object",
        properties: { call: { type: "string" }, output: { type: "string" } },
        required: ["call", "output"],
      },
    },
  },
  required: ["script_output"],
};
const S_FINDINGS = {
  type: "object",
  properties: {
    findings: {
      type: "array",
      items: {
        type: "object",
        properties: {
          klass: { type: "string" },
          sections: { type: "array", items: { type: "string" } },
          detail: { type: "string" },
          decision_shaped: { type: "boolean" },
          atoms: { type: "array", items: { type: "string" } },
        },
        required: ["klass", "sections", "detail"],
      },
    },
  },
  required: ["findings"],
};
const S_VERIFIER = {
  type: "object",
  properties: {
    atom_id: { type: "string" },
    state: { type: "string" },              // "verified" | "unverifiable"
    finding_conclusion: { type: ["string", "null"] }, // finding text, or null/"sound"
    computed_against_hash: { type: "string" },
    input_set: {
      type: "object",
      properties: {
        sections: { type: "array", items: { type: "string" } },
        external: { type: "array", items: { type: "object", properties: { path: { type: "string" }, hash: { type: "string" } } } },
      },
    },
  },
  required: ["atom_id", "state", "input_set"],
};
const S_CANDIDATES = {
  type: "object",
  properties: { candidates: { type: "array", items: { type: "object" } } },
  required: ["candidates"],
};
const S_AGG = {
  type: "object",
  properties: {
    findings: {
      type: "array",
      items: {
        type: "object",
        properties: {
          type: { type: "string" },
          atoms: { type: "array", items: { type: "string" } },
          evidence: { type: "string" },
          decision_shaped: { type: "boolean" },
        },
        required: ["type", "atoms", "evidence"],
      },
    },
  },
  required: ["findings"],
};
const S_DEDUP = {
  type: "object",
  properties: {
    kept: { type: "array", items: { type: "object" } },
    folded: { type: "array", items: { type: "object", properties: { finding_id: { type: "string" }, record_id: { type: "string" } } } },
  },
  required: ["kept"],
};
const S_JUDGE = {
  type: "object",
  properties: {
    ballots: {
      type: "object",
      additionalProperties: {
        type: "object",
        properties: { substantive: { type: "boolean" }, needs_user: { type: "boolean" }, exclusion: { type: "boolean" } },
        required: ["substantive", "needs_user", "exclusion"],
      },
    },
  },
  required: ["ballots"],
};
const S_H2H_JUDGE = {
  type: "object",
  properties: { ballots: { type: "object", additionalProperties: { type: "string" } } },
  required: ["ballots"],
};
const S_REWRITE = {
  type: "object",
  properties: { anchor_unit: { type: "string" }, replacement: { type: "string" } },
  required: ["anchor_unit", "replacement"],
};
const S_RESEARCH = {
  type: "object",
  properties: {
    decision_id: { type: "string" },
    options: { type: "array", items: { type: "object", properties: { option: { type: "string" }, tradeoff: { type: "string" } } } },
    recommendation: { type: "string" },
    edit_estimate_sections: { type: "array", items: { type: "string" } },
    confidence: { type: "string" },
    near_tie: { type: "boolean" },
    reverses_directive: { type: "boolean" },
    reverses_non_goal: { type: "boolean" },
  },
  required: ["decision_id", "options", "recommendation", "edit_estimate_sections"],
};
const S_FIX_PLAN = {
  type: "object",
  properties: {
    plan: {
      type: "array",
      items: {
        type: "object",
        properties: {
          finding_id: { type: "string" },
          outcome: { type: "string" },        // auto-fixable | below-bar | needs-user | proposed-non-goal
          whole_unit: { type: "boolean" },
          anchor_unit: { type: "string" },
        },
        required: ["finding_id", "outcome"],
      },
    },
    decisions_created: { type: "array", items: { type: "object", properties: { finding_id: { type: "string" }, decision_id: { type: "string" } } } },
    below_bar_count: { type: "number" },
    fixed_count: { type: "number" },
    touched_sections: { type: "array", items: { type: "string" } },
    script_output: { type: "array", items: { type: "object", properties: { call: { type: "string" }, output: { type: "string" } }, required: ["call", "output"] } },
  },
  required: ["plan", "script_output"],
};
const S_DECIDE = {
  type: "object",
  properties: {
    verdicts: {
      type: "array",
      items: {
        type: "object",
        properties: {
          decision_id: { type: "string" },
          verdict: { type: "string" },        // takeable | blocked
          post_take_sections: { type: "array", items: { type: "string" } },
          post_take_atoms: { type: "array", items: { type: "string" } },
          whole_unit: { type: "boolean" },    // true ⇒ the take writes/amends a WHOLE anchor unit (D-block) → competitive rewrite
          anchor_unit: { type: "string" },    // the anchor unit a whole_unit take lands (deferred to the competitive rewrite)
        },
        required: ["decision_id", "verdict"],
      },
    },
    script_output: { type: "array", items: { type: "object", properties: { call: { type: "string" }, output: { type: "string" } }, required: ["call", "output"] } },
  },
  required: ["verdicts", "script_output"],
};

// ─────────────────────────────────────────────────────────────────────────────
// 3. RELAY HELPERS  (JSON.parse + shape-validate BEFORE branching — concept relay contract)
// ─────────────────────────────────────────────────────────────────────────────
function parseJSON(s) { try { return JSON.parse(s); } catch (_e) { return undefined; } }

function relaySingle(ret) {
  if (!ret) return undefined;
  const raw = ret.script_output;
  if (typeof raw !== "string") return undefined;
  return parseJSON(raw);
}
function relayKeyed(ret, tag) {
  if (!ret || !Array.isArray(ret.script_output)) return undefined;
  const e = ret.script_output.find((x) => x && x.call === tag);
  if (!e || typeof e.output !== "string") return undefined;
  return parseJSON(e.output);
}

// Shape validators — reject an off-shape (paraphrased-into-valid-but-wrong-key) relay before branching.
function vTally(o) { return o && typeof o === "object" && !Array.isArray(o); }
function vH2H(o) { return o && typeof o === "object" && Object.values(o).every((v) => v && (v.winner === "A" || v.winner === "B")); }
function vBlockGate(o) { return o && (o.verdict === "blocked" || o.verdict === "takeable") && Array.isArray(o.units); }
function vReanchor(o) { return o && Array.isArray(o.relocated) && Array.isArray(o.vanished) && Array.isArray(o.new_regions); }
function vMarkDirty(o) { return o && Array.isArray(o.dirty); }
function vCoverage(o) { return o && typeof o.total === "number" && typeof o.complete === "boolean"; }
function vRadius(o) { return o && Array.isArray(o.sections) && typeof o.units === "number"; }
function vRecord(o) { return o && typeof o.applied === "number"; }
function vExtract(o) { return o && Array.isArray(o.atoms); }
function vMerge(o) { return o && Array.isArray(o.merged_atoms); }
function vFloor(o) { return o && (o.status === "pass" || o.status === "fail"); }
function vNoteIds(o) { return Array.isArray(o); }
function vAllocId(o) { return o && typeof o.id === "string"; }
function vDecisions(o) { return Array.isArray(o); }
function vChurnCheck(o) { return o && Array.isArray(o.flip_escalate_lineages) && Array.isArray(o.fix_escalate_lineages) && Array.isArray(o.escalate_macros); }
function vMacroIds(o) { return o && Array.isArray(o.ids); }

// ─────────────────────────────────────────────────────────────────────────────
// 4. AGENT WRAPPERS  (failure policy: one re-spawn per null / off-shape call, then degrade)
// ─────────────────────────────────────────────────────────────────────────────
async function callAgent(prompt, opts) {
  cumulativeAgents++;
  return await agent(prompt, opts);
}

// Plain reader/judge/verifier — one retry on null; may still return null → caller degrades.
async function reader(prompt, opts) {
  let r = await callAgent(prompt, opts);
  if (r === null) r = await callAgent(prompt, opts);
  return r;
}

// Script-running agent — spawn, parse+validate each relayed call; one retry on null-or-off-shape.
// spec.single: { tag, validate } ; spec.keyed: [{ tag, validate }]  Returns { ret, data } or null.
async function relayAgent(prompt, opts, spec) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const r = await callAgent(prompt, opts);
    if (r === null) continue;
    if (spec.single) {
      const p = relaySingle(r);
      if (p !== undefined && (!spec.single.validate || spec.single.validate(p))) return { ret: r, data: p };
    } else if (spec.keyed) {
      const data = {};
      let ok = true;
      for (const t of spec.keyed) {
        const p = relayKeyed(r, t.tag);
        if (p === undefined || (t.validate && !t.validate(p))) { ok = false; break; }
        data[t.tag] = p;
      }
      if (ok) return { ret: r, data };
    }
  }
  return null; // dead/malformed after retry — fail loud (round ends unsnapshotted → round-cap)
}

// Fan-out cap (Situation: up to 4096 items per fan-out call). Chunk any wider fan-out so no single
// parallel() call trips the documented per-call limit. Realistically unreachable on a real spec, but guarded.
const FANOUT_CAP = 4096;
async function parallelCapped(thunks) {
  if (thunks.length <= FANOUT_CAP) return await parallel(thunks);
  const out = [];
  for (let i = 0; i < thunks.length; i += FANOUT_CAP) {
    const chunk = await parallel(thunks.slice(i, i + FANOUT_CAP));
    for (const x of chunk) out.push(x);
  }
  return out;
}

// End the run honestly: a critical role died / a relay stayed malformed / an assert failed.
function deadRole(label) {
  log(`FAILURE: ${label} — round ${roundIndex} ends unsnapshotted; exiting round-cap.`);
  status = "round-cap";
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. AGENT-CEILING BRAKE  (checked at top of every round, BEFORE spawning)
// ─────────────────────────────────────────────────────────────────────────────
function projectWidth(p) {
  const dirty = p.dirty || 0;
  const sections = p.sections || 0;
  const pending = p.pending || 0;
  const scopeItems = p.scopeItems || 0;
  return (
    dirty * 1 + 1 /* floor */ +
    sections * 1 + 1 /* dedup */ + 3 /* judges */ +
    pending * 2 /* researcher + taker */ +
    scopeItems * 3 /* 2 probes + comparator */ +
    (p.regionsAwaiting ? 2 : 0) +
    (p.phaseHqueued ? 3 : 0) +
    (p.wholeUnitFixes || 0) * 5 /* 2 rewrites + 3 judges per fix */
  );
}
function brakeTrips(projected) {
  return cumulativeAgents >= AGENT_FLOOR || cumulativeAgents + projected >= AGENT_CEILING;
}
// Returns true (and sets status) if the round must NOT open.
function brakeCheck(projShape) {
  if (roundIndex >= ROUND_CAP) { log(`Round cap ${ROUND_CAP} reached.`); status = "round-cap"; return true; }
  const projected = projectWidth(projShape);
  if (brakeTrips(projected)) {
    log(`Agent-ceiling brake: cumulative=${cumulativeAgents} projected=${projected} — exiting round-cap.`);
    status = "round-cap";
    return true;
  }
  return false;
}

// ─────────────────────────────────────────────────────────────────────────────
// 6. SHARED PROMPT FRAGMENTS
// ─────────────────────────────────────────────────────────────────────────────
const CTX = `Working copy (the spec under refinement): ${DOC}
Concept template (the structure the spec should follow): ${TEMPLATE}
NON-GOALS sidecar (approved scope exclusions): ${NON_GOALS}
IMPLEMENTER-NOTES sidecar (below-bar advisory notes): ${NOTES}
You may read the working copy, the template, the two sidecars, and any code the spec cites. NEVER read history/, the ledger, or DECISIONS.json.`;

const RELAY_RULE = `RELAY CONTRACT: return the script's raw JSON stdout VERBATIM in the script_output field, separate from your own reasoning. Do not paraphrase, reformat, or summarize it.`;
const RELAY_KEYED_RULE = `RELAY CONTRACT (keyed list): script_output is a LIST with one entry per branch-driving script call — {call: "<tag>", output: "<raw JSON stdout verbatim>"}. Include one entry per required tag. Do not merge, paraphrase, or reorder the raw outputs.`;

const CHECK_BY_TYPE = {
  claim: "Check this claim against the code/files it cites. State verified or a finding.",
  assumption: "Check whether the spec states this assumption explicitly AND grounds it in cited evidence (or promotes it to a D-block if it is itself a design choice). An unstated or ungrounded assumption is a finding.",
  citation: "Check whether the D-block actually motivates the item it cites. If the Why does not discriminate the choice from its alternatives, that is a finding.",
  example: "Check this example against the adjacent contract text. Divergence is a finding.",
  "scope-item": "Check this scope item against the Verification section — is it covered? An uncovered scope item is a finding.",
  "d-block": "Check whether the D-block's Why discriminates between the chosen option and its alternatives. A non-discriminating Why is a finding.",
  contract: "Check this contract against 3-5 enumerated edge and lifecycle questions answerable from the spec alone. Also: a code-fenced block that is a function body (algorithm implementation) rather than an interface/contract is an over-specification finding.",
  heading: "(headings carry no micro-check)",
};

// ─────────────────────────────────────────────────────────────────────────────
// 7. WORKLIST BOOKKEEPING FROM RELAYS
// ─────────────────────────────────────────────────────────────────────────────
function ingestAtoms(atomList) {
  const ids = [];
  for (const a of atomList || []) {
    if (!a || !a.id) continue;
    idTypeMap[a.id] = a.type || idTypeMap[a.id] || "claim";
    if (a.anchor) idAnchorMap[a.id] = a.anchor;
    if (a.lineage_id) idLineageMap[a.id] = a.lineage_id;
    ids.push(a.id);
  }
  return ids;
}
function applyReanchor(delta) {
  for (const r of delta.relocated || []) { if (r && r.id && r.new) idAnchorMap[r.id] = r.new; }
}

// ─────────────────────────────────────────────────────────────────────────────
// 8. NOTE-IDS FETCH (phase-H path; phase P gets these from the floor agent's keyed relay)
// ─────────────────────────────────────────────────────────────────────────────
async function fetchNoteIds() {
  const res = await relayAgent(
    `Run exactly one command and relay its stdout:
  ${IMPROVE} note-ids ${SOURCE}
${RELAY_RULE}`,
    { label: "note-ids", agentType: "general-purpose" },
    { single: { validate: vNoteIds } }
  );
  return res ? res.data : [];
}

// JS deterministic set-difference: drop findings whose id is already an IMPLEMENTER-NOTE.
function findingId(f) {
  // id = type/class + the lineage ids it stands on (Loop step 7). Deterministic, JS-computed.
  const kind = f.type || f.klass || "finding";
  const atoms = (f.atoms || []).map((id) => idLineageMap[id] || id).sort();
  return atoms.length ? `${kind}:${atoms.join("+")}` : `${kind}:${(f.sections || []).slice().sort().join("|")}`;
}
function dropBelowBar(findings, noteIds) {
  const seen = new Set(noteIds || []);
  // Macro findings carry a canonical script-computed id (attachMacroIds); prefer it over the JS recompute
  // so the below-bar memory compares the SAME id `append-note` recorded, never a divergent JS re-derivation.
  // Floor findings are definitionally substantive (concept §Verify) — never note-suppressed while floor
  // fails, else a note-suppressed floor violation would keep floorGreen false and loop to the round-cap.
  return findings.filter((f) => (f.type === "floor" || f.klass === "floor") || !seen.has(f.id || findingId(f)));
}

// Macro finding-id (Loop step 7): the SCRIPT is the sole canonicalizer of the section-path set, so the
// macro id (`<class>:<canonical sections>`) is a relayed `atoms macro-ids` value, never a JS sort/join.
// Returns rawFindings with the canonical id + type attached (input order), or null on relay failure.
async function attachMacroIds(rawFindings, phaseTag) {
  if (!rawFindings.length) return [];
  const payload = rawFindings.map((f) => ({ class: f.klass, sections: f.sections || [] }));
  const fpath = `${SCRATCH}/${phaseTag}-macro-findings.json`;
  const res = await relayAgent(
    `Compute canonical macro-finding ids (the script is the sole canonicalizer — you NEVER sort, join, or normalize section paths yourself).
STEP 1 — write EXACTLY this JSON verbatim to ${fpath}:
${JSON.stringify(payload)}
STEP 2 — run: ${SPEC_CHECKS} atoms macro-ids --doc ${DOC} --findings "$(cat ${fpath})"
${RELAY_RULE}`,
    { label: "macro-ids", phase: phaseTag, agentType: "general-purpose", schema: S_RELAY_SINGLE },
    { single: { validate: vMacroIds } }
  );
  if (!res) return null;
  const ids = res.data.ids || [];
  return rawFindings.map((f, i) => ({ ...f, id: ids[i], type: f.klass }));
}

// MINOR 2: a macro finding's fix_count is bumped by record-verdicts only when fixed:true — so mark it
// fixed ONLY when this round's gate outcome was auto-fixable (i.e. actually applied), never unconditionally.
function markMacroFixed(rawMacroFindings, roundLog) {
  const out = roundLog._outcomes || {};
  roundLog.macro_findings = rawMacroFindings.map((f) => ({ id: f.id, fixed: out[f.id] === "auto-fixable" }));
}

// Churn escalation (Loop step 7): a finding whose lineage/macro id sits in churn-check's escalation sets
// escalates to Decide BEFORE a 3rd fix. Pure set-membership LOOKUP — the >=2 thresholds live in churn-check.
function escalateChurn(gate) {
  for (const f of gate.ided) {
    // A finding present in the current gate IS the re-emergence — no JS cross-round memory needed; the
    // relayed sets are ledger-persisted (hold across invocation boundaries), so membership alone suffices.
    const lineages = (f.atoms || []).map((a) => idLineageMap[a]).filter(Boolean);
    const isMacro = !(f.atoms && f.atoms.length);
    let escalate = false;
    if (lineages.some((l) => churnSets.flip.has(l))) escalate = true;       // direct oscillation (verdict flips >=2)
    else if (lineages.some((l) => churnSets.fix.has(l))) escalate = true;   // fixed twice AND re-emerged (ledger-computed)
    else if (isMacro && churnSets.macros.has(f.id)) escalate = true;        // macro fixed twice AND re-emerged (ledger-computed)
    if (escalate) gate.outcomes[f.id] = "needs-user";                       // route to the decision machinery
  }
}

// Floor findings are definitionally substantive (concept §Verify): the judge gate may never demote them to
// below-bar or exclusion (which would let dropBelowBar note-suppress them and hang floorGreen at the round-cap).
// Force each floor finding's outcome to an actionable one — needs-user when any judge (or churn) flagged an
// intent/scope/architecture change, else auto-fixable. A set-membership override in JS, never vote math.
function forceFloorOutcomes(gate) {
  for (const f of gate.ided) {
    if (f.type !== "floor" && f.klass !== "floor") continue;
    const ballots = (gate.votes && gate.votes[f.id]) || {};
    const needsUser = Object.values(ballots).some((b) => b && b.needs_user) || gate.outcomes[f.id] === "needs-user";
    gate.outcomes[f.id] = needsUser ? "needs-user" : "auto-fixable";
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 9. GATE  (3 judges → marshaled votes file → fixer/recorder runs `tally`)
// ─────────────────────────────────────────────────────────────────────────────
async function runGate(findings, roundTag) {
  if (!findings.length) return { outcomes: {}, votes: {} };
  // Attach a deterministic id to each finding so votes/tally key stably.
  const ided = findings.map((f) => ({ ...f, id: f.id || findingId(f) }));
  const findingsForJudges = ided.map((f) => ({ id: f.id, detail: f.detail || f.evidence || "", sections: f.sections || [], atoms: f.atoms || [] }));

  const judgeNames = ["builds-wrong-thing", "implementer-blocked", "scope-intent-drift"];
  const judgeThunks = judgeNames.map((persona) => async () => {
    const r = await reader(
      `You are the "${persona}" judge on a 3-judge spec-refinement gate. ${CTX}
For EACH finding below cast three boolean votes: substantive (would the implementer build the wrong thing, get stuck, or have to come back and ask if this is not fixed?), needs_user (does resolving this change intent, scope, or architecture?), exclusion (is this an intentional scope exclusion?).
Findings (JSON): ${JSON.stringify(findingsForJudges)}
Return { ballots: { "<finding-id>": {substantive, needs_user, exclusion}, ... } } with one entry per finding id.`,
      { label: `judge-${persona}`, phase: roundTag, agentType: "Explore", schema: S_JUDGE }
    );
    return r ? { persona, ballots: r.ballots || {} } : null;
  });
  const judgeResults = (await parallel(judgeThunks)).filter(Boolean);
  if (judgeResults.length < 3) { deadRole(`gate panel held ${judgeResults.length}/3 judges`); return null; }

  // Marshal the votes file: { "<findingId>": { "<persona>": {substantive,needs_user,exclusion}, ... } }
  const votes = {};
  for (const f of findingsForJudges) {
    votes[f.id] = {};
    for (const jr of judgeResults) votes[f.id][jr.persona] = jr.ballots[f.id] || { substantive: false, needs_user: false, exclusion: false };
  }
  const votesPath = `${SCRATCH}/r${roundIndex}-votes.json`;
  const res = await relayAgent(
    `Marshal a votes file, then tally it (vote math is NEVER done by you — the script computes it).
STEP 1 — write EXACTLY this JSON verbatim to ${votesPath}:
${JSON.stringify(votes)}
STEP 2 — run: ${SPEC_CHECKS} tally ${votesPath}
(Exit 1 means a panel had fewer than 3 judges — report that as a failure, do not fabricate a result.)
${RELAY_RULE}`,
    { label: "tally", phase: roundTag, agentType: "general-purpose", schema: S_RELAY_SINGLE },
    { single: { validate: vTally } }
  );
  if (!res) { deadRole("tally (votes marshal / tally)"); return null; }
  return { outcomes: res.data, votes, ided };
}

// ─────────────────────────────────────────────────────────────────────────────
// 10. COMPETITIVE STRUCTURAL REWRITE  (per whole-unit fix: 2 rewrites + 3 head-to-head judges)
// ─────────────────────────────────────────────────────────────────────────────
async function competitiveRewrite(wholeUnitFixes, roundTag) {
  // Returns { winners: { "<anchor_unit>": "<replacement text>" } } or null on failure.
  const h2hVotes = {};      // anchor_unit -> { persona: "A"|"B" }
  const candidates = {};    // anchor_unit -> { A, B }
  for (const wf of wholeUnitFixes) {
    const unit = wf.anchor_unit;
    const rw = (await parallel([
      async () => await reader(
        `Produce a replacement for the WHOLE anchor unit "${unit}" resolving this finding. ${CTX}
Finding: ${JSON.stringify(wf)}
Return { anchor_unit, replacement } — the full replacement markdown for that unit only.`,
        { label: "rewrite-A", phase: roundTag, agentType: "Explore", schema: S_REWRITE }
      ),
      async () => await reader(
        `Independently produce a replacement for the WHOLE anchor unit "${unit}" resolving this finding. ${CTX}
Finding: ${JSON.stringify(wf)}
Return { anchor_unit, replacement } — the full replacement markdown for that unit only.`,
        { label: "rewrite-B", phase: roundTag, agentType: "Explore", schema: S_REWRITE }
      ),
    ]));
    if (!rw[0] || !rw[1]) { deadRole(`competitive rewrite for ${unit}`); return null; }
    candidates[unit] = { A: rw[0].replacement, B: rw[1].replacement };
    const judges = ["builds-wrong-thing", "implementer-blocked", "scope-intent-drift"];
    const ballots = (await parallel(judges.map((persona) => async () => {
      const r = await reader(
        `You are the "${persona}" judge. Two candidate rewrites (A and B) replace the anchor unit "${unit}". ${CTX}
Finding: ${JSON.stringify(wf)}
Candidate A: ${JSON.stringify(rw[0].replacement)}
Candidate B: ${JSON.stringify(rw[1].replacement)}
Return { ballots: { "${unit}": "A" | "B" } } — your single vote for the stronger rewrite.`,
        { label: `h2h-${persona}`, phase: roundTag, agentType: "Explore", schema: S_H2H_JUDGE }
      );
      return r ? { persona, vote: (r.ballots || {})[unit] } : null;
    }))).filter(Boolean);
    if (ballots.length < 3) { deadRole(`head-to-head panel for ${unit}`); return null; }
    h2hVotes[unit] = {};
    for (const b of ballots) h2hVotes[unit][b.persona] = b.vote === "B" ? "B" : "A";
  }

  const h2hPath = `${SCRATCH}/r${roundIndex}-h2h-votes.json`;
  const res = await relayAgent(
    `Marshal the head-to-head ballots, then compute the winners (2-of-3 majority — NEVER counted by you).
STEP 1 — write EXACTLY this JSON verbatim to ${h2hPath}:
${JSON.stringify(h2hVotes)}
STEP 2 — run: ${SPEC_CHECKS} tally --head-to-head ${h2hPath}
(Exit 1 means a key lacked a 2-of-3 majority or a panel was short — report as failure.)
${RELAY_RULE}`,
    { label: "tally-h2h", phase: roundTag, agentType: "general-purpose", schema: S_RELAY_SINGLE },
    { single: { validate: vH2H } }
  );
  if (!res) { deadRole("tally --head-to-head"); return null; }
  const winners = {};
  for (const unit of Object.keys(res.data)) winners[unit] = candidates[unit][res.data[unit].winner];
  return { winners };
}

// ─────────────────────────────────────────────────────────────────────────────
// 11. FIX & RECORD  (step-5 invocation: tally already run in runGate; here apply)
// ─────────────────────────────────────────────────────────────────────────────
async function fixAndRecord(gate, roundTag, roundLog) {
  // gate.ided: findings with ids ; gate.outcomes: id -> outcome
  // finding_atoms is the JS-computed lineage-id list (same mapping as the pendingDecisions push below) —
  // marshaled into the prompt so the context-free fixer transcribes the authoritative value into the
  // append-decision record's finding_atoms rather than guessing it from atom ids it cannot resolve.
  const findingsWithOutcome = gate.ided.map((f) => ({ ...f, outcome: gate.outcomes[f.id], finding_atoms: (f.atoms || []).map((id) => idLineageMap[id] || id) }));
  const plan = await relayAgent(
    `You are the fixer/recorder (step-5 fix-and-record invocation). ${CTX}
Changelog path: ${CHANGELOG}   Run: ${RUN}   Round: ${roundIndex}
Each finding below carries its gate outcome (auto-fixable | below-bar | needs-user | proposed-non-goal), pre-computed by the tally script — do NOT re-classify.
Findings: ${JSON.stringify(findingsWithOutcome)}

Do, in order:
  1. below-bar → ${IMPROVE} append-note ${SOURCE} --finding-id <id> "<text>" (one per below-bar finding).
  2. needs-user → ${IMPROVE} append-decision ${SOURCE} --kind decision --title "<t>" --finding "<f>" --finding-atoms '<the finding's finding_atoms field, verbatim JSON list — do NOT derive or guess it>'  (the id is allocated BY the script; relay its {"id":...} stdout, tagged "append-decision:<finding-id>").
  3. proposed-non-goal → ${IMPROVE} append-decision ${SOURCE} --kind non-goal-proposal --title "<t>" --finding "<f>" (relay tagged the same way).
  4. auto-fixable → EDIT the working copy to apply the fix, then ${IMPROVE} append-changelog ${SOURCE} --run ${RUN} --round ${roundIndex} --kind fix "<what changed>". For a fix that replaces at least one WHOLE anchor unit (### or the enclosing ## in heading-free regions), DO NOT edit yet — flag it whole_unit:true with its anchor_unit (a competitive rewrite lands it later).
Report a plan array: one entry per finding { finding_id, outcome, whole_unit, anchor_unit }, plus decisions_created:[{finding_id,decision_id}], below_bar_count, fixed_count (non-whole auto-fixes applied), and touched_sections (raw headings you edited).
${RELAY_KEYED_RULE} Relay each append-decision's {"id":...} stdout under the tag "append-decision:<finding-id>".`,
    { label: "fix-plan", phase: roundTag, agentType: "general-purpose", schema: S_FIX_PLAN },
    { keyed: (findingsWithOutcome.filter((f) => f.outcome === "needs-user" || f.outcome === "proposed-non-goal").map((f) => ({ tag: `append-decision:${f.id}`, validate: vAllocId }))) }
  );
  if (!plan) { deadRole("fixer step-5 fix-plan"); return null; }

  // Agent-authored S_FIX_PLAN fields live on plan.ret; plan.data holds ONLY the keyed
  // append-decision:<finding-id> relays (the script-allocated decision ids).
  fixed += plan.ret.fixed_count || 0;
  belowBar += plan.ret.below_bar_count || 0;
  roundLog.findings = gate.ided.map((f) => ({ id: f.id, atoms: f.atoms || [], evidence: f.detail || f.evidence || "" }));
  roundLog.votes = gate.votes;
  roundLog.tally = gate.outcomes;

  // Register newly-created decision records as pending for Decide.
  // finding_id is agent-authored (plan.ret); the authoritative decision_id is the
  // script-allocated value bound from the validated append-decision:<finding-id> relay.
  const created = plan.ret.decisions_created || [];
  for (const d of created) {
    const relay = plan.data[`append-decision:${d.finding_id}`];
    const decisionId = (relay && relay.id) ? relay.id : d.decision_id;
    if (!decisionId) continue; // no script-allocated id → nothing to re-attempt
    const src = gate.ided.find((f) => f.id === d.finding_id) || {};
    pendingDecisions.push({ decision_id: decisionId, finding_atoms: (src.atoms || []).map((id) => idLineageMap[id] || id), macro: !(src.atoms && src.atoms.length) });
  }

  // Competitive structural rewrite for whole-unit fixes.
  const wholeUnit = (plan.ret.plan || []).filter((p) => p.whole_unit && p.outcome === "auto-fixable");
  let touched = plan.ret.touched_sections || [];
  if (wholeUnit.length) {
    const cr = await competitiveRewrite(wholeUnit.map((p) => ({ anchor_unit: p.anchor_unit, finding: gate.ided.find((f) => f.id === p.finding_id) })), roundTag);
    if (!cr) return null;
    roundLog.head_to_head = cr.winners;
    const applyRes = await relayAgent(
      `You are the fixer/recorder (competitive-rewrite APPLY invocation). ${CTX}
Changelog: ${CHANGELOG}   Run: ${RUN}   Round: ${roundIndex}
Land each winning rewrite as an ordinary fix: EDIT the working copy to replace the whole anchor unit with the winning text, then ${IMPROVE} append-changelog ${SOURCE} --run ${RUN} --round ${roundIndex} --kind fix "<unit> rewritten".
Winners (anchor_unit -> replacement markdown): ${JSON.stringify(cr.winners)}
After landing all winners, report the anchor units you touched.
Return script_output as an empty list (the append-changelog calls are side-effecting, not branch-driving).`,
      { label: "fix-apply", phase: roundTag, agentType: "general-purpose", schema: S_RELAY_KEYED },
      { keyed: [] }
    );
    if (!applyRes) { deadRole("fixer competitive-rewrite apply"); return null; }
    fixed += wholeUnit.length;
    touched = touched.concat(Object.keys(cr.winners));
    for (const p of plan.ret.plan) if (p.whole_unit) markStructuralTrigger();
  }
  return { touched };
}

let structuralTrigger = false;
function markStructuralTrigger() { structuralTrigger = true; }

// ─────────────────────────────────────────────────────────────────────────────
// 12. DECIDE  (researchers per decision → decision-taker: radius + block-gate → take/block)
// ─────────────────────────────────────────────────────────────────────────────
async function decide(roundTag, roundLog) {
  if (!pendingDecisions.length) return { blocked: false, touched: [] };
  const queue = pendingDecisions.slice();
  pendingDecisions = [];
  nullCallCarry = [];

  // One researcher per decision (read-only).
  const research = (await parallelCapped(queue.map((d) => async () => {
    const r = await reader(
      `Research decision ${d.decision_id} for autonomous take. ${CTX}
Finding atoms (lineage ids, empty ⇒ macro-derived — you must name the units yourself): ${JSON.stringify(d.finding_atoms)}
Gather codebase context, enumerate 2-4 options with tradeoffs, give a recommendation, and DECLARE your edit-estimate section set (the anchor units your recommendation would write/amend). Also declare: confidence (high|low), near_tie (top two options within a small value margin?), reverses_directive (does the recommendation reverse an explicit user directive?), reverses_non_goal (does it reverse a NON-GOALS entry?).
Return the S_RESEARCH shape with decision_id set to ${d.decision_id}.`,
      { label: `research-${d.decision_id}`, phase: roundTag, agentType: "Explore", schema: S_RESEARCH }
    );
    return r ? { d, r } : { d, r: null };
  })));

  // Decision-taker: per decision run `atoms radius` (pyramid) then `block-gate`; on takeable write D-block.
  const takeInputs = [];
  for (const item of research) {
    if (!item.r) { nullCallCarry.push(item.d); pendingDecisions.push(item.d); continue; } // researcher died → carry to next round untaken
    takeInputs.push({ decision_id: item.d.decision_id, finding_atoms: item.d.finding_atoms, macro: item.d.macro, research: item.r });
  }
  if (!takeInputs.length) return { blocked: false, touched: [] };

  const radiusTags = takeInputs.filter((t) => !t.macro).map((t) => ({ tag: `radius:${t.decision_id}`, validate: vRadius }));
  const gateTags = takeInputs.map((t) => ({ tag: `block-gate:${t.decision_id}`, validate: vBlockGate }));

  const takerRes = await relayAgent(
    `You are the decision-taker (Bash+Edit). ${CTX}
Decisions to resolve (each with its researcher's output): ${JSON.stringify(takeInputs)}
Changelog: ${CHANGELOG}   DECISIONS.json is written ONLY via ${IMPROVE} update-decision.   Run: ${RUN}   Round: ${roundIndex}

For EACH decision:
  1. Pre-take radius (evidence footprint), for decisions with finding_atoms (lineage ids):
       ${SPEC_CHECKS} atoms radius --ledger ${LEDGER} --atoms '<json lineage-id list>'   (relay tagged "radius:<id>")
     For a macro decision (empty finding_atoms) the researcher named the units — skip radius.
  2. Marshal a block-gate inputs file to ${SCRATCH}/r${roundIndex}-blockgate-<id>.json with:
       { "evidence_sections": <the atoms radius "sections", or [] for macro>,
         "estimate_sections": <researcher edit_estimate_sections>,
         "reverses_directive": <researcher bool>, "reverses_non_goal": <researcher bool> }
     then run: ${SPEC_CHECKS} block-gate ${SCRATCH}/r${roundIndex}-blockgate-<id>.json   (relay tagged "block-gate:<id>" — the script UNIONS the two section sets and counts; you NEVER do set arithmetic.)
  3. On verdict "takeable": record the take metadata — ${IMPROVE} append-changelog ${SOURCE} --run ${RUN} --round ${roundIndex} --kind decision-take "<title>", and ${IMPROVE} update-decision ${SOURCE} --id <id> --set '<json: taken, taken_by:"auto", research, options, pre_take_radius, post_take_radius, confidence, near_tie, review_first (true on low confidence OR near_tie OR a large sub-threshold radius), semantic_depends_on>'.
       Take the recommendation by default; on low confidence or a near-tie take the smaller-blast-radius option.
       For the D-block text: if the take writes/amends a WHOLE anchor unit (### D-block, or the enclosing ## in a heading-free region), DO NOT edit the D-block yet — flag whole_unit:true with its anchor_unit; a competitive rewrite lands it later. Otherwise EDIT the working copy to apply the partial D-block amendment now and set whole_unit:false.
  4. On verdict "blocked": ${IMPROVE} update-decision ${SOURCE} --id <id> --set '<json: untakeable "<reason>">' and mark the decision blocked (do NOT write a D-block).
Report verdicts:[{decision_id, verdict, post_take_sections, post_take_atoms, whole_unit, anchor_unit}] — whole_unit/anchor_unit set only on a whole-unit takeable take.
${RELAY_KEYED_RULE}`,
    { label: "decision-taker", phase: roundTag, agentType: "general-purpose", schema: S_DECIDE },
    { keyed: radiusTags.concat(gateTags) }
  );
  if (!takerRes) { deadRole("decision-taker"); return null; }

  // Branch `blocked` ONLY on the validated block-gate relay (takerRes.data), NEVER the
  // agent's paraphrased verdicts. Agent-authored post-take fields come off takerRes.ret.
  const retVerdicts = (takerRes.ret && Array.isArray(takerRes.ret.verdicts)) ? takerRes.ret.verdicts : [];
  const retById = {};
  for (const v of retVerdicts) if (v && v.decision_id) retById[v.decision_id] = v;

  let blocked = false;
  const touched = [];
  const wholeUnitTakes = [];
  for (const t of takeInputs) {
    const id = t.decision_id;
    const g = takerRes.data[`block-gate:${id}`];
    if (!g) { deadRole(`decision-taker missing block-gate relay for ${id}`); return null; }
    if (g.verdict === "blocked") { blocked = true; continue; }
    // takeable — fold this take's post-take sections so round-close mark-dirty re-verifies
    // every atom whose input set names a decision-edited section (concept step 6 round-close).
    const v = retById[id] || {};
    for (const s of (v.post_take_sections || [])) touched.push(s);
    if (v.whole_unit && v.anchor_unit) {
      wholeUnitTakes.push({ anchor_unit: v.anchor_unit, finding: { decision_id: id, research: t.research, detail: `decision-take ${id}` } });
    }
  }

  // A whole-unit decision take fires the competitive rewrite (2 rewrites + 3-judge head-to-head)
  // and queues the scoped structural re-check, exactly like a phase-P whole-unit fix (concept step 7).
  if (wholeUnitTakes.length) {
    const cr = await competitiveRewrite(wholeUnitTakes, roundTag);
    if (!cr) return null;
    roundLog.head_to_head = Object.assign({}, roundLog.head_to_head || {}, cr.winners);
    const applyRes = await relayAgent(
      `You are the decision-take rewrite APPLY agent (Bash+Edit). ${CTX}
Changelog: ${CHANGELOG}   Run: ${RUN}   Round: ${roundIndex}
Land each winning D-block rewrite as the decision take: EDIT the working copy to replace the WHOLE anchor unit with the winning text, then ${IMPROVE} append-changelog ${SOURCE} --run ${RUN} --round ${roundIndex} --kind decision-take "<unit> rewritten".
Winners (anchor_unit -> replacement markdown): ${JSON.stringify(cr.winners)}
Return script_output as an empty list (the append-changelog calls are side-effecting, not branch-driving).`,
      { label: "decision-take-apply", phase: roundTag, agentType: "general-purpose", schema: S_RELAY_KEYED },
      { keyed: [] }
    );
    if (!applyRes) { deadRole("decision-take competitive-rewrite apply"); return null; }
    for (const u of Object.keys(cr.winners)) touched.push(u);
    markStructuralTrigger();
  }

  return { blocked, touched };
}

// ─────────────────────────────────────────────────────────────────────────────
// 13. ROUND CLOSE  (pinned order: reanchor+mark-dirty → scoped extract → record-verdicts → coverage → snapshot)
// ─────────────────────────────────────────────────────────────────────────────
async function roundClose(roundLog, touchedSections) {
  const touchedJson = JSON.stringify(touchedSections || []);
  // (a) reanchor + mark-dirty — fold post-step-5 edits (auto-fixes, D-block writes, directive edits).
  const raRes = await relayAgent(
    `You are the round-close fixer/recorder (Bash+Edit), part 1: fold this round's edits into the ledger delta.
Run, and relay each:
  ${SPEC_CHECKS} atoms reanchor ${DOC} --ledger ${LEDGER}                 (tag "reanchor")
  ${SPEC_CHECKS} atoms mark-dirty ${DOC} --ledger ${LEDGER} --touched '${touchedJson}'   (tag "mark-dirty")
Both are pure compute-and-relay — they write nothing.
${RELAY_KEYED_RULE}`,
    { label: "round-close-reanchor", phase: `round-${roundIndex}`, agentType: "general-purpose", schema: S_RELAY_KEYED },
    { keyed: [{ tag: "reanchor", validate: vReanchor }, { tag: "mark-dirty", validate: vMarkDirty }] }
  );
  if (!raRes) { deadRole("round-close reanchor/mark-dirty"); return null; }
  const reanchor = raRes.data["reanchor"];
  const markDirty = raRes.data["mark-dirty"];
  applyReanchor(reanchor);
  roundLog.reanchor_delta = { relocated: reanchor.relocated, vanished: reanchor.vanished, external_stale: reanchor.external_stale };
  roundLog.dirty = markDirty.dirty;

  // (b) if reanchor flags new regions, the WORKFLOW spawns scoped prose extractors; round-close fixer runs
  //     region-scoped extract (emit-only) + merge (emit-only). Conditional stage (D2).
  let newAtomIds = [];
  if (reanchor.new_regions && reanchor.new_regions.length) {
    const regions = reanchor.new_regions;
    const proseCands = (await parallel([
      async () => await reader(`Extract prose atoms (claims, assumptions, scope items, examples) ONLY from these edited regions of ${DOC}: ${JSON.stringify(regions)}. ${CTX} Return { candidates: [ {type, anchor, text, span} ... ] }.`, { label: "scoped-extract-A", agentType: "Explore", schema: S_CANDIDATES }),
      async () => await reader(`Independently extract prose atoms ONLY from these edited regions of ${DOC}: ${JSON.stringify(regions)}. ${CTX} Return { candidates: [ {type, anchor, text, span} ... ] }.`, { label: "scoped-extract-B", agentType: "Explore", schema: S_CANDIDATES }),
    ]));
    const c1 = proseCands[0] ? proseCands[0].candidates : [];
    const c2 = proseCands[1] ? proseCands[1].candidates : [];
    const f1 = `${SCRATCH}/r${roundIndex}-inc-cand1.json`;
    const f2 = `${SCRATCH}/r${roundIndex}-inc-cand2.json`;
    const incRes = await relayAgent(
      `You are the round-close fixer/recorder, part 2 (incremental extraction — EMIT ONLY, writes nothing; the atoms persist via record-verdicts below).
STEP 1 — write ${JSON.stringify(c1)} verbatim to ${f1} and ${JSON.stringify(c2)} verbatim to ${f2}.
STEP 2 — region-scoped mechanical extraction: ${SPEC_CHECKS} atoms extract ${DOC}    (emit-only; tag "extract")
STEP 3 — merge prose candidates against mechanical spans: ${SPEC_CHECKS} atoms merge ${DOC} --ledger ${LEDGER} --candidates ${f1},${f2}    (emit-only, no --write; tag "merge")
${RELAY_KEYED_RULE}`,
      { label: "round-close-incremental", phase: `round-${roundIndex}`, agentType: "general-purpose", schema: S_RELAY_KEYED },
      { keyed: [{ tag: "extract", validate: vExtract }, { tag: "merge", validate: vMerge }] }
    );
    if (!incRes) { deadRole("round-close incremental extraction"); return null; }
    const merged = incRes.data["merge"].merged_atoms || [];
    roundLog.new_atoms = merged;
    newAtomIds = ingestAtoms(merged);
  }

  // (c) marshal the whole round delta → record-verdicts (sole round-close writer); assert applied === marshaled.
  const verdictLog = {
    run: RUN,
    round: roundIndex,
    atom_verdicts: roundLog.atom_verdicts || [],
    reanchor_delta: {
      relocated: (roundLog.reanchor_delta.relocated || []).map((r) => ({ id: r.id, new: r.new })),
      vanished: roundLog.reanchor_delta.vanished || [],
      external_stale: roundLog.reanchor_delta.external_stale || [],
    },
    dirty: roundLog.dirty || [],
    new_atoms: roundLog.new_atoms || [],
    macro_findings: roundLog.macro_findings || [],
  };
  const marshaledCount = verdictLog.atom_verdicts.length;
  const vpath = `${SCRATCH}/r${roundIndex}-verdicts.json`;
  const recRes = await relayAgent(
    `You are the round-close fixer/recorder, part 3: persist this round's whole delta (the SOLE round-close ledger write).
STEP 1 — write EXACTLY this JSON verbatim to ${vpath}:
${JSON.stringify(verdictLog)}
STEP 2 — run: ${SPEC_CHECKS} atoms record-verdicts --ledger ${LEDGER} --verdicts ${vpath}   (NOTE: no <doc> positional.)
This marshaled ${marshaledCount} atom_verdicts — the script echoes {"applied":N}; relay it verbatim so the JS can assert applied === ${marshaledCount}.
${RELAY_RULE}`,
    { label: "record-verdicts", phase: `round-${roundIndex}`, agentType: "general-purpose", schema: S_RELAY_SINGLE },
    { single: { validate: vRecord } }
  );
  if (!recRes) { deadRole("record-verdicts"); return null; }
  if (recRes.data.applied !== marshaledCount) { deadRole(`record-verdicts applied ${recRes.data.applied} != marshaled ${marshaledCount}`); return null; }

  // (d) coverage — AFTER record-verdicts so `complete` reflects this round.
  const covRes = await relayAgent(
    `Round-close part 4: read coverage AFTER the delta persisted.
Run: ${SPEC_CHECKS} atoms coverage --ledger ${LEDGER}
${RELAY_RULE}`,
    { label: "coverage", phase: `round-${roundIndex}`, agentType: "general-purpose", schema: S_RELAY_SINGLE },
    { single: { validate: vCoverage } }
  );
  if (!covRes) { deadRole("coverage"); return null; }

  // (d2) churn-check — read step-7 escalation sets AFTER record-verdicts bumped the churn counters.
  // The relayed sets seed the NEXT round's escalateChurn (set membership only — thresholds stay in Python).
  const churnRes = await relayAgent(
    `Round-close part 4b: read the step-7 churn escalation sets AFTER the delta persisted.
Run: ${SPEC_CHECKS} atoms churn-check --ledger ${LEDGER}
${RELAY_RULE}`,
    { label: "churn-check", phase: `round-${roundIndex}`, agentType: "general-purpose", schema: S_RELAY_SINGLE },
    { single: { validate: vChurnCheck } }
  );
  if (!churnRes) { deadRole("churn-check"); return null; }
  churnSets = {
    flip: new Set(churnRes.data.flip_escalate_lineages || []),
    fix: new Set(churnRes.data.fix_escalate_lineages || []),
    macros: new Set(churnRes.data.escalate_macros || []),
  };

  // (e) snapshot — exactly one per round, after decision-take edits.
  await callAgent(
    `Round-close part 5: archive this round.
Run: ${IMPROVE} snapshot ${SOURCE} --run ${RUN} --round ${roundIndex} --verdicts ${vpath}
(Idempotent on a byte-match; exit 1 only on a genuinely reused run number.) This is side-effecting; no relay needed.`,
    { label: "snapshot", phase: `round-${roundIndex}`, agentType: "general-purpose" }
  );

  return { coverage: covRes.data, newAtomIds };
}

// ─────────────────────────────────────────────────────────────────────────────
// 14. SHARED FINDINGS-ROUND PIPELINE (dedup → below-bar drop → gate → fix → decide)
// ─────────────────────────────────────────────────────────────────────────────
async function processFindings(rawFindings, noteIds, roundTag, roundLog) {
  if (!rawFindings.length && !pendingDecisions.length) return { substantive: false, blocked: false, touched: [] };

  // Global dedup (read-only, sees DECISIONS.json) — fold re-emissions BEFORE the gate.
  let findings = rawFindings;
  if (rawFindings.length) {
    const ded = await reader(
      `You are the global dedup agent. ${CTX}
You MAY read DECISIONS.json (${DECISIONS}) directly. Fold any candidate finding that re-surfaces an ALREADY-RECORDED decision or an ACTIVE (non-dropped) non-goal proposal into that record — suppress-with-reference (drop it, note the record id). A proposal the user DROPPED is NOT folded — keep it. The match is semantic (same decision subject restated), not id-equality.
Candidate findings: ${JSON.stringify(rawFindings.map((f) => ({ id: f.id || findingId(f), detail: f.detail || f.evidence || "", sections: f.sections || [], atoms: f.atoms || [] })))}
Return { kept: [ <the candidate findings that survive, unchanged> ], folded: [ {finding_id, record_id} ] }.`,
      { label: "dedup", phase: roundTag, agentType: "Explore", schema: S_DEDUP }
    );
    if (ded && Array.isArray(ded.kept)) {
      const keptIds = new Set(ded.kept.map((k) => k.id));
      findings = rawFindings.filter((f) => keptIds.has(f.id || findingId(f)));
    } // dedup death degrades to no-fold (findings pass through) — exit exam is the guard.
  }

  // Below-bar memory: JS set-difference vs relayed note-ids (deterministic id-equality; never judge-injected).
  findings = dropBelowBar(findings, noteIds);

  // Gate.
  let touched = [];
  let substantive = false;
  if (findings.length) {
    const gate = await runGate(findings, roundTag);
    if (!gate) return null; // panel died → round-cap
    // Churn escalation (concept step 7): override matching findings to needs-user BEFORE the fixer reads
    // the outcomes — a set-membership lookup against churn-check's script-computed escalation sets.
    escalateChurn(gate);
    // Floor findings are definitionally substantive — force them out of any below-bar/exclusion outcome the
    // judges may have voted, so they are always fixed (or routed to Decide) and never note-suppressed.
    forceFloorOutcomes(gate);
    roundLog._outcomes = gate.outcomes; // MINOR 2: consulted by markMacroFixed after this returns.
    const outVals = Object.values(gate.outcomes);
    substantive = outVals.some((o) => o === "auto-fixable" || o === "needs-user");
    const fr = await fixAndRecord(gate, roundTag, roundLog);
    if (!fr) return null;
    touched = fr.touched;
  }

  // Decide (conditional — only if there are pending decisions).
  const dec = await decide(roundTag, roundLog);
  if (dec === null) return null;
  // Union the decision-takes' post-take sections into the round's touched set so round-close
  // mark-dirty folds every edit made after step 5 — each D-block write/amendment (concept step 6).
  touched = touched.concat(dec.touched || []);

  return { substantive, blocked: dec.blocked, touched };
}

// ─────────────────────────────────────────────────────────────────────────────
// 15. DIRECTIVE PRELUDE  (only on a directive/override run)
// ─────────────────────────────────────────────────────────────────────────────
async function applyPrelude() {
  if (!OVERRIDES.length && !DIRECTIVES.length) return true;
  phase("Directive prelude");
  const res = await relayAgent(
    `You are the directive apply agent (Bash+Edit). ${CTX}
Changelog: ${CHANGELOG}   DECISIONS.json via ${IMPROVE} update-decision.   Run: ${RUN}
FREE-FORM DIRECTIVES (edit the working copy, log each with ${IMPROVE} append-changelog ${SOURCE} --run ${RUN} --round 0 --kind fix "<what>"):
${JSON.stringify(DIRECTIVES)}
STRUCTURED OVERRIDES (each carries a decision_id):
${JSON.stringify(OVERRIDES)}
  For an override of an already-TAKEN decision: ${IMPROVE} update-decision ${SOURCE} --id <id> --set '{"taken":"<user resolution>","taken_by":"user"}' (the prior take moves to superseded by the script), then re-dirty its recorded post_take_radius by editing/touching those units.
  For a resolved BLOCKED decision (no prior take): ${IMPROVE} update-decision ${SOURCE} --id <id> --set '{"taken":"<user resolution>","taken_by":"user","post_take_radius":<now-known>}' and edit the touched units (which dirties their atoms).
FINALLY run: ${SPEC_CHECKS} atoms reanchor ${DOC} --ledger ${LEDGER}   (so the JS can fold your edits into the dirty set; tag "reanchor")
${RELAY_KEYED_RULE}`,
    { label: "apply-agent", phase: "prelude", agentType: "general-purpose", schema: S_RELAY_KEYED },
    { keyed: [{ tag: "reanchor", validate: vReanchor }] }
  );
  if (!res) { deadRole("directive apply agent"); return false; }
  applyReanchor(res.data["reanchor"]);
  return true;
}

// ─────────────────────────────────────────────────────────────────────────────
// 16. PHASE H — Horizontal (macro first, D12)
// ─────────────────────────────────────────────────────────────────────────────
async function phaseH(scoped) {
  phase("Horizontal macro pass");
  while (status === null) {
    if (brakeCheck({ phaseHqueued: true })) return;
    roundIndex++;
    const roundLog = { atom_verdicts: [], macro_findings: [] };

    // 2-3 whole-document readers hunting macro classes only.
    const readerThunks = [1, 2, 3].map((n) => async () => {
      const r = await reader(
        `You are whole-document reader #${n} in the horizontal (macro-first) phase. ${CTX}
Hunt ONLY macro classes: gaps (undefined flows, missing connective tissue, deferred commitments / parked open questions that should be settled now), disconnects (sections that do not compose), contradictions (across distant sections), and the simpler-whole-design alternative (subsumes over-engineering — any component more elaborate than its job requires).${scoped ? " SCOPED re-check: focus on the recently edited slices." : ""}
Return { findings: [ {klass, sections:[canonical section paths], detail, decision_shaped} ] }.`,
        { label: `macro-reader-${n}`, phase: `H-round-${roundIndex}`, agentType: "Explore", schema: S_FINDINGS }
      );
      return r ? r.findings : null;
    });
    const pooled = (await parallel(readerThunks)).filter(Boolean).flat().filter(Boolean);

    if (!pooled.length) { log("Phase H dry — no substantive macro finding."); return; } // → decompose

    // Macro finding-ids are canonical script-computed values (attachMacroIds), never a JS sort/join.
    const macroFindings = await attachMacroIds(pooled, `H-round-${roundIndex}`);
    if (macroFindings === null) { deadRole("phase-H macro-ids"); return; }

    const noteIds = await fetchNoteIds();
    const res = await processFindings(macroFindings, noteIds, `H-round-${roundIndex}`, roundLog);
    if (res === null) return; // status already round-cap

    // Record macro findings in the ledger's macro table; fixed:true (→ fix_count bump) only when auto-fixed.
    markMacroFixed(macroFindings, roundLog);

    const closed = await roundClose(roundLog, res.touched);
    if (closed === null) return;
    if (res.blocked) { status = "blocked"; return; }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 17. PHASE P ENTRY — one-time full decompose (step 1)
// ─────────────────────────────────────────────────────────────────────────────
async function decomposeEntry() {
  phase("Atom decomposition");
  // Two redundant prose extractors (read-only) → candidate sets.
  const proseCands = (await parallel([
    async () => await reader(`Extract prose atoms (claims, assumptions, scope items, examples) from the WHOLE working copy ${DOC}. ${CTX} Anchor each by section path (### where present, enclosing ## otherwise). Return { candidates: [ {type, anchor, text, span} ] }.`, { label: "prose-extract-A", phase: "decompose", agentType: "Explore", schema: S_CANDIDATES }),
    async () => await reader(`Independently extract prose atoms from the WHOLE working copy ${DOC}. ${CTX} Return { candidates: [ {type, anchor, text, span} ] }.`, { label: "prose-extract-B", phase: "decompose", agentType: "Explore", schema: S_CANDIDATES }),
  ]));
  const c1 = proseCands[0] ? proseCands[0].candidates : [];
  const c2 = proseCands[1] ? proseCands[1].candidates : [];
  const f1 = `${SCRATCH}/decompose-cand1.json`;
  const f2 = `${SCRATCH}/decompose-cand2.json`;

  const res = await relayAgent(
    `You are the decompose agent (Bash+Edit) — the one-time entry pass against an empty ledger. ${CTX}
STEP 1 — mechanical atoms (headings, D-blocks, citations, code-fenced contracts), PERSISTING them:
    ${SPEC_CHECKS} atoms extract ${DOC} --ledger ${LEDGER} --write     (tag "extract")
STEP 2 — write the two relayed prose candidate sets verbatim: ${JSON.stringify(c1)} → ${f1} , ${JSON.stringify(c2)} → ${f2}
STEP 3 — merge + persist the prose atoms (candidates overlapping a mechanical span are dropped by the script):
    ${SPEC_CHECKS} atoms merge ${DOC} --ledger ${LEDGER} --candidates ${f1},${f2} --write     (tag "merge")
${RELAY_KEYED_RULE}`,
    { label: "decompose", phase: "decompose", agentType: "general-purpose", schema: S_RELAY_KEYED },
    { keyed: [{ tag: "extract", validate: vExtract }, { tag: "merge", validate: vMerge }] }
  );
  if (!res) { deadRole("decompose entry pass"); return null; }
  const all = ingestAtoms((res.data["extract"].atoms || []).concat(res.data["merge"].merged_atoms || []));
  // Worklist = all non-heading atoms, unverified.
  return all.filter((id) => idTypeMap[id] !== "heading");
}

// ─────────────────────────────────────────────────────────────────────────────
// 18. PHASE P — per-round pyramid (steps 2-7)
// ─────────────────────────────────────────────────────────────────────────────
async function phasePRound(worklist) {
  const roundLog = { atom_verdicts: [], macro_findings: [] };
  const dirtyScopeItems = worklist.filter((id) => idTypeMap[id] === "scope-item");
  const sectionsGuess = new Set(worklist.map((id) => idAnchorMap[id] || "")).size;
  if (brakeCheck({ dirty: worklist.length, sections: sectionsGuess, pending: pendingDecisions.length, scopeItems: dirtyScopeItems.length, regionsAwaiting: false, phaseHqueued: structuralTrigger, wholeUnitFixes: 0 })) return null;
  roundIndex++;

  // Scoped phase-H re-check queued by a prior structural edit runs as the opening step.
  if (structuralTrigger) {
    structuralTrigger = false;
    const recheckThunks = [1, 2].map((n) => async () => {
      const r = await reader(`Whole-document reader #${n}, SCOPED structural re-check of recently rewritten slices of ${DOC}. ${CTX} Hunt macro classes (gaps, disconnects, contradictions, simpler-whole-design) introduced by the structural edit. Return { findings:[{klass,sections,detail,decision_shaped}] }.`, { label: `struct-recheck-${n}`, phase: `P-round-${roundIndex}`, agentType: "Explore", schema: S_FINDINGS });
      return r ? r.findings : null;
    });
    const recheckRaw = (await parallel(recheckThunks)).filter(Boolean).flat().filter(Boolean);
    if (recheckRaw.length) {
      const recheck = await attachMacroIds(recheckRaw, `P-round-${roundIndex}`);
      if (recheck === null) { deadRole("structural re-check macro-ids"); return null; }
      const noteIds0 = await fetchNoteIds();
      const rr = await processFindings(recheck, noteIds0, `P-round-${roundIndex}`, roundLog);
      if (rr === null) return null;
      markMacroFixed(recheck, roundLog);
      if (rr.blocked) { const closed0 = await roundClose(roundLog, rr.touched); if (closed0 === null) return null; status = "blocked"; return null; }
    }
  }

  // STEP 2 — VERIFY swarm (1 per dirty/unverified atom) + floor agent + implementability probes, concurrently.
  const verifyThunks = worklist.map((id) => async () => {
    const t = idTypeMap[id] || "claim";
    if (t === "heading") return null;
    const r = await reader(
      `You are a verifier for a single atom. ${CTX}
Atom id: ${id}   type: ${t}   anchor: ${idAnchorMap[id] || "(infer from text)"}
Check: ${CHECK_BY_TYPE[t] || CHECK_BY_TYPE.claim}
Answer this one narrow question with minimal context. Return { atom_id:"${id}", state:"verified"|"unverifiable", finding_conclusion:<finding text, or null if sound>, computed_against_hash:"<the atom's current text hash>", input_set:{sections:[canonical paths you read], external:[{path,hash} for code files you read]} }.
A completed check that cannot settle from spec+cited inputs alone returns state:"unverifiable".`,
      { label: `verify-${id}`, phase: `P-round-${roundIndex}`, agentType: "Explore", schema: S_VERIFIER }
    );
    return r;
  });

  const floorThunk = async () => await relayAgent(
    `You are the floor agent (Bash). ${CTX}
Run BOTH and relay each:
  ${SPEC_CHECKS} floor ${DOC}                 (tag "floor" — exit 1 means violations FOUND, which is a finding, not a failure; capture and relay its stdout JSON regardless)
  ${IMPROVE} note-ids ${SOURCE}               (tag "note-ids")
${RELAY_KEYED_RULE}`,
    { label: "floor", phase: `P-round-${roundIndex}`, agentType: "general-purpose", schema: S_RELAY_KEYED },
    { keyed: [{ tag: "floor", validate: vFloor }, { tag: "note-ids", validate: vNoteIds }] }
  );

  const probeThunks = dirtyScopeItems.map((id) => async () => {
    const res = await parallel([
      async () => await reader(`Implementability probe A for scope item ${id} (anchor ${idAnchorMap[id] || ""}). ${CTX} Answer: what would you build for this ONE bullet, and which decisions would you have to make yourself? Return { atom_id:"${id}", state:"verified", finding_conclusion:null, input_set:{sections:[],external:[]} } but put your build description in finding_conclusion.`, { label: `probe-A-${id}`, phase: `P-round-${roundIndex}`, agentType: "Explore", schema: S_VERIFIER }),
      async () => await reader(`Implementability probe B for scope item ${id}. ${CTX} Same question, independently. Same return shape.`, { label: `probe-B-${id}`, phase: `P-round-${roundIndex}`, agentType: "Explore", schema: S_VERIFIER }),
    ]);
    if (!res[0] || !res[1]) return null;
    const cmp = await reader(`Comparator: diff these two build-plans for scope item ${id}. Divergence ⇒ an underdetermination finding. A:${JSON.stringify(res[0].finding_conclusion)} B:${JSON.stringify(res[1].finding_conclusion)}. Return { findings:[ {type:"scope-item", atoms:["${id}"], evidence:"<divergence>", decision_shaped:true} ] } (empty findings if they agree).`, { label: `comparator-${id}`, phase: `P-round-${roundIndex}`, agentType: "Explore", schema: S_AGG });
    return cmp ? cmp.findings : [];
  });

  const [verifierResults, floorRes, ...probeResults] = await Promise.all([
    parallelCapped(verifyThunks),
    floorThunk(),
    ...probeThunks.map((t) => t()),
  ]);
  const verdicts = verifierResults.filter(Boolean);
  // Dead verifiers leave their atoms unverified → they re-enter next round; coverage will report incomplete.
  roundLog.atom_verdicts = verdicts.map((v) => ({
    atom_id: v.atom_id,
    finding_conclusion: v.finding_conclusion || "sound",
    state: v.state || "verified",
    computed_against_hash: v.computed_against_hash || "",
    input_set: v.input_set || { sections: [], external: [] },
  }));

  // Unverifiable atoms → append to IMPLEMENTER-NOTES (advisory) and count as covered.
  const unverifiable = verdicts.filter((v) => v.state === "unverifiable");

  // Floor + note-ids relays. Floor green (status === "pass") is a phase-E entry condition (MINOR 1);
  // floor findings are definitionally substantive — they join the gate but are excluded from below-bar
  // note-suppression and forced to an actionable outcome (see dropBelowBar / forceFloorOutcomes).
  let floorFindings = [];
  let noteIds = [];
  let floorGreen = true;
  if (floorRes) {
    const floor = floorRes.data["floor"];
    noteIds = floorRes.data["note-ids"] || [];
    if (floor && floor.status === "fail") {
      floorGreen = false;
      floorFindings = (floor.findings || []).map((ff) => ({ klass: "floor", type: "floor", sections: [ff.heading || ""], detail: ff.detail || ff.source, atoms: [] }));
    }
  } else {
    floorGreen = false;              // floor died → green cannot be confirmed → not a phase-E-entry round
    noteIds = await fetchNoteIds();  // floor died → still fetch memory; floor findings degrade to none this round
  }

  // STEP 3 — AGGREGATE (1 per section with verdicts; slice-only, never the raw dump).
  const bySection = {};
  for (const v of verdicts) {
    const sec = (v.input_set && v.input_set.sections && v.input_set.sections[0]) || idAnchorMap[v.atom_id] || "(unanchored)";
    (bySection[sec] = bySection[sec] || []).push(v);
  }
  const aggThunks = Object.keys(bySection).map((sec) => async () => {
    const r = await reader(
      `You are a per-section aggregator for section "${sec}". ${CTX}
Compose evidence-chained candidate findings from WITHIN-section patterns only (unanswered contract questions clustering, several dirty atoms on one D-block). Do NOT compose cross-section relationships. Every finding names the atom ids it stands on.
This section's verdicts (slice only): ${JSON.stringify(bySection[sec].map((v) => ({ atom_id: v.atom_id, state: v.state, finding_conclusion: v.finding_conclusion })))}
Return { findings:[ {type, atoms:[ids], evidence, decision_shaped} ] }.`,
      { label: `aggregate-${sec}`, phase: `P-round-${roundIndex}`, agentType: "Explore", schema: S_AGG }
    );
    return r ? r.findings : []; // aggregator death leaves its section uncomposed → re-attempted next round.
  });
  const aggFindings = (await parallelCapped(aggThunks)).flat();
  const probeFindings = probeResults.filter(Boolean).flat();

  // Churn escalation: any finding whose atoms accumulated fix_count/verdict_flips >=2 routes to Decide.
  // (Churn counters are ledger-owned; the aggregators/verifiers surface re-emergence, the ledger tracks the count —
  //  record-verdicts bumps it. Here we simply forward decision_shaped findings; the gate's needs-user vote escalates.)

  const candidateFindings = []
    .concat(aggFindings.map((f) => ({ ...f, klass: f.type, id: findingId(f) })))
    .concat(floorFindings.map((f) => ({ ...f, id: findingId(f) })))
    .concat(probeFindings.map((f) => ({ ...f, klass: f.type, id: findingId(f) })));

  // Record unverifiable notes via the fixer path piggy-backed as below-bar-style notes is handled by fixAndRecord;
  // but unverifiable atoms specifically go straight to append-note here (they are not gate findings).
  if (unverifiable.length) {
    await callAgent(
      `Append these UNVERIFIABLE atoms to IMPLEMENTER-NOTES (advisory — the design could not settle them). ${CTX}
Run one per atom: ${IMPROVE} append-note ${SOURCE} --finding-id "<atom-id>" "<the atom's unverifiable conclusion>"
Atoms: ${JSON.stringify(unverifiable.map((v) => ({ id: v.atom_id, note: v.finding_conclusion })))}
Side-effecting; no relay needed.`,
      { label: "note-unverifiable", phase: `P-round-${roundIndex}`, agentType: "general-purpose" }
    );
  }

  // STEP 4-6 — gate, fix, decide.
  const res = await processFindings(candidateFindings, noteIds, `P-round-${roundIndex}`, roundLog);
  if (res === null) return null;

  // STEP 6 — round close.
  const closed = await roundClose(roundLog, res.touched);
  if (closed === null) return null;
  if (res.blocked) { status = "blocked"; return null; }

  // STEP 7 — loop assembly: next dirty set = coverage.dirty ∪ newly-minted unverified atoms.
  const cov = closed.coverage;
  const nextDirty = Array.from(new Set((cov.dirty || []).concat(cov.never_verified || []).concat(closed.newAtomIds || [])));
  return { coverage: cov, nextDirty, substantive: res.substantive, floorGreen };
}

// Runs phase-P rounds until the loop condition is false (or status set / brake).  Returns coverage on clean exit.
async function phasePRounds(seedWorklist) {
  let worklist = seedWorklist;
  let lastCoverage = null;
  while (status === null) {
    const r = await phasePRound(worklist);
    if (r === null) return null;            // status already set (blocked/round-cap)
    lastCoverage = r.coverage;
    const anyPending = pendingDecisions.length > 0;
    // Loop while: NOT coverage-complete OR gate not dry OR any pending decision OR floor not green (MINOR 1).
    if (!r.coverage.complete || r.substantive || anyPending || !r.floorGreen) {
      worklist = r.nextDirty;
      if (!worklist.length && r.coverage.complete && !r.substantive && !anyPending && r.floorGreen) break;
      continue;
    }
    break; // coverage-complete + dry + no pending + floor green → exit to phase E
  }
  return lastCoverage;
}

// ─────────────────────────────────────────────────────────────────────────────
// 19. PHASE E — Exit exam (reads UNCOUNTED against the cap)
// ─────────────────────────────────────────────────────────────────────────────
async function phaseE() {
  phase("Exit exam");
  const examThunks = [1, 2, 3].map((n) => async () => {
    const r = await reader(
      `You are a FRESH exit-exam reader #${n} that has seen nothing earlier in this run. ${CTX}
Read the WHOLE working copy with two targets: (1) what the atoms cannot compose into (every brick verifies while the building leans), and (2) what extraction never atomized. Report only SUBSTANTIVE findings.
Return { findings:[ {klass, sections, detail, decision_shaped} ] }.`,
      { label: `exam-${n}`, phase: "exam", agentType: "Explore", schema: S_FINDINGS }
    );
    return r ? r.findings : null;
  });
  const pooled = (await parallel(examThunks)).filter(Boolean).flat().filter(Boolean);
  if (!pooled.length) return [];
  // Canonical macro-ids (script-computed); null ⇒ relay died — the caller treats it as a dead role, never as clean.
  const withIds = await attachMacroIds(pooled, "exam");
  if (withIds === null) { deadRole("exam macro-ids"); return null; }
  return withIds;
}

// ─────────────────────────────────────────────────────────────────────────────
// 20. CONTINUATION MODE SELECT — reanchor a non-empty ledger, rebuild the worklist
// ─────────────────────────────────────────────────────────────────────────────
async function loadContinuation() {
  // Returns { worklist } on a non-empty ledger, or null if the ledger is empty (⇒ full phase H).
  if (!PATHS.atoms_exists) return null;
  // DECISIONS.json is the cross-invocation source of truth for the Decide queue; relay its
  // projection too when it exists so status:pending records rebuild the re-attempt queue.
  const wantDecisions = !!PATHS.decisions_exists;
  const decisionsLine = wantDecisions
    ? `\n  ${SPEC_CHECKS} decisions summary ${DECISIONS}          (tag "decisions" — prior-run decision projection; status:pending records rebuild the Decide re-attempt queue)`
    : "";
  const keyed = [{ tag: "reanchor", validate: vReanchor }, { tag: "coverage", validate: vCoverage }];
  if (wantDecisions) keyed.push({ tag: "decisions", validate: vDecisions });
  const res = await relayAgent(
    `You are the decompose agent on a CONTINUATION load (Bash). ${CTX}
The ledger persists from a prior run. Run ${wantDecisions ? "ALL of" : "BOTH of"} the following and relay each:
  ${SPEC_CHECKS} atoms reanchor ${DOC} --ledger ${LEDGER}      (tag "reanchor" — re-walks the ledger, re-hashes external inputs, reports dirty/relocated/vanished/new-regions)
  ${SPEC_CHECKS} atoms coverage --ledger ${LEDGER}             (tag "coverage" — its dirty + never_verified lists rebuild the worklist)${decisionsLine}
${RELAY_KEYED_RULE}`,
    { label: "continuation-load", phase: "load", agentType: "general-purpose", schema: S_RELAY_KEYED },
    { keyed }
  );
  if (!res) { deadRole("continuation load reanchor/coverage"); return null; }
  const reanchor = res.data["reanchor"];
  const coverage = res.data["coverage"];
  applyReanchor(reanchor);

  // Rebuild the Decide re-attempt queue from on-disk status:pending records (concept Continuation-runs):
  // a decision whose researcher/taker never completed survives as "pending" and must be re-attempted
  // this run, else anyPending is false and Decide is never re-entered. (finding_atoms is not carried by
  // the projection → seed macro; the researcher re-names the units.)
  if (wantDecisions) {
    for (const r of (res.data["decisions"] || [])) {
      if (r && r.status === "pending" && r.id) {
        const fa = Array.isArray(r.finding_atoms) ? r.finding_atoms : [];
        pendingDecisions.push({ decision_id: r.id, finding_atoms: fa, macro: fa.length === 0 });
      }
    }
  }

  if (coverage.total === 0) return null; // empty ledger ⇒ full phase H
  const worklist = Array.from(new Set((coverage.dirty || []).concat(coverage.never_verified || []).concat(reanchor.external_stale || [])));
  return { worklist };
}

// ─────────────────────────────────────────────────────────────────────────────
// 21. MAIN CONTROL FLOW
// ─────────────────────────────────────────────────────────────────────────────
log(`spec-improve-auto drain: run ${RUN}, overrides=${OVERRIDES.length}, directives=${DIRECTIVES.length}`);

if (!SOURCE || !DOC || !LEDGER || !SCRIPTS || !SCRATCH) {
  log("FATAL: missing required args (paths.source/auto_improve/atoms, scriptsDir, scratchDir).");
  status = "round-cap";
} else {
  // PRELUDE — directive/override channel (conditional stage).
  const preludeOk = await applyPrelude();
  if (!preludeOk) { /* status already round-cap */ }
  else {
    // MODE SELECT — keys on ledger state.
    const cont = await loadContinuation();
    if (status === null) {
      if (cont) {
        // Continuation / directive-on-non-empty: phase H already cleared. Resume phase P.
        // (Directive runs additionally get a scoped phase-H re-check via the structural trigger set by the apply agent's edits.)
        if (OVERRIDES.length || DIRECTIVES.length) structuralTrigger = true;
        const seed = cont.worklist.length ? cont.worklist : Array.from(new Set(Object.keys(idTypeMap).filter((id) => idTypeMap[id] !== "heading")));
        let worklist = seed;
        let clean = false;
        while (status === null && !clean) {
          const cov = await phasePRounds(worklist);
          if (status !== null) break;
          const examFindings = await phaseE();
          if (examFindings === null) break; // exam macro-ids relay died → status already round-cap, never clean
          if (examFindings.length) {
            // Exam findings re-enter phase P (their fixes count; the exam read did not).
            const roundLog = { atom_verdicts: [], macro_findings: [] };
            if (brakeCheck({ dirty: 0, sections: 0, pending: pendingDecisions.length })) break;
            roundIndex++;
            const noteIds = await fetchNoteIds();
            const rr = await processFindings(examFindings, noteIds, `E-round-${roundIndex}`, roundLog);
            if (rr === null) break;
            markMacroFixed(examFindings, roundLog); // MINOR 2: fixed:true only when auto-fixed this round.
            const closed = await roundClose(roundLog, rr.touched);
            if (closed === null) break;
            if (rr.blocked) { status = "blocked"; break; }
            worklist = Array.from(new Set((closed.coverage.dirty || []).concat(closed.coverage.never_verified || []).concat(closed.newAtomIds || [])));
          } else {
            status = "converged";
            clean = true;
          }
        }
      } else {
        // Empty ledger ⇒ full horizontal pass, then decompose, then phase P + exit exam.
        await phaseH(false);
        if (status === null) {
          const worklist0 = await decomposeEntry();
          if (worklist0 !== null && status === null) {
            let worklist = worklist0;
            let clean = false;
            while (status === null && !clean) {
              await phasePRounds(worklist);
              if (status !== null) break;
              const examFindings = await phaseE();
              if (examFindings === null) break; // exam macro-ids relay died → status already round-cap, never clean
              if (examFindings.length) {
                const roundLog = { atom_verdicts: [], macro_findings: [] };
                if (brakeCheck({ dirty: 0, sections: 0, pending: pendingDecisions.length })) break;
                roundIndex++;
                const noteIds = await fetchNoteIds();
                const rr = await processFindings(examFindings, noteIds, `E-round-${roundIndex}`, roundLog);
                if (rr === null) break;
                markMacroFixed(examFindings, roundLog); // MINOR 2: fixed:true only when auto-fixed this round.
                const closed = await roundClose(roundLog, rr.touched);
                if (closed === null) break;
                if (rr.blocked) { status = "blocked"; break; }
                worklist = Array.from(new Set((closed.coverage.dirty || []).concat(closed.coverage.never_verified || []).concat(closed.newAtomIds || [])));
              } else {
                status = "converged";
                clean = true;
              }
            }
          }
        }
      }
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 22. RETURN — thin control-flow signal ONLY (decision/atom data derived command-side)
// ─────────────────────────────────────────────────────────────────────────────
return { status: status || "round-cap", rounds: roundIndex, fixed, below_bar: belowBar };
