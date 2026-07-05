"""MCP adapter: a thin VIEW into the core store.

The proactive loops (policy, consolidation, compilation) live in the
CLI core; this server only lets any MCP-capable assistant surface read
the knowledge model and write observations during normal work.

Run: `apprentice serve`   (requires `pip install apprentice-harness[mcp]`)
"""

from __future__ import annotations

import json

from . import policy
from .store import Store


def build_server(store: Store):
    from mcp.server.fastmcp import FastMCP  # lazy: optional dependency

    mcp = FastMCP("apprentice")

    @mcp.tool()
    def list_workflows() -> str:
        """List the workflows the apprentice is learning."""
        return json.dumps(store.list_workflows())

    @mcp.tool()
    def recall_context(workflow: str) -> str:
        """Inject the knowledge model for a workflow into the session.
        Call this at the start of any task that matches a known workflow."""
        model = store.load_model(workflow)
        return json.dumps(model, ensure_ascii=False)

    @mcp.tool()
    def log_observation(workflow: str, kind: str, content: str, note: str = "") -> str:
        """Record evidence from the current session.
        kind: 'volunteered' (context/constraints the user stated),
              'correction' (content = JSON {"draft": ..., "final": ...}),
              'artifact' (a template or exemplary document)."""
        if kind not in ("volunteered", "correction", "artifact"):
            return json.dumps({"error": "kind must be volunteered|correction|artifact"})
        payload: dict = {"note": note}
        if kind == "correction":
            try:
                payload.update(json.loads(content))
            except json.JSONDecodeError:
                payload["diff"] = content
        else:
            payload["content"] = content
        ep = store.append_episode(workflow, kind, payload)
        return json.dumps({"recorded": ep["id"]})

    @mcp.tool()
    def get_pending_question(workflow: str) -> str:
        """Fetch at most ONE budgeted elicitation question. Only call at a
        natural task boundary (work just completed), never mid-flow. May
        return nothing — the budget and convergence rules are server-side."""
        q = policy.next_question(store, workflow)
        return json.dumps(q or {"question": None}, ensure_ascii=False)

    @mcp.tool()
    def record_answer(workflow: str, question_id: str, answer: str) -> str:
        """Store the expert's answer to a previously served question."""
        ep = policy.record_answer(store, workflow, question_id, answer)
        return json.dumps({"recorded": ep["id"]})

    return mcp


def serve(store: Store) -> None:
    build_server(store).run()
