# Voice-Enabled Chatbot — Project Report

## Introduction

This report documents the design and implementation of a voice-enabled chatbot that
adopts a sarcastic Gen-Z therapist persona. The system accepts spoken input in any of
several supported Indian languages, transcribes and translates it, classifies the
speaker's intent using a Deep Learning model, selects a response, and returns that
response as both text and synthesized speech.

The project satisfies four core requirements: integration of speech recognition for
voice input, a Deep Learning model for intent classification, a user interface that
displays both the recognized speech and the chatbot response, and deployment of the
working application online.

## Dataset

The conversational dataset is a purpose-built file, `intents.json`, containing a set of
intent tags. Each intent maps to a list of user utterance patterns and a list of
candidate responses. The persona's wording is contained entirely within this file; the
machine learning model is responsible only for selecting the correct intent.

The dataset comprises ten intent tags — `greeting`, `venting`, `advice_request`,
`relationship_problem`, `breakup`, `smalltalk`, `thanks`, `goodbye`, `crisis`, and
`fallback` — containing 117 utterance patterns in total. Each intent provides at least
eight patterns and at least three responses. The `crisis` intent is treated as
non-negotiable: it drops the sarcastic tone and returns a helpline rather than a humorous
reply. It was deliberately over-provisioned with indirect phrasings (for example, "i feel
hopeless", "i feel like a burden to everyone") so that it does not depend on explicit
crisis vocabulary to be recognised.

No suitable public dataset exists for this specific persona, so the dataset was authored
for this project. Its schema is frozen and validated by a dedicated validation script.

## Model Architecture

Intent classification is performed by a fine-tuned MiniLM sequence classifier. The base
model is `sentence-transformers/all-MiniLM-L6-v2`, a compact six-layer transformer of
approximately 22 million parameters, loaded through `AutoModelForSequenceClassification`
with a classification head sized to the number of intents.

The classifier operates on English text. Input in any supported language is translated to
English before classification (a translate-at-the-edge approach), which keeps the model
small and fast on CPU while remaining language-agnostic at the boundary.

For serving, the trained model is exported to ONNX and dynamically quantized to int8,
producing `model.onnx`. The serving runtime is `onnxruntime` (CPU); `torch` and
`transformers` are not required at serve time.

## Methodology

Training follows a supervised text-classification workflow:

1. Load the patterns and their intent tags from `intents.json` (117 patterns, 10 intents).
2. Tokenize the text with the fast tokenizer associated with the base model, with a maximum
   sequence length of 64 tokens.
3. Split the data into stratified train (81), validation (18), and test (18) partitions.
4. Fine-tune the sequence classifier using AdamW at a learning rate of 2e-4, batch size 16,
   for up to 60 epochs, with early stopping based on validation loss (patience 10).
5. Evaluate the trained model on the held-out test partition and record the metrics.
6. Run stratified 5-fold cross-validation over the entire dataset to obtain a stable
   accuracy estimate that does not depend on the single small test partition.

The trained model is then exported to ONNX with dynamic axes and dynamically quantized
to int8. The quantized model is verified by loading it with `onnxruntime` and confirming
that its predictions agree with the PyTorch model on a small set of sample inputs.

At serving time, the pipeline processes a request as follows: speech is transcribed by
Sarvam Saaras v3 in code-mixed mode, the resulting transcript is translated to English by
Sarvam Mayura, the intent model predicts an intent and confidence, a response is drawn
from `intents.json`, the response is localized back to the detected language, and Sarvam
Bulbul v3 synthesizes the reply audio. Inputs whose confidence falls below the configured
threshold are routed to the `fallback` intent.

Training was performed on a CPU-only host in an isolated virtual environment. The
environment was removed after training, leaving only the exported artifacts.

## Results

All figures below are taken directly from the training run recorded in
`training/model/metrics.json`. Training used a CPU-only host (no GPU was used).

### Overall Metrics

| Metric | Value |
|---|---|
| 5-fold cross-validation accuracy | **0.846 ± 0.043** |
| Test accuracy (held-out) | 0.8333 (15/18) |
| Macro-average F1 | 0.8333 |
| Weighted-average F1 | 0.8333 |
| Best validation loss | 0.3562 |
| Training set size | 81 |
| Validation set size | 18 |
| Test set size | 18 |
| Epochs run | 25 (early stopping) |

The primary result is the cross-validation figure, **84.6% ± 4.3%**, averaged over five
folds covering the entire dataset. The held-out test accuracy of 83.3% is consistent with
it. The cross-validation number is reported as the headline because the single test
partition contains only eighteen examples, where each example is worth 5.6 percentage
points; the fold-to-fold spread (79.2%–91.7%) quantifies exactly how noisy a single split
is. For the same reason, the earlier single-split results from a smaller dataset (81.25%
on sixteen examples) are not directly comparable to these figures.

### Per-Class F1 Scores

| Intent | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| greeting | 0.50 | 0.50 | 0.50 | 2 |
| venting | 1.00 | 1.00 | 1.00 | 1 |
| advice_request | 1.00 | 1.00 | 1.00 | 1 |
| relationship_problem | 1.00 | 1.00 | 1.00 | 2 |
| breakup | 0.50 | 1.00 | 0.67 | 1 |
| smalltalk | 1.00 | 1.00 | 1.00 | 1 |
| thanks | 1.00 | 0.50 | 0.67 | 2 |
| goodbye | 0.50 | 0.50 | 0.50 | 2 |
| crisis | **1.00** | **1.00** | **1.00** | 4 |
| fallback | 1.00 | 1.00 | 1.00 | 2 |

Six of the ten intents achieved perfect precision, recall, and F1, including `crisis`,
which reached 1.00 on both precision and recall across its four test examples.

### Confusion Matrix

Rows are the actual intent, columns the predicted intent, in the label order
`advice_request, breakup, crisis, fallback, goodbye, greeting, relationship_problem,
smalltalk, thanks, venting`.

```
                  adv  brk  cri  fal  goo  gre  rel  sma  tha  ven
advice_request  [   1    0    0    0    0    0    0    0    0    0 ]
breakup         [   0    1    0    0    0    0    0    0    0    0 ]
crisis          [   0    0    4    0    0    0    0    0    0    0 ]
fallback        [   0    0    0    2    0    0    0    0    0    0 ]
goodbye         [   0    1    0    0    1    0    0    0    0    0 ]
greeting        [   0    0    0    0    1    1    0    0    0    0 ]
relationship_…  [   0    0    0    0    0    0    2    0    0    0 ]
smalltalk       [   0    0    0    0    0    0    0    1    0    0 ]
thanks          [   0    0    0    0    0    1    0    0    1    0 ]
venting         [   0    0    0    0    0    0    0    0    0    1 ]
```

Three of the eighteen test examples were misclassified:

| Actual | Predicted as | Count |
|---|---|---|
| goodbye | breakup | 1 |
| greeting | goodbye | 1 |
| thanks | greeting | 1 |

### Discussion

The most important outcome of this evaluation is that the `crisis` intent is now detected
reliably. In an earlier iteration the classifier missed one of two crisis examples,
routing it to `venting`, which would have produced a sarcastic reply where a sincere
helpline is required. That error was addressed by expanding the `crisis` patterns from
eleven to twenty-two, deliberately adding indirect phrasings that avoid explicit crisis
vocabulary. Crisis detection subsequently reached perfect precision and recall on the test
partition, and the model's overall validation loss fell sharply (from 0.90 to 0.36),
indicating that the added examples improved the decision boundary rather than merely
inflating one class.

The remaining errors are all confusions between short, low-content utterances. `greeting`,
`goodbye`, and `thanks` are each represented by very brief phrases ("hi", "bye", "thanks")
that carry little lexical signal, and the classifier confuses them with one another — one
`thanks` example was read as `greeting`, and one `greeting` example as `goodbye`. A
labeling conflict was also found and corrected during this work: the phrase "what's up" had
appeared in both `smalltalk` and `greeting` under different labels, which is precisely the
kind of inconsistency that inflates error rates on small datasets.

Two limitations should be stated plainly. First, the dataset remains small (117 patterns),
so all per-class figures rest on one to four test examples and should be read as indicative
rather than precise; this is why cross-validation is reported as the headline. Second,
validation loss reached its minimum around epoch 25 and then began to rise, which is the
expected signature of a model beginning to memorise a small training set; the early-stopping
criterion restored the best checkpoint rather than the final one.

The principal direction for improvement is dataset scale and balance. The three
short-utterance intents (`greeting`, `goodbye`, `thanks`) would benefit most from additional
patterns, since their current errors stem from having too few examples to define a stable
boundary. Expanding `crisis` further with indirect phrasings remains worthwhile even at
perfect test performance, because recall on this class matters more than on any other and a
single held-out example cannot demonstrate reliability.

## Deployment

The application is a Flask web service with a browser-based frontend. The backend exposes
endpoints for text chat, audio transcription, speech synthesis, and a health check. The
frontend captures microphone audio with the MediaRecorder API and renders the native
transcript, the English interpretation, and the bot reply.

The service is kept container-portable, with a serve-time dependency set that excludes
`torch` and `transformers`. The hosting platform is selected after local verification;
candidate platforms include Hugging Face Spaces, Google Cloud Run, and Render.

Local verification was completed successfully. The backend was exercised with the Sarvam
calls placed in a stub mode, confirming that the intent model loads from its int8 ONNX
artifacts and that each endpoint returns the expected response shape: the health check
reported ten labels, a greeting input was classified as `greeting` with 0.86 confidence, a
venting input as `venting` with 0.90 confidence, and a crisis input as `crisis` with 0.91
confidence, returning the sincere helpline response rather than a sarcastic one. The
frontend page and its static assets were served correctly. Public hosting is the remaining
step and requires a hosting account and a live Sarvam API key.

The Sarvam API key is provided to the server through the `SARVAM_API_KEY` environment
variable only. It is never transmitted to the browser, and the local `.env` file is
excluded from version control while `.env.example` is committed.

## Conclusion

Three of the four core requirements are fully met and verified locally. Speech recognition
for voice input is integrated through the Sarvam Saaras v3 model in code-mixed mode, which
also supports the Indian languages and Hinglish/Tenglish-style blends that were the primary
target. A Deep Learning model for intent classification is implemented as a fine-tuned
MiniLM transformer, trained on a purpose-built dataset and achieving **84.6% ± 4.3%**
cross-validation accuracy (83.3% on a held-out test split) with a macro-average F1 of 0.83
across ten intents. The user interface displays both the recognized speech and the chatbot
response, showing the native transcript, the English interpretation, and the reply.

The fourth requirement — public deployment — remains outstanding. The application runs
correctly as a local web service and has been verified end to end in that mode; it has not
yet been hosted on a public platform, which requires a hosting account and a live Sarvam
API key. This is the immediate next step.

The principal limitation is dataset size. With 117 patterns across ten intents, per-class
figures rest on only one to four test examples each, which is why cross-validation is
reported as the headline metric; validation loss reached its minimum around epoch 25 and
then rose, the expected signature of mild overfitting on a small training set.

Reliability on the `crisis` intent was treated as a hard requirement rather than a metric to
optimise. An earlier iteration misclassified a genuine crisis utterance as `venting`, which
would have produced a sarcastic response where a sincere helpline is required. Expanding the
crisis patterns with indirect phrasings resolved this: crisis detection now achieves perfect
precision and recall. The remaining errors are confined to the short-utterance intents
(`greeting`, `goodbye`, `thanks`), whose phrases carry little lexical signal.

Directions for future work include enlarging and balancing the dataset — particularly the
three short-utterance intents and the `crisis` class, where recall matters more than
anywhere else — evaluating a multilingual intent model in place of the translate-at-the-edge
design, adding automated tests around the full HTTP pipeline with recorded audio fixtures,
and containerising the service for deployment.
