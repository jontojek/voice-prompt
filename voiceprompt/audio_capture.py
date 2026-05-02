"""
Low-latency mic capture + simple energy/VAD segmentation.

Segments an utterance when RMS stays below threshold for ``end_silence_ms``
after speech was detected. This gates Whisper so we only run ASR after a
natural pause (fast path when user is silent).
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from voiceprompt.config import Settings


def _rms(block: np.ndarray) -> float:
    if block.size == 0:
        return 0.0
    x = block.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(np.square(x))))


class UtteranceSegmenter:
    """
    Pulls mono int16 audio from the default (or selected) device and invokes
    ``on_utterance(block_f32)`` with float32 mono samples in [-1, 1] at
    ``settings.sample_rate`` when a pause ends an utterance.
    """

    def __init__(
        self,
        settings: Settings,
        on_utterance: Callable[[np.ndarray], None],
        device: Optional[int] = None,
    ) -> None:
        self.settings = settings
        self.on_utterance = on_utterance
        self.device = device
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._stream: Optional[sd.InputStream] = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="UtteranceSegmenter", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._stream is not None:
            try:
                self._stream.abort()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        sr = int(self.settings.sample_rate)
        block_samples = max(1, int(sr * self.settings.block_ms / 1000))
        silence_blocks = max(1, int(self.settings.end_silence_ms / self.settings.block_ms))
        min_blocks = max(1, int(self.settings.min_speech_ms / self.settings.block_ms))
        max_samples = int(self.settings.max_utterance_s * sr)

        buffer: list[np.ndarray] = []
        in_speech = False
        speech_blocks = 0
        trailing_silence = 0

        def callback(indata, frames, _, status) -> None:  # type: ignore[no-untyped-def]
            nonlocal buffer, in_speech, speech_blocks, trailing_silence
            if status:
                pass
            mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
            level = _rms(mono)

            voiced = level >= float(self.settings.speech_rms_threshold)

            if not in_speech:
                if voiced:
                    in_speech = True
                    speech_blocks = 1
                    trailing_silence = 0
                    buffer = [mono]
                return

            buffer.append(mono)
            total = sum(b.shape[0] for b in buffer)

            if voiced:
                speech_blocks += 1
                trailing_silence = 0
            else:
                trailing_silence += 1

            utterance_done = trailing_silence >= silence_blocks and speech_blocks >= min_blocks
            too_long = total >= max_samples

            if utterance_done or too_long:
                pcm = np.concatenate(buffer, axis=0)
                f32 = (pcm.astype(np.float32)) / 32768.0
                in_speech = False
                speech_blocks = 0
                trailing_silence = 0
                buffer = []
                if f32.shape[0] > sr // 10:
                    try:
                        self.on_utterance(f32.copy())
                    except Exception:
                        # Caller handles logging; avoid killing audio thread.
                        pass

            elif total >= max_samples * 2:
                buffer.pop(0)

        try:
            self._stream = sd.InputStream(
                device=self.device,
                channels=1,
                dtype="int16",
                samplerate=sr,
                blocksize=block_samples,
                callback=callback,
            )
            self._stream.start()
            while not self._stop.is_set():
                time.sleep(0.05)
        except Exception:
            raise
        finally:
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
