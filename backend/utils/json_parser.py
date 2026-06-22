import json
import re
from typing import Any


def _fix_backtick_strings(text: str) -> str:
    return re.sub(r"`([^`]*)`", r'"\1"', text)


def extract_json(text: str) -> dict[str, Any] | list[Any]:
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code blocks: ```json ... ``` or ``` ... ```
    code_block = re.search(
        r"```(?:json)?\s*\n?(.*?)\n?```",
        text,
        re.DOTALL,
    )
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try extracting from code block content after fixing backtick strings
    if code_block:
        fixed_block = _fix_backtick_strings(code_block.group(1).strip())
        try:
            return json.loads(fixed_block)
        except json.JSONDecodeError:
            pass

    # Try finding a JSON object with curly braces
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # Try finding a JSON array with square brackets
    bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
    if bracket_match:
        try:
            return json.loads(bracket_match.group(0))
        except json.JSONDecodeError:
            pass

    # Final attempt: fix backtick strings across the whole text and retry
    fixed = _fix_backtick_strings(text)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    raise json.JSONDecodeError(
        "Could not extract valid JSON from response",
        text[:500],
        0,
    )
