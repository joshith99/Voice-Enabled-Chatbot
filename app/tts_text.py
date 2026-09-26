"""Text helpers that prepare Myra's streamed reply for TTS.

The same LLM text drives the UI (where ``*stage directions*`` render italic)
and TTS (where they must be stripped). Punctuation and capitalization are the
only intensity controls Bulbul v3 has, so they are preserved verbatim.
"""

import re

_SPAN_RE = re.compile(r"\*[^*]*\*")
_MULTISPACE_RE = re.compile(r" {2,}")


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
