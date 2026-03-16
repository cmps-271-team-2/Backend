from __future__ import annotations

import pytest

from app.services import openai_service


class FakeOpenAIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.chat = type("Chat", (), {"completions": type("Completions", (), {"create": self._chat_create})()})()
        self.embeddings = type("Embeddings", (), {"create": self._emb_create})()

    def _chat_create(self, **kwargs):
        message = type("Message", (), {"content": "assistant reply"})()
        choice = type("Choice", (), {"message": message})()
        return type("Resp", (), {"choices": [choice]})()

    def _emb_create(self, **kwargs):
        input = kwargs["input"]
        if isinstance(input, list):
            data = [type("Emb", (), {"embedding": [float(i)]})() for i, _ in enumerate(input, start=1)]
        else:
            data = [type("Emb", (), {"embedding": [0.1, 0.2]})()]
        return type("Resp", (), {"data": data})()


def test_openai_service_requires_api_key(monkeypatch):
    monkeypatch.setattr(openai_service, "OPENAI_API_KEY", None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        openai_service.OpenAIService()


def test_openai_service_methods(monkeypatch):
    monkeypatch.setattr(openai_service, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai_service, "OpenAI", FakeOpenAIClient)

    service = openai_service.OpenAIService()
    text = service.generate_llm_response([
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi"},
    ])
    emb = service.get_embedding("hello")
    embs = service.get_embeddings(["a", "b"])

    assert text == "assistant reply"
    assert emb == [0.1, 0.2]
    assert len(embs) == 2


def test_get_embeddings_empty_returns_empty(monkeypatch):
    monkeypatch.setattr(openai_service, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai_service, "OpenAI", FakeOpenAIClient)
    service = openai_service.OpenAIService()
    assert service.get_embeddings([]) == []
