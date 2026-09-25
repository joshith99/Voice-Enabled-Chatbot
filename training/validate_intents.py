"""Validate intents.json against the frozen schema (spec section 3.1).

Standard library only. Run from the repo root:

    python training/validate_intents.py

Exits 0 with PASS, or 1 with the specific failures.
"""

import json
import sys
from pathlib import Path

REQUIRED_TAGS = [
    "greeting",
    "venting",
    "advice_request",
    "relationship_problem",
    "breakup",
    "smalltalk",
    "thanks",
    "goodbye",
    "crisis",
    "fallback",
]
MIN_PATTERNS = 8
MIN_RESPONSES = 3
INTENTS_PATH = Path(__file__).resolve().parent.parent / "intents.json"


def fail(errors):
    print("FAIL")
    for error in errors:
        print("  - " + error)
    sys.exit(1)


def main():
    if not INTENTS_PATH.is_file():
        fail(["{} not found".format(INTENTS_PATH)])

    try:
        data = json.loads(INTENTS_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(["could not read/parse {}: {}".format(INTENTS_PATH, exc)])

    if not isinstance(data, dict) or not isinstance(data.get("intents"), list):
        fail(["top-level 'intents' list is missing or not a list"])

    intents = data["intents"]
    if not intents:
        fail(["'intents' list is empty"])

    errors = []
    seen_tags = []

    for index, intent in enumerate(intents):
        label = "intents[{}]".format(index)
        if not isinstance(intent, dict):
            errors.append("{} is not an object".format(label))
            continue

        tag = intent.get("tag")
        if not isinstance(tag, str) or not tag.strip():
            errors.append("{} has a missing or empty tag".format(label))
            continue
        seen_tags.append(tag)

        patterns = intent.get("patterns")
        if not isinstance(patterns, list):
            errors.append("'{}' has no patterns list".format(tag))
        else:
            if len(patterns) < MIN_PATTERNS:
                errors.append(
                    "'{}' has {} patterns (need >= {})".format(
                        tag, len(patterns), MIN_PATTERNS
                    )
                )
            for pattern in patterns:
                if not isinstance(pattern, str) or not pattern.strip():
                    errors.append("'{}' has an empty or non-string pattern".format(tag))

        responses = intent.get("responses")
        if not isinstance(responses, list):
            errors.append("'{}' has no responses list".format(tag))
        else:
            if len(responses) < MIN_RESPONSES:
                errors.append(
                    "'{}' has {} responses (need >= {})".format(
                        tag, len(responses), MIN_RESPONSES
                    )
                )
            for response in responses:
                if not isinstance(response, str) or not response.strip():
                    errors.append(
                        "'{}' has an empty or non-string response".format(tag)
                    )

    duplicates = sorted({tag for tag in seen_tags if seen_tags.count(tag) > 1})
    if duplicates:
        errors.append("duplicate tags: " + ", ".join(duplicates))

    missing = [tag for tag in REQUIRED_TAGS if tag not in seen_tags]
    if missing:
        errors.append("missing required tags: " + ", ".join(missing))

    unexpected = [tag for tag in seen_tags if tag not in REQUIRED_TAGS]
    if unexpected:
        errors.append("unexpected tags: " + ", ".join(unexpected))

    if errors:
        fail(errors)

    total_patterns = sum(len(intent["patterns"]) for intent in intents)
    print("intents: {}".format(len(intents)))
    for intent in intents:
        print(
            "  {:20s} {:3d} patterns, {} responses".format(
                intent["tag"], len(intent["patterns"]), len(intent["responses"])
            )
        )
    print("total patterns: {}".format(total_patterns))
    print("PASS")


if __name__ == "__main__":
    main()
