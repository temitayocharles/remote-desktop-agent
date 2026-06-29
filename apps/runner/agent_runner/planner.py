import json
import re
import shlex

import httpx

from .config import config

SYSTEM = '''You are the execution planner for a personal remote computer operator. Return strict JSON only:
{"actions":[{"type":"shell|browser|browser_open|browser_search|browser_workflow|app|macos_mail_search|file_read|file_write|unsupported_target","value":"... or an object","risk":"LOW|MEDIUM|HIGH","reason":"...","verify":{"result_verified":true}}],"summary":"..."}
Use minimal, truthful actions. browser and browser_open verify only that the OS accepted the launch. browser_search verifies that the named browser was asked to open the search URL; it does not claim to have read search results. browser_workflow is for interacting with a website and requires workflow-level evidence. Do not invent credentials, contacts, or phone access.'''

SAFE_SHORTCUTS = {
    "pwd": {"actions": [{"type": "shell", "value": "pwd", "risk": "LOW", "reason": "show working directory", "verify": {"result_verified": True}}], "summary": "Show the runner working directory."},
    "where am i": {"actions": [{"type": "shell", "value": "pwd", "risk": "LOW", "reason": "show working directory", "verify": {"result_verified": True}}], "summary": "Show the runner working directory."},
    "list files": {"actions": [{"type": "shell", "value": "ls -la", "risk": "LOW", "reason": "list current directory", "verify": {"result_verified": True}}], "summary": "List files in the runner working directory."},
}

BROWSER_NAMES = {"safari": "Safari", "brave": "Brave Browser", "brave browser": "Brave Browser", "chrome": "Google Chrome", "google chrome": "Google Chrome", "firefox": "Firefox"}


def _chatgpt_image(text: str):
    lowered = text.lower()
    if "chatgpt" not in lowered or not any(word in lowered for word in ("create", "generate", "make")):
        return None
    if not any(word in lowered for word in ("image", "photo", "picture", "artwork")):
        return None
    match = re.search(r"(?:create|generate|make)\s+(.*?)(?:\s+(?:and\s+)?save\b|$)", text, re.I)
    prompt = (match.group(1).strip() if match else text).strip(" .")
    destination = "~/Desktop/generated-image.png" if "desktop" in lowered else None
    return {"actions": [{"type": "browser_workflow", "value": {"workflow": "chatgpt_image", "prompt": prompt, "destination": destination}, "risk": "LOW", "reason": "generate the explicitly requested image and verify it is saved locally", "verify": {"result_verified": True}}], "summary": "Generate the requested image in ChatGPT and save a verified local copy."}


def _browser_search(text: str):
    lowered = text.lower()
    match = re.search(r"(?:open\s+)?(?P<browser>safari|brave(?:\s+browser)?|chrome|google\s+chrome|firefox)(?:\s+browser)?\s+(?:and\s+)?search\s+(?:for\s+)?(?P<query>.+)$", text, re.I)
    if not match:
        return None
    browser_key = re.sub(r"\s+", " ", match.group("browser").lower()).strip()
    query = match.group("query").strip(" .")
    if not query:
        return None
    return {"actions": [{"type": "browser_search", "value": {"browser": BROWSER_NAMES[browser_key], "query": query}, "risk": "LOW", "reason": "open the requested browser with the requested search URL", "verify": {"result_verified": True}}], "summary": f"Open {BROWSER_NAMES[browser_key]} with a search for: {query}"}


def _browser_open(text: str):
    lowered = text.lower()
    browser_match = re.search(r"(?:open\s+)?(?P<site>chatgpt)(?:\s+(?:in|with)\s+(?P<browser>safari|brave(?:\s+browser)?|chrome|google\s+chrome|firefox))?$", text.strip(), re.I)
    if not browser_match:
        return None
    browser_raw = browser_match.group("browser")
    browser = BROWSER_NAMES.get(re.sub(r"\s+", " ", browser_raw.lower()).strip()) if browser_raw else None
    return {"actions": [{"type": "browser_open", "value": {"url": "https://chatgpt.com/", "browser": browser}, "risk": "LOW", "reason": "open ChatGPT in the requested browser", "verify": {"result_verified": True}}], "summary": "Open ChatGPT."}


def _junk_mail(text: str):
    lowered = text.lower()
    if "mail" not in lowered or not any(word in lowered for word in ("spam", "junk")):
        return None
    if not any(word in lowered for word in ("search", "find", "show", "open", "list")):
        return None
    match = re.search(r"(?:for|about)\s+(.+?)(?:[?.!]|$)", text, re.I)
    query = match.group(1).strip() if match else ""
    if query.lower() in {"spam", "junk", "spam emails", "junk emails"}:
        query = ""
    return {"actions": [{"type": "macos_mail_search", "value": {"query": query, "limit": 20}, "risk": "LOW", "reason": "read-only search of Junk/Spam message metadata", "verify": {"result_verified": True}}], "summary": "Search the macOS Mail Junk/Spam mailbox and return matching message metadata."}


def _resume_search(text: str):
    lowered = text.lower()
    if "resume" not in lowered or not any(phrase in lowered for phrase in ("search for", "find", "any file named", "file named")):
        return None
    command = "mdfind 'kMDItemFSName == \"*Resume*\"cd' | grep -F \"$HOME/\" | head -n 200"
    return {"actions": [{"type": "shell", "value": command, "risk": "LOW", "reason": "use Spotlight metadata search within the local user home directory instead of recursively scanning disks", "verify": {"result_verified": True}}], "summary": "Find resume-named files indexed under the local user home directory."}


def _phone_target(text: str):
    if re.search(r"\b(on|from) my phone\b", text, re.I):
        return {"actions": [{"type": "unsupported_target", "value": "No phone runner is registered. This Mac runner cannot operate a phone; register a mobile runner or issue the request from the phone's own operator.", "risk": "LOW", "reason": "target device is not available"}], "summary": "Phone-targeted request cannot run on this Mac runner."}
    return None


def explicit(text: str):
    text = text.strip()
    for shortcut in (_phone_target, _chatgpt_image, _browser_search, _browser_open, _junk_mail, _resume_search):
        output = shortcut(text)
        if output:
            return output
    for prefix, kind in (("shell:", "shell"), ("browser:", "browser"), ("app:", "app"), ("read:", "file_read"), ("write:", "file_write")):
        if text.lower().startswith(prefix):
            return {"actions": [{"type": kind, "value": text[len(prefix):].strip(), "risk": "HIGH" if kind == "shell" else "LOW", "reason": "explicit action", "verify": {"result_verified": True}}], "summary": "Explicit action."}
    if text.lower() in SAFE_SHORTCUTS:
        return SAFE_SHORTCUTS[text.lower()]
    if re.match(r"^https?://", text):
        return {"actions": [{"type": "browser", "value": text, "risk": "LOW", "reason": "open URL", "verify": {"result_verified": True}}], "summary": "Open URL."}
    return None


def plan(text: str):
    direct = explicit(text)
    if direct:
        return direct
    if not (config.llm_base_url and config.llm_api_key and config.llm_model):
        raise RuntimeError("Natural-language task planning requires LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL on the runner.")
    response = httpx.post(config.llm_base_url.rstrip("/") + "/chat/completions", headers={"Authorization": "Bearer " + config.llm_api_key, "Content-Type": "application/json"}, json={"model": config.llm_model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}], "temperature": 0}, timeout=75)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"].strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I).strip()
    data = json.loads(content)
    if not isinstance(data.get("actions"), list) or not data["actions"]:
        raise ValueError("planner response has no executable actions")
    return data
