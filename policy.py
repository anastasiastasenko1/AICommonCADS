"""Elicitation policy engine.

Decides WHAT to ask, WHEN, and WHEN TO STOP:
- queue ranked by expected information gain (contradictions first,
  then low-confidence/high-usage assertions, then coverage gaps),
  conditioned on the task type's characteristic blind spot;
- hard daily budget, questions served only at task boundaries;
- yield tracking: when answers stop changing the model, go quiet.
"""

from __future__ import annotations

import datetime as _dt

from . import schema, tasktypes
from .store import Store

STRATEGIES = ("cdm_probe", "contrast", "constrained", "teach_back", "confirm")


def _today() -> str:
    return _dt.date.today().isoformat()


def asked_today(qstate: dict) -> int:
    return sum(1 for q in qstate.get("asked", []) if str(q.get("asked_at", "")).startswith(_today()))


def rolling_yield(qstate: dict, window: int) -> float | None:
    answered = [q for q in qstate.get("asked", []) if "yield" in q]
    if len(answered) < window:
        return None
    recent = answered[-window:]
    return sum(1 for q in recent if q["yield"]) / len(recent)


def rank_queue(model: dict, qstate: dict) -> list[dict]:
    """Sort the pending queue by expected information gain."""
    def score(q: dict) -> float:
        s = float(q.get("priority", 0.5))
        if q.get("strategy") == "confirm":
            s += 0.3                      # contradiction/hypothesis confirmations first
        blind_probe = tasktypes.get(model["task_type"])["probe"]
        if q.get("strategy") == blind_probe:
            s += 0.15                     # type-conditioned blind-spot bonus
        return s

    return sorted(qstate.get("queue", []), key=score, reverse=True)


def next_question(store: Store, workflow: str) -> dict | None:
    """Return at most one question, respecting budget and convergence."""
    cfg = store.config()
    model = store.load_model(workflow)
    qstate = store.questions(workflow)

    if model.get("status") == "converged":
        return None
    if asked_today(qstate) >= int(cfg.get("question_budget_per_day", 3)):
        return None

    # teach-back is scheduled, not gain-ranked
    n_eps = len(store.episodes(workflow))
    every = int(cfg.get("teach_back_every_n_episodes", 25))
    last_tb = qstate.get("last_teach_back_at_episode", 0)
    if n_eps and every and n_eps - last_tb >= every:
        qstate["last_teach_back_at_episode"] = n_eps
        q = {
            "id": schema.new_id("q"),
            "strategy": "teach_back",
            "text": ("Let me explain how I currently understand this workflow, "
                     "and you correct me where I'm wrong."),
        }
        qstate.setdefault("queue", []).insert(0, q)
        store.save_questions(workflow, qstate)

    ranked = rank_queue(model, qstate)
    if not ranked:
        return None

    q = ranked[0]
    qstate["queue"] = [x for x in qstate["queue"] if x["id"] != q["id"]]
    q["asked_at"] = schema.now()
    qstate.setdefault("asked", []).append(q)
    store.save_questions(workflow, qstate)
    return q


def record_answer(store: Store, workflow: str, question_id: str, answer: str) -> dict:
    """Store the answer as an episode; consolidation decides yield later."""
    qstate = store.questions(workflow)
    q = next((x for x in qstate.get("asked", []) if x["id"] == question_id), None)
    if q is None:
        raise KeyError(f"unknown or un-asked question: {question_id}")
    q["answer"] = answer
    q["answered_at"] = schema.now()
    store.save_questions(workflow, qstate)
    return store.append_episode(workflow, "answer",
                                {"question_id": question_id,
                                 "question": q.get("text"),
                                 "strategy": q.get("strategy"),
                                 "answer": answer})


def check_convergence(store: Store, workflow: str) -> bool:
    """Mark the workflow converged when rolling yield drops below threshold."""
    cfg = store.config()
    qstate = store.questions(workflow)
    y = rolling_yield(qstate, int(cfg.get("yield_window", 20)))
    if y is not None and y < float(cfg.get("yield_threshold", 0.2)):
        model = store.load_model(workflow)
        if model.get("status") == "active":
            model["status"] = "converged"
            store.save_model(workflow, model)
        return True
    return False
