"""Compiler: knowledge model → synthetic environment spec.

v0.1 emits the spec; trajectory generation and training consume it
downstream. Real episodes are reserved as held-out validation cases
(sim-to-real check) and are NEVER used for scenario generation.
"""

from __future__ import annotations

import yaml

from . import tasktypes
from .store import Store

MIN_CONFIDENCE = 0.5


def compile_environment(store: Store, workflow: str, min_confidence: float = MIN_CONFIDENCE) -> dict:
    model = store.load_model(workflow)
    tt = tasktypes.get(model["task_type"])

    usable = lambda a: a.get("confidence", 0) >= min_confidence  # noqa: E731
    excluded = []

    exceptions = []
    for ex in model.get("exceptions", []):
        (exceptions if usable(ex) else excluded).append(ex)

    checkers = []
    for qc in model.get("quality_criteria", []):
        text = qc.get("text") if isinstance(qc, dict) else str(qc)
        if not isinstance(qc, dict) or usable(qc):
            checkers.append({"kind": "rubric", "criterion": text})
        else:
            excluded.append(qc)

    decision_rules = []
    for dp in model.get("inference", {}).get("decision_points", []):
        (decision_rules if usable(dp) else excluded).append(dp)

    held_out = [e["id"] for e in store.episodes(workflow) if e["kind"] in ("correction", "artifact")]

    spec = {
        "environment": model["workflow"],
        "task_type": model["task_type"],
        "compiled_from": {
            "model_status": model.get("status"),
            "min_confidence": min_confidence,
            "assertions_excluded_below_threshold": len(excluded),
        },
        "scaffold": tt["scaffold"],
        "scenario_generator": {
            "strategy": tt["scaffold"]["generator"],
            "entities": model.get("domain", {}).get("entities", []),
            "glossary": model.get("domain", {}).get("glossary", {}),
            "workflow_steps": model.get("task", {}).get("steps", []),
            "exception_distribution": [
                {"condition": ex.get("condition"),
                 "handling": ex.get("handling"),
                 "frequency": ex.get("frequency", "unknown")}
                for ex in exceptions
            ],
        },
        "reference_policy": {
            "decision_rules": [
                {"id": dp.get("id"), "cues": dp.get("cues", []), "rule": dp.get("rule")}
                for dp in decision_rules
            ],
        },
        "checkers": checkers,
        "held_out_cases": {
            "episode_ids": held_out,
            "note": "real episodes, consented + anonymised; validation only, never generation",
        },
        "open_gaps": [q.get("text", q) if isinstance(q, dict) else q
                      for q in model.get("open_questions", [])],
    }
    return spec


def write_spec(store: Store, workflow: str, min_confidence: float = MIN_CONFIDENCE):
    spec = compile_environment(store, workflow, min_confidence)
    path = store.workflow_dir(workflow) / "environment_spec.yaml"
    path.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
    return path, spec
