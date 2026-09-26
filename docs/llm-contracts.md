# LLM Persona Streaming — Frozen Contracts

Branch: `feat/llm-persona-streaming`. Every agent implements to these signatures
exactly. Do not change a signature; if something is wrong, note it in your report.

## `app/persona.py`

```python
PERSONA_NAME: str = "Myra"
DEFAULT_TOPICS: list[str] = [...10 intent tags...]

def get_system_prompt() -> str:
    """Return the full system prompt for the LLM. Cached, no I/O per call."""
```

The prompt MUST instruct the model to begin every reply with a metadata line:
`[[topic|confidence]]` — topic from `DEFAULT_TOPICS`, confidence 0.0–1.0 —
followed by a newline and then the reply prose.

## `app/tts_text.py`

```python
def strip_stage_directions(text: str) -> str:
    """Remove *...* spans (incl. the asterisks) for TTS. Keeps ... — ?! caps."""

def has_balanced_asterisks(text: str) -> bool:
    """True if the count of '*' is even (no unterminated stage direction)."""

def split_sentences(buffer: str) -> tuple[list[str], str]:
    """Split complete sentences off the front. Returns (sentences, remainder).
    Only splits on [.!?] followed by whitespace. Never splits inside '...'.
    Never splits inside an unbalanced '*...*' span."""
```

## `app/llm.py`

```python
class LLMError(RuntimeError): ...

def stream_chat(message: str, history: list[dict]) -> Iterator[dict]:
    """Stream a reply from the 7api OpenAI-compatible endpoint.

    history: [{"role": "user"|"assistant", "content": str}, ...]

    Yields dicts, in order:
      {"type": "meta",  "topic": str, "confidence": float}
      {"type": "token", "text": str}      # repeated; UI text, incl. *stage directions*
      {"type": "error", "message": str}   # terminal; nothing after
    """
```

Environment: `LLM_API_KEY` (required), `LLM_BASE_URL` (default
`https://7api.st/v1`), `LLM_MODEL` (default `deepseek-v4.1-flash`).

Must set `reasoning_effort: "none"`, send `stream: true`, and **drop every
`reasoning_content` delta** — never emit it as a token. The endpoint returns
SSE (`text/event-stream`) even when `stream` is not set, so parse SSE always.

## `app/app.py`

Existing endpoints stay unless noted.

```python
POST /api/transcribe      # multipart field "audio" -> {"transcript","language_code"}
                          # STT only. No translate, no classify, no TTS.
POST /api/chat/stream     # body {"message": str, "history": [{"role","content"}]}
                          # -> text/event-stream, see SSE protocol below
POST /api/chat            # body {"message", "history"} -> {"topic","confidence","response"}
                          # non-streaming wrapper over the same LLM call (for curl/tests)
GET  /api/health          # {"status","model","labels"}
GET  /                    # serves app/static/index.html
```

**Fallback:** if `llm.stream_chat` raises `LLMError`, fall back to the ONNX
classifier (`model_io.predict`) + `intents.json` response, and emit
`{"type":"error"}` only if that also fails. `app/model_io.py` and
`intents.json` stay in the repo for this purpose.

### SSE protocol (shared by app.py and app.js)

```
event: meta    data: {"topic":"breakup","confidence":0.93}
event: token   data: {"text":"Agent Midnight. "}
event: audio   data: {"b64":"<base64 mp3>"}
event: done    data: {}
event: error   data: {"message":"..."}
```

`meta` once, at the start. `token` many times. `audio` once per completed
sentence, emitted by the server via `sarvam.tts()` after
`strip_stage_directions()`. `done` once, at the end. `error` is terminal.

## `app/static/app.js`

- POST to `/api/chat/stream` and consume SSE progressively.
- Render `token` text live into the bot bubble; `*...*` spans render **italic**.
- Queue `audio` chunks and play them **in order**, sequentially.
- Maintain `history` as `[{role,content}]`, cap ~10 turns (oldest trimmed),
  persist to `localStorage` key `myra.history.v1`, tolerate corrupt JSON.
- Show the `meta` topic/confidence as the existing caption format:
  `topic: X · confidence: 0.93`.
- **New chat** button: clears history + localStorage + transcript, returns to
  the opening greeting. `confirm()` only when history is non-empty.
- Keep the text-input fallback and the mic path (mic -> `/api/transcribe` ->
  then send the transcript through `/api/chat/stream`).
