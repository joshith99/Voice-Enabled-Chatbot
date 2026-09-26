"""Regression tests for the metadata-line parsing in app.llm.

The model is instructed to open every reply with `[[topic|confidence]]` on its
own line. These tests drive `_iter_sse` with synthetic SSE frames - no network,
no API key - and cover the cases that actually bit us:

  * a leading blank line before the metadata (made the "first line" empty, so
    the topic silently degraded to fallback/0.0 while the reply still looked
    fine)
  * a well-formed first line
  * a missing metadata line (content must not be lost)
  * reasoning_content deltas must never surface as tokens
  * an empty `choices` list must not raise

Run from the repo root:
    .\\.venv\\Scripts\\python.exe test_llm_meta.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app import llm  # noqa: E402


class _FakeResponse:
    """Stands in for requests.Response: only iter_lines is used."""

    def __init__(self, chunks):
        self._chunks = chunks

    def iter_lines(self, decode_unicode=False):
        for chunk in self._chunks:
            yield "data: " + json.dumps(chunk)
        yield "data: [DONE]"

    def close(self):
        pass


def _delta(content=None, reasoning=None, no_choices=False):
    if no_choices:
        return {"choices": []}
    d = {}
    if content is not None:
        d["content"] = content
    if reasoning is not None:
        d["reasoning_content"] = reasoning
    return {"choices": [{"delta": d}]}


def collect(chunks):
    """Run _iter_sse over synthetic frames and return (meta, text)."""
    meta = None
    text = []
    for event in llm._iter_sse(_FakeResponse(chunks)):
        if event["type"] == "meta":
            meta = event
        elif event["type"] == "token":
            text.append(event["text"])
    return meta, "".join(text)


class TestMetaParsing(unittest.TestCase):
    def test_well_formed_first_line(self):
        meta, text = collect([
            _delta("[[venting|0.7]]"),
            _delta("\nThat sounds rough."),
        ])
        self.assertEqual(meta["topic"], "venting")
        self.assertAlmostEqual(meta["confidence"], 0.7)
        self.assertEqual(text, "That sounds rough.")

    def test_leading_blank_line_is_skipped(self):
        # The exact shape that produced fallback/0.0 in the UI.
        meta, text = collect([
            _delta("\n"),
            _delta("[[crisis|0.9]]"),
            _delta("\nOkay. Stop."),
        ])
        self.assertEqual(meta["topic"], "crisis")
        self.assertAlmostEqual(meta["confidence"], 0.9)
        self.assertEqual(text, "Okay. Stop.")

    def test_leading_blank_line_arrives_with_metadata(self):
        meta, text = collect([
            _delta("\n[[greeting|0.98]]"),
            _delta("\nWell, well."),
        ])
        self.assertEqual(meta["topic"], "greeting")
        self.assertEqual(text, "Well, well.")

    def test_missing_metadata_keeps_all_text(self):
        meta, text = collect([
            _delta("No metadata here."),
            _delta("\nSecond line."),
        ])
        self.assertEqual(meta["topic"], "fallback")
        self.assertEqual(meta["confidence"], 0.0)
        self.assertIn("No metadata here.", text)
        self.assertIn("Second line.", text)

    def test_confidence_is_clamped(self):
        meta, _ = collect([
            _delta("[[venting|4.2]]"),
            _delta("\ntext"),
        ])
        self.assertEqual(meta["confidence"], 1.0)

    def test_reasoning_never_becomes_a_token(self):
        _, text = collect([
            _delta(reasoning="chain of thought that must not surface"),
            _delta("[[venting|0.7]]"),
            _delta("\nvisible reply"),
        ])
        self.assertNotIn("chain of thought", text)
        self.assertIn("visible reply", text)

    def test_empty_choices_does_not_raise(self):
        meta, text = collect([
            _delta(no_choices=True),
            _delta("[[venting|0.7]]"),
            _delta("\nreply"),
        ])
        self.assertEqual(meta["topic"], "venting")
        self.assertEqual(text, "reply")

    def test_metadata_only_stream(self):
        meta, text = collect([_delta("[[thanks|0.95]]")])
        self.assertEqual(meta["topic"], "thanks")
        self.assertEqual(text, "")


class TestFormatReminder(unittest.TestCase):
    """The metadata rule loses to recency in long conversations, so it is
    restated in the final user turn on every request."""

    def setUp(self):
        self.captured = {}
        self._orig_post = llm.requests.post

        class _Resp:
            status_code = 200
            encoding = "utf-8"

            def iter_lines(self, decode_unicode=False):
                yield "data: " + json.dumps(_delta("[[venting|0.7]]"))
                yield "data: " + json.dumps(_delta("\nreply"))
                yield "data: [DONE]"

            def close(self):
                pass

        def fake_post(url, json=None, **kwargs):
            self.captured["body"] = json
            return _Resp()

        llm.requests.post = fake_post

    def tearDown(self):
        llm.requests.post = self._orig_post

    def _send(self, message, history):
        list(llm.stream_chat(message, history))
        return self.captured["body"]["messages"]

    def test_reminder_is_in_the_final_user_turn(self):
        msgs = self._send("hello", [])
        self.assertEqual(msgs[-1]["role"], "user")
        self.assertIn("[[topic|confidence]]", msgs[-1]["content"])
        self.assertTrue(msgs[-1]["content"].startswith("hello"))

    def test_reminder_comes_after_the_history(self):
        history = [
            {"role": "user", "content": "turn one"},
            {"role": "assistant", "content": "reply one"},
        ]
        msgs = self._send("turn two", history)
        self.assertEqual([m["role"] for m in msgs], ["system", "user", "assistant", "user"])
        self.assertIn("[[topic|confidence]]", msgs[-1]["content"])

    def test_history_is_not_polluted(self):
        history = [
            {"role": "user", "content": "turn one"},
            {"role": "assistant", "content": "reply one"},
        ]
        before = json.dumps(history)
        self._send("turn two", history)
        self.assertEqual(json.dumps(history), before)

    def test_caller_message_is_not_mutated(self):
        message = "hello"
        self._send(message, [])
        self.assertEqual(message, "hello")

    def test_reasoning_is_disabled(self):
        self._send("hello", [])
        self.assertEqual(
            self.captured["body"].get("thinking"), {"type": "disabled"}
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
