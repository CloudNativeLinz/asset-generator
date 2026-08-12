from __future__ import annotations

import json
from typing import Any

import requests

from .config import AzureOpenAISettings


class LLMError(RuntimeError):
    pass


def _extract_text_from_message(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()

    return ""


def azure_chat_completion(
    settings: AzureOpenAISettings, *, system_prompt: str, user_prompt: str
) -> str:
    endpoint = settings.endpoint.rstrip("/")
    url = (
        f"{endpoint}/openai/deployments/{settings.deployment}/chat/completions"
        f"?api-version={settings.api_version}"
    )

    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
    }

    headers = {
        "Content-Type": "application/json",
        "api-key": settings.api_key,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=45)
    except requests.RequestException as exc:
        raise LLMError(f"Failed to reach Azure OpenAI: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip()[:500]
        raise LLMError(f"Azure OpenAI request failed ({response.status_code}): {detail}")

    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise LLMError("Azure OpenAI returned non-JSON response") from exc

    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMError("Azure OpenAI response did not include choices")

    message = choices[0].get("message", {})
    text = _extract_text_from_message(message.get("content"))
    if not text:
        raise LLMError("Azure OpenAI returned an empty completion")

    return text
