"""
Sanity checks run before anything is written to the database.

Kept intentionally strict: for a public tool, a bad write (wrong weights,
garbled ISINs) is worse than a missed update. Anything that fails is
returned in `issues` so the caller can decide to skip that fund, retry, or
fall through to the LLM fallback parser.
"""
import re

ISIN_RE = re.compile(r"^IN[A-Z0-9]{9}\d$")


def validate_fund_holdings(fund: dict, fund_holdings: list) -> list:
    """
    fund_holdings: list of (isin, qty, mv, weight_pct) for ONE fund.
    Returns a list of human-readable issue strings; empty list = passed.
    """
    issues = []

    if not fund_holdings:
        issues.append("no holdings extracted")
        return issues

    total_weight = sum(h[3] for h in fund_holdings)
    # Equity funds: equity weight should be a meaningful chunk of NAV but
    # rarely exactly 100% (cash, derivatives, other buckets exist too).
    # Flag only clearly-wrong extractions, not normal cash drag.
    if total_weight > 100.5:
        issues.append(f"equity weights sum to {total_weight:.2f}% (>100%, likely a parsing bug)")
    if total_weight < 1.0:
        issues.append(f"equity weights sum to only {total_weight:.2f}% (suspiciously low)")

    bad_isins = [h[0] for h in fund_holdings if not ISIN_RE.match(str(h[0]))]
    if bad_isins:
        issues.append(f"{len(bad_isins)} rows have invalid ISIN format: {bad_isins[:3]}")

    negative_weights = [h for h in fund_holdings if h[3] < 0]
    if negative_weights:
        issues.append(f"{len(negative_weights)} rows have negative weight_pct")

    duplicate_isins = [
        isin for isin in {h[0] for h in fund_holdings}
        if sum(1 for h in fund_holdings if h[0] == isin) > 1
    ]
    if duplicate_isins:
        issues.append(f"duplicate ISIN rows within one fund: {duplicate_isins[:3]}")

    if not fund.get("as_of_date"):
        issues.append("could not determine as_of_date for this fund")

    return issues
