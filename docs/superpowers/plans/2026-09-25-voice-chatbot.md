# Voice-Enabled Chatbot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Wave 1 tasks (A–E) have disjoint file ownership and may be dispatched in parallel**; Wave 2 tasks (F–J) are sequential and run in the main session.

**Goal:** Build a voice-enabled chatbot with a sarcastic Gen-Z therapist persona, using Sarvam for speech and a fine-tuned MiniLM intent classifier exported to int8 ONNX.

**Architecture:** Browser records audio → Flask backend calls Sarvam STT (code-mixed) → Sarvam Mayura translates to English → local ONNX intent model classifies → response from `intents.json` → Mayura localizes → Bulbul TTS returns audio.

**Tech Stack:** Python 3.12, Flask, Gunicorn, onnxruntime, tokenizers, numpy, requests (serve); PyTorch, transformers, datasets, scikit-learn (train); vanilla HTML/CSS/JS (frontend).

**Spec:** `docs/superpowers/specs/2026-09-25-voice-chatbot-design.md`

## Global Constraints

- Serve-time dependencies MUST NOT include `torch` or `transformers`.
- Sarvam API key read from `SARVAM_API_KEY` env var only; never sent to the browser, never committed.
- `.env` MUST be gitignored; `.env.example` MUST be committed.
- Supported languages: `en-IN, hi-IN, te-IN, ta-IN, kn-IN, pa-IN` plus code-mixed input.
- Sarvam STT: model `saaras:v3`, `mode=codemix`. TTS: model `bulbul:v3`.
- Confidence threshold default `0.4` → `fallback` intent.
- Training host `jengas-linux` is CPU-only and isolated: no system pip, no systemd/Docker changes, no GPU use, venv removed after training.
- Do NOT commit unless the user explicitly asks.

---

## Wave 0 — Contracts (complete)

Spec written and self-reviewed. Contracts frozen in the spec:
- `intents.json` schema (§3.1)
- HTTP API (§5.1)
- Model artifacts (§5.2)

---

## Wave 1 — Parallel (disjoint file ownership)

### Task A: Dataset — `intents.json`

**Files:**
- Create: `intents.json`
- Test: `training/validate_intents.py`

**Interfaces:**
- Produces: `{"intents":[{"tag":str,"patterns":[str],"responses":[str]}]}` consumed by Tasks B and C.

- [ ] **Step 1:** Write `intents.json` with ~10 intents: `greeting`, `venting`, `advice_request`, `relationship_problem`, `breakup`, `smalltalk`, `thanks`, `goodbye`, `crisis`, `fallback`. Each ≥8 patterns and ≥3 responses, written in a sarcastic Gen-Z therapist voice. `crisis` MUST be sincere and return a helpline (e.g. India: Tele-MANAS 14416).
- [ ] **Step 2:** Write `training/validate_intents.py` asserting: valid JSON, unique tags, ≥8 patterns and ≥3 responses per intent, `crisis` and `fallback` present, no empty strings.
- [ ] **Step 3:** Run `python training/validate_intents.py` → expect PASS.
- [ ] **Step 4:** Commit (only if user asks).

### Task B: Training pipeline — `training/**`

**Files:**
- Create: `training/train.py`, `training/export_onnx.py`, `training/requirements.txt`
- Test: `training/test_pipeline.py`
- Produces artifacts into `training/model/` (contract §5.2)

**Interfaces:**
- Consumes: `intents.json` (Task A schema).
- Produces: `training/model/model.onnx`, `tokenizer.json`, `labels.json`, `metrics.json`.

- [ ] **Step 1:** `training/requirements.txt`: `torch`, `transformers`, `scikit-learn`, `onnx`, `onnxruntime`, `numpy` (CPU wheels).
- [ ] **Step 2:** `train.py`: load `intents.json`; base `sentence-transformers/all-MiniLM-L6-v2` via `AutoModelForSequenceClassification`; stratified 70/15/15 split; `Trainer` or manual loop with AdamW + early stopping on val loss; write `labels.json`, `tokenizer.json`, `metrics.json` (accuracy, per-class P/R/F1, confusion matrix, split sizes); assert test accuracy ≥ 0.6.
- [ ] **Step 3:** `export_onnx.py`: export to ONNX with dynamic axes, apply dynamic int8 quantization, write `model.onnx`; verify `onnxruntime` loads it and predictions match the PyTorch model on 5 samples.
- [ ] **Step 4:** Run `python training/train.py && python training/export_onnx.py` on a small synthetic set to prove the pipeline runs.
- [ ] **Step 5:** Commit (only if user asks).

### Task C: Backend — `app/*.py`, root `requirements.txt`, `.env.example`

**Files:**
- Create: `app/app.py`, `app/model_io.py`, `app/sarvam.py`, `requirements.txt`, `.env.example`
- Test: `test_model_io.py`

**Interfaces:**
- Consumes: model artifacts (Task B), `intents.json` (Task A).
- Produces: `predict(text) -> (intent: str, confidence: float)`; HTTP endpoints per spec §5.1.

