"""Plain-file knowledge store.

$APPRENTICE_HOME (default ~/.apprentice, or ./.apprentice if present)
├─ config.yaml
└─ workflows/<name>/
   ├─ model.yaml        the knowledge model (employee-owned artifact)
   ├─ episodes.jsonl    append-only observation log (raw evidence)
   └─ questions.yaml    question queue with status + yield tracking

Git-friendly on purpose: version it, diff it, merge it. Nothing hidden.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from . import schema

DEFAULT_CONFIG = {
    "owner": "",
    "question_budget_per_day": 3,
    "teach_back_every_n_episodes": 25,
    "yield_threshold": 0.2,
    "yield_window": 20,
    "llm": {
        "provider": "anthropic",          # anthropic | openai-compatible
        "model": "claude-sonnet-5",
        "base_url": "",                    # override for openai-compatible / local
        "api_key_env": "ANTHROPIC_API_KEY",
    },
}


def home() -> Path:
    env = os.environ.get("APPRENTICE_HOME")
    if env:
        return Path(env)
    local = Path.cwd() / ".apprentice"
    if local.is_dir():
        return local
    return Path.home() / ".apprentice"


class Store:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else home()

    # -- lifecycle -----------------------------------------------------
    def init(self, owner: str) -> Path:
        (self.root / "workflows").mkdir(parents=True, exist_ok=True)
        cfg_path = self.root / "config.yaml"
        if not cfg_path.exists():
            cfg = dict(DEFAULT_CONFIG)
            cfg["owner"] = owner
            cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
        return self.root

    def config(self) -> dict:
        cfg_path = self.root / "config.yaml"
        cfg = dict(DEFAULT_CONFIG)
        if cfg_path.exists():
            cfg.update(yaml.safe_load(cfg_path.read_text()) or {})
        return cfg

    # -- workflows -----------------------------------------------------
    def workflow_dir(self, name: str) -> Path:
        return self.root / "workflows" / name

    def list_workflows(self) -> list[str]:
        wf = self.root / "workflows"
        if not wf.is_dir():
            return []
        return sorted(p.name for p in wf.iterdir() if (p / "model.yaml").exists())

    def create_workflow(self, name: str, task_type: str, description: str = "") -> dict:
        d = self.workflow_dir(name)
        if (d / "model.yaml").exists():
            raise FileExistsError(f"workflow '{name}' already exists")
        d.mkdir(parents=True, exist_ok=True)
        model = schema.empty_model(name, task_type, self.config().get("owner", ""), description)
        self.save_model(name, model)
        (d / "episodes.jsonl").touch()
        self._save_questions(name, {"queue": [], "asked": []})
        return model

    # -- model ---------------------------------------------------------
    def load_model(self, name: str) -> dict:
        p = self.workflow_dir(name) / "model.yaml"
        if not p.exists():
            raise FileNotFoundError(f"no such workflow: {name}")
        return yaml.safe_load(p.read_text())

    def save_model(self, name: str, model: dict) -> None:
        p = self.workflow_dir(name) / "model.yaml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(yaml.safe_dump(model, sort_keys=False, allow_unicode=True))

    # -- episodes (append-only) -----------------------------------------
    def append_episode(self, name: str, kind: str, payload: dict) -> dict:
        """kind: correction | volunteered | artifact | answer | interview"""
        ep = {
            "id": schema.new_id("ep"),
            "ts": schema.now(),
            "kind": kind,
            "consolidated": False,
            "payload": payload,
        }
        path = self.workflow_dir(name) / "episodes.jsonl"
        with path.open("a") as f:
            f.write(json.dumps(ep, ensure_ascii=False) + "\n")
        return ep

    def episodes(self, name: str, unconsolidated_only: bool = False) -> list[dict]:
        path = self.workflow_dir(name) / "episodes.jsonl"
        if not path.exists():
            return []
        eps = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if unconsolidated_only:
            eps = [e for e in eps if not e.get("consolidated")]
        return eps

    def mark_consolidated(self, name: str, episode_ids: set[str]) -> None:
        eps = self.episodes(name)
        for e in eps:
            if e["id"] in episode_ids:
                e["consolidated"] = True
        path = self.workflow_dir(name) / "episodes.jsonl"
        path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in eps))

    # -- questions -------------------------------------------------------
    def questions(self, name: str) -> dict:
        p = self.workflow_dir(name) / "questions.yaml"
        if not p.exists():
            return {"queue": [], "asked": []}
        return yaml.safe_load(p.read_text()) or {"queue": [], "asked": []}

    def _save_questions(self, name: str, q: dict) -> None:
        p = self.workflow_dir(name) / "questions.yaml"
        p.write_text(yaml.safe_dump(q, sort_keys=False, allow_unicode=True))

    def save_questions(self, name: str, q: dict) -> None:
        self._save_questions(name, q)

    # -- reports -----------------------------------------------------------
    def write_report(self, name: str, stem: str, text: str) -> Path:
        d = self.workflow_dir(name) / "reports"
        d.mkdir(exist_ok=True)
        p = d / f"{stem}-{schema.now()[:10]}.md"
        p.write_text(text)
        return p
