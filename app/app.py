"""Flask backend for the voice-enabled chatbot (spec 5.1)."""

import json
import os
import random

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

from . import model_io, sarvam

load_dotenv()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTENTS_PATH = os.path.join(ROOT, "intents.json")
CONFIDENCE_THRESHOLD = 0.4
FALLBACK_TAG = "fallback"

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


def _to_english(text: str) -> str:
    try:
        return sarvam.translate(text, "auto", "en-IN")
    except sarvam.SarvamError as exc:
        app.logger.warning("translate->en failed: %s", exc)
        return text


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/health")
def health():
    return jsonify(
        {"status": "ok", "model": "minilm-intent", "labels": model_io.num_labels()}
    )


@app.post("/api/chat")
def chat():
    body = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "missing 'message'"}), 400

    english = _to_english(message)
    try:
        intent, confidence = _classify(english)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify(
        {
            "intent": intent,
            "confidence": confidence,
            "response": _response_for(intent),
        }
    )


@app.post("/api/transcribe")
def transcribe():
    audio = request.files.get("audio")
    if audio is None:
        return jsonify({"error": "missing 'audio' file field"}), 400

    try:
        result = sarvam.transcribe(audio.read(), audio.filename or "audio.webm")
    except sarvam.SarvamError as exc:
        return jsonify({"error": f"transcription failed: {exc}"}), 502

    transcript = result["transcript"]
    language_code = result.get("language_code") or "en-IN"

    english = _to_english(transcript)
    try:
        intent, confidence = _classify(english)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

    response = _response_for(intent)

    localized = response
    if language_code != "en-IN":
        try:
            localized = sarvam.translate(response, "en-IN", language_code)
        except sarvam.SarvamError as exc:
            app.logger.warning("localize failed: %s", exc)

    try:
        audio_b64 = sarvam.tts(localized, language_code)
    except sarvam.SarvamError as exc:
        app.logger.warning("TTS failed: %s", exc)
        audio_b64 = None

    return jsonify(
        {
            "transcript": transcript,
            "language_code": language_code,
            "english": english,
            "intent": intent,
            "confidence": confidence,
            "response": localized,
            "audio": audio_b64,
        }
    )


@app.post("/api/speak")
def speak():
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    language_code = body.get("language_code") or "en-IN"
    if not text:
        return jsonify({"error": "missing 'text'"}), 400
    try:
        return jsonify({"audio": sarvam.tts(text, language_code)})
    except sarvam.SarvamError as exc:
        return jsonify({"error": f"tts failed: {exc}"}), 502


if __name__ == "__main__":
    app.run(debug=True)
