"""
Orchestration: segmented mic audio → Whisper → LM Studio → ComfyUI → disk image.

All heavy steps run off the realtime audio callback path (queue + worker thread).
"""

from __future__ import annotations

import queue
import threading
import time
import traceback
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from voiceprompt.audio_capture import UtteranceSegmenter
from voiceprompt.comfy_client import (
    ComfyClient,
    first_output_filename,
    inject_prompt,
    load_workflow,
    read_local_comfy_output,
)
from voiceprompt.config import Settings
from voiceprompt.lm_client import PromptEnhancer
from voiceprompt.state import AppState, GenerationRecord, outputs_dir
from voiceprompt.transcription import WhisperService


class VoicePipeline:
    def __init__(self, settings: Settings, state: AppState) -> None:
        self.settings = settings
        self.state = state
        self.whisper = WhisperService(settings)
        self.enhancer = PromptEnhancer(settings)
        self.comfy = ComfyClient(settings.comfy_host, settings.comfy_port)

        self._audio_q: queue.Queue[np.ndarray] = queue.Queue(maxsize=4)
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._segmenter: Optional[UtteranceSegmenter] = None
        self._mic_device: Optional[int] = None
        self._workflow_cache: Optional[dict] = None
        self._workflow_mtime: float = 0.0
        self._on_status: Callable[[str], None] = lambda s: None

    def set_status_hook(self, fn: Callable[[str], None]) -> None:
        self._on_status = fn

    def _set(self, msg: str) -> None:
        self.state.set_status(msg)
        self._on_status(msg)

    def set_microphone_device(self, device: Optional[int]) -> None:
        self._mic_device = device

    def reload_workflow_if_needed(self) -> dict:
        path = Path(self.settings.comfy_workflow_path)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        if self._workflow_cache is None or mtime != self._workflow_mtime:
            self._workflow_cache = load_workflow(path)
            self._workflow_mtime = mtime
        assert self._workflow_cache is not None
        return self._workflow_cache

    def warmup_whisper(self) -> None:
        """First call downloads/loads weights — run once at startup or on demand."""
        self._set("Loading Whisper model (first run can take a minute)…")
        silent = np.zeros(int(self.settings.sample_rate) // 4, dtype=np.float32)
        try:
            self.whisper.transcribe(silent)
        except Exception as e:
            self.state.remember_error(str(e))
            raise
        self._set("Ready")

    def start_listening(self) -> None:
        if self._segmenter is not None and self._segmenter.is_running():
            return

        if self._worker is None or not self._worker.is_alive():
            self._stop.clear()
            self._worker = threading.Thread(target=self._worker_loop, name="PipelineWorker", daemon=True)
            self._worker.start()

        def _enqueue(block: np.ndarray) -> None:
            try:
                self._audio_q.put_nowait(block)
            except queue.Full:
                # Drop if model is still busy — keeps latency predictable.
                pass

        self._segmenter = UtteranceSegmenter(
            self.settings,
            on_utterance=_enqueue,
            device=self._mic_device,
        )
        self._segmenter.start()
        self.state.set_listen_flag(True)
        self._set("Listening…")

    def stop_listening(self) -> None:
        if self._segmenter is not None:
            self._segmenter.stop()
            self._segmenter = None
        self.state.set_listen_flag(False)
        self._set("Ready")

    def shutdown(self) -> None:
        self.stop_listening()
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=2.0)
            self._worker = None

    def regenerate_last(self) -> None:
        enhanced = self.state.get_last_enhanced_prompt().strip()
        if not enhanced:
            self._set("Nothing to regenerate yet.")
            return

        def _job() -> None:
            try:
                self._generate_and_publish(enhanced=enhanced, raw_spoken="(regenerate)")
            except Exception as e:
                tb = traceback.format_exc()
                self.state.remember_error(str(e))
                self._set(f"Regenerate failed: {e}")
                print(tb)

        threading.Thread(target=_job, name="Regenerate", daemon=True).start()

    # --- internals ---

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                audio = self._audio_q.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                self._process_audio(audio)
            except Exception as e:
                tb = traceback.format_exc()
                self.state.remember_error(str(e))
                self._set(f"Error: {e}")
                print(tb)

    def _process_audio(self, audio: np.ndarray) -> None:
        self._set("Transcribing…")
        text, _lang = self.whisper.transcribe(audio)
        text = text.strip()
        if not text:
            self._set("Listening…")
            return

        print("", flush=True)
        print(f"[You said]  {text}", flush=True)
        self._set(f"Heard: “{text[:80]}{'…' if len(text) > 80 else ''}”")

        self._set("Enhancing prompt…")
        enhanced = self.enhancer.enhance(text).strip()
        if not enhanced:
            self.state.remember_transcripts(text, "")
            self._set("Listening…")
            return

        self.state.remember_transcripts(text, enhanced)
        self._generate_and_publish(enhanced=enhanced, raw_spoken=text)

    def _generate_and_publish(self, enhanced: str, raw_spoken: str) -> None:
        print("", flush=True)
        if raw_spoken == "(regenerate)":
            print("[Regen]     Reusing last enhanced prompt (see line below).", flush=True)
        print(f"[Enhanced]  {enhanced}", flush=True)
        print("", flush=True)
        self._set("Generating image…")
        base_wf = self.reload_workflow_if_needed()
        wf = inject_prompt(
            base_wf,
            node_id=str(self.settings.comfy_prompt_node_id),
            field=str(self.settings.comfy_prompt_field),
            prompt_text=enhanced,
        )
        pid = self.comfy.queue_prompt(wf)
        print(f"[VoicePrompt] Queued ComfyUI job prompt_id={pid}", flush=True)

        def _tick(elapsed_s: float) -> None:
            self._set(f"Generating image… ({int(elapsed_s)}s · ComfyUI)")

        hist = self.comfy.wait_for_finished(pid, on_tick=_tick)

        # Rare race: ``outputs`` exists but image rows are not listed yet on the first poll.
        for _ in range(40):
            try:
                fn, sub, folder_type = first_output_filename(hist)
                break
            except RuntimeError:
                time.sleep(0.12)
                refreshed = self.comfy.history(pid)
                if refreshed:
                    hist = refreshed
        else:
            raise RuntimeError(
                "ComfyUI finished, but no image entries were found in the history payload "
                "(check Save Image node id / Comfy version)."
            )

        binary = self._fetch_output_bytes(fn, subfolder=sub, folder_type=folder_type)

        ts = time.time()
        out_dir = outputs_dir(override_dir=(self.settings.output_history_dir or "").strip())
        out_path = out_dir / f"vp_{int(ts)}.png"
        out_path.write_bytes(binary)
        print(f"[VoicePrompt] Saved gallery image → {out_path.resolve()} ({len(binary)} bytes)", flush=True)

        rec = GenerationRecord(
            ts=ts,
            image_path=str(out_path.resolve()),
            raw_text=raw_spoken,
            enhanced_prompt=enhanced,
        )
        self.state.push_generation(rec)

        listening = self.state.is_listening()
        self._set("Listening…" if listening else "Ready")

    def _fetch_output_bytes(self, filename: str, subfolder: str, folder_type: str) -> bytes:
        """Prefer HTTP ``/view``; fall back to reading ComfyUI's on-disk ``output`` folder."""
        try:
            return self.comfy.get_image_binary(filename, subfolder=subfolder, folder_type=folder_type)
        except Exception as http_err:
            root = (self.settings.comfy_output_dir or "").strip()
            if not root:
                raise
            blob = read_local_comfy_output(Path(root), filename, subfolder=subfolder)
            if blob is not None:
                print(
                    f"[VoicePrompt] Loaded output from disk ({root}); HTTP /view failed: {http_err}",
                    flush=True,
                )
                return blob
            raise RuntimeError(
                f"Could not read image via HTTP or from Comfy's output folder.\n"
                f"HTTP: {http_err}\n"
                f"Disk tried: {root}\n"
                f"filename={filename!r} subfolder={subfolder!r} type={folder_type!r}"
            ) from http_err
