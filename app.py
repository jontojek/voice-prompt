"""
VoicePrompt — console entrypoint (speech → Whisper → LM Studio → ComfyUI → disk).

Run: python app.py   or   python run.py
"""

from __future__ import annotations

import atexit
import shlex

import sounddevice as sd

from voiceprompt.config import Settings
from voiceprompt.pipeline import VoicePipeline
from voiceprompt.state import AppState, outputs_dir


def _list_input_devices() -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for i, dev in enumerate(sd.query_devices()):
        if int(dev.get("max_input_channels", 0) or 0) > 0:
            rows.append((i, str(dev.get("name", "device"))))
    return rows


def _print_help() -> None:
    print(
        """
Commands (type one line and press Enter):
  help       Show this list
  start      Begin microphone listening
  stop       Stop listening
  warmup     Load Whisper once (recommended before first start)
  regen      Regenerate from last enhanced prompt (ComfyUI)
  status     Print status, last image path, last error
  mics       List microphone indices for ``mic <n>``
  mic <n>    Use microphone index n on next ``start`` (default: system default)
  quit       Exit

Tips:
  • LM Studio: put your FLUX / rewrite instructions in the server or chat preset — VoicePrompt only
    sends your spoken line as the ``user`` message.
  • Speak, then pause briefly so Whisper knows you finished the phrase.
  • Saved PNGs: outputs/history/vp_*.png
""".strip(),
        flush=True,
    )


def main() -> None:
    settings = Settings()
    state = AppState(gallery_max=settings.gallery_max)
    pipeline = VoicePipeline(settings, state)
    atexit.register(pipeline.shutdown)

    gallery_root = outputs_dir(override_dir=(settings.output_history_dir or "").strip())

    def _on_status(msg: str) -> None:
        print(msg, flush=True)

    pipeline.set_status_hook(_on_status)

    print(
        f"[VoicePrompt] Images save under: {gallery_root.resolve()}",
        flush=True,
    )
    print("Type `help` for commands. Ctrl+C or `quit` to exit.\n", flush=True)

    try:
        while True:
            try:
                line = input("voice-prompt> ").strip()
            except EOFError:
                break
            if not line:
                continue
            parts = shlex.split(line)
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in ("quit", "exit", "q"):
                break
            if cmd == "help":
                _print_help()
            elif cmd == "start":
                pipeline.start_listening()
            elif cmd == "stop":
                pipeline.stop_listening()
            elif cmd == "warmup":
                try:
                    pipeline.warmup_whisper()
                except Exception:
                    pass
            elif cmd == "regen":
                pipeline.regenerate_last()
            elif cmd == "status":
                snap = state.get_snapshot()
                st, listening, preview, thumbs, raw_t, enh_t, err = snap
                print(f"  status:    {st}", flush=True)
                print(f"  listening: {listening}", flush=True)
                print(f"  latest:    {preview}", flush=True)
                print(f"  gallery:   {len(thumbs)} item(s)", flush=True)
                if err:
                    print(f"  error:     {err}", flush=True)
            elif cmd == "mics":
                for idx, name in _list_input_devices():
                    print(f"  {idx}: {name}", flush=True)
            elif cmd == "mic":
                if not args:
                    print("Usage: mic <index>   (see ``mics``)", flush=True)
                    continue
                try:
                    n = int(args[0])
                except ValueError:
                    print("Mic index must be a number.", flush=True)
                    continue
                pipeline.set_microphone_device(n)
                print(f"Microphone set to index {n}. Use ``start`` to listen.", flush=True)
            else:
                print(f"Unknown command: {cmd}   (try ``help``)", flush=True)

    except KeyboardInterrupt:
        print("\n[VoicePrompt] Interrupted.", flush=True)
    finally:
        pipeline.shutdown()


if __name__ == "__main__":
    main()
