"""Provider determinístico e offline — usado sem OPENAI_API_KEY, em testes e na demo."""

from __future__ import annotations

import hashlib

from app.ai.providers.base import LLMResponse


class FakeLLMProvider:
    name = "fake"
    model = "fake-deterministic-v1"

    async def complete(self, *, system: str, prompt: str, max_tokens: int = 800) -> LLMResponse:
        digest = hashlib.sha256((system + prompt).encode("utf-8")).hexdigest()[:8]
        # Final do prompt: é onde ficam os dados do usuário (documento, objetivo da cláusula)
        excerpt = " ".join(prompt.split())[-400:]
        content = (
            "[Resposta simulada — configure OPENAI_API_KEY para usar a OpenAI]\n"
            f"Referência: {digest}\n"
            f"Trecho da entrada: {excerpt}"
        )
        return LLMResponse(content=content, provider=self.name, model=self.model)
