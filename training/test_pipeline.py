"""Lightweight checks for the dataset and training artifacts.

Run with pytest (`pytest training/test_pipeline.py`) or directly
(`python training/test_pipeline.py`). Missing inputs/artifacts skip, not fail.
"""
import json
from pathlib import Path

try:
    import pytest
except ImportError:
    pytest = None

REPO_ROOT = Path(__file__).resolve().parent.parent
INTENTS_PATH = REPO_ROOT / "intents.json"
MODEL_DIR = REPO_ROOT / "training" / "model"
EXPECTED_ARTIFACTS = ["model.onnx", "tokenizer.json", "labels.json", "metrics.json"]


def _skip(message):
    if pytest is not None:
        pytest.skip(message)
    print(f"SKIP: {message}")


def test_intents_json_loads_with_unique_tags():
    if not INTENTS_PATH.exists():
        return _skip(f"{INTENTS_PATH} not present yet")
    data = json.loads(INTENTS_PATH.read_text(encoding="utf-8"))
    intents = data["intents"]
    assert intents, "intents list is empty"
    tags = [intent["tag"] for intent in intents]
    assert len(tags) == len(set(tags)), f"duplicate tags: {tags}"
    for intent in intents:
        assert intent["patterns"], f"intent {intent['tag']} has no patterns"
        assert intent["responses"], f"intent {intent['tag']} has no responses"


def test_training_artifacts_present():
    missing = [name for name in EXPECTED_ARTIFACTS if not (MODEL_DIR / name).exists()]
    if missing:
        return _skip(f"training artifacts absent: {missing}")
    assert not missing


if __name__ == "__main__":
    test_intents_json_loads_with_unique_tags()
    test_training_artifacts_present()
    print("test_pipeline: checks complete")
