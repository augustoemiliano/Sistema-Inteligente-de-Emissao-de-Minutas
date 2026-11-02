from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.ai.providers import FakeLLMProvider, get_llm_provider
from app.ai.providers.openai_provider import OpenAIProvider
from app.core.config import get_settings

API = "/api/v1"


def test_factory_falls_back_to_fake_without_key() -> None:
    settings = get_settings().model_copy(update={"ai_provider": "auto", "openai_api_key": None})
    assert isinstance(get_llm_provider(settings), FakeLLMProvider)


def test_factory_uses_openai_when_key_present() -> None:
    settings = get_settings().model_copy(
        update={"ai_provider": "auto", "openai_api_key": "sk-test-nao-usada"}
    )
    provider = get_llm_provider(settings)
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == settings.openai_model


async def test_openai_provider_parses_response_with_stub_client() -> None:
    calls: list[dict] = []

    async def create(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(content="  Cláusula sugerida  ")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    stub = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    provider = OpenAIProvider(api_key="x", model="gpt-test", timeout=1, client=stub)
    result = await provider.complete(system="sys", prompt="oi")

    assert result.content == "Cláusula sugerida"
    assert result.provider == "openai"
    assert calls[0]["model"] == "gpt-test"
    assert calls[0]["messages"][0] == {"role": "system", "content": "sys"}


async def test_openai_provider_wraps_errors() -> None:
    import openai

    from app.ai.providers import LLMProviderError

    async def create(**_kwargs):
        raise openai.AuthenticationError(
            "chave inválida", response=_fake_http_response(401), body=None
        )

    stub = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    provider = OpenAIProvider(api_key="x", model="gpt-test", timeout=1, client=stub)
    with pytest.raises(LLMProviderError):
        await provider.complete(system="s", prompt="p")


def _fake_http_response(status: int):
    import httpx

    return httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1"))


def test_suggest_clause_with_fake_provider(client: TestClient, editor_headers) -> None:
    response = client.post(
        f"{API}/ai/clauses/suggest",
        json={"contract_type": "Locação residencial", "objective": "multa por atraso"},
        headers=editor_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "fake"
    assert "multa por atraso" in body["content"]


def test_review_minuta_and_audit(
    client: TestClient, editor_headers, admin_headers, minuta_id
) -> None:
    response = client.post(
        f"{API}/ai/review", json={"minuta_id": minuta_id}, headers=editor_headers
    )
    assert response.status_code == 200
    assert "Maria Silva" in response.json()["content"]

    logs = client.get(f"{API}/audit?action=ai.", headers=admin_headers).json()
    assert logs["total"] == 1
    assert logs["items"][0]["extra"]["minuta_id"] == minuta_id


def test_review_requires_exactly_one_source(client: TestClient, editor_headers, minuta_id) -> None:
    response = client.post(
        f"{API}/ai/review",
        json={"minuta_id": minuta_id, "text": "texto livre com mais de vinte caracteres"},
        headers=editor_headers,
    )
    assert response.status_code == 422


def test_viewer_cannot_use_ai(client: TestClient, viewer_headers) -> None:
    response = client.post(
        f"{API}/ai/review",
        json={"text": "texto livre com mais de vinte caracteres"},
        headers=viewer_headers,
    )
    assert response.status_code == 403
