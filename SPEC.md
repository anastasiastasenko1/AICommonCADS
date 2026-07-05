# Apprentice — Specification v0.1

**Tacit-knowledge elicitation harness for enterprise agents.**
Wraps the assistant employees already use, captures the knowledge they volunteer while working, consolidates it into an auditable CommonKADS-lite knowledge model, and compiles that model into synthetic-environment specs for training specialised agents.

---

## 1. Problem and thesis

The bottleneck for enterprise agents is not model capability but undocumented context: exceptions, unwritten quality bars, local vocabulary, who-to-ask-when. This knowledge is tacit — its holders cannot author it on demand (the *paradox of expertise*: knowledge proceduralises and loses verbal access). But three empirical findings from the knowledge-acquisition literature (1977–1995) point to what works:

1. **People are poor rule-authors but excellent critics.** Corrections to a draft are cheap, grounded, and socially frictionless. (Teach-back; Argyris's espoused-theory vs theory-in-use.)
2. **Tacit content lives in incidents and discriminations, not descriptions.** Critical Decision Method probes ("what would a novice have missed?") and repertory-grid contrasts ("you handled A and B differently — why?") outperform interviews.
3. **Knowledge engineering is modelling, not extraction** (CommonKADS). You construct an artifact that agrees with expert behaviour; reusable *task types* give the artifact structure.

**Thesis:** elicitation is already happening — every time an employee explains context to a copilot to get a better answer. Apprentice persists it, asks the few questions that matter, and never surveils.

## 2. Design principles

- **Selfish value first.** The employee's own assistant stops needing re-explanation. The knowledge model is *their* persistent memory before it is anyone's training data.
- **Ownership and auditability.** Plain YAML/Markdown files the employee can read, edit, delete. No hidden state. Aggregation into team models is a separate, explicit, credited act.
- **Critique over generation.** The primary data channel is the diff between the assistant's draft and what the employee actually shipped.
- **Budgeted curiosity.** At most N questions/day (default 3), asked after task completion, never mid-flow. When question yield drops, the apprentice goes quiet.
- **No log mining.** Apprentice runs as a layer the employee controls, not as analytics over copilot logs. That distinction is the entire privacy story.
- **CLI-first, adapters second.** State and loops live in a local core; MCP is a *view* into it, so any assistant surface (Claude Code, Cowork, claude.ai, Copilot via bridge) reads and writes the same store.

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Assistant surfaces (Claude Code / Cowork / claude.ai / …)   │
│        ▲ recall_context, get_pending_question                │
│        ▼ log_observation, record_answer                      │
├────────────── MCP adapter (`apprentice serve`) ──────────────┤
│                                                              │
│  CORE  (local Python package, owns all state)                │
│  ├─ store/        plain-file knowledge store (YAML + JSONL)  │
│  ├─ schema        CommonKADS-lite model, provenance, conf.   │
│  ├─ tasktypes     task-type library → env scaffolds          │
│  ├─ policy        elicitation policy engine (budgeted queue) │
│  ├─ consolidate   offline LLM pass (episodes → assertions)   │
│  └─ compiler      knowledge model → environment spec         │
│                                                              │
├────────────── CLI (`apprentice …`) ──────────────────────────┤
│  init · status · observe · ask · answer · interview          │
│  consolidate (cron) · review · compile · serve               │
└─────────────────────────────────────────────────────────────┘
```

Why not MCP+skill alone: the policy engine is **proactive** (budgets, nightly consolidation, contradiction detection, queue generation), correction capture happens **outside chat** (the final artifact the employee ships is never seen in-session), and compilation is **batch**. Those three loops need a process the employee owns; a tool server that only wakes on model calls cannot host them.

### 3.1 Storage layout

```
$APPRENTICE_HOME/            (default ~/.apprentice, or ./.apprentice per project)
├─ config.yaml               owner, LLM endpoint, budgets
└─ workflows/<name>/
   ├─ model.yaml             the knowledge model (§4) — the artifact
   ├─ episodes.jsonl         append-only observation log (§5)
   └─ questions.yaml         question queue with status + yield tracking
```

Git-friendly by design: a workflow directory can be versioned, diffed, and (when the employee chooses) merged into a team repository. Merge conflicts between experts are *surfaced as contradictions*, not averaged away.

## 4. Knowledge model schema (CommonKADS-lite)

We keep CommonKADS's knowledge-model triad (domain / inference / task) and its task-type library; we drop the six-model waterfall and CML formalism.

```yaml
workflow: incoming_nda_triage
task_type: assessment            # from the task-type library (§6)
description: Triage incoming NDAs before counsel review
owner: marie@example.com
status: active                   # active | converged | stale

domain:                          # what things are
  glossary:
    red flag: non-mutual confidentiality obligations
  entities: [counterparty, governing_law, ip_clause, msa]

inference:                       # how decisions are made
  decision_points:
    - id: escalate_or_approve
      cues: [counterparty_size, governing_law, ip_clauses]
      rule: escalate if governing law is not FR/EU
      confidence: 0.9
      provenance: {source: marie, episode: ep-2026-06-12-3, method: correction}

task:                            # workflow skeleton
  steps: [receive, check_existing_agreements, assess, decide, notify]

exceptions:                      # the value is here
  - condition: US counterparty with existing MSA
    handling: skip review, approve directly
    frequency: monthly
    confidence: 0.8
    provenance: {source: marie, episode: ep-2026-06-14-1, method: volunteered}

quality_criteria:                # compile to checkers
  - never approve without checking existing agreements
  - response to sales within 24h

open_questions:
  - id: q-014
    text: what happens when the counterparty is a direct competitor?
    strategy: cdm_probe
    status: pending
```

Every assertion carries `confidence` (0–1, updated by confirmation/contradiction) and `provenance` (who, which episode, which elicitation method). Nothing enters the model without a source.

## 5. Data channels (in priority order)

| Channel | What | How captured |
|---|---|---|
| **Corrections** | diff between assistant draft and shipped artifact | `apprentice observe --draft a.md --final b.md`, or MCP `log_observation` |
| **Volunteered context** | constraints/preferences stated in prompts | MCP adapter flags them during sessions |
| **Artifacts** | templates, exemplary past work | `apprentice observe --artifact f.md --note "gold standard"` |
| **Answers** | responses to queued questions | `apprentice answer` / MCP `record_answer` |
| **Interviews** | CDM bootstrap sessions | `apprentice interview <workflow>` |

Each becomes an **episode** (append-only JSONL): `{id, ts, kind, payload, workflow}`. Episodes are raw evidence; only consolidation turns them into model assertions.

## 6. Task-type library → environment scaffolds

Adapted from the CommonKADS catalogue. `task_type` selects the environment scaffold at compile time and conditions the elicitation strategy (each type has characteristic blind spots).

| Task type | Inference structure | Env scaffold | Characteristic blind spot → favoured probe |
|---|---|---|---|
| classification | match case → class | generate labelled cases from exception distribution; check class | unstated cues → contrast triads |
| assessment | case vs norms → verdict | generate cases with ground-truth verdicts; check verdict + criteria use | under-reported cues → constrained processing |
| diagnosis | symptoms → cause hypothesis | generate faulty systems; check root cause found | hypothesis-ordering → CDM timeline probes |
| monitoring | stream vs expectations → alarm | generate streams with injected anomalies; check detection/precision | expectancies → "what did you expect here?" |
| prediction | state → future state | generate scenarios with known outcomes; score calibration | base rates → frequency questions |
| configuration | requirements + constraints → assembly | generate requirement sets; check constraint satisfaction | implicit constraints → counterexample generation |
| planning | goal → action sequence | generate goals/resources; check plan validity + preferences | preference trade-offs → forced-choice pairs |
| scheduling | jobs + resources → allocation | generate job sets; check feasibility + soft-constraint score | soft constraints → critique of naive schedules |
| assignment | items ↔ slots | generate matching problems; check assignment quality | tie-breaking rules → paired comparisons |

## 7. Elicitation policy engine

**Question strategies** (from the KA literature):

- `cdm_probe` — critical-incident deepening: cues, expectancies, novice-contrast
- `contrast` — repertory-grid triads: "A and B handled differently — what distinguishes them?"
- `constrained` — "if you could only see one field, which?"
- `teach_back` — apprentice explains its model; expert corrects (doubles as trust-building)
- `confirm` — one-shot confirmation of a rule hypothesised from a correction diff

**Policy:**

1. Queue ranked by expected information gain: contradictions first, then low-confidence high-usage assertions, then coverage gaps in the exception catalogue, conditioned on task-type blind spots.
2. Hard budget (default 3/day/person); asked at task boundaries.
3. Every asked question records whether its answer changed the model (**yield**). Rolling yield below threshold (default 0.2 over 20 questions) ⇒ workflow marked `converged`, apprentice goes quiet.
4. `teach_back` is scheduled, not gain-ranked (every N episodes, default 25).

## 8. Consolidation (offline, cron-able)

`apprentice consolidate` — the nightly pass, LLM-backed and model-agnostic (any OpenAI/Anthropic-compatible endpoint; designed so a Pleias model can replace the frontier model later):

1. Read unconsolidated episodes.
2. Propose model deltas: new/updated assertions with provenance, confidence updates (confirmations ↑, contradictions ↓ + flag).
3. Detect contradictions (within one expert over time, or between experts in a merged team model) → generate `confirm`/`contrast` questions.
4. Refresh question queue; mark stale assertions (no confirmation in M days on active workflows).
5. Write a human-readable consolidation report; deltas apply automatically but are individually revertible (`apprentice review`).

## 9. Compiler (environment export)

`apprentice compile <workflow>` → `environment_spec.yaml`:

- **scenario_generator** — case-generation config seeded by domain entities, weighted by the elicited exception distribution
- **checkers** — quality criteria compiled to verifiable checks (LLM-judge rubrics or programmatic where possible)
- **held_out_cases** — real (consented, anonymised) episodes reserved for sim-to-real validation, never used for generation
- **scaffold** — trajectory shape from the task type (§6)

v0.1 emits the spec; trajectory generation and training are downstream consumers (Phase 3).

## 10. Data lifecycle and the harness → SYNTH interface

Four layers, each with a distinct retention rule. The design principle: **raw
evidence is never discarded, distilled knowledge is always re-derivable.**

| Layer | Artifact | Lives | Retention |
|---|---|---|---|
| 1. Raw evidence | `episodes.jsonl` | customer-side, per employee | append-only; deleted only by owner request |
| 2. Distilled knowledge | `model.yaml` | customer-side, employee-owned | re-derivable from L1; assertions individually deletable |
| 3. Environment spec | `environment_spec.yaml` | customer-side; shareable | compiled from L2; contains no real data |
| 4. Synthetic corpus | `cases.jsonl` + `trajectories.jsonl` | training infra | fully synthetic; regenerable from L3 |

**Why L1 is sacred.** The knowledge model is a function of the consolidator's
quality. Re-running a better consolidator (eventually a specialised Pleias
model) over the same episodes yields a strictly better model for free —
exactly the raw-crawl vs processed-corpus distinction. Discarding episodes
forfeits every future improvement in extraction.

**Provenance chain and deletion.** Every assertion points to its source
episodes; every synthetic case points to the assertion IDs it was generated
from (`derived_from`). Deleting an episode therefore mechanically invalidates
derived assertions at the next consolidation, and invalidated assertions
mechanically invalidate derived synthetic cases at the next compile. GDPR
erasure propagates through the whole pipeline without manual audit.

**Pooling across customers.** Episodes and models never leave the customer.
What Pleias accumulates is the population of *schema-conformant knowledge
models keyed by task_type*: fifty assessment workflows teach you what a good
assessment scenario generator looks like, letting you meta-improve the
compiler without pooling any content. Format note: YAML/JSONL is the contract
at single-employee scale; stable IDs + provenance make migration to
parquet/warehouse mechanical when a deployment grows.

### 10.1 Trajectory format (what the environment consumer emits)

The compiled spec is consumed by a generator that produces two JSONL streams,
the harness→SYNTH interface:

```jsonc
// cases.jsonl — one line per synthetic scenario
{
  "case_id": "case-9f3a1c02",
  "environment": "nda_triage",
  "task_type": "assessment",
  "generator_version": "0.1.0",
  "seed": 42,
  "scenario": { "counterparty": "...", "governing_law": "DE", "documents": ["..."] },
  "reference": {                     // ground truth, from the reference policy
    "verdict": "escalate",
    "rationale_rule_ids": ["de-af2b0b36"]
  },
  "derived_from": {                  // provenance → enables cascade invalidation
    "exceptions": ["ex-4b724000"],
    "decision_rules": ["de-af2b0b36"],
    "model_version": "sha-or-ts"
  },
  "held_out": false                  // true only for anonymised real episodes
}

// trajectories.jsonl — one line per agent rollout on a case
{
  "traj_id": "traj-77b0e4d1",
  "case_id": "case-9f3a1c02",
  "agent": { "model": "pleias-x", "version": "...", "harness": "apprentice-env-0.1" },
  "steps": [
    { "obs": "...", "action": "check_existing_agreements", "tool_result": "no MSA found" },
    { "obs": "...", "action": "verdict", "output": "escalate — governing law DE" }
  ],
  "scores": {                        // one entry per compiled checker
    "verdict_match": 1.0,
    "qu-5104f30d": 1.0               // quality-criterion rubric score
  },
  "reward": 1.0,
  "passed": true,
  "ts": "2026-07-05T18:00:00Z"
}
```

Rules: held-out cases (real, consented, anonymised episodes) appear in
`cases.jsonl` with `held_out: true` and are used **only** to measure the
sim-to-real gap — trajectories on them are never trained on. `reward` is a
deterministic aggregation of `scores` declared in the spec, so reward
definitions are auditable and re-scorable offline.

## 11. MCP adapter

`apprentice serve` exposes the core to any MCP-capable assistant:

| Tool | Purpose |
|---|---|
| `recall_context(workflow?)` | inject relevant knowledge model into the session |
| `log_observation(kind, payload, workflow?)` | record volunteered context / drafts / corrections |
| `get_pending_question(workflow?)` | fetch ≤1 budgeted question for the session's end |
| `record_answer(question_id, answer)` | store the expert's answer |
| `list_workflows()` | discovery |

A companion **skill** instructs the assistant: recall context at session start; log volunteered constraints; at task completion, ask the one pending question if the moment is natural; never ask mid-flow; never exceed the served budget.

## 12. Privacy & ownership model

- Store is local to the employee; nothing leaves without an explicit `apprentice` command.
- Team aggregation = the employee pushes chosen workflow dirs to a shared repo; contributions are provenance-attributed (credited).
- The employee can `review`, edit, or delete any assertion; deletion is honoured at next consolidation and compile.
- Compiled environments contain **no real customer data** — scenarios are synthetic; held-out real cases require explicit consent and anonymisation.

## 13. Metrics

- **Draft acceptance rate** — is the apprentice improving? (primary)
- **Question yield** — fraction of questions that change the model (convergence signal)
- **Exception coverage** — new exceptions/week (should decay)
- **Sim-to-real gap** — agent score on held-out real cases vs synthetic (post-compile)

## 14. Roadmap

- **Phase 1 (this prototype):** CLI core, file store, policy engine, consolidation, MCP adapter, skill, compiler stub.
- **Phase 2:** team merge + contradiction workflow; question-yield-tuned policy; type-conditioned interview scripts.
- **Phase 3:** trajectory generation from compiled environments; distillation into specialised Pleias models; the specialised model slots back behind the same harness.
