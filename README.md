# Voice-Enabled Chatbot

A voice-first chatbot with a **sarcastic Gen-Z therapist** persona: you talk, it listens, roasts you gently, and actually helps. Speech in any supported Indian language, text and spoken reply out.

The persona lives entirely in `intents.json`. The graded component is a real Deep Learning model that classifies the user's **intent** from their utterance.

## Assignment Requirement Mapping

| Requirement | How this project meets it |
|---|---|
| Integrate Speech Recognition for voice input | Sarvam **Saaras v3** STT (`/api/transcribe`, `mode=codemix`) with automatic language detection |
| Deep Learning model for intent classification | Fine-tuned **MiniLM** sequence classifier, exported to **int8 ONNX** |
| Display recognized speech and chatbot response | Chat UI shows the native/code-mixed transcript, the English interpretation, and the bot reply |
| Deploy the working application online | Flask app, container-portable; hosting platform chosen after local verification |
| Submit live link, source code, brief report | GitHub repository + `report/report.md` populated from real metrics |

## Architecture

```
                        ┌───────────────────────────────────────────────┐
                        │                 Browser                        │
                        │  mic ──▶ MediaRecorder (audio/webm;opus)       │
                        └───────────────────────┬───────────────────────┘
                                                │ POST /api/transcribe
                                                ▼
                        ┌───────────────────────────────────────────────┐
                        │            Flask backend (app/app.py)          │
                        │                                               │
   audio bytes ────────▶│  1. Sarvam STT   saaras:v3  mode=codemix       │
                        │         │  code-mixed transcript + language    │
                        │         ▼                                      │
                        │  2. Sarvam Mayura (auto ──▶ en-IN)             │
                        │         │  English text                        │
                        │         ▼                                      │
                        │  3. Local MiniLM int8 ONNX classifier          │
                        │         │  intent + confidence                 │
                        │         ▼                                      │
                        │  4. intents.json  (fallback if conf < 0.4)     │
                        │         │  response text                       │
                        │         ▼                                      │
                        │  5. Sarvam Mayura (en-IN ──▶ detected lang)    │
                        │         │  localized reply                     │
                        │         ▼                                      │
                        │  6. Sarvam Bulbul v3 TTS                       │
                        │         │  base64 mp3                          │
                        └─────────┼─────────────────────────────────────┘
                                  ▼
   { transcript, language_code, english, intent, confidence, response, audio }
```

Intent classification runs on **English text only** (translate-at-the-edge). This keeps the model small and fast while still supporting every input language.

## Supported Languages

English, Hindi, Telugu, Tamil, Kannada, Punjabi — plus **code-mixed blends**, which are the primary demo target:

- Hinglish (Hindi + English)
- Tenglish (Telugu + English)
- Tanglish (Tamil + English)
- Kanglish (Kannada + English)

Input language is auto-detected by Sarvam STT; the reply is localized back to the detected language.

## Setup

Requires Python 3.12.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Create your environment file and add the API key:

```bash
cp .env.example .env
# then set SARVAM_API_KEY=<your key>
```

Run the app:

```bash
flask --app app.app run
```

Then open `http://localhost:5000`.

### Running without an API key

To exercise the full pipeline without Sarvam credentials, enable stub mode. STT, translation, and TTS return canned values while the real intent model still runs:

```bash
SARVAM_STUB=1 flask --app app.app run
```

## Training

The intent classifier is fine-tuned from `sentence-transformers/all-MiniLM-L6-v2` as a sequence-classification head, then quantized for CPU serving.

```bash
pip install -r training/requirements.txt
python training/train.py        # fine-tune, writes labels.json, tokenizer.json, metrics.json
python training/export_onnx.py  # export to ONNX + dynamic int8 quantization
```

`train.py` performs a stratified train/val/test split, trains with AdamW and early stopping on validation loss, and asserts a minimum test accuracy. `export_onnx.py` writes `training/model/model.onnx` and verifies the quantized model's predictions match the PyTorch model on sample inputs.

Artifacts written to `training/model/`:

| File | Contents |
|---|---|
| `model.onnx` | int8-quantized MiniLM sequence classifier (`input_ids`, `attention_mask` → logits) |
| `tokenizer.json` | HuggingFace fast tokenizer |
| `labels.json` | Intent labels, index-aligned with logits |
| `metrics.json` | Accuracy, per-class precision/recall/F1, confusion matrix, split sizes |

## API Endpoints

| Method | Path | Request | Response |
|---|---|---|---|
| `GET` | `/` | — | Chat page |
| `POST` | `/api/chat` | `{ "message": "<text>" }` | `{ "intent", "confidence", "response" }` |
| `POST` | `/api/transcribe` | multipart form-data, field `audio` (webm/opus) | `{ "transcript", "language_code", "english", "intent", "confidence", "response", "audio" }` |
| `POST` | `/api/speak` | `{ "text", "language_code" }` | `{ "audio": "<base64 mp3>" }` |
| `GET` | `/api/health` | — | `{ "status": "ok", "model": "minilm-intent", "labels": 10 }` |

## Security Note

The Sarvam API key is **server-side only**. It is read from the `SARVAM_API_KEY` environment variable, is never sent to the browser, and `.env` is gitignored. Only `.env.example` (with an empty key) is committed.

## License

See the repository for details.
