import sys
sys.path.insert(0, "apps/control-plane")
from app.llm import classify, chat_reply

def test_greetings_are_conversation_without_llm(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert classify("Hello")["kind"] == "chat"
    assert "online" in chat_reply("How are you?").lower()

def test_operational_intent_is_task_without_llm(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert classify("pwd")["kind"] == "task"
