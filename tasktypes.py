"""Task-type library (CommonKADS catalogue, adapted).

Each task type carries:
- inference: the canonical inference structure (documentation + prompts)
- blind_spot: what experts of this type systematically under-report
- probe: the elicitation strategy favoured for that blind spot
- scaffold: the environment template the compiler instantiates
"""

TASK_TYPES = {
    "classification": {
        "inference": "match case features against class definitions",
        "blind_spot": "the cues actually used are unstated; experts cite textbook features",
        "probe": "contrast",
        "scaffold": {
            "trajectory": ["present_case", "agent_classifies", "check_class"],
            "generator": "sample cases across the elicited exception distribution with known labels",
            "checker": "exact/rubric match on class; penalise use of non-elicited cues",
        },
    },
    "assessment": {
        "inference": "evaluate a case against norms to reach a verdict",
        "blind_spot": "cues are under-reported; verdicts look holistic",
        "probe": "constrained",
        "scaffold": {
            "trajectory": ["present_case", "agent_assesses", "check_verdict_and_criteria"],
            "generator": "generate cases with ground-truth verdicts weighted by exception frequency",
            "checker": "verdict match + quality_criteria compliance (LLM-judge rubric)",
        },
    },
    "diagnosis": {
        "inference": "from symptoms, hypothesise and discriminate causes",
        "blind_spot": "hypothesis ordering and early anomaly detection",
        "probe": "cdm_probe",
        "scaffold": {
            "trajectory": ["present_symptoms", "agent_investigates", "agent_names_cause", "check_root_cause"],
            "generator": "inject known faults into simulated systems",
            "checker": "root cause found; investigation steps vs elicited cue priorities",
        },
    },
    "monitoring": {
        "inference": "compare a stream against expectations; raise alarms",
        "blind_spot": "expectancies (what 'normal' feels like) are never written down",
        "probe": "cdm_probe",
        "scaffold": {
            "trajectory": ["stream_events", "agent_flags", "check_detection"],
            "generator": "generate event streams with injected anomalies at elicited frequencies",
            "checker": "detection recall/precision against injected anomalies",
        },
    },
    "prediction": {
        "inference": "project a system state into the future",
        "blind_spot": "base rates and reference-class choices",
        "probe": "confirm",
        "scaffold": {
            "trajectory": ["present_state", "agent_predicts", "score_calibration"],
            "generator": "scenarios with known outcomes from historical/exception distribution",
            "checker": "calibration and resolution scoring",
        },
    },
    "configuration": {
        "inference": "assemble components satisfying requirements and constraints",
        "blind_spot": "implicit constraints ('nobody would ever combine those')",
        "probe": "contrast",
        "scaffold": {
            "trajectory": ["present_requirements", "agent_configures", "check_constraints"],
            "generator": "sample requirement sets incl. constraint-violating traps",
            "checker": "hard-constraint satisfaction + elicited soft preferences",
        },
    },
    "planning": {
        "inference": "compose actions to reach a goal under constraints",
        "blind_spot": "preference trade-offs between valid plans",
        "probe": "contrast",
        "scaffold": {
            "trajectory": ["present_goal", "agent_plans", "check_plan"],
            "generator": "generate goals/resources incl. elicited exception scenarios",
            "checker": "plan validity + preference ordering (forced-choice rubric)",
        },
    },
    "scheduling": {
        "inference": "allocate jobs to resources over time",
        "blind_spot": "soft constraints and tacit priorities",
        "probe": "teach_back",
        "scaffold": {
            "trajectory": ["present_jobs", "agent_schedules", "check_schedule"],
            "generator": "job/resource sets stressing elicited soft constraints",
            "checker": "feasibility + soft-constraint score",
        },
    },
    "assignment": {
        "inference": "match items to slots one-to-one or many-to-one",
        "blind_spot": "tie-breaking rules",
        "probe": "contrast",
        "scaffold": {
            "trajectory": ["present_items_slots", "agent_assigns", "check_assignment"],
            "generator": "matching problems with near-ties at elicited frequencies",
            "checker": "assignment quality vs elicited tie-breaking rules",
        },
    },
}


def get(task_type: str) -> dict:
    return TASK_TYPES[task_type]
