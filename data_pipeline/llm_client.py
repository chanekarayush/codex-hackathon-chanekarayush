"""OpenAI JSON-mode LLM client with rate-limit retries."""

from __future__ import annotations

import os
from dataclasses import dataclass

from data_pipeline.common import call_with_backoff, get_logger


@dataclass(frozen=True)
class LLMConfig:
    model: str
    temperature: float = 0.0
    max_attempts: int = 6


def load_llm_config() -> LLMConfig:
    model = os.getenv("DITTO_LLM_MODEL", "gpt-4o-mini")
    temperature = float(os.getenv("DITTO_LLM_TEMPERATURE", "0"))
    max_attempts = int(os.getenv("DITTO_LLM_MAX_ATTEMPTS", "6"))
    return LLMConfig(
        model=model,
        temperature=temperature,
        max_attempts=max_attempts,
    )


class LLMClient:
    """OpenAI adapter for JSON-returning enrichment calls."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or load_llm_config()
        self.logger = get_logger(__name__)

    def generate_json_text(self, *, system_prompt: str, user_text: str) -> str:
        return call_with_backoff(
            lambda: self._generate_openai(system_prompt=system_prompt, user_text=user_text),
            logger=self.logger,
            max_attempts=self.config.max_attempts,
        )

    def _generate_openai(self, *, system_prompt: str, user_text: str) -> str:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for LLM enrichment.")

        from openai import OpenAI

        client = OpenAI()
        response = client.chat.completions.create(
            model=self.config.model,
            temperature=self.config.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("OpenAI returned an empty response.")
        return content
