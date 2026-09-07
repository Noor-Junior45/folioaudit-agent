"""
LLM fallback parser — only called when the deterministic parser (e.g.
parse_nippon.py) returns zero holdings for a fund, or validate.py flags an
issue that suggests the file format changed.

This is the "second agent" layer: instead of hardcoding a new parser the
moment an AMC tweaks their spreadsheet layout, we hand the raw rows to
Claude with a strict schema and let it find the right columns. This keeps
routine monthly runs fast and free (deterministic path handles them) while
still degrading gracefully instead of silently breaking when a format
changes.

Requires ANTHROPIC_API_KEY in the environment.
"""
import json
import os

import anthropic

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You extract equity holdings from one sheet of a mutual \
fund's SEBI-mandated monthly portfolio disclosure file. You will be given \
raw spreadsheet rows as a JSON array of arrays.

Find the section listing individual company stock holdings (usually under \
a header like "Equity & Equity related", sometimes with sub-labels for \
listed/unlisted). Ignore debt instruments, government securities, money \
market instruments, cash, and any subtotal/total rows.

Return ONLY a JSON array (no prose, no markdown fences) where each element \
is: {"isin": "...", "name": "...", "sector": "... or null", \
"quantity": number or null, "market_value": number or null, \
"weight_pct": number}. weight_pct must be on a 0-100 scale (if the source \
column is a 0-1 fraction, multiply by 100). Only include rows with a \
plausible Indian ISIN (starts with "IN", 12 characters)."""


def extract_holdings_via_llm(rows: list) -> list:
    """
    rows: list of row tuples/lists as read from the sheet (values_only).
    Returns a list of dicts matching the schema in SYSTEM_PROMPT, or raises
    on API/parsing failure so the caller can decide how to handle it (e.g.
    skip this fund for this run and flag it for manual review).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set; cannot use LLM fallback")

    client = anthropic.Anthropic(api_key=api_key)

    # Trim to a reasonable size — most sheets' equity sections are well
    # under a few hundred rows; send everything and let the model find
    # the right slice rather than trying to pre-locate it ourselves (that
    # pre-location is exactly what failed and triggered this fallback).
    payload = json.dumps(rows, default=str)

    message = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": payload}],
    )

    text = "".join(block.text for block in message.content if block.type == "text").strip()
    # Defensive: strip accidental code fences even though the prompt says not to.
    # Use a line-based approach — str.strip("`") would also eat backticks inside
    # JSON string values and corrupt the payload.
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop the opening fence line (```json or ```) and closing fence line (```)
        start = 1
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end]).strip()
    return json.loads(text)
