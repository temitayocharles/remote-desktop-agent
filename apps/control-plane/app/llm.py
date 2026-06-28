import json
import os
import re
from typing import Any
import httpx

CHAT_HINTS = re.compile(r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|how are you\??|thanks|thank you|what can you do\??|help)\s*$", re.I)
OPS_HINTS = re.compile(r"\b(?:pwd|ls|list|open|close|search|find|read|write|create|edit|run|test|build|deploy|restart|install|uninstall|check|inspect|monitor|download|upload|git|docker|kubectl|terraform|browser|terminal|file|folder|directory|application|app)\b", re.I)

class LLMUnavailable(RuntimeError):
    pass

def config() -> tuple[str, str, str]:
    base = os.getenv("LLM_BASE_URL", "").rstrip("/")
    key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "")
    return base, key, model

def is_configured() -> bool:
    base, key, model = config()
    return bool(base and key and model)

def _chat(messages: list[dict[str, str]], temperature: float = 0) -> str:
    base, key, model = config()
    if not (base and key and model):
        raise LLMUnavailable("LLM reasoning is not configured")
    response = httpx.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": temperature},
        timeout=75,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM returned an empty response")
    return content.strip()

def classify(text: str) -> dict[str, Any]:
    text = text.strip()
    if CHAT_HINTS.match(text):
        return {"kind": "chat", "reason": "conversation"}
    if OPS_HINTS.search(text):
        return {"kind": "task", "reason": "operational intent"}
    if not is_configured():
        return {"kind": "chat", "reason": "conversation fallback"}
    system = (
        "Classify the user message for a personal remote operator. Return strict JSON only: "
        '{"kind":"chat|task","reason":"short explanation"}. '
        "Use task only when the user wants an action performed on a registered computer, browser, file, application, terminal, or connected service. "
        "Use chat for conversation, questions, explanations, or ambiguous social messages."
    )
    raw = _chat([{"role":"system","content":system},{"role":"user","content":text}])
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I).strip()
    data = json.loads(raw)
    if data.get("kind") not in {"chat", "task"}:
        raise ValueError("LLM classifier returned an invalid kind")
    return data

def chat_reply(text: str) -> str:
    if not is_configured():
        if CHAT_HINTS.match(text):
            return "I am online and ready. Tell me what you want done on a registered device."
        return "I can execute work on your registered devices. Configure LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL to enable free-form conversation and natural-language task planning."
    return _chat([
        {"role":"system", "content": "You are a concise personal operations assistant in Telegram. Answer naturally. Do not claim to have performed a task unless the runner result confirms it. For requests that require device actions, ask the user to state the intended outcome clearly."},
        {"role":"user", "content": text},
    ], temperature=0.3)
