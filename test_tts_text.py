"""Unit tests for app.tts_text (stage-direction stripping + sentence splitting).

Run from the repo root:
    .\\.venv\\Scripts\\python.exe test_tts_text.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.tts_text import (  # noqa: E402
    has_balanced_asterisks,
    split_sentences,
    strip_stage_directions,
)


class TestStripStageDirections(unittest.TestCase):
    def test_single_span(self):
        self.assertEqual(
            strip_stage_directions("*slams gavel* Guilty."), "Guilty."
        )

    def test_multiple_spans(self):
        self.assertEqual(
            strip_stage_directions("*sighs* Fine. *gavel* Done."),
            "Fine. Done.",
        )

    def test_span_with_internal_spaces(self):
        self.assertEqual(
            strip_stage_directions("*sighs in professionally licensed*"), ""
        )

    def test_preserves_punctuation_and_case(self):
        text = "*gavel* VERDICT: Guilty. Of. Delulu. ...Okay?!"
        self.assertEqual(
            strip_stage_directions(text),
            "VERDICT: Guilty. Of. Delulu. ...Okay?!",
        )

    def test_unbalanced_leaves_trailing_partial_span(self):
        self.assertEqual(
            strip_stage_directions("*slams gavel"), "*slams gavel"
        )

    def test_no_stars_unchanged(self):
        text = "You knew the pitch was hostile... and you took the strike anyway."
        self.assertEqual(strip_stage_directions(text), text)


class TestHasBalancedAsterisks(unittest.TestCase):
    def test_balanced_pair(self):
        self.assertTrue(has_balanced_asterisks("*slams gavel*"))

    def test_unbalanced(self):
        self.assertFalse(has_balanced_asterisks("*slams"))

    def test_no_stars(self):
        self.assertTrue(has_balanced_asterisks("no stars"))

    def test_even_count(self):
        self.assertTrue(has_balanced_asterisks("a * b * c"))


class TestSplitSentences(unittest.TestCase):
    def test_two_sentences(self):
        self.assertEqual(
            split_sentences("He ghosted you. After you planned his birthday. "),
            (["He ghosted you.", "After you planned his birthday."], ""),
        )

    def test_trailing_fragment_is_remainder(self):
        self.assertEqual(
            split_sentences("Done. And then"), (["Done."], "And then")
        )

    def test_ellipsis_is_not_a_terminator(self):
        self.assertEqual(
            split_sentences("hostile... and you took the strike anyway."),
            (["hostile... and you took the strike anyway."], ""),
        )

    def test_double_period_is_not_a_terminator(self):
        self.assertEqual(
            split_sentences("hostile.. and you"), ([], "hostile.. and you")
        )

    def test_unbalanced_span_blocks_splitting(self):
        self.assertEqual(
            split_sentences("*slams gavel"), ([], "*slams gavel")
        )
        self.assertEqual(
            split_sentences("*slams gavel. Guilty."),
            ([], "*slams gavel. Guilty."),
        )

    def test_balanced_span_allows_splitting(self):
        self.assertEqual(
            split_sentences("*slams gavel* Guilty. "),
            (["*slams gavel* Guilty."], ""),
        )

    def test_shock_and_exclamation_terminators(self):
        self.assertEqual(
            split_sentences("He said WHAT?! And you said nothing."),
            (["He said WHAT?!", "And you said nothing."], ""),
        )
        self.assertEqual(
            split_sentences("Stop! Listen."), (["Stop!", "Listen."], "")
        )

    def test_empty_buffer(self):
        self.assertEqual(split_sentences(""), ([], ""))


class TestPersonaRoundTrip(unittest.TestCase):
    LINE = (
        "*slams gavel* VERDICT: Guilty of first-degree delulu. "
        "Sentence: hydrate."
    )

    def test_stripped_for_tts_keeps_periods_and_colon(self):
        self.assertEqual(
            strip_stage_directions(self.LINE),
            "VERDICT: Guilty of first-degree delulu. Sentence: hydrate.",
        )

    def test_splitting_yields_two_sentences(self):
        sentences, remainder = split_sentences(self.LINE)
        self.assertEqual(len(sentences), 2)
        self.assertEqual(
            [strip_stage_directions(s) for s in sentences],
            [
                "VERDICT: Guilty of first-degree delulu.",
                "Sentence: hydrate.",
            ],
        )
        self.assertEqual(remainder, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
