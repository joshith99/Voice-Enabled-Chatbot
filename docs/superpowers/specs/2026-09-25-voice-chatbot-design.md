# Voice-Enabled Chatbot — Design Spec

Date: 2026-09-25
Status: Approved (design agreed in session; implementation pending)

## 1. Overview

A voice-first chatbot with a **Gen-Z sarcastic therapist / relationship counsellor** persona —
stand-up-comic wit, but genuinely useful. The user speaks; the system transcribes, classifies
intent with a Deep Learning model, and replies in text and speech.

The persona lives entirely in the dataset (`intents.json`). The Deep Learning model performs
real intent classification — the graded component.

## 2. Assignment Requirement Mapping

| Requirement | How this design meets it |
|---|---|
| Integrate Speech Recognition for voice input | Sarvam Saaras v3 STT (`/speech-to-text`, `mode=codemix`), auto language detection |
| Deep Learning model for intent classification | Fine-tuned MiniLM sequence classifier, exported to int8 ONNX |
| Display both recognized speech and chatbot response | Chat UI shows native/code-mixed transcript, English interpretation, and bot reply |
| Deploy the working application online | Flask app, container-portable; hosting platform chosen after local verification |
| Submit live link, source code, brief report | GitHub repo + `report/report.md` from real metrics |

## 3. Persona and Dataset

- Persona: sarcastic Gen-Z therapist / relationship counsellor.
- Voice (wording of responses) comes from `intents.json`; the model only selects the intent.
- Includes a `crisis` intent that **drops the sarcasm** and returns a helpline. Non-negotiable.
- Dataset is our own (no suitable public dataset exists for this persona).

### 3.1 `intents.json` contract (frozen)

```json
{
  "intents": [
    {
      "tag": "venting",
      "patterns": ["i had such a bad day", "everything is going wrong", "..."],
      "responses": ["...", "..."]
    }
  ]
}
```

- `tag`: unique intent label (string).
- `patterns`: user utterances that map to the tag (>= 8 recommended).
- `responses`: candidate replies; one is chosen at random at serve time.
- Target set (~10 intents): `greeting`, `venting`, `advice_request`, `relationship_problem`,
  `breakup`, `smalltalk`, `thanks`, `goodbye`, `crisis`, `fallback`.

## 4. Languages

Supported: **English, Hindi, Telugu, Tamil, Kannada, Punjabi** — plus **code-mixed blends**
(Hinglish, Tenglish, Tanglish, Kanglish), which are the primary demo target.

- Input: auto-detected by Sarvam STT; the detected BCP-47 `language_code` is returned.
- Classification: performed on **English text** (translate-at-the-edge approach).
- Reply: localized back to the detected language (or left code-mixed where natural).

## 5. Architecture and Data Flow

```
Browser (index.html + app.js)
  mic -> MediaRecorder (audio/webm;codecs=opus)
      -> POST /api/transcribe
            |
            v
  Flask app (app/app.py)
    Sarvam STT  saaras:v3  mode=codemix   -> code-mixed transcript + language_code
    Sarvam Mayura (auto -> en-IN)         -> English text
    YOUR intent model (int8 ONNX)         -> intent + confidence
    intents.json                          -> response (fallback if conf < threshold)
    Sarvam Mayura (en-IN -> detected)     -> localized reply
    Sarvam Bulbul v3 TTS                  -> base64 audio
            |
            v
  { transcript, language_code, english, intent, confidence, response, audio }
```

### 5.1 HTTP API contract (frozen)

`GET /`
- Returns the chat page.

`POST /api/chat` (text-input fallback; no audio)
- Request: `{ "message": "<text in any supported language or code-mix>" }`
- Behaviour: non-English input is translated to English via Mayura, then classified.
- Response: `{ "intent": "...", "confidence": 0.93, "response": "..." }` (English text)

`POST /api/transcribe`
- Request: multipart/form-data, field `audio` (webm/opus blob)
- Response: `{ "transcript": "...", "language_code": "te-IN", "english": "...",
  "intent": "...", "confidence": 0.9, "response": "...", "audio": "<base64 mp3|null>" }`

`POST /api/speak`
- Request: `{ "text": "...", "language_code": "te-IN" }`
- Response: `{ "audio": "<base64 mp3>" }`

`GET /api/health`
- Response: `{ "status": "ok", "model": "minilm-intent", "labels": 10 }`

### 5.2 Model artifact contract (frozen)

