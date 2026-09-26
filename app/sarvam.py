"""Thin wrappers around the Sarvam AI HTTP APIs (STT, translate, TTS).

Set ``SARVAM_STUB=1`` to run the whole app with canned responses and no API
key. Otherwise ``SARVAM_API_KEY`` must be set in the environment.
"""

import base64
import mimetypes
import os

import requests

STT_URL = "https://api.sarvam.ai/speech-to-text"
TRANSLATE_URL = "https://api.sarvam.ai/translate"
TTS_URL = "https://api.sarvam.ai/text-to-speech"

STT_MODEL = "saaras:v3"
STT_MODE = "codemix"
TRANSLATE_MODEL = "mayura:v1"
TTS_MODEL = "bulbul:v3"

TIMEOUT = 60

# A single MPEG-1 Layer III frame header (128 kbps, 44.1 kHz) padded to 417
# bytes; repeated ~1s. Used only in stub mode so audio playback has something
# decodable to work with.
_FRAME = bytes([0xFF, 0xFB, 0x90, 0x64]) + b"\x00" * 413
STUB_MP3_B64 = base64.b64encode(_FRAME * 40).decode()


class SarvamError(RuntimeError):
    """Raised when a Sarvam API call fails."""


def _stub() -> bool:
    return os.environ.get("SARVAM_STUB", "0") == "1"


def _key() -> str:
    key = os.environ.get("SARVAM_API_KEY")
    if not key:
        raise SarvamError(
            "SARVAM_API_KEY is not set (or set SARVAM_STUB=1 to run without a key)"
        )
    return key


def _post(url: str, **kwargs):
    try:
        resp = requests.post(url, timeout=TIMEOUT, **kwargs)
    except requests.exceptions.RequestException as exc:
        raise SarvamError(f"Request to {url} failed: {exc}") from exc
    if resp.status_code != 200:
        raise SarvamError(
            f"Sarvam API {url} returned {resp.status_code}: {resp.text[:300]}"
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise SarvamError(f"Sarvam API {url} returned non-JSON body") from exc


def _audio_content_type(content_type: str, filename: str) -> str:
    """Resolve the multipart Content-Type Sarvam should receive.

    Browsers send values like ``audio/webm;codecs=opus``. Sarvam rejects any
    type outside its allow-list with "Invalid file type", so strip parameters
    and fall back to the filename, then to webm (what MediaRecorder produces).

    Note: requests does NOT guess the type for a 2-tuple; the file part must be
    a 3-tuple or no Content-Type is sent at all.
    """
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype.startswith("audio/") or ctype == "application/octet-stream":
        return ctype
    guessed = mimetypes.guess_type(filename or "")[0] or ""
    return guessed if guessed.startswith("audio/") else "audio/webm"


def transcribe(audio_bytes: bytes, filename: str, content_type: str = "") -> dict:
    """Speech-to-text (code-mixed). Returns {transcript, language_code}."""
    if _stub():
        return {
            "transcript": "i am so done with everything",
            "language_code": "en-IN",
        }

    data = _post(
        STT_URL,
        headers={"api-subscription-key": _key()},
        files={
            "file": (
                filename or "audio.webm",
                audio_bytes,
                _audio_content_type(content_type, filename),
            )
        },
        data={"model": STT_MODEL, "mode": STT_MODE},
    )
    return {
        "transcript": data.get("transcript", ""),
        "language_code": data.get("language_code") or "en-IN",
    }


def translate(text: str, source_language_code: str, target_language_code: str) -> str:
    """Translate text via Mayura. ``source_language_code`` may be "auto"."""
    if _stub():
        return text

    data = _post(
        TRANSLATE_URL,
        headers={"api-subscription-key": _key()},
        json={
            "input": text,
            "source_language_code": source_language_code,
            "target_language_code": target_language_code,
            "model": TRANSLATE_MODEL,
        },
    )
    return data.get("translated_text", "")


def tts(text: str, language_code: str) -> str:
    """Text-to-speech via Bulbul v3. Returns base64-encoded mp3."""
    if _stub():
        return STUB_MP3_B64

    data = _post(
        TTS_URL,
        headers={"api-subscription-key": _key()},
        json={
            "text": text,
            "language_code": language_code or "en-IN",
            "model": TTS_MODEL,
            "output_audio_codec": "mp3",
        },
    )
    audios = data.get("audios") or []
    if not audios:
        raise SarvamError("Sarvam TTS returned no audio")
    return audios[0]
