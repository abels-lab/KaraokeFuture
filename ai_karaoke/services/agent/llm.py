"""One DJ Co-Pilot chat turn: pick the provider (Settings → AI Co-Pilot), let the model call the
asker's tools for up to MAX_ROUNDS rounds, and log tool errors and give-ups to the backlog."""
import os
from typing import Any

from core import auth, settings
from services.agent import llm_gemini, llm_openai, store
from services.agent.prompt import system_prompt
from services.agent.registry import execute_tool, tools_for

MAX_ROUNDS = 8
HISTORY_TURNS = 8


def _api_key() -> str:
    return settings.get("agent_api_key").strip() or os.getenv("GEMINI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")


def _clean_history(history: list[dict] | None) -> list[dict[str, str]]:
    """The last turns as plain {role: user|assistant, content} text: nothing else gets through."""
    out = []
    for h in (history or [])[-HISTORY_TURNS:]:
        if isinstance(h, dict) and isinstance(h.get("content"), str):
            role = "assistant" if h.get("role") in ("assistant", "model") else "user"
            out.append({"role": role, "content": h["content"][:2000]})
    return out


class Turn:
    """What happened during one turn: the tools run (shown as chips in the chat) and how to run one."""

    def __init__(self, who: auth.Who, message: str):
        self.who, self.message, self.tool_calls = who, message, []

    async def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        result = await execute_tool(name, args, self.who)
        self.tool_calls.append({"name": name, "args": args, "result": result})
        if "error" in result:
            store.record_improvement("tool_error", f"Tool '{name}' error: {result['error']}",
                                     {"tool": name, "args": args, "error": result["error"]}, self.message)
        return result

    def done(self, reply: str) -> dict[str, Any]:
        return {"reply": reply or "Done!", "tool_calls": self.tool_calls}

    def gave_up(self) -> dict[str, Any]:
        store.record_improvement("turn_limit_exhausted", f"Hit {MAX_ROUNDS}-round limit: {self.message[:100]}",
                                 {"tools_called": [t["name"] for t in self.tool_calls]}, self.message)
        used = ", ".join(dict.fromkeys(t["name"] for t in self.tool_calls)) or "various tools"
        return self.done(f"🎤 That took more steps than I'm allowed in one go (I used {used}). "
                         "I've noted it for the developers. Want to try it in smaller pieces?")


async def chat_with_agent(message: str, history: list[dict] | None, who: auth.Who) -> dict[str, Any]:
    provider, model, key = settings.get("agent_provider"), settings.get("agent_model"), _api_key()
    if provider == "gemini" and not key:
        return {"reply": "⚠️ Please add a **Google AI Studio API key** in Settings → AI Co-Pilot "
                         "(or set GEMINI_API_KEY on the laptop).", "tool_calls": []}
    turn = Turn(who, message)
    args = (message, _clean_history(history), system_prompt(who), tools_for(who), turn)
    if provider == "gemini":
        if not model or model.strip().removeprefix("models/") == "gemini-2.5-flash":
            model = "gemini-3.8-flash"
        return await llm_gemini.chat(*args, model=model, api_key=key)
    return await llm_openai.chat(*args, model=model, api_key=key)
