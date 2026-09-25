"""Export the fine-tuned model to int8 ONNX and verify it matches PyTorch.

Reads the PyTorch model written by train.py (training/model/), writes
training/model/model.onnx. CPU-only.
"""
import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from onnxruntime.quantization import QuantType, quantize_dynamic

TRAINING_DIR = Path(__file__).resolve().parent
REPO_ROOT = TRAINING_DIR.parent
MAX_LEN = 64


def main():
    ap = argparse.ArgumentParser(description="Export fine-tuned model to dynamic-int8 ONNX.")
    ap.add_argument("--model-dir", default=str(TRAINING_DIR / "model"))
    ap.add_argument("--intents", default=str(REPO_ROOT / "intents.json"))
    args = ap.parse_args()

    model_dir = Path(args.model_dir)
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.eval()
    labels = json.loads((model_dir / "labels.json").read_text(encoding="utf-8"))

    dummy = tokenizer(["hello world"], padding="max_length", truncation=True, max_length=MAX_LEN, return_tensors="pt")
    fp32_path = model_dir / "model_fp32.onnx"
    onnx_path = model_dir / "model.onnx"

    torch.onnx.export(
        model,
        (dummy["input_ids"], dummy["attention_mask"]),
        str(fp32_path),
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "sequence"},
            "attention_mask": {0: "batch", 1: "sequence"},
            "logits": {0: "batch"},
        },
        opset_version=14,
        do_constant_folding=True,
        dynamo=False,
    )
    quantize_dynamic(str(fp32_path), str(onnx_path), weight_type=QuantType.QInt8)
    fp32_path.unlink()

    import onnxruntime as ort

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])

    intents = json.loads(Path(args.intents).read_text(encoding="utf-8"))["intents"]
    samples = [p for intent in intents for p in intent["patterns"]]
    enc = tokenizer(samples, padding=True, truncation=True, max_length=MAX_LEN, return_tensors="pt")

    with torch.no_grad():
        torch_preds = model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"]).logits.argmax(-1).tolist()
    ort_logits = session.run(
        ["logits"],
        {"input_ids": enc["input_ids"].numpy(), "attention_mask": enc["attention_mask"].numpy()},
    )[0]
    ort_preds = np.argmax(ort_logits, axis=-1).tolist()

    # int8 quantization is lossy, so a handful of near-tie predictions can flip.
    # Measure agreement across the whole pattern set rather than demanding an
    # exact match on a few samples.
    mismatches = [
        (samples[i], labels[torch_preds[i]], labels[ort_preds[i]])
        for i in range(len(samples))
        if torch_preds[i] != ort_preds[i]
    ]
    agree = len(samples) - len(mismatches)
    rate = agree / len(samples)
    print(f"int8 agreement with PyTorch: {agree}/{len(samples)} = {rate:.3f}")
    for text, a, b in mismatches[:10]:
        print(f"  mismatch: {text!r} torch={a} onnx={b}")
    assert rate >= 0.90, f"int8 ONNX agreement {rate:.3f} < 0.90"

    size_kb = onnx_path.stat().st_size / 1024
    print(f"OK: int8 ONNX agrees with PyTorch on {agree}/{len(samples)} patterns "
          f"({rate:.1%}) -> {onnx_path} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
