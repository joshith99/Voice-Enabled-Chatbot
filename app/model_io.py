"""Load the exported MiniLM intent classifier and run inference.

Artifacts live in ``training/model/`` (see spec 5.2):
  model.onnx, tokenizer.json, labels.json

Loading is lazy: importing this module never fails if the artifacts are
missing, so the Flask app can still start. ``predict`` raises a clear error
instead.
"""

import json
import os

import numpy as np

MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "training", "model"
)

MAX_LEN = 64
_MODEL_PATH = os.path.join(MODEL_DIR, "model.onnx")
_TOKENIZER_PATH = os.path.join(MODEL_DIR, "tokenizer.json")
_LABELS_PATH = os.path.join(MODEL_DIR, "labels.json")

_session = None
_tokenizer = None
_labels = None
_load_error = None
_loaded = False


def _load():
    global _session, _tokenizer, _labels, _load_error, _loaded
    if _loaded:
        return
    _loaded = True
    try:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        missing = [
            p
            for p in (_MODEL_PATH, _TOKENIZER_PATH, _LABELS_PATH)
            if not os.path.exists(p)
        ]
        if missing:
            raise FileNotFoundError(
                "Missing model artifact(s): " + ", ".join(missing)
            )
        with open(_LABELS_PATH, "r", encoding="utf-8") as f:
            _labels = json.load(f)
        _tokenizer = Tokenizer.from_file(_TOKENIZER_PATH)
        _tokenizer.enable_truncation(max_length=MAX_LEN)
        _tokenizer.enable_padding(length=MAX_LEN)
        _session = ort.InferenceSession(
            _MODEL_PATH, providers=["CPUExecutionProvider"]
        )
    except Exception as exc:  # noqa: BLE001 - surfaced later by predict()
        _load_error = exc


def num_labels() -> int:
    """Number of intent labels, or 0 if labels.json is unavailable."""
    _load()
    return len(_labels) if _labels else 0


def predict(text: str) -> tuple:
    """Classify ``text`` -> (label, confidence). Raises if artifacts missing."""
    _load()
    if _session is None:
        raise RuntimeError(f"Intent model unavailable: {_load_error}")

    enc = _tokenizer.encode(text)
    input_ids = np.array([enc.ids], dtype=np.int64)
    attention_mask = np.array([enc.attention_mask], dtype=np.int64)

    logits = _session.run(
        None,
        {"input_ids": input_ids, "attention_mask": attention_mask},
    )[0][0]

    exp = np.exp(logits - np.max(logits))
    probs = exp / exp.sum()
    idx = int(np.argmax(probs))
    return _labels[idx], float(probs[idx])
