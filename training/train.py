"""Fine-tune MiniLM for intent classification and write training/model artifacts.

CPU-only by design: see docs/superpowers/specs/2026-09-25-voice-chatbot-design.md §7.
"""
import argparse
import json
import os
import random
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np
import torch
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, train_test_split
from torch.utils.data import DataLoader, TensorDataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer

BASE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SEED = 42
MAX_LEN = 64
BATCH_SIZE = 16
EPOCHS = 60
LR = 2e-4
PATIENCE = 10
MIN_ACCURACY = 0.6

# Cross-validation: the held-out split is tiny (~18 examples), so a single
# accuracy figure is noise-dominated. K-fold averages over all data.
CV_FOLDS = 5
CV_EPOCHS = 30

TRAINING_DIR = Path(__file__).resolve().parent
REPO_ROOT = TRAINING_DIR.parent


def load_intents(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    intents = data["intents"]
    tags = [i["tag"] for i in intents]
    assert len(tags) == len(set(tags)), "duplicate tags in intents.json"
    return intents


def build_examples(intents):
    labels = sorted(i["tag"] for i in intents)
    label2id = {t: n for n, t in enumerate(labels)}
    texts, ys = [], []
    for intent in intents:
        for pattern in intent["patterns"]:
            if pattern.strip():
                texts.append(pattern)
                ys.append(label2id[intent["tag"]])
    return labels, texts, ys


def tokenize(tokenizer, texts):
    enc = tokenizer(texts, padding="max_length", truncation=True, max_length=MAX_LEN, return_tensors="pt")
    return enc["input_ids"], enc["attention_mask"]


def make_loader(tokenizer, texts, ys, shuffle):
    ids, mask = tokenize(tokenizer, texts)
    ds = TensorDataset(ids, mask, torch.tensor(ys, dtype=torch.long))
    return DataLoader(ds, batch_size=BATCH_SIZE, shuffle=shuffle)


def evaluate(model, loader):
    model.eval()
    loss_fn = torch.nn.CrossEntropyLoss()
    losses, preds, gold = [], [], []
    with torch.no_grad():
        for ids, mask, y in loader:
            logits = model(input_ids=ids, attention_mask=mask).logits
            losses.append(loss_fn(logits, y).item())
            preds.extend(logits.argmax(-1).tolist())
            gold.extend(y.tolist())
    return float(np.mean(losses)), np.array(preds), np.array(gold)


def run_cross_validation(texts, ys, labels, folds):
    """Stratified k-fold accuracy over the whole dataset."""
    skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=SEED)
    loss_fn = torch.nn.CrossEntropyLoss()
    scores = []
    for fold, (tr_idx, te_idx) in enumerate(skf.split(texts, ys), 1):
        tok = AutoTokenizer.from_pretrained(BASE_MODEL)
        mdl = AutoModelForSequenceClassification.from_pretrained(
            BASE_MODEL, num_labels=len(labels)
        )
        tr_loader = make_loader(
            tok, [texts[i] for i in tr_idx], [ys[i] for i in tr_idx], shuffle=True
        )
        te_loader = make_loader(
            tok, [texts[i] for i in te_idx], [ys[i] for i in te_idx], shuffle=False
        )
        opt = torch.optim.AdamW(mdl.parameters(), lr=LR)
        for _ in range(CV_EPOCHS):
            mdl.train()
            for ids, mask, y in tr_loader:
                opt.zero_grad()
                loss_fn(mdl(input_ids=ids, attention_mask=mask).logits, y).backward()
                opt.step()
        _, preds, gold = evaluate(mdl, te_loader)
        acc = float(accuracy_score(gold, preds))
        scores.append(acc)
        print(f"  cv fold {fold}/{folds}: acc={acc:.4f}")
    return scores


def main():
    ap = argparse.ArgumentParser(description="Fine-tune MiniLM intent classifier (CPU).")
    ap.add_argument("--intents", default=str(REPO_ROOT / "intents.json"))
    ap.add_argument("--out", default=str(TRAINING_DIR / "model"))
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    ap.add_argument("--lr", type=float, default=LR)
    ap.add_argument("--folds", type=int, default=CV_FOLDS)
    args = ap.parse_args()

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)

    intents = load_intents(args.intents)
    labels, texts, ys = build_examples(intents)
    print(f"Loaded {len(texts)} patterns across {len(labels)} intents: {labels}")

    x_train, x_tmp, y_train, y_tmp = train_test_split(
        texts, ys, test_size=0.30, random_state=SEED, stratify=ys
    )
    x_val, x_test, y_val, y_test = train_test_split(
        x_tmp, y_tmp, test_size=0.50, random_state=SEED, stratify=y_tmp
    )
    print(f"Split sizes -> train={len(x_train)} val={len(x_val)} test={len(x_test)}")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(BASE_MODEL, num_labels=len(labels))

    train_loader = make_loader(tokenizer, x_train, y_train, shuffle=True)
    val_loader = make_loader(tokenizer, x_val, y_val, shuffle=False)
    test_loader = make_loader(tokenizer, x_test, y_test, shuffle=False)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    loss_fn = torch.nn.CrossEntropyLoss()
    best_val, best_state, bad_epochs = float("inf"), None, 0

    for epoch in range(1, args.epochs + 1):
        model.train()
        for ids, mask, y in train_loader:
            optimizer.zero_grad()
            loss = loss_fn(model(input_ids=ids, attention_mask=mask).logits, y)
            loss.backward()
            optimizer.step()
        val_loss, _, _ = evaluate(model, val_loader)
        print(f"epoch {epoch}: val_loss={val_loss:.4f}")
        if val_loss < best_val:
            best_val, bad_epochs = val_loss, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            bad_epochs += 1
            if bad_epochs >= PATIENCE:
                print(f"early stopping at epoch {epoch} (best val_loss={best_val:.4f})")
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    _, preds, gold = evaluate(model, test_loader)
    accuracy = float(accuracy_score(gold, preds))
    report = classification_report(
        gold, preds, labels=list(range(len(labels))), target_names=labels,
        output_dict=True, zero_division=0,
    )
    matrix = confusion_matrix(gold, preds, labels=list(range(len(labels)))).tolist()

    cv_scores = []
    if args.folds > 1:
        print(f"\n=== {args.folds}-fold cross-validation ===")
        cv_scores = run_cross_validation(texts, ys, labels, args.folds)
        print(
            f"CV accuracy: {np.mean(cv_scores):.4f} +/- {np.std(cv_scores):.4f} "
            f"(folds={args.folds})"
        )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "labels.json").write_text(json.dumps(labels, indent=2), encoding="utf-8")
    tokenizer.save_pretrained(out_dir)
    model.save_pretrained(out_dir)
    metrics = {
        "accuracy": accuracy,
        "classification_report": report,
        "confusion_matrix": matrix,
        "labels": labels,
        "split_sizes": {"train": len(x_train), "val": len(x_val), "test": len(x_test)},
        "val_loss": best_val,
        "cv_folds": args.folds,
        "cv_accuracy_mean": float(np.mean(cv_scores)) if cv_scores else None,
        "cv_accuracy_std": float(np.std(cv_scores)) if cv_scores else None,
        "cv_fold_accuracies": cv_scores,
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(f"\nTEST ACCURACY: {accuracy:.4f}")
    print(classification_report(gold, preds, labels=list(range(len(labels))), target_names=labels, zero_division=0))
    print(f"Artifacts written to {out_dir}")

    assert accuracy >= MIN_ACCURACY, f"test accuracy {accuracy:.4f} < {MIN_ACCURACY}"


if __name__ == "__main__":
    main()
