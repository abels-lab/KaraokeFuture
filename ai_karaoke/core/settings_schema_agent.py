"""Settings for the embedded AI Co-Pilot / Host Assistant."""
from core.settings_kinds import NOW, _s

AGENT_SPECS = [
    _s("agent_provider", "agent", "AI Provider", "gemini", "choice",
       "Model provider for the host AI assistant. Google Gemini (Google AI Studio) is recommended for low latency.",
       NOW, choices=[["gemini", "Google Gemini (AI Studio)"], ["openai", "OpenAI / Local Ollama"]]),
    _s("agent_api_key", "agent", "API Key", "", "text",
       "Google AI Studio API key (starts with AIza...) or OpenAI API key. If left blank, reads from GEMINI_API_KEY environment variable.",
       NOW, max_len=128),
    _s("agent_model", "agent", "Model name", "gemini-3.8-flash", "text",
       "Model to use (e.g. gemini-3.8-flash, gemini-flash-latest, gemini-3.5-flash, or qwen2.5-coder:7b for Ollama).",
       NOW, max_len=64),
    _s("agent_base_url", "agent", "Custom Base URL", "", "text",
       "Custom endpoint when using a local LLM like Ollama or LM Studio (e.g. http://localhost:11434/v1). Leave blank for Gemini.",
       NOW, max_len=128),
    _s("agent_drawer_position", "agent", "DJ Co-Pilot Panel Side", "right", "choice",
       "Which side the DJ Co-Pilot drawer opens on (/tv): 'left' or 'right'. Left side keeps the queue sidebar visible.",
       NOW, client=True, choices=[["right", "Right side"], ["left", "Left side"]]),
    _s("agent_layout_mode", "agent", "DJ Co-Pilot Layout Mode", "split", "choice",
       "How DJ Co-Pilot opens on /tv: 'split' (docked 3-column stage) or 'drawer' (floating slide-over).",
       NOW, client=True, choices=[["split", "Docked Split Screen (Stage | Co-Pilot | Queue)"], ["drawer", "Floating Drawer Overlay"]]),
]
