"""Prompt enhancement via LM Studio’s OpenAI-compatible HTTP API."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from openai import OpenAI

from voiceprompt.config import Settings

_LEGACY_MODEL_PLACEHOLDER = "local-model"
_SYSTEM_PROMPT_FILE = Path(__file__).resolve().parent / "lm_system_default.txt"


def _load_system_instruction() -> str:
    """Single policy: FLUX rewriter text lives in ``lm_system_default.txt`` (edit that file to tune)."""
    if not _SYSTEM_PROMPT_FILE.is_file():
        raise RuntimeError(
            f"Missing {_SYSTEM_PROMPT_FILE.name} next to lm_client.py (expected at {_SYSTEM_PROMPT_FILE})."
        )
    text = _SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"{_SYSTEM_PROMPT_FILE.name} is empty — add the FLUX prompt-rewriter instructions.")
    return text


class PromptEnhancer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = OpenAI(base_url=settings.lm_base_url, api_key=settings.lm_api_key)
        self._resolved_model: Optional[str] = None
        self._system_instruction = _load_system_instruction()

    def _chat_model_id(self) -> str:
        """Use explicit VOICEPROMPT_LM_MODEL when set; else first id from ``/v1/models``."""
        configured = (self.settings.lm_model or "").strip()
        if configured and configured != _LEGACY_MODEL_PLACEHOLDER:
            return configured
        if self._resolved_model is not None:
            return self._resolved_model

        lst = self._client.models.list()
        data = getattr(lst, "data", None) or []
        ids: list[str] = []
        for m in data:
            mid = getattr(m, "id", None)
            if isinstance(mid, str) and mid:
                ids.append(mid)
        if not ids:
            raise RuntimeError(
                "LM Studio returned no models from /v1/models. "
                "Start the local server and load a model, or set VOICEPROMPT_LM_MODEL to the exact model id."
            )
        self._resolved_model = ids[0]
        return self._resolved_model

    def enhance(self, raw_spoken: str) -> str:
        text = (raw_spoken or "").strip()
        if not text:
            return ""

        rsp = self._client.chat.completions.create(
            model=self._chat_model_id(),
            temperature=float(self.settings.lm_temperature),
            max_tokens=int(self.settings.lm_max_tokens),
            messages=[
                {"role": "system", "content": self._system_instruction},
                {"role": "user", "content": text},
            ],
        )
        choice = rsp.choices[0].message.content or ""
        return choice.strip()
