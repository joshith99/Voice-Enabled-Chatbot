"""Streaming client for the 7api [OI]-compatible chat completions endpoint.

The endpoint always speaks SSE, even without ``stream: true``, so this module
parses ``data:`` frames unconditionally. These are reasoning models: deltas may
carry ``reasoning_content`` next to ``content``; only ``content`` is ever read,
which is what actually keeps chain-of-thought out of the output.
"""

import json
import os
import re
from typing import Iterator

import requests

from .persona import get_system_prompt

_DEFAULT_BASE_URL = "https://7api.st/v1"
_DEFAULT_MODEL = "deepseek-v4.1-flash"
# The reply is short; reasoning is disabled, so this only needs headroom for
# the metadata line plus a couple of sentences. It is a cap, not a charge, but
# a huge cap invites rambling. Overridable via LLM_MAX_TOKENS.
_DEFAULT_MAX_TOKENS = 1200
_TIMEOUT = (120, 120)
_META_RE = re.compile(r"\[\[\s*([a-z_]+)\s*\|\s*([0-9]*\.?[0-9]+)\s*\]\]")

# reasoning_effort:"none" is accepted but ignored by this gateway: measured
# 2.6k-7.8k reasoning chars per call, which both wastes billed output tokens
# and pushed time-to-first-token to 15-60s. `thinking:{"type":"disabled"}` is
# the parameter that actually works here (verified 0 reasoning chars across
# repeated calls, TTFT 1.9-11.5s). Overridable with LLM_EXTRA_BODY (JSON).
_DEFAULT_EXTRA_BODY = {"thinking": {"type": "disabled"}}

# After a long conversation the model drifts into pure dialogue and silently
# drops the metadata line, which degrades the topic to "fallback". A rule
# buried in a 2.5k-token system prompt loses to recency, so restate it in the
# final user turn: measured 3/3 vs 0/3 with the prompt alone at 14 turns.
# Appended per request only - never written into the caller's history.
_FORMAT_REMINDER = (
    "\n\n(Format reminder: the FIRST line of your reply must be exactly "
    "[[topic|confidence]] - topic from the allowed list, confidence 0-1 - "
    "followed by a newline, then your reply.)"
)


class LLMError(RuntimeError):
    """Raised when the LLM cannot be called at all (e.g. missing API key)."""


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _emit_first_line(first_line: str, rest: str) -> Iterator[dict]:
    """Yield the meta event for the metadata line, then any reply text."""
    match = _META_RE.search(first_line)
    if match:
        yield {
            "type": "meta",
            "topic": match.group(1),
            "confidence": _clamp(float(match.group(2))),
        }
        after = first_line[match.end():]
        text = after + rest
        if text:
            yield {"type": "token", "text": text}
    else:
        yield {"type": "meta", "topic": "fallback", "confidence": 0.0}
        text = first_line + ("\n" + rest if rest else "")
        if text:
            yield {"type": "token", "text": text}


def _iter_sse(resp: requests.Response) -> Iterator[dict]:
    """Parse SSE frames, buffering until the first metadata line is complete."""
    buffer = ""
    meta_done = False

    for raw in resp.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        line = raw.strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue

        choices = obj.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        if not content:
            continue

        if not meta_done:
            buffer += content
            # The model occasionally opens with a blank line before the
            # metadata line; splitting on that would leave an empty "first
            # line" and lose the topic. Drop leading newlines first.
            lead = buffer.lstrip("\r\n")
            if lead != buffer:
                buffer = lead
                if not buffer:
                    continue
            if "\n" not in buffer:
                continue
            first_line, rest = buffer.split("\n", 1)
            buffer = ""
            meta_done = True
            yield from _emit_first_line(first_line, rest)
        else:
            yield {"type": "token", "text": content}

    if not meta_done and buffer:
        yield from _emit_first_line(buffer, "")


def stream_chat(message: str, history: list[dict]) -> Iterator[dict]:
    """Stream a reply from the 7api [OI]-compatible endpoint.

    history: [{"role": "user"|"assistant", "content": str}, ...]

    Yields dicts, in order:
      {"type": "meta",  "topic": str, "confidence": float}
      {"type": "token", "text": str}      # repeated
      {"type": "error", "message": str}   # terminal
    """
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise LLMError("LLM_API_KEY is not set; cannot call the LLM endpoint")

    base_url = os.environ.get("LLM_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
    url = base_url + "/chat/completions"
    body = {
        "model": os.environ.get("LLM_MODEL", _DEFAULT_MODEL),
        "messages": [{"role": "system", "content": get_system_prompt()}]
        + list(history)
        + [{"role": "user", "content": message + _FORMAT_REMINDER}],
        "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS))),
        "temperature": 0.9,
        "stream": True,
    }
    extra = os.environ.get("LLM_EXTRA_BODY")
    if extra:
        try:
            body.update(json.loads(extra))
        except json.JSONDecodeError as exc:
            raise LLMError("LLM_EXTRA_BODY is not valid JSON: %s" % exc) from exc
    else:
        body.update(_DEFAULT_EXTRA_BODY)
    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }

    resp = None
    try:
        resp = requests.post(
            url, json=body, headers=headers, stream=True, timeout=_TIMEOUT
        )
        if resp.status_code != 200:
            yield {
                "type": "error",
                "message": "LLM HTTP %s: %s" % (resp.status_code, resp.text[:1000]),
            }
            return
        resp.encoding = "utf-8"
        yield from _iter_sse(resp)
    except requests.RequestException as exc:
        yield {"type": "error", "message": "LLM request failed: %s" % exc}
    finally:
        if resp is not None:
            resp.close()
