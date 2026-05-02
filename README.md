```text
================================================================================
                                                                                
      __     __      _____ __                                                   
      \ \   / /___  |___ /____ ___  ____ ____ ____                             
       \ \ / / _ \   |_ \ / _ \ \ /\ / / _` | '_ \                             
        \_/ \___/  ____) \___/_/_\_\ _,_| .__/                                 
                                         |_|                                   
                                                                                
              .-----------------------------------------------.                 
             /                                                 \                
            |     __      __       _____ __                     |               
            |     \ \    / /___  __|___ /____ ___  ____ ____    |               
            |      \ \/\/ / _ \ \/ / |_ \ / _ \ \ /\ / / _` |   |               
            |       \_/\_/\___/\__/____)_\___/_/_\_\ _,_|       |               
            |                                                  |               
            |          V O I C E  -  P R O M P T                |               
            |                                                  |               
             \                                                 /                
              '-----------------------------------------------'                 
                                                                                
               *  *  *   v o i c e   -   p r o m p t   *  *  *                 
                                                                                
              Local speech  -->  LM Studio  -->  ComfyUI  -->  PNG              
                                                                                
================================================================================
```

# VoicePrompt — simple guide for getting it running

VoicePrompt listens to your microphone, turns speech into text, asks a local AI (LM Studio) to rewrite it as a strong image prompt, then asks ComfyUI to draw the picture. **Everything stays on your computer** — nothing is sent to the cloud.

This guide assumes **Windows** and that your project folder is something like:

`D:\AI_software\Github_repos\voice-prompt`

If yours is different, use **your** path everywhere below.

---

## What you need installed (once)

