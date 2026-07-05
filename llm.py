"""Model-agnostic LLM client (stdlib only).

Anthropic Messages API by default; any OpenAI-compatible endpoint
(vLLM, Ollama, a Pleias model) via config. The consolidator is designed
so a frontier model bootstraps the knowledge and a small specialised
model can replace it later — this client is where that swap happens.
"""

from __future__ import annotations

import json
import os
import urllib.request


class LLMError(RuntimeError):
    pass


def chat(system: str, user: str, cfg: dict, max_tokens: int = 4096) -> str:
    llm = cfg.get("llm", {})
    provider = llm.get("provider", "anthropic")
    model = llm.get("model", "claude-sonnet-5")
    api_key = os.environ.get(llm.get("api_key_env", "ANTHROPIC_API_KEY"), "")

    if provider == "anthropic":
        url = (llm.get("base_url") or "https://api.anthropic.com") + "/v1/messages"
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        data = _post(url, body, headers)
        return "".join(b.get("text", "") for b in data.get("content", []))

    # openai-compatible
    url = (llm.get("base_url") or "https://api.openai.com") + "/v1/chat/completions"
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {"content-type": "application/json", "authorization": f"Bearer {api_key}"}
    data = _post(url, body, headers)
    return data["choices"][0]["message"]["content"]


def _post(url: str, body: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:  # pragma: no cover
        raise LLMError(f"LLM call failed ({e.code}): {e.read().decode()[:500]}") from e
    except urllib.error.URLError as e:  # pragma: no cover
        raise LLMError(f"LLM endpoint unreachable: {e.reason}") from e


def extract_json(text: str):
    """Tolerant JSON extraction from an LLM reply (handles code fences)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
    if start < 0:
        raise LLMError("no JSON found in LLM reply")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text[start:])
    return obj
