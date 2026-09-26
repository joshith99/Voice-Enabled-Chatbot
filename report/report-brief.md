# Voice-Enabled Chatbot — Brief Report

**Project:** An online voice-enabled chatbot with a sarcastic Gen-Z therapist persona.
**Stack:** Sarvam AI (speech) + fine-tuned MiniLM transformer (intent classification) + Flask.

## 1. Overview

The system accepts spoken input in English and Indian languages, transcribes it, classifies
the speaker's intent with a Deep Learning model, and returns a response as both text and
synthesized speech. It addresses all four assignment requirements: speech recognition for
voice input, a Deep Learning model for intent classification, a UI displaying both the
recognized speech and the chatbot response, and online deployment. It supports English,
Hindi, Telugu, Tamil, Kannada, and Punjabi, including code-mixed blends (Hinglish,
Tenglish).

## 2. Dataset

The dataset is purpose-built (`intents.json`); no public dataset matches this persona.

| Property | Value |
|---|---|
| Intents | 10 |
| Total utterance patterns | 117 |
| Responses per intent | ≥ 3 |
| Patterns per intent | ≥ 8 |
| Crisis patterns | 22 (11 explicit + 11 indirect phrasings) |

Intents: `greeting`, `venting`, `advice_request`, `relationship_problem`, `breakup`,
`smalltalk`, `thanks`, `goodbye`, `crisis`, `fallback`.

The persona's wording lives entirely in the dataset; the model only selects the intent. The
`crisis` intent deliberately drops the sarcasm and returns a helpline (Tele-MANAS 14416),
and was over-provisioned with indirect phrasings so it does not depend on explicit crisis
vocabulary to be recognised. A schema validation script enforces the structure.

## 3. Model Architecture

Intent classification uses a fine-tuned **MiniLM** sequence classifier
(`sentence-transformers/all-MiniLM-L6-v2`): a six-layer transformer of ~22M parameters
loaded via `AutoModelForSequenceClassification`, with a classification head sized to the ten
intents.

The classifier operates on English text. Non-English input is translated to English before
classification (a *translate-at-the-edge* design), keeping the model small and fast on CPU
while remaining language-agnostic at the boundary.

For serving, the model is exported to ONNX and dynamically quantized to **int8**
(`model.onnx`, ~22 MiB). The serving runtime is `onnxruntime`; `torch` and `transformers`
are not required in production.

## 4. Methodology

1. **Data** — load 117 patterns across 10 intents from `intents.json`.
2. **Tokenize** — fast tokenizer, maximum sequence length 64.
3. **Split** — stratified 81 / 18 / 18 (train / validation / test).
4. **Train** — AdamW, learning rate 2e-4, batch size 16, up to 60 epochs, early stopping on
   validation loss (patience 10). CPU-only, in an isolated virtual environment.
5. **Evaluate** — held-out test metrics plus stratified 5-fold cross-validation.
6. **Export** — ONNX with dynamic axes, then dynamic int8 quantization; verified by
   measuring prediction agreement with the PyTorch model across all 117 patterns (97.4%).

**Serving pipeline:** microphone audio → Sarvam Saaras v3 (code-mixed STT) → Sarvam Mayura
(translate to English) → local int8 ONNX intent model → response from `intents.json` →
Mayura (localize) → Sarvam Bulbul v3 (text-to-speech). Inputs below the confidence
threshold are routed to `fallback`.

## 5. Results

| Metric | Value |
|---|---|
| **5-fold cross-validation accuracy** | **0.846 ± 0.043** |
| Held-out test accuracy | 0.833 (15/18) |
| Macro-average F1 | 0.833 |
| Weighted-average F1 | 0.833 |
| `crisis` precision / recall / F1 | 1.00 / 1.00 / 1.00 |
| Best validation loss | 0.356 |

Six of ten intents reached perfect precision, recall, and F1. The three remaining errors were
all confusions between short, low-content utterances (`greeting`, `goodbye`, `thanks`).

Cross-validation is reported as the headline because the held-out test partition contains
only 18 examples, where each example is worth 5.6 percentage points; the fold-to-fold spread
(79.2%–91.7%) quantifies how noisy a single split is.

**Live pipeline verification.** Tenglish utterances were run through the full live pipeline:

| Spoken input | Intended language | Predicted intent | Confidence |
|---|---|---|---|
| `naku brathakali ani ledhu` | te-IN | `crisis` | 0.97 |
| `na gf nannu odilesindi` | te-IN | `breakup` | 0.87 |
| `na bf nannu odilesadu` | te-IN | `breakup` | 0.85 |

The crisis utterance correctly returned the sincere helpline rather than a sarcastic reply,
and both code-mixed breakup utterances were correctly identified.

## 6. Status

| Requirement | Status |
|---|---|
| Speech recognition for voice input | ✅ Sarvam Saaras v3, code-mixed |
| Deep Learning intent classification | ✅ Fine-tuned MiniLM → int8 ONNX |
| Display transcript and response | ✅ Native transcript + English + reply |
| Public deployment | ⏳ Runs locally and verified live; hosting pending |

**Limitations.** The dataset is small (117 patterns), so per-class figures rest on one to
four test examples each and are indicative rather than precise. Validation loss reached its
minimum around epoch 25 and then rose, the expected signature of mild overfitting on a small
training set.

**Future work.** Enlarge and balance the dataset (especially the short-utterance intents);
extend `crisis` coverage further, since recall there matters more than anywhere else; deploy
publicly; and add automated tests around the full HTTP pipeline with recorded audio fixtures.