1. **Python 3.10 or newer** — from [python.org](https://www.python.org/downloads/). During setup, turn on **“Add Python to PATH”** if you see it.
2. **LM Studio** — for the “make my casual words into a fancy Flux-style prompt” step.
3. **ComfyUI** — for actually generating the image from your workflow.
4. **A microphone** — built-in or headset.

You also need your **ComfyUI workflow** exported as an API JSON file (you already saved yours as `workflows\voice-prompt_v01.json` or similar).

---

## One-time setup (first day only)

### Step A — Install VoicePrompt’s Python packages

The easiest way on Windows:

1. Open the folder `voice-prompt` in File Explorer.
2. Double‑click **`start_voiceprompt.bat`**.

That script installs dependencies and starts the app. The **first** run may download speech models — it can take a few minutes.

**Important:** If you ever run VoicePrompt from a command prompt yourself, prefer:

```text
py -3 app.py
```

instead of plain `python app.py`. On some PCs, `python` points at the wrong install and things break.

### Step B — LM Studio (model + server)

1. Open **LM Studio**.
2. Load the model you want (for example **Qwen**).
3. Start the **local server** (often port **1234**). Leave LM Studio open.

### Step C — ComfyUI

1. Start **ComfyUI** the way you usually do (desktop shortcut, pinokio, etc.).
2. Make sure it’s listening on the normal API port (**8188** is the default).
3. Leave ComfyUI running.

### Step D — Tell VoicePrompt which LM Studio model to use

VoicePrompt reads the model **id** from the environment variable **`VOICEPROMPT_LM_MODEL`** (or uses the built‑in default if you skip this).

1. In LM Studio, note the **exact** model id for the model you load (for example `qwen2.5-vl-7b-instruct`).  
   If unsure, open `http://127.0.0.1:1234/v1/models` in a browser and copy the **`id`** from the response.
2. In Windows, set a **user environment variable** `VOICEPROMPT_LM_MODEL` to that id (Search “environment variables” → *Edit the system environment variables* → *Environment Variables…* → New under your user variables).  
   Or set it only for one session in Command Prompt:  
   `set VOICEPROMPT_LM_MODEL=qwen2.5-vl-7b-instruct`  
   before running `py -3 app.py`.

### Step E — Workflow file (ComfyUI export)

Defaults expect your API JSON at **`workflows\voice-prompt_v01.json`** and prompt injection on node **`76`**, field **`value`**. If yours differs, set:

| Environment variable | Purpose |
|---------------------|---------|
| `VOICEPROMPT_COMFY_WORKFLOW` | Full or relative path to your exported workflow JSON |
| `VOICEPROMPT_COMFY_PROMPT_NODE` | Node id string (e.g. `76`) |
| `VOICEPROMPT_COMFY_PROMPT_FIELD` | Field name (e.g. `value`) |

---

## Every time you use VoicePrompt (quick checklist)

Do these **in order**, then use the app.

| Order | What to start | What “good” looks like |
|------|----------------|-------------------------|
| 1 | **LM Studio** | Model loaded, **server running** (port 1234). |
| 2 | **ComfyUI** | Running; you can run graphs as usual. |
| 3 | **VoicePrompt** | Double‑click **`start_voiceprompt.bat`** or run `py -3 app.py`. |

Then in the **black console window** (you’ll see a `voice-prompt>` prompt):

1. Type **`help`** and press Enter to see all commands.
2. **Optional but recommended:** type **`warmup`** once — loads Whisper so the first phrase isn’t slow.
3. Type **`start`** to listen on the microphone.
4. Say your idea in plain language, then **pause** for about a second so the app knows you finished the phrase.
5. Watch the status messages until you see the image saved under **`outputs\history`**.
6. Type **`stop`** when you’re done talking to the app (or leave **`start`** running for another phrase).

Use **`mics`** and **`mic <number>`** if you need to pick a specific microphone before **`start`**.

---

## Where your pictures actually go (your “gallery”)

**Your gallery is a normal Windows folder** (there is no separate web gallery):

```
voice-prompt\outputs\history\
```

Each run saves a file named like **`vp_<numbers>.png`**.

**Tip:** Pin that folder in File Explorer, or sort by **Date modified** so the newest image is always on top. Double‑click any PNG to open it in your default viewer.

You should also see lines like this in the black console window when a save worked:

```text
[VoicePrompt] Saved gallery image → ...\outputs\history\vp_....png (... bytes)
```

---

## If something goes wrong

| Problem | What to try |
|--------|--------------|
| **“No module named …”** when starting | Use **`py -3 app.py`** or **`start_voiceprompt.bat`**, not a random `python`. |
| **LM Studio errors / empty prompts** | Server on? **`VOICEPROMPT_LM_MODEL`** matches LM Studio’s model **id**? Model loaded? |
| **Comfy errors / no image from Comfy** | ComfyUI running? Port **8188**? Workflow env vars / paths correct? Try the **same** workflow once inside Comfy by hand. |
| **Want last prompt again** | At `voice-prompt>`, type **`regen`** (uses last enhanced text + Comfy again). |
| **Something failed** | Type **`status`** — if there’s an **error** line, it usually points to LM Studio or ComfyUI. |

---

## Optional advanced bits (ignore unless you need them)

VoicePrompt sends only your transcribed line as the **`user`** message to LM Studio. Configure FLUX-style rewrite instructions in **LM Studio** (preset / system prompt for the server).

These are **environment variables** you can set in Windows if you ever need to override defaults (most people never do):

| Variable | Meaning |
|----------|---------|
| `OPENAI_BASE_URL` | LM Studio API address (default `http://127.0.0.1:1234/v1`). |
| `VOICEPROMPT_LM_MODEL` | LM Studio model **id** (required if it doesn’t match the default). |
| `VOICEPROMPT_COMFY_HOST` / `VOICEPROMPT_COMFY_PORT` | Where ComfyUI listens (default `127.0.0.1` and `8188`). |
| `VOICEPROMPT_COMFY_WORKFLOW` | Path to your workflow JSON. |
| `VOICEPROMPT_COMFY_OUTPUT_DIR` | Folder where **ComfyUI** saves images (helps if downloading fails). |
| `VOICEPROMPT_OUTPUT_DIR` | Optional different folder for VoicePrompt’s **`vp_*.png`** copies. |

---

## Short “don’t forget next week” summary

1. Start **LM Studio** (model + server).  
2. Start **ComfyUI**.  
3. Run **`start_voiceprompt.bat`** (or `py -3 app.py`).  
4. At **`voice-prompt>`**, type **`warmup`** once, then **`start`**, speak + pause.  
5. Open **`outputs\history`** in Explorer for your newest **`vp_*.png`**.  
6. **`stop`** or **`quit`** when finished.

That’s the whole loop.