Emitted by `training/`, loaded by `app/model_io.py`:

| File | Contents |
|---|---|
| `training/model/model.onnx` | int8-quantized MiniLM sequence classifier; inputs `input_ids`, `attention_mask`; output logits |
| `training/model/tokenizer.json` | HuggingFace fast tokenizer |
| `training/model/labels.json` | `["greeting", "venting", ...]` index-aligned with logits |
| `training/model/metrics.json` | accuracy, per-class precision/recall/F1, confusion matrix, split sizes |

`app/model_io.py` exposes `predict(text) -> (intent: str, confidence: float)`.

## 6. Repository Layout

```
app/
  app.py            Flask app + routes
  model_io.py       ONNX load + predict()
  sarvam.py         Sarvam STT / Mayura / Bulbul wrappers (with stub mode)
  static/
    index.html
    app.js
    style.css
training/
  train.py          fine-tune MiniLM, write artifacts
  export_onnx.py    export + int8 quantization
  requirements.txt
  model/            artifacts (committed; small)
intents.json
requirements.txt
.env.example
.gitignore
README.md
report/report.md
docs/superpowers/specs/2026-09-25-voice-chatbot-design.md
```

## 7. Training

- Host: `jengas-linux`, **isolated venv** at `/home/joshith/projects/voice-chatbot/`.
- **CPU-only** (see §9). No GPU contact.
- Interpreter: 3.12 via `uv venv` (system Python is 3.14, which lacks torch wheels).
- Model: `sentence-transformers/all-MiniLM-L6-v2` (6 layers, ~22M params) loaded as an
  `AutoModelForSequenceClassification` head. Pinned because classification runs on English
  text and this base is small and fast on CPU.
- Pipeline: stratified train/val/test split; AdamW; early stopping on val loss; report test metrics.
- Export: PyTorch -> ONNX -> dynamic int8 quantization -> `onnxruntime` CPU.
- Artifacts `scp`'d back to the repo; **venv deleted** afterwards.

## 8. Serving and Frontend

- Serving deps: `flask`, `gunicorn`, `onnxruntime`, `tokenizers`, `numpy`, `requests`
  (~50 MB total; **no torch, no transformers** at serve time).
- Sarvam API key read from environment (`SARVAM_API_KEY`); never sent to the browser.
- Frontend: mic button, three-part display (native transcript / English interpretation / reply),
  text-input fallback, reply audio playback.
- Confidence threshold (`0.4` default) routes low-confidence inputs to the `fallback` intent.

## 9. Isolation Guarantees (shared `jengas-linux`)

- Dedicated venv under the user's home directory; no system `pip` writes.
- CPU-only: no GPU memory contact, so the shared Ollama/LiteLLM/Open WebUI stack cannot be
  evicted or starved. (GPU isolation is not physically possible: consumer RTX 5070 has no MIG,
  and VRAM is a single pool — see Risks.)
- No systemd changes, no Docker changes, no changes to the shared AI stack.
- Venv removed after training; only exported artifacts leave the box.

## 10. Deployment (deferred)

App is kept container-portable. Platform decided after local verification. Candidates:
Hugging Face Spaces (preferred), Google Cloud Run, Render. The Pi is not a target.

## 11. Verification

- `training/` writes `metrics.json`; `train.py` asserts a minimum test accuracy.
- `test_model_io.py`: asserts known phrases map to expected intents.
- Manual: `curl` each endpoint; mic test in Chrome; confirm both transcript and reply display.

## 12. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| GPU cannot be isolated on shared box (no MIG, single VRAM pool, typically <1 GB free while the shared Ollama stack is resident) | Train CPU-only in isolated venv; model is ~22M params, ~1–3 min on CPU |
| System Python 3.14 lacks torch wheels | `uv venv --python 3.12`, isolated from system Python |
| Mayura translation quality on code-mixed text | Fallback: second STT call with `mode="translate"` (reliable, one extra cheap call) |
| Few hundred phrases -> overfitting | Stratified split, early stopping, honest reporting |
| Sarvam key leakage | Server-side env var only; `.env` gitignored; `.env.example` committed |

## 13. Out of Scope

- All 22 Sarvam languages (6 + code-mixing is the target).
- Multilingual intent model (translate-at-the-edge chosen instead; upgrade path left open).
- Server-side ASR (Sarvam API used instead).
- Deployment platform selection and CI/CD.
