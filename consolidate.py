"""Consolidation: the offline (nightly, cron-able) pass.

Episodes are raw evidence; only this pass turns them into model
assertions. It proposes deltas with provenance, updates confidence,
detects contradictions, scores question yield, and refreshes the
question queue. Deltas apply automatically but every one is visible in
the report and revertible by editing model.yaml (`apprentice review`).
"""

from __future__ import annotations

import json

from . import llm, policy, schema, tasktypes
from .store import Store

SYSTEM = """You are the consolidation engine of a tacit-knowledge elicitation harness.
You receive a knowledge model (CommonKADS-lite) and a batch of raw episodes
(corrections, volunteered context, artifacts, answers to elicitation questions,
interview notes) from ONE expert's real work.

Your job:
1. Propose model deltas grounded ONLY in the episodes. Never invent knowledge.
   Prefer updating an existing assertion over adding a near-duplicate.
2. Detect confirmations (episode supports an existing assertion) and
   contradictions (episode conflicts with one).
3. For each answered question in the episodes, judge yield: did the answer
   add or change anything in the model? (true/false)
4. Propose at most 5 new elicitation questions, favouring: confirmations of
   rules you hypothesised from correction diffs; contrasts between episodes
   handled differently; gaps in the exception catalogue.
   The expert's task type has a known blind spot — bias one question toward
   the indicated probe strategy.

Answer with ONLY a JSON object:
{
 "new_decision_points": [{"id"?, "cues": [..], "rule": "..", "confidence": 0.0-1.0, "episode": "ep-.."}],
 "new_exceptions": [{"condition": "..", "handling": "..", "frequency": "..", "confidence": .., "episode": ".."}],
 "new_quality_criteria": [{"text": "..", "confidence": .., "episode": ".."}],
 "new_glossary": {"term": "definition"},
 "new_steps": ["step", ..],
 "confirmations": ["assertion-id", ..],
 "contradictions": [{"id": "assertion-id", "note": "..", "episode": ".."}],
 "question_yields": {"q-id": true/false},
 "new_questions": [{"strategy": "cdm_probe|contrast|constrained|confirm", "text": "..", "priority": 0.0-1.0}]
}
Omit empty keys. Be conservative: fewer, better-grounded deltas."""


def consolidate(store: Store, workflow: str, chat_fn=None) -> dict:
    """Run one consolidation pass. Returns a summary dict."""
    cfg = store.config()
    model = store.load_model(workflow)
    eps = store.episodes(workflow, unconsolidated_only=True)
    if not eps:
        return {"workflow": workflow, "episodes": 0, "message": "nothing to consolidate"}

    tt = tasktypes.get(model["task_type"])
    user = json.dumps({
        "knowledge_model": model,
        "task_type_blind_spot": tt["blind_spot"],
        "favoured_probe": tt["probe"],
        "episodes": eps,
    }, ensure_ascii=False)

    chat_fn = chat_fn or (lambda s, u: llm.chat(s, u, cfg))
    deltas = llm.extract_json(chat_fn(SYSTEM, user))

    summary = _apply(store, workflow, model, deltas, eps)
    store.mark_consolidated(workflow, {e["id"] for e in eps})
    policy.check_convergence(store, workflow)
    report = _report(workflow, summary, deltas)
    path = store.write_report(workflow, "consolidation", report)
    summary["report"] = str(path)
    return summary


def _apply(store: Store, workflow: str, model: dict, deltas: dict, eps: list[dict]) -> dict:
    owner = model.get("owner", "")
    n = {"added": 0, "confirmed": 0, "contradicted": 0, "questions": 0}

    def _src(d):
        return d.get("episode") or (eps[-1]["id"] if eps else None)

    for dp in deltas.get("new_decision_points", []):
        model["inference"]["decision_points"].append(schema.make_assertion(
            "decision_point", {k: dp[k] for k in ("id", "cues", "rule") if k in dp},
            owner, _src(dp), "consolidation", dp.get("confidence", 0.6)))
        n["added"] += 1
    for ex in deltas.get("new_exceptions", []):
        model["exceptions"].append(schema.make_assertion(
            "exception", {k: ex[k] for k in ("condition", "handling", "frequency") if k in ex},
            owner, _src(ex), "consolidation", ex.get("confidence", 0.6)))
        n["added"] += 1
    for qc in deltas.get("new_quality_criteria", []):
        model["quality_criteria"].append(schema.make_assertion(
            "quality_criterion", {"text": qc.get("text", "")},
            owner, _src(qc), "consolidation", qc.get("confidence", 0.6)))
        n["added"] += 1
    model["domain"]["glossary"].update(deltas.get("new_glossary", {}))
    for step in deltas.get("new_steps", []):
        if step not in model["task"]["steps"]:
            model["task"]["steps"].append(step)

    by_id = {a["id"]: a for _, a in schema.iter_assertions(model) if "id" in a}
    for aid in deltas.get("confirmations", []):
        if aid in by_id:
            schema.bump_confidence(by_id[aid], confirmed=True)
            n["confirmed"] += 1
    for c in deltas.get("contradictions", []):
        if c.get("id") in by_id:
            schema.bump_confidence(by_id[c["id"]], confirmed=False)
            by_id[c["id"]]["contradiction_note"] = c.get("note", "")
            n["contradicted"] += 1

    store.save_model(workflow, model)

    qstate = store.questions(workflow)
    for qid, y in deltas.get("question_yields", {}).items():
        for q in qstate.get("asked", []):
            if q["id"] == qid:
                q["yield"] = bool(y)
    for q in deltas.get("new_questions", []):
        if q.get("strategy") in policy.STRATEGIES and q.get("text"):
            qstate.setdefault("queue", []).append({
                "id": schema.new_id("q"),
                "strategy": q["strategy"],
                "text": q["text"],
                "priority": float(q.get("priority", 0.5)),
            })
            n["questions"] += 1
    store.save_questions(workflow, qstate)

    n["episodes"] = len(eps)
    n["workflow"] = workflow
    return n


def _report(workflow: str, s: dict, deltas: dict) -> str:
    lines = [
        f"# Consolidation report — {workflow}",
        "",
        f"Episodes processed: {s['episodes']} · assertions added: {s['added']} · "
        f"confirmed: {s['confirmed']} · contradicted: {s['contradicted']} · "
        f"new questions: {s['questions']}",
        "",
    ]
    if deltas.get("contradictions"):
        lines.append("## Contradictions flagged")
        for c in deltas["contradictions"]:
            lines.append(f"- `{c.get('id')}` — {c.get('note', '')}")
        lines.append("")
    if deltas.get("new_questions"):
        lines.append("## Questions queued")
        for q in deltas["new_questions"]:
            lines.append(f"- [{q.get('strategy')}] {q.get('text')}")
        lines.append("")
    lines.append("Every delta above is in `model.yaml` with provenance; edit or delete freely.")
    return "\n".join(lines)
