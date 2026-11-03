"""DJ Co-Pilot over Google Gemini (AI Studio generateContent with function calling)."""
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _error_reply(status: int, text: str, model: str) -> str:
    tip = ""
    if status == 404:
        tip = (f"\n\n💡 *Tip: model '{model}' was not found. Try 'gemini-3.8-flash', 'gemini-flash-latest' "
               "or 'gemini-3.5-flash' in Settings → AI Co-Pilot.*")
    elif status == 400 and "API_KEY_INVALID" in text:
        tip = "\n\n💡 *Tip: the Google AI Studio API key looks invalid. Check Settings → AI Co-Pilot.*"
    return f"❌ Gemini API Error ({status}): {text[:250]}{tip}"


async def chat(message: str, history: list[dict], system: str, tools: list[dict], turn,
               model: str, api_key: str) -> dict[str, Any]:
    from services.agent.llm import MAX_ROUNDS
    clean_model = model.strip().removeprefix("models/")
    contents = [{"role": "model" if h["role"] == "assistant" else "user", "parts": [{"text": h["content"]}]}
                for h in history]
    contents.append({"role": "user", "parts": [{"text": message}]})
    declarations = [{"functionDeclarations": [{k: t[k] for k in ("name", "description", "parameters")}
                                              for t in tools]}]
    async with httpx.AsyncClient(timeout=30.0) as client:
        for _ in range(MAX_ROUNDS):
            res = await client.post(API.format(model=clean_model), headers={"x-goog-api-key": api_key}, json={
                "systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "tools": declarations})
            if res.status_code != 200:
                log.error("Gemini API error %d: %s", res.status_code, res.text)
                return {"reply": _error_reply(res.status_code, res.text, clean_model), "tool_calls": turn.tool_calls}
            candidates = res.json().get("candidates", [])
            if not candidates:
                return turn.done("Received an empty response from Gemini.")
            parts = candidates[0].get("content", {}).get("parts", [])
            calls = [part["functionCall"] for part in parts if "functionCall" in part]
            if not calls:
                return turn.done("\n".join(part.get("text", "") for part in parts if "text" in part).strip())
            contents.append({"role": "model", "parts": parts})
            answers = []
            for call in calls:
                result = await turn.run(call.get("name"), call.get("args") or {})
                answers.append({"functionResponse": {"name": call.get("name"), "response": {"result": result}}})
            contents.append({"role": "user", "parts": answers})
    return turn.gave_up()
