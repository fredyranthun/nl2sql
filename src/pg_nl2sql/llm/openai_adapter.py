"""OpenAI implementation of the LLM generator interface."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import error, request

from pydantic import ValidationError

from pg_nl2sql.llm.base import LLMError, LLMGenerator
from pg_nl2sql.models.generation import SQLGenerationResult
from pg_nl2sql.prompts.sql_generation import PromptBundle


@dataclass(frozen=True)
class OpenAIAdapter(LLMGenerator):
    """Generate SQL payloads using the OpenAI Chat Completions API."""

    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: int = 60

    def generate_sql(self, prompt: PromptBundle) -> SQLGenerationResult:
        body = {
            "model": self.model,
            "temperature": 1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt.system_prompt},
                {"role": "user", "content": prompt.user_prompt},
            ],
        }

        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        req = request.Request(
            endpoint,
            method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise LLMError(
                f"OpenAI request failed with HTTP {exc.code}: {details}"
            ) from exc
        except error.URLError as exc:
            raise LLMError(f"OpenAI request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMError("OpenAI request timed out.") from exc
        except json.JSONDecodeError as exc:
            raise LLMError("OpenAI response was not valid JSON.") from exc

        content = self._extract_message_content(payload)
        try:
            response_obj = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError("LLM response content was not valid JSON.") from exc

        try:
            return SQLGenerationResult.model_validate(response_obj)
        except ValidationError as exc:
            raise LLMError(f"LLM response violated output contract: {exc}") from exc

    @staticmethod
    def _extract_message_content(payload: dict[str, object]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMError("OpenAI response is missing choices.")

        first = choices[0]
        if not isinstance(first, dict):
            raise LLMError("OpenAI response has invalid choice format.")

        message = first.get("message")
        if not isinstance(message, dict):
            raise LLMError("OpenAI response is missing message content.")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMError("OpenAI message content is empty.")
        return content
