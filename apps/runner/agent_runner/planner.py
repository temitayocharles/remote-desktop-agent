import json
import re

import httpx

from .config import config

SYSTEM = '''You are the execution planner for a personal remote computer operator. Return strict JSON only:
{"actions":[{"type":"shell|browser|browser_workflow|app|file_read|file_write","value":"... or an object for browser_workflow","risk":"LOW|MEDIUM|HIGH","reason":"..."}],"summary":"..."}
Translate the user goal into minimal, verifiable actions. browser is only for opening a URL. browser_workflow is for interacting with a website and must contain explicit steps or a supported workflow. Do not claim a goal is complete unless the requested artifact or page state can be verified. Do not invent credentials.'''

SAFE_SHORTCUTS = {
    "pwd": {"actions": [{"type": "shell", "value": "pwd", "risk": "LOW", "reason": "show working directory"}], "summary": "Show the runner working directory."},
    "where am i": {"actions": [{"type": "shell", "value": "pwd", "risk": "LOW", "reason": "show working directory"}], "summary": "Show the runner working directory."},
    "list files": {"actions": [{"type": "shell", "value": "ls -la", "risk": "LOW", "reason": "list current directory"}], "summary": "List files in the runner working directory."},
}


def _chatgpt_image(text: str):
    lowered = text.lower()
    if "chatgpt" not in lowered or not any(word in lowered for word in ("create", "generate", "make")):
        return None
    if not any(word in lowered for word in ("image", "photo", "picture", "artwork")):
        return None
    match = re.search(r"(?:create|generate|make)\s+(.*?)(?:\s+(?:and\s+)?save\b|$)", text, re.I)
    prompt = (match.group(1).strip() if match else text).strip(" .")
    destination = "~/Desktop/generated-image.png" if "desktop" in lowered else None
    return {
        "actions": [{
            "type": "browser_workflow",
            "value": {"workflow": "chatgpt_image", "prompt": prompt, "destination": destination},
            "risk": "LOW",
            "reason": "generate the explicitly requested image and verify it is saved locally",
        }],
        "summary": "Generate the requested image in ChatGPT and save a verified local copy.",
    }


def explicit(text):
    text = text.strip()
    image_plan = _chatgpt_image(text)
    if image_plan:
        return image_plan
    for prefix, kind in (("shell:", "shell"), ("browser:", "browser"), ("app:", "app"), ("read:", "file_read"), ("write:", "file_write")):
        if text.lower().startswith(prefix):
            return {"actions": [{"type": kind, "value": text[len(prefix):].strip(), "risk": "HIGH" if kind == "shell" else "LOW", "reason": "explicit action"}], "summary": "explicit action"}
    if text.lower() in SAFE_SHORTCUTS:
        return SAFE_SHORTCUTS[text.lower()]
    if re.match(r"^https?://", text):
        return {"actions": [{"type": "browser", "value": text, "risk": "LOW", "reason": "open URL"}], "summary": "Open URL."}
    return None


def plan(text):
    direct = explicit(text)
    if direct:
        return direct
    if not (config.llm_base_url and config.llm_api_key and config.llm_model):
        raise RuntimeError("Natural-language task planning requires LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL on the runner.")
    response = httpx.post(
        config.llm_base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": "Bearer " + config.llm_api_key, "Content-Type": "application/json"},
        json={"model": config.llm_model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}], "temperature": 0},
        timeout=75,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"].strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I).strip()
    data = json.loads(content)
    if not isinstance(data.get("actions"), list):
        raise ValueError("planner response has no actions array")
    return data
