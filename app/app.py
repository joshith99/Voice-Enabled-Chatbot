"""Flask backend for the voice-enabled chatbot (spec 5.1)."""

import json
import os
import random
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_from_directory

from . import llm, model_io, sarvam, tts_text

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTENTS_PATH = os.path.join(ROOT, "intents.json")
CONFIDENCE_THRESHOLD = 0.4
FALLBACK_TAG = "fallback"
DEFAULT_LANGUAGE = "en-IN"

app = Flask(__name__, static_folder="static", static_url_path="/static")


def _load_intents() -> dict:
    try:
        with open(INTENTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {i["tag"]: i for i in data.get("intents", [])}
    except Exception as exc:  # noqa: BLE001 - app must still start
        app.logger.warning("Could not load intents.json: %s", exc)
        return {}


INTENTS = _load_intents()


def _classify(message: str) -> tuple:
    """Return (intent, confidence), routing low confidence to fallback."""
    intent, confidence = model_io.predict(message)
    if confidence < CONFIDENCE_THRESHOLD:
        intent = FALLBACK_TAG
    return intent, confidence


def _response_for(intent: str) -> str:
    entry = INTENTS.get(intent) or INTENTS.get(FALLBACK_TAG)
    if not entry or not entry.get("responses"):
        return "Hmm, I've got nothing. Tell me more?"
    return random.choice(entry["responses"])


def _history(body: dict) -> list:
    raw = body.get("history")
    if not isinstance(raw, list):
        return []
    turns = []
    for turn in raw:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            turns.append({"role": role, "content": content})
    return turns


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# TTS costs a ~1s blocking round trip per clip. Two mitigations: coalesce
# fragments into longer clips, and synthesize clips concurrently on a small
# pool (emitted in order, so the browser still plays them sequentially).
TTS_MIN_CHARS = 140
TTS_FIRST_MIN_CHARS = 60
TTS_WORKERS = 4


def _pop_ready(pending: list, sent_any: bool) -> str | None:
    """Join pending sentences into a clip once they are worth one TTS call."""
    if not pending:
        return None
    length = sum(len(s) for s in pending) + len(pending) - 1
    threshold = TTS_MIN_CHARS if sent_any else TTS_FIRST_MIN_CHARS
    if length < threshold:
        return None
    return " ".join(pending)


def _synth(clip: str, default_language: str) -> str | None:
    """Synthesize one clip; None marks a clip whose TTS call failed.

    The language is detected per clip so a reply that mixes English and an
    Indic language is voiced correctly in each part.
    """
    spoken = tts_text.strip_stage_directions(clip)
    try:
        return sarvam.tts(spoken, tts_text.detect_language(spoken, default_language))
    except sarvam.SarvamError as exc:
        app.logger.warning("TTS failed: %s", exc)
        return None


def _drain_ready(futures: list, stop_at: int = -1) -> list:
    """Collect finished clips in submission order.

    Stops at the first unfinished future (so audio stays in order) or after
    ``stop_at`` clips when flushing.
    """
    frames = []
    while futures:
        if stop_at >= 0 and len(frames) >= stop_at:
            break
        head = futures[0]
        if not head.done():
            break
        futures.pop(0)
        b64 = head.result()
        if b64:
            frames.append(_sse("audio", {"b64": b64}))
    return frames


def _fallback_frames(message: str):
    try:
        intent, confidence = _classify(message)
    except RuntimeError as exc:
        yield _sse("error", {"message": str(exc)})
        return
    yield _sse("meta", {"topic": intent, "confidence": confidence})
    yield _sse("token", {"text": _response_for(intent)})


def _stream(message: str, history: list, language_code: str = ""):
    buffer = ""
    pending: list = []
    sent_any = False
    futures: list = []
    pool = ThreadPoolExecutor(max_workers=TTS_WORKERS)
    # The STT language is only a fallback for a reply the model romanised
    # instead of writing in native script. Once the reply shows Indic script,
    # a clip without it is English, so English clips are not read by an Indic
    # voice just because the user spoke an Indic language.
    fallback_language = language_code or DEFAULT_LANGUAGE
    seen_indic = False

    def submit(clip: str) -> None:
        nonlocal sent_any, seen_indic
        if not clip or not tts_text.has_balanced_asterisks(clip):
            return
        sent_any = True
        spoken = tts_text.strip_stage_directions(clip)
        if tts_text.has_indic_script(spoken):
            seen_indic = True
        default = "en-IN" if seen_indic else fallback_language
        futures.append(pool.submit(_synth, clip, default))

    def flush_pending() -> None:
        nonlocal pending
        if pending:
            submit(" ".join(pending))
            pending = []

    try:
        try:
            for chunk in llm.stream_chat(message, history):
                kind = chunk.get("type")
                if kind == "meta":
                    yield _sse(
                        "meta",
                        {
                            "topic": chunk.get("topic"),
                            "confidence": chunk.get("confidence"),
                        },
                    )
                elif kind == "token":
                    text = chunk.get("text") or ""
                    yield _sse("token", {"text": text})
                    buffer += text
                    sentences, buffer = tts_text.split_sentences(buffer)
                    pending.extend(sentences)
                    clip = _pop_ready(pending, sent_any)
                    if clip is not None:
                        pending = []
                        submit(clip)
                    for frame in _drain_ready(futures):
                        yield frame
                elif kind == "error":
                    raise llm.LLMError(chunk.get("message") or "LLM error")
            if buffer.strip():
                pending.append(buffer)
                buffer = ""
            flush_pending()
        except llm.LLMError as exc:
            app.logger.warning("LLM stream failed, using fallback: %s", exc)
            yield from _fallback_frames(message)
    except Exception as exc:  # noqa: BLE001 - never break the SSE stream
        yield _sse("error", {"message": str(exc)})
    finally:
        # Emit every remaining clip in submission order before closing.
        while futures:
            for frame in _drain_ready(futures, stop_at=1):
                yield frame
            if futures:
                futures[0].result()
        pool.shutdown(wait=False)
    yield _sse("done", {})


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/health")
def health():
    return jsonify(
        {"status": "ok", "model": "minilm-intent", "labels": model_io.num_labels()}
    )


@app.post("/api/transcribe")
def transcribe():
    audio = request.files.get("audio")
    if audio is None:
        return jsonify({"error": "missing 'audio' file field"}), 400

    try:
        result = sarvam.transcribe(
            audio.read(),
            audio.filename or "audio.webm",
            audio.content_type or "",
        )
    except sarvam.SarvamError as exc:
        return jsonify({"error": f"transcription failed: {exc}"}), 502

    return jsonify(
        {
            "transcript": result["transcript"],
            "language_code": result.get("language_code") or DEFAULT_LANGUAGE,
        }
    )


@app.post("/api/chat/stream")
def chat_stream():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "missing 'message'"}), 400

    language_code = (body.get("language_code") or "").strip()

    return Response(
        _stream(message, _history(body), language_code),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat")
def chat():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "missing 'message'"}), 400

    topic = None
    confidence = 0.0
    parts = []
    try:
        for chunk in llm.stream_chat(message, _history(body)):
            kind = chunk.get("type")
            if kind == "meta":
                topic = chunk.get("topic")
                confidence = chunk.get("confidence")
            elif kind == "token":
                parts.append(chunk.get("text") or "")
            elif kind == "error":
                raise llm.LLMError(chunk.get("message") or "LLM error")
    except llm.LLMError as exc:
        app.logger.warning("LLM failed, using fallback: %s", exc)
        try:
            topic, confidence = _classify(message)
        except RuntimeError as fallback_exc:
            return jsonify({"error": str(fallback_exc)}), 503
        parts = [_response_for(topic)]

    return jsonify(
        {"topic": topic, "confidence": confidence, "response": "".join(parts)}
    )


if __name__ == "__main__":
    app.run(debug=True)
