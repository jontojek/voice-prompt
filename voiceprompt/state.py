"""Thread-safe shared state for UI and background workers."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class GenerationRecord:
    """Single gallery item."""

    ts: float
    image_path: str
    raw_text: str
    enhanced_prompt: str


class AppState:
    """Keeps status line, latest image path, and rolling gallery."""

    def __init__(self, gallery_max: int = 24) -> None:
        self._lock = threading.Lock()
        self.status: str = "Ready"
        self.listening: bool = False
        self.latest_image_path: Optional[str] = None
        self.last_raw_transcript: str = ""
        self.last_enhanced_prompt: str = ""
        self.gallery: List[GenerationRecord] = []
        self.gallery_max = gallery_max
        self.last_error: Optional[str] = None

    def set_status(self, text: str) -> None:
        with self._lock:
            self.status = text

    def get_snapshot(
        self,
    ) -> Tuple[str, bool, Optional[str], List[Tuple[float, str, str, str]], str, str, Optional[str]]:
        """Snapshot for console status / debugging."""
        with self._lock:
            thumbs = [(r.ts, r.image_path, r.raw_text[:120], r.enhanced_prompt[:200]) for r in self.gallery]
            return (
                self.status,
                self.listening,
                self.latest_image_path,
                thumbs,
                self.last_raw_transcript,
                self.last_enhanced_prompt,
                self.last_error,
            )

    def push_generation(self, record: GenerationRecord) -> None:
        with self._lock:
            self.latest_image_path = record.image_path
            self.gallery.insert(0, record)
            self.gallery[:] = self.gallery[: self.gallery_max]

    def set_listen_flag(self, on: bool) -> None:
        with self._lock:
            self.listening = on

    def remember_transcripts(self, raw: str, enhanced: str) -> None:
        with self._lock:
            self.last_raw_transcript = raw
            self.last_enhanced_prompt = enhanced

    def remember_error(self, msg: str) -> None:
        with self._lock:
            self.last_error = f"{msg} @ {time.strftime('%H:%M:%S')}"

    def get_last_enhanced_prompt(self) -> str:
        with self._lock:
            return self.last_enhanced_prompt

    def get_last_raw_transcript(self) -> str:
        with self._lock:
            return self.last_raw_transcript

    def is_listening(self) -> bool:
        with self._lock:
            return bool(self.listening)


def outputs_dir(base: Optional[Path] = None, override_dir: str = "") -> Path:
    """Directory for VoicePrompt gallery files (vp_*.png)."""
    override = (override_dir or os.environ.get("VOICEPROMPT_OUTPUT_DIR") or "").strip()
    if override:
        out = Path(override).expanduser().resolve()
    else:
        root = base or Path(__file__).resolve().parent.parent
        out = root / "outputs" / "history"
    out.mkdir(parents=True, exist_ok=True)
    return out
