"""Text helpers that prepare Myra's streamed reply for TTS.

The same LLM text drives the UI (where ``*stage directions*`` render italic)
and TTS (where they must be stripped). Punctuation and capitalization are the
only intensity controls Bulbul v3 has, so they are preserved verbatim.
"""

import re

_SPAN_RE = re.compile(r"\*[^*]*\*")
_MULTISPACE_RE = re.compile(r" {2,}")

# Indic script blocks -> BCP-47 codes. Detected per TTS clip so a reply that
# mixes English and Telugu is voiced in the right language for each part.
_SCRIPT_RANGES = (
    ("te-IN", "\u0c00", "\u0c7f"),  # Telugu
    ("kn-IN", "\u0c80", "\u0cff"),  # Kannada
    ("ta-IN", "\u0b80", "\u0bff"),  # Tamil
    ("ml-IN", "\u0d00", "\u0d7f"),  # Malayalam
    ("gu-IN", "\u0a80", "\u0aff"),  # Gujarati
    ("pa-IN", "\u0a00", "\u0a7f"),  # Gurmukhi (Punjabi)
    ("bn-IN", "\u0980", "\u09ff"),  # Bengali
    ("od-IN", "\u0b00", "\u0b7f"),  # Odia
    ("hi-IN", "\u0900", "\u097f"),  # Devanagari (Hindi/Marathi)
)

# Minimum Indic characters before a script wins; guards against one stray
# glyph pulling an otherwise-English clip into another language.
_SCRIPT_MIN_CHARS = 3


def has_indic_script(text: str) -> bool:
    """True if ``text`` contains Indic-script characters."""
    for char in text:
        point = ord(char)
        for _, low, high in _SCRIPT_RANGES:
            if ord(low) <= point <= ord(high):
                return True
    return False


def detect_language(text: str, default: str = "en-IN") -> str:
    """Pick a TTS language code from the script used in ``text``.

    The persona is asked to write Indic languages in their native script, so
    script detection is enough to voice each clip correctly. Falls back to
    ``default`` (usually the STT-detected language) when no script dominates.
    """
    counts = {code: 0 for code, _, _ in _SCRIPT_RANGES}
    for char in text:
        point = ord(char)
        for code, low, high in _SCRIPT_RANGES:
            if ord(low) <= point <= ord(high):
                counts[code] += 1
                break
    best = max(counts, key=lambda c: counts[c])
    if counts[best] >= _SCRIPT_MIN_CHARS:
        return best
    return default or "en-IN"


def strip_stage_directions(text: str) -> str:
    """Remove *...* spans (incl. the asterisks) for TTS. Keeps ... — ?! caps."""
    cleaned = _SPAN_RE.sub("", text)
    return _MULTISPACE_RE.sub(" ", cleaned).strip()


def has_balanced_asterisks(text: str) -> bool:
    """True if the count of '*' is even (no unterminated stage direction)."""
    return text.count("*") % 2 == 0


def split_sentences(buffer: str) -> tuple[list[str], str]:
    """Split complete sentences off the front. Returns (sentences, remainder).

    Only splits on [.!?] followed by whitespace (or end of buffer). Never
    splits inside '...' (a run of 2+ periods). Never splits inside an
    unbalanced '*...*' span.
    """
    sentences: list[str] = []
    start = 0
    i = 0
    n = len(buffer)
    unmatched = -1 if has_balanced_asterisks(buffer) else buffer.rfind("*")

    while i < n:
        if buffer[i] not in ".!?":
            i += 1
            continue

        j = i
        while j < n and buffer[j] in ".!?":
            j += 1
        run = buffer[i:j]

        is_period_run = len(run) >= 2 and run == "." * len(run)
        at_boundary = j == n or buffer[j].isspace()
        inside_open_span = unmatched != -1 and j > unmatched

        if not is_period_run and at_boundary and not inside_open_span:
            sentence = buffer[start:j].strip()
            if sentence:
                sentences.append(sentence)
            start = j

        i = j

    return sentences, buffer[start:].strip()


def merge_sentences(sentences: list[str], min_chars: int = 140) -> list[str]:
    """Coalesce short fragments into longer TTS clips.

    Myra's staccato verdicts ("Guilty. Of. Delulu.") produce many one-word
    sentences. Each one costs a separate TTS round trip, so joining them up to
    ``min_chars`` cuts the number of calls without changing what is spoken.
    """
    merged: list[str] = []
    buf = ""
    for sentence in sentences:
        buf = f"{buf} {sentence}".strip() if buf else sentence
        if len(buf) >= min_chars:
            merged.append(buf)
            buf = ""
    if buf:
        if merged:
            merged[-1] = f"{merged[-1]} {buf}"
        else:
            merged.append(buf)
    return merged
