"""
LLM fallback parser — only called when the deterministic parser (e.g.
parse_nippon.py) returns zero holdings for a fund, or validate.py flags an
issue that suggests the file format changed.

This is the "second agent" layer: instead of hardcoding a new parser the
moment an AMC tweaks their spreadsheet layout, we hand the raw rows to an
LLM with a strict schema and let it find the right columns.

Supported LLMs (auto-detected from environment keys, in priority order):
  1. Google Gemini  — set GEMINI_API_KEY (free tier available at ai.google.dev)
  2. Anthropic Claude — set ANTHROPIC_API_KEY (console.anthropic.com)

At least one key must be present. If both are set, Gemini is used first.
"""
import json
import os

# ---------------------------------------------------------------------------
# Shared system prompt — same instruction for both models
# ---------------------------------------------------------------------------
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


def _strip_code_fences(text: str) -> str:
    """Remove accidental ```json ... ``` fences without corrupting JSON content."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end]).strip()
    return text


# ---------------------------------------------------------------------------
# Gemini backend
# ---------------------------------------------------------------------------
def _extract_via_gemini(rows: list, api_key: str) -> list:
    import google.generativeai as genai  # lazy import — only if key is set

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=SYSTEM_PROMPT,
    )
    payload = json.dumps(rows, default=str)
    response = model.generate_content(payload)
    text = _strip_code_fences(response.text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Claude (Anthropic) backend
# ---------------------------------------------------------------------------
def _extract_via_claude(rows: list, api_key: str) -> list:
    import anthropic  # lazy import — only if key is set

    client = anthropic.Anthropic(api_key=api_key)
    payload = json.dumps(rows, default=str)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": payload}],
    )
    text = "".join(
        block.text for block in message.content if block.type == "text"
    ).strip()
    text = _strip_code_fences(text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Public entry point — auto-selects available LLM
# ---------------------------------------------------------------------------
def extract_holdings_via_llm(rows: list) -> list:
    """
    rows: list of row tuples/lists as read from the sheet (values_only).
    Returns a list of dicts matching the schema in SYSTEM_PROMPT, or raises
    on API/parsing failure so the caller can skip this fund for this run.

    Priority:
      1. GEMINI_API_KEY   → uses Google Gemini 2.0 Flash (free tier available)
      2. ANTHROPIC_API_KEY → uses Claude Sonnet
      If neither is set, raises RuntimeError.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY")
    claude_key = os.environ.get("ANTHROPIC_API_KEY")

    if gemini_key:
        print("[llm_fallback] using Gemini 2.0 Flash")
        return _extract_via_gemini(rows, gemini_key)

    if claude_key:
        print("[llm_fallback] using Claude Sonnet")
        return _extract_via_claude(rows, claude_key)

    raise RuntimeError(
        "No LLM API key found. Set GEMINI_API_KEY (free: ai.google.dev) "
        "or ANTHROPIC_API_KEY in your .env / GitHub Secrets."
    )
