import json, re, httpx
from .config import config
SYSTEM = '''You are the execution planner for a personal remote computer operator. Return strict JSON only in this exact shape:
{"actions":[{"type":"shell|browser|app|file_read|file_write","value":"...","risk":"LOW|MEDIUM|HIGH","reason":"..."}],"summary":"..."}
Translate the user goal into a minimal, verifiable plan for the target operating system. For terminal actions, produce one command per action. Use browser actions only for full http(s) URLs. For file_write, value must be a file path on the first line and content after the first newline. Do not invent credentials. Do not carry out destructive, financial, identity, account, credential, or production-impacting actions unless the user explicitly requested them. End a change workflow with a verification action when feasible.'''
SAFE_SHORTCUTS={
    "pwd": {"actions":[{"type":"shell","value":"pwd","risk":"LOW","reason":"show working directory"}],"summary":"Show the runner working directory."},
    "where am i": {"actions":[{"type":"shell","value":"pwd","risk":"LOW","reason":"show working directory"}],"summary":"Show the runner working directory."},
    "list files": {"actions":[{"type":"shell","value":"ls -la","risk":"LOW","reason":"list current directory"}],"summary":"List files in the runner working directory."},
}
def explicit(text):
    text=text.strip()
    for prefix,kind in (("shell:","shell"),("browser:","browser"),("app:","app"),("read:","file_read"),("write:","file_write")):
        if text.lower().startswith(prefix): return {"actions":[{"type":kind,"value":text[len(prefix):].strip(),"risk":"HIGH" if kind=="shell" else "LOW","reason":"explicit action"}],"summary":"explicit action"}
    if text.lower() in SAFE_SHORTCUTS: return SAFE_SHORTCUTS[text.lower()]
    if re.match(r"^https?://",text): return {"actions":[{"type":"browser","value":text,"risk":"LOW","reason":"open URL"}],"summary":"open URL"}
    return None
def plan(text):
    if direct:=explicit(text): return direct
    if not (config.llm_base_url and config.llm_api_key and config.llm_model):
        raise RuntimeError("Natural-language task planning requires LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL on the runner. Explicit shell:, browser:, app:, read:, and write: requests remain available.")
    response=httpx.post(config.llm_base_url.rstrip("/")+"/chat/completions",headers={"Authorization":"Bearer "+config.llm_api_key,"Content-Type":"application/json"},json={"model":config.llm_model,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":text}],"temperature":0},timeout=75)
    response.raise_for_status(); content=response.json()["choices"][0]["message"]["content"].strip(); content=re.sub(r"^```(?:json)?\s*|\s*```$","",content,flags=re.I).strip(); data=json.loads(content)
    if not isinstance(data.get("actions"),list): raise ValueError("planner response has no actions array")
    return data
