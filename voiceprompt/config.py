"""
Defaults and runtime settings for VoicePrompt.
Override via environment variables (see README).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _env_int(key: str, default: int) -> int:
    v = os.environ.get(key)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    v = os.environ.get(key)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


@dataclass
class Settings:
    # Audio (16 kHz mono recommended for Whisper)
    sample_rate: int = _env_int("VOICEPROMPT_SAMPLE_RATE", 16000)
    block_ms: int = _env_int("VOICEPROMPT_BLOCK_MS", 30)
    speech_rms_threshold: float = _env_float("VOICEPROMPT_SPEECH_RMS", 0.012)
    min_speech_ms: int = _env_int("VOICEPROMPT_MIN_SPEECH_MS", 200)
    end_silence_ms: int = _env_int("VOICEPROMPT_END_SILENCE_MS", 700)
    max_utterance_s: float = _env_float("VOICEPROMPT_MAX_UTTERANCE_S", 25.0)

    # Faster Whisper — prefer small/base for latency; bump for accuracy
    whisper_model: str = os.environ.get("VOICEPROMPT_WHISPER_MODEL", "small")
    whisper_device: str = os.environ.get("VOICEPROMPT_WHISPER_DEVICE", "auto")
    whisper_compute_type: str = os.environ.get("VOICEPROMPT_WHISPER_COMPUTE", "default")
    whisper_vad_filter: bool = os.environ.get("VOICEPROMPT_WHISPER_VAD", "1") != "0"
    whisper_language: Optional[str] = os.environ.get("VOICEPROMPT_LANGUAGE") or None

    # LM Studio (OpenAI-compatible)
    lm_base_url: str = os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1")
    lm_api_key: str = os.environ.get("OPENAI_API_KEY", "lm-studio")
    lm_model: str = os.environ.get("VOICEPROMPT_LM_MODEL", "local-model")
    lm_temperature: float = _env_float("VOICEPROMPT_LM_TEMP", 0.35)
    lm_max_tokens: int = _env_int("VOICEPROMPT_LM_MAX_TOKENS", 512)

    # ComfyUI
    comfy_host: str = os.environ.get("VOICEPROMPT_COMFY_HOST", "127.0.0.1")
    comfy_port: int = _env_int("VOICEPROMPT_COMFY_PORT", 8188)
    comfy_workflow_path: str = os.environ.get(
        "VOICEPROMPT_COMFY_WORKFLOW",
        os.path.join("workflows", "voice-prompt_v01.json"),
    )
    # Positive prompt injection target (must exist on your exported graph).
    # workflows/voice-prompt_v01.json: PrimitiveStringMultiline node "76", field "value".
    comfy_prompt_node_id: str = os.environ.get("VOICEPROMPT_COMFY_PROMPT_NODE", "76")
    comfy_prompt_field: str = os.environ.get("VOICEPROMPT_COMFY_PROMPT_FIELD", "value")
    # Where ComfyUI writes Save Image files on disk (usually …/ComfyUI/output). Used if HTTP /view fails.
    comfy_output_dir: str = os.environ.get("VOICEPROMPT_COMFY_OUTPUT_DIR", "")
    # Override for VoicePrompt gallery files (default: <repo>/outputs/history).
    output_history_dir: str = os.environ.get("VOICEPROMPT_OUTPUT_DIR", "")

    # Rolling history list size (in-memory; PNGs still saved under ``outputs/history``).
    gallery_max: int = _env_int("VOICEPROMPT_GALLERY_MAX", 24)

    # Internal copy for overrides (patched at runtime)
    extra: dict = field(default_factory=dict)
