"""DJ Co-Pilot over an OpenAI-compatible chat API (OpenAI, or a local Ollama / LM Studio at
Settings → AI Co-Pilot → Custom Base URL)."""
import json
from typing import Any

import httpx

from core import settings


def _lower_types(params: Any) -> Any:
    """Gemini's schema says "STRING", OpenAI's "string"."""
    if not isinstance(params, dict):
        return params
    return {k: v.lower() if k == "type" and isinstance(v, str) else _lower_types(v) for k, v in params.items()}


async def chat(message: str, history: list[dict], system: str, tools: list[dict], turn,
               model: str, api_key: str) -> dict[str, Any]:
    from services.agent.llm import MAX_ROUNDS
    url = (settings.get("agent_base_url").strip().rstrip("/") or "https://api.openai.com/v1") + "/chat/completions"
    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": message}]
    functions = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                   "parameters": _lower_types(t["parameters"])}} for t in tools]
    headers = {"Authorization": f"Bearer {api_key or 'local'}"}
    async with httpx.AsyncClient(timeout=45.0) as client:
        for _ in range(MAX_ROUNDS):
            res = await client.post(url, headers=headers, json={"model": model, "messages": messages,
                                                                "tools": functions})
            if res.status_code != 200:
                return {"reply": f"❌ API Error ({res.status_code}): {res.text[:200]}", "tool_calls": turn.tool_calls}
            msg = res.json()["choices"][0]["message"]
            messages.append(msg)
            if not msg.get("tool_calls"):
                return turn.done(msg.get("content") or "")
            for call in msg["tool_calls"]:
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                except ValueError:
                    args = {}
                result = await turn.run(call["function"]["name"], args)
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
    return turn.gave_up()
