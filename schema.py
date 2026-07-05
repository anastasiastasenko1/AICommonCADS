"""CommonKADS-lite knowledge model schema.

The model is a plain dict persisted as YAML so employees can read,
edit, diff and delete it. This module owns the canonical structure,
provenance/confidence conventions, and light validation — nothing else.
"""

from __future__ import annotations

import datetime as _dt
import uuid

TASK_TYPES = [
    "classification",
    "assessment",
    "diagnosis",
    "monitoring",
    "prediction",
    "configuration",
    "planning",
    "scheduling",
    "assignment",
]

STATUSES = ["active", "converged", "stale"]


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def empty_model(workflow: str, task_type: str, owner: str, description: str = "") -> dict:
    if task_type not in TASK_TYPES:
        raise ValueError(f"unknown task_type '{task_type}' (choose from {', '.join(TASK_TYPES)})")
    return {
        "workflow": workflow,
        "task_type": task_type,
        "description": description,
        "owner": owner,
        "status": "active",
        "created": now(),
        "domain": {"glossary": {}, "entities": []},
        "inference": {"decision_points": []},
        "task": {"steps": []},
        "exceptions": [],
        "quality_criteria": [],
        "open_questions": [],
    }


def provenance(source: str, episode: str | None = None, method: str = "volunteered") -> dict:
    """method: correction | volunteered | answer | interview | artifact | consolidation"""
    return {"source": source, "episode": episode, "method": method, "recorded": now()}


def make_assertion(kind: str, payload: dict, source: str, episode: str | None,
                   method: str, confidence: float = 0.6) -> dict:
    """kind: decision_point | exception | quality_criterion | glossary | step"""
    a = dict(payload)
    a.setdefault("id", new_id(kind[:2]))
    a["confidence"] = round(float(confidence), 2)
    a["provenance"] = provenance(source, episode, method)
    return a


def bump_confidence(assertion: dict, confirmed: bool, step: float = 0.1) -> None:
    c = assertion.get("confidence", 0.6)
    c = min(0.99, c + step) if confirmed else max(0.05, c - 2 * step)
    assertion["confidence"] = round(c, 2)
    if not confirmed:
        assertion["contradicted"] = now()


def validate(model: dict) -> list[str]:
    """Return a list of problems (empty = valid). Deliberately lenient:
    the model is employee-editable and must tolerate hand edits."""
    problems = []
    for key in ("workflow", "task_type", "domain", "inference", "task"):
        if key not in model:
            problems.append(f"missing key: {key}")
    if model.get("task_type") not in TASK_TYPES:
        problems.append(f"unknown task_type: {model.get('task_type')}")
    if model.get("status", "active") not in STATUSES:
        problems.append(f"unknown status: {model.get('status')}")
    return problems


def iter_assertions(model: dict):
    """Yield (section, assertion_dict) for everything carrying confidence."""
    for dp in model.get("inference", {}).get("decision_points", []):
        yield "decision_points", dp
    for ex in model.get("exceptions", []):
        yield "exceptions", ex
    for qc in model.get("quality_criteria", []):
        if isinstance(qc, dict):
            yield "quality_criteria", qc
