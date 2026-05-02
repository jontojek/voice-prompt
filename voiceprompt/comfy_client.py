"""
Minimal ComfyUI API client (local HTTP).

Loads an API-format workflow JSON and injects the positive prompt into a
CLIP Text Encode node (configurable keys). Saves the decoded output PNG to disk.
Adapt ``workflows/*.json`` to your Flux.2 Klein graph and node ids.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests


def _extract_history_entry(data: Any, prompt_id: str) -> Optional[Dict[str, Any]]:
    """
    ComfyUI usually returns ``{ "<prompt_id>": { ... } }``, but versions differ.
    Some builds return a flat record with ``outputs`` / ``status`` at the top level.
    """
    if not isinstance(data, dict):
        return None
    if prompt_id in data and isinstance(data[prompt_id], dict):
        return data[prompt_id]
    # Single-entry shorthand
    if len(data) == 1:
        sole = next(iter(data.values()))
        if isinstance(sole, dict):
            return sole
    # Flat record (seen on some ``/history_v2``-style payloads)
    if "outputs" in data or isinstance(data.get("status"), dict):
        return data
    return None


def _outputs_have_images(outputs: Any) -> bool:
    if not isinstance(outputs, dict):
        return False
    for node_out in outputs.values():
        imgs = (node_out or {}).get("images") if isinstance(node_out, dict) else None
        if imgs:
            return True
    return False


def _execution_done(entry: Dict[str, Any]) -> bool:
    """
    Only treat the run as finished once ``outputs`` lists saved images.

    Some ComfyUI builds set ``status.completed`` before ``outputs.images`` is
    populated; finishing early caused ``first_output_filename`` to fail and
    nothing to appear in the UI/logs as expected.
    """
    return _outputs_have_images(entry.get("outputs"))


# ComfyUI puts normal lifecycle events in ``status.messages`` too — never treat these as failures.
_IGNORE_EXECUTION_TAGS = frozenset(
    {
        "execution_cached",
        "execution_start",
        "execution_success",
        "execution_interrupted",
        "executing",
        "progress",
        "progress_state",
    }
)


def _execution_error_message(entry: Dict[str, Any]) -> Optional[str]:
    """Turn ComfyUI history errors into a short user-visible string."""
    status = entry.get("status")
    if not isinstance(status, dict):
        return None

    messages = status.get("messages")
    if messages:
        parts: list[str] = []
        for m in messages:
            try:
                if isinstance(m, (list, tuple)) and len(m) >= 2:
                    tag = str(m[0])
                    payload = m[1]
                    if tag == "execution_error":
                        if isinstance(payload, dict):
                            parts.append(payload.get("exception_message") or str(payload))
                        else:
                            parts.append(str(payload))
                    elif tag in _IGNORE_EXECUTION_TAGS:
                        continue
                    else:
                        # Unknown tags are usually informational; do not abort the pipeline.
                        continue
                else:
                    continue
            except Exception:
                continue
        if parts:
            return "; ".join(p for p in parts if p)[:2000]

    err = status.get("error") or status.get("error_message")
    if err:
        return str(err)

    if (status.get("status_str") or "").lower() == "error":
        return "ComfyUI reported execution error (see ComfyUI console for details)."

    return None


class ComfyClient:
    def __init__(self, host: str, port: int) -> None:
        self.base = f"http://{host}:{port}"

    def queue_prompt(self, workflow: Dict[str, Any], client_id: Optional[str] = None) -> str:
        cid = client_id or str(uuid.uuid4())
        resp = requests.post(
            f"{self.base}/prompt",
            json={"prompt": workflow, "client_id": cid},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        pid = data.get("prompt_id")
        if not pid:
            raise RuntimeError(f"No prompt_id in response: {data}")
        return str(pid)

    def history(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Normalize ``/history/{prompt_id}`` (and optional ``/history_v2``) payloads."""
        for path in (f"/history/{prompt_id}", f"/history_v2/{prompt_id}"):
            try:
                r = requests.get(f"{self.base}{path}", timeout=30)
            except requests.RequestException:
                continue
            if r.status_code != 200:
                continue
            try:
                data = r.json()
            except ValueError:
                continue
            entry = _extract_history_entry(data, prompt_id)
            if entry is not None:
                return entry
        return None

    def wait_for_finished(
        self,
        prompt_id: str,
        poll_s: float = 0.15,
        timeout_s: float = 600.0,
        on_tick: Optional[Callable[[float], None]] = None,
    ) -> Dict[str, Any]:
        """
        Wait until ComfyUI records outputs or marks completion.

        Some builds omit ``status.completed`` until late or structure ``status``
        differently; we also treat non-empty ``outputs`` as done.
        """
        t0 = time.time()
        last_ui = -1.0
        while time.time() - t0 < timeout_s:
            elapsed = time.time() - t0
            if on_tick is not None and elapsed - last_ui >= 0.9:
                last_ui = elapsed
                try:
                    on_tick(elapsed)
                except Exception:
                    pass

            h = self.history(prompt_id)
            if not h:
                time.sleep(poll_s)
                continue

            err = _execution_error_message(h)
            if err:
                raise RuntimeError(err)

            if _execution_done(h):
                return h

            time.sleep(poll_s)

        raise TimeoutError(
            f"ComfyUI prompt {prompt_id} did not finish within {timeout_s}s "
            f"(is ComfyUI running on {self.base}, GPU busy, or queue stuck?)."
        )

    def get_image_binary(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        """Fetch rendered file via /view."""
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        r = requests.get(f"{self.base}/view", params=params, timeout=120)
        r.raise_for_status()
        return r.content


def load_workflow(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(
            f"Workflow not found: {p.resolve()}\n"
            "Export an API-format graph from ComfyUI (Save / API format) and point settings to it."
        )
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Workflow JSON must be an object keyed by node id strings.")
    # Comfy API keys are string node ids: "9", "76", and subgraph ids like "75:65".
    # Only strip human-only keys (e.g. "__doc__"), not colons — isdigit() would drop subgraphs.
    _node_id = re.compile(r"^(?:\d+)(?::\d+)*$")

    def _keep_key(k: object) -> bool:
        s = str(k)
        if s.startswith("__"):
            return False
        return bool(_node_id.match(s))

    return {str(k): v for k, v in data.items() if _keep_key(k)}


def inject_prompt(
    workflow: Dict[str, Any],
    node_id: str,
    field: str,
    prompt_text: str,
) -> Dict[str, Any]:
    """Returns a deep-copied workflow with the text field replaced."""
    import copy

    wf = copy.deepcopy(workflow)
    node = wf.get(node_id)
    if not isinstance(node, dict):
        raise KeyError(f"Node id {node_id!r} not found in workflow.")
    inputs = node.setdefault("inputs", {})
    if field not in inputs:
        raise KeyError(f"Field {field!r} not in node {node_id} inputs: {list(inputs.keys())}")
    inputs[field] = prompt_text
    return wf


def list_output_images(history_doc: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """Collect (filename, subfolder, folder_type) from every Save Image–style output."""
    found: List[Tuple[str, str, str]] = []
    outputs = history_doc.get("outputs") or {}
    for _node_id, node_out in outputs.items():
        if not isinstance(node_out, dict):
            continue
        for img in node_out.get("images") or []:
            if not isinstance(img, dict):
                continue
            fn = img.get("filename")
            if not fn:
                continue
            sub = img.get("subfolder") or ""
            typ = img.get("type") or "output"
            found.append((str(fn), str(sub), str(typ)))
    return found


def read_local_comfy_output(comfy_output_root: Path, filename: str, subfolder: str = "") -> Optional[bytes]:
    """
    Read bytes ComfyUI wrote under its ``output`` folder when HTTP ``/view`` is flaky.
    ``subfolder`` may contain nested segments (e.g. ``voice-prompt``).
    """
    root = comfy_output_root.expanduser().resolve()
    sub = (subfolder or "").replace("\\", "/").strip().strip("/")
    candidates: List[Path] = []
    if sub:
        candidates.append(root.joinpath(*sub.split("/")) / filename)
    candidates.append(root / filename)
    for p in candidates:
        try:
            if p.is_file():
                return p.read_bytes()
        except OSError:
            continue
    return None


def first_output_filename(history_doc: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Parse ComfyUI history payload for the first image output.
    Returns (filename, subfolder, folder_type).
    """
    found = list_output_images(history_doc)
    if found:
        return found[0]
    outputs = history_doc.get("outputs") or {}
    raise RuntimeError(f"No image output found in history: keys={list(outputs.keys())}")
