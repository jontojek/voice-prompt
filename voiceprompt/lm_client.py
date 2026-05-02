"""Prompt enhancement via LM Studio’s OpenAI-compatible HTTP API."""

from __future__ import annotations

from openai import OpenAI

from voiceprompt.config import Settings


class PromptEnhancer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = OpenAI(base_url=settings.lm_base_url, api_key=settings.lm_api_key)

    def enhance(self, raw_spoken: str) -> str:
        text = (raw_spoken or "").strip()
        if not text:
            return ""

        # Only ``user`` — system instructions belong in LM Studio’s preset / server UI.
        rsp = self._client.chat.completions.create(
            model=self.settings.lm_model,
            temperature=float(self.settings.lm_temperature),
            max_tokens=int(self.settings.lm_max_tokens),
            messages=[{"role": "user", "content": text}],
        )
        choice = rsp.choices[0].message.content or ""
        return choice.strip()
