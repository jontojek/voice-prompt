"""Faster Whisper wrapper tuned for short utterances."""

from __future__ import annotations

import threading
from typing import Optional, Tuple

import numpy as np

from voiceprompt.config import Settings


def _to_whisper_16k_mono(audio_f32: np.ndarray, sample_rate: int) -> np.ndarray:
    """Whisper models expect 16 kHz mono float32; cheap linear resample if needed."""
    if sample_rate == 16000:
        return np.ascontiguousarray(audio_f32, dtype=np.float32)
    if audio_f32.size == 0:
        return audio_f32.astype(np.float32)
    target_n = max(1, int(round(audio_f32.shape[0] * 16000 / float(sample_rate))))
    x_old = np.linspace(0.0, 1.0, num=audio_f32.shape[0], endpoint=False, dtype=np.float64)
    x_new = np.linspace(0.0, 1.0, num=target_n, endpoint=False, dtype=np.float64)
    y = np.interp(x_new, x_old, audio_f32.astype(np.float64))
    return y.astype(np.float32)


class WhisperService:
    """Lazy-loads the model once; safe to call from a worker thread."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._model = None
        self._loaded_key: tuple[str, str, str] | None = None

    def _ensure_model(self) -> None:
        device = self.settings.whisper_device
        compute_type = self.settings.whisper_compute_type
        if compute_type == "default":
            compute_type = "float16" if device == "cuda" else "int8"
        model_name = self.settings.whisper_model
        key = (model_name, str(device), str(compute_type))
        if self._model is not None and self._loaded_key == key:
            return
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model_name, device=device, compute_type=compute_type)
        self._loaded_key = key

    def transcribe(self, audio_f32: np.ndarray) -> Tuple[str, Optional[str]]:
        """
        Returns (text, detected_language). Text may be empty if silent/noise.
        """
        with self._lock:
            self._ensure_model()
            assert self._model is not None
            audio_16k = _to_whisper_16k_mono(audio_f32, int(self.settings.sample_rate))
            segments, info = self._model.transcribe(
                audio_16k,
                language=self.settings.whisper_language,
                vad_filter=bool(self.settings.whisper_vad_filter),
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            parts: list[str] = []
            for seg in segments:
                t = (seg.text or "").strip()
                if t:
                    parts.append(t)
            text = " ".join(parts).strip()
            lang = getattr(info, "language", None)
            return text, lang
