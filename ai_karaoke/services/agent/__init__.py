"""DJ Co-Pilot: party chat that orders songs and restyles the screens in plain language.

It acts with the rights of whoever is talking (registry.py) and changes the look only through
settings (tools_style.py, custom CSS checked by core/css_guard.py); it has no access to files or code.
  store.py      Control Panel layout + improvement backlog       prompt.py   instructions + who's talking
  schema_*.py   tool definitions                                 tools_*.py  what the tools do
  llm.py        one chat turn (llm_gemini.py, llm_openai.py)
"""
from services.agent.llm import chat_with_agent
from services.agent.registry import execute_tool, tools_for
from services.agent.store import get_ui_config, list_improvements, record_improvement

__all__ = ["chat_with_agent", "execute_tool", "tools_for", "get_ui_config", "list_improvements",
           "record_improvement"]