- [ ] **Step 1:** `requirements.txt`: `flask`, `gunicorn`, `onnxruntime`, `tokenizers`, `numpy`, `requests`, `python-dotenv`. **No torch/transformers.**
- [ ] **Step 2:** `app/model_io.py`: load `model.onnx` + `tokenizer.json` + `labels.json` once; `predict(text)` tokenizes, pads, runs `onnxruntime`, softmaxes, returns `(label, confidence)`.
- [ ] **Step 3:** `app/sarvam.py`: `transcribe(audio_bytes) -> {transcript, language_code}`, `translate(text, source, target) -> str`, `tts(text, language_code) -> base64 mp3`. Key from `SARVAM_API_KEY`. Include a `SARVAM_STUB=1` mode returning canned values so the app runs without a key.
- [ ] **Step 4:** `app/app.py`: `GET /` (serve static), `POST /api/chat`, `POST /api/transcribe`, `POST /api/speak`, `GET /api/health`. Load `intents.json`; pick a random response; threshold → `fallback`. Handle Sarvam errors with a graceful text-only response.
- [ ] **Step 5:** `.env.example` with `SARVAM_API_KEY=` and `SARVAM_STUB=0`.
- [ ] **Step 6:** `test_model_io.py`: assert 3 known phrases map to expected intents (skipped if artifacts absent).
- [ ] **Step 7:** Run `flask --app app.app run` with `SARVAM_STUB=1`; `curl /api/health` and `curl -X POST /api/chat -d '{"message":"hi"}'`.
- [ ] **Step 8:** Commit (only if user asks).

### Task D: Frontend — `app/static/**`

**Files:**
- Create: `app/static/index.html`, `app/static/app.js`, `app/static/style.css`

**Interfaces:**
- Consumes: HTTP API per spec §5.1.

- [ ] **Step 1:** `index.html`: chat log, mic button, text input + send, language indicator.
- [ ] **Step 2:** `app.js`: `MediaRecorder` (`audio/webm;codecs=opus`), stop cleanly, assert `blob.size > 0`, POST to `/api/transcribe`; render three bubbles (native transcript / English interpretation / reply); play returned base64 audio; text fallback posts to `/api/chat`; disable mic with a clear message if `navigator.mediaDevices` is unavailable.
- [ ] **Step 3:** `style.css`: readable chat layout, mic recording state, responsive.
- [ ] **Step 4:** Manual check in Chrome at `http://localhost:5000` with `SARVAM_STUB=1`.
- [ ] **Step 5:** Commit (only if user asks).

### Task E: Docs — `README.md`, `.gitignore`, `report/report.md`

**Files:**
- Create: `README.md`, `.gitignore`, `report/report.md`

- [ ] **Step 1:** `.gitignore`: `.env`, `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `.pytest_cache/`, `node_modules/`.
- [ ] **Step 2:** `README.md`: what it is, architecture diagram, setup (install, train, run), env vars, supported languages, how to use.
- [ ] **Step 3:** `report/report.md` skeleton with sections: Dataset, Model Architecture, Methodology, Results (placeholder to be filled with real `metrics.json` in Wave 2), Deployment. **Do not invent numbers.**
- [ ] **Step 4:** Commit (only if user asks).

---

## Wave 2 — Sequential (main session)

### Task F: Train on `jengas-linux` (isolated, CPU)

**Files:** `training/**` (unchanged); artifacts copied back to `training/model/`.

- [ ] **Step 1:** `ssh joshith@100.77.183.77`; `mkdir -p ~/projects/voice-chatbot`; copy `intents.json` + `training/`.
- [ ] **Step 2:** Create isolated venv: `uv venv --python 3.12 .venv` (fallback: pyenv 3.12 if `uv` absent). Activate; install `training/requirements.txt` (CPU wheels).
- [ ] **Step 3:** Run `python train.py && python export_onnx.py`.
- [ ] **Step 4:** `scp` `training/model/*` back to the repo.
- [ ] **Step 5:** `rm -rf ~/projects/voice-chatbot` — leave nothing on the shared box.
- [ ] **Step 6:** Verify `metrics.json` exists and accuracy meets the floor.

### Task G: Integrate and verify locally

- [ ] **Step 1:** `python training/validate_intents.py` → PASS.
- [ ] **Step 2:** `python test_model_io.py` → PASS (artifacts present).
- [ ] **Step 3:** Run the app with the real key; `curl /api/health`, `/api/chat`, then a mic test in Chrome.
- [ ] **Step 4:** Fix integration issues; re-run.

### Task H: Fill the report

- [ ] **Step 1:** Populate `report/report.md` Results from real `metrics.json` (accuracy, per-class F1, confusion matrix).
- [ ] **Step 2:** Document the dataset, architecture, methodology, and deployment honestly.

### Task I: Push to GitHub

- [ ] **Step 1:** Confirm `.env` is ignored and no secrets are staged.
- [ ] **Step 2:** Push (only when the user asks).

### Task J: Hosting (deferred)

- [ ] **Step 1:** Decide platform (HF Spaces preferred). Container-portable; no code changes required.

---

## Self-Review

**Spec coverage:** §3 dataset → A; §5.2 artifacts → B; §5.1 API → C; §8 frontend → D; §11 verification → B/G; §7 training → F; §10 deployment → J; report → E/H. §9 isolation → F constraints. All covered.

**Placeholder scan:** Report Results intentionally deferred to Task H (real metrics required); no other placeholders.

**Type consistency:** `predict(text) -> (str, float)` used identically in C and G. Endpoint names match spec §5.1 across C and D. Artifact filenames match §5.2 across B, C, F.
