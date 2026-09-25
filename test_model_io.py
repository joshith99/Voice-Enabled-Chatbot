"""Smoke test: known phrases map to expected intents.

Skips (does not fail) when the trained artifacts are absent, so the backend
can be verified before Task B has produced them.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import model_io  # noqa: E402

ARTIFACTS = [
    os.path.join(model_io.MODEL_DIR, name)
    for name in ("model.onnx", "tokenizer.json", "labels.json")
]
HAVE_ARTIFACTS = all(os.path.exists(p) for p in ARTIFACTS)

CASES = [
    ("hi there", "greeting"),
    ("i am so done with everything", "venting"),
    ("thanks so much for listening", "thanks"),
]


@unittest.skipUnless(HAVE_ARTIFACTS, "model artifacts not present yet")
class TestPredict(unittest.TestCase):
    def test_known_phrases(self):
        for phrase, expected in CASES:
            with self.subTest(phrase=phrase):
                intent, confidence = model_io.predict(phrase)
                self.assertEqual(intent, expected)
                self.assertGreater(confidence, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
