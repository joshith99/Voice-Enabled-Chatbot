"""Unit tests for app.tts_text (stage-direction stripping + sentence splitting).

Run from the repo root:
    .\\.venv\\Scripts\\python.exe test_tts_text.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.tts_text import (  # noqa: E402
    detect_language,
    has_balanced_asterisks,
    has_indic_script,
    split_sentences,
    strip_stage_directions,
)


class TestHasIndicScript(unittest.TestCase):
    def test_telugu_true(self):
        self.assertTrue(has_indic_script("\u0c05\u0c30\u0c46\u0c2f\u0c4d"))

    def test_english_false(self):
        self.assertFalse(has_indic_script("Okay. Court is in session."))

    def test_empty_false(self):
        self.assertFalse(has_indic_script(""))

    def test_romanised_telugu_false(self):
        # No native script, so the STT hint is what carries the language.
        self.assertFalse(has_indic_script("na preysi nannu vodilipoyindi"))


class TestDetectLanguage(unittest.TestCase):
    def test_telugu_script(self):
        self.assertEqual(detect_language("\u0c05\u0c30\u0c46\u0c2f\u0c4d \u0c28\u0c41\u0c35\u0c4d\u0c35\u0c41 \u0c2c\u0c3e\u0c17\u0c41\u0c28\u0c4d\u0c28\u0c3e\u0c35\u0c41"), "te-IN")

    def test_devanagari(self):
        self.assertEqual(detect_language("\u0928\u092e\u0938\u094d\u0924\u0947 \u0915\u0948\u0938\u0947 \u0939\u094b"), "hi-IN")

    def test_tamil(self):
        self.assertEqual(detect_language("\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd \u0ba8\u0bb2\u0bcd\u0bb2\u0ba4\u0bc1"), "ta-IN")

    def test_kannada(self):
        self.assertEqual(detect_language("\u0ca8\u0cae\u0cb8\u0ccd\u0c95\u0cbe\u0cb0 \u0cb9\u0cc7\u0c97\u0cc6"), "kn-IN")

    def test_english_is_default(self):
        self.assertEqual(detect_language("Okay. Court is in session."), "en-IN")

    def test_empty_uses_default(self):
        self.assertEqual(detect_language("", "te-IN"), "te-IN")

    def test_default_is_honoured_for_english_text(self):
        # A romanised Telugu reply cannot be detected; the STT hint carries it.
        self.assertEqual(detect_language("na preysi nannu vodilipoyindi", "te-IN"), "te-IN")

    def test_single_stray_glyph_does_not_flip_language(self):
        # One Indic char in an otherwise English clip should not change the voice.
        self.assertEqual(detect_language("Okay \u0c05 fine, moving on now"), "en-IN")

    def test_mixed_reply_picks_dominant_script(self):
        self.assertEqual(detect_language("\u0c05\u0c30\u0c46\u0c2f\u0c4d. \u0c28\u0c41\u0c35\u0c4d\u0c35\u0c41 \u0c2c\u0c3e\u0c17\u0c41\u0c28\u0c4d\u0c28\u0c3e\u0c35\u0c41?"), "te-IN")



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
