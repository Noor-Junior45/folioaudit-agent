"""
Deterministic PDF parser for AMC monthly portfolio disclosure files.

Exposes the same parse_workbook(path, amc_name) interface as parse_nippon.py
so main.py can use it as a drop-in replacement when a PDF is detected.

Strategy
--------
1. Extract all tables from every page using pdfplumber.
2. Scan each row for a valid Indian ISIN (IN + 10 alphanum chars).
3. For each ISIN row, heuristically locate: name, sector, quantity,
   market value, and weight % from the surrounding cells.
4. Attempt to extract fund name + disclosure date from page text.
5. If a multi-scheme PDF is detected (multiple distinct scheme headers),
   group holdings by scheme; otherwise treat the whole file as one fund.

When this returns zero funds, the caller (main.py) will invoke the LLM
fallback — which receives the raw extracted rows and tries again.
"""
import re

import pdfplumber

ISIN_RE = re.compile(r"^IN[A-Z0-9]{9}\d$")

# "Portfolio Statement as on January 31, 2026"
DATE_RE = re.compile(
    r"(?:portfolio\s+statement\s+as\s+on|as\s+on)\s+"
    r"([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})",
    re.IGNORECASE,
)
# Fallback: "as on 31/07/2026" or "as on 31-07-2026"
DATE_RE2 = re.compile(
    r"as\s+on\s+(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})",
    re.IGNORECASE,
)

MONTH_MAP = {
    m.lower(): i
    for i, m in enumerate(
        [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ],
        start=1,
    )
}

# Keywords that likely mark a new scheme section in multi-scheme PDFs
SCHEME_HEADER_RE = re.compile(
    r"^(scheme\s+name|fund\s+name|portfolio\s+of|RLMF|[A-Z]{2,6}\d{3,})",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(s):
    if s is None:
        return None
    return re.sub(r"\s+", " ", str(s)).strip()


def _to_float(s) -> float | None:
    """Convert a cell value to float, stripping commas/spaces. Returns None on failure."""
    if s is None:
        return None
    try:
        return float(str(s).replace(",", "").replace(" ", "").strip())
    except (ValueError, TypeError):
        return None


def _extract_date(text: str) -> str | None:
    """Try to parse as_of_date from a block of text. Returns 'YYYY-MM-DD' or None."""
    m = DATE_RE.search(text)
    if m:
        month_name, day, year = m.group(1).lower(), m.group(2), m.group(3)
        month_num = MONTH_MAP.get(month_name)
        if month_num:
            return f"{year}-{month_num:02d}-{int(day):02d}"
    m2 = DATE_RE2.search(text)
    if m2:
        day, month_num, year = m2.group(1), m2.group(2), m2.group(3)
        year = f"20{year}" if len(year) == 2 else year
        return f"{year}-{int(month_num):02d}-{int(day):02d}"
    return None


def _find_isin_col(row: list) -> int:
    """Return the column index of the first valid ISIN in the row, or -1."""
    for i, cell in enumerate(row):
        if cell and ISIN_RE.match(str(cell).strip()):
            return i
    return -1


def _parse_holding_row(row: list, isin_col: int):
    """
    Given a row and the index of the ISIN cell, extract:
    (isin, name, sector, qty, market_value, weight_pct)

    Layout heuristic (most Indian AMCs):
      [...text...] | ISIN | Name | Sector | Qty | MktVal | Weight%
    or
      ISIN | Name | Sector | Qty | MktVal | Weight%

    We collect all text cells and all numeric cells separately,
    then assign positionally.
    """
    isin = str(row[isin_col]).strip()

    # Split remaining cells into text and numeric buckets
    text_cells = []
    num_cells = []
    for i, cell in enumerate(row):
        if i == isin_col or not cell:
            continue
        val = _to_float(cell)
        if val is not None:
            num_cells.append(val)
        else:
            stripped = str(cell).strip()
            if stripped:
                text_cells.append(stripped)

    name   = text_cells[0] if len(text_cells) > 0 else None
    sector = text_cells[1] if len(text_cells) > 1 else None

    # Numeric columns: last = weight%, second-last = market value, third-last = qty
    wt  = num_cells[-1] if len(num_cells) >= 1 else None
    mv  = num_cells[-2] if len(num_cells) >= 2 else None
    qty = num_cells[-3] if len(num_cells) >= 3 else None

    # Convert fraction to percentage if needed (values <= 1.0 are fractions)
    if wt is not None and 0 < wt <= 1.0:
        wt = round(wt * 100, 4)

    return isin, name, sector, qty, mv, wt


# ---------------------------------------------------------------------------
# Raw row extractor (for LLM fallback)
# ---------------------------------------------------------------------------

def get_raw_rows_for_llm(path: str) -> list[list]:
    """
    Extract all table rows from the PDF as a list of string lists.
    Used to feed data to llm_fallback.extract_holdings_via_llm() when
    the deterministic parser returns no results.
    """
    all_rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for row in table or []:
                    all_rows.append([str(c) if c is not None else "" for c in row])
    return all_rows


# ---------------------------------------------------------------------------
# Public interface — same signature as parse_nippon.parse_workbook
# ---------------------------------------------------------------------------

def parse_workbook(path: str, amc_name: str = ""):
    """
    Parse a PDF portfolio disclosure file.

    Returns (funds, stocks, holdings):
      funds:    list of fund dicts {scheme_code, name, amc, fund_type, category, as_of_date}
      stocks:   dict isin -> (name, sector)
      holdings: list of (scheme_code, isin, qty, market_value_lacs, weight_pct)

    Returns ([], {}, []) when nothing useful is extracted — the caller
    should then invoke the LLM fallback via get_raw_rows_for_llm().
    """
    all_holding_rows: list[tuple] = []   # (scheme_code, isin, name, sector, qty, mv, wt)
    stocks: dict = {}
    as_of_date: str | None = None
    full_text = ""

    # -- current scheme tracking for multi-scheme PDFs --
    current_scheme_code = "PDF_SCHEME_1"
    current_scheme_name = ""
    scheme_counter = 1

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            full_text += " " + page_text

            # Extract date from first page that has it
            if as_of_date is None:
                as_of_date = _extract_date(page_text)

            for table in page.extract_tables() or []:
                for row in table or []:
                    if not row:
                        continue

                    isin_col = _find_isin_col(row)
                    if isin_col >= 0:
                        # Valid holding row
                        isin, name, sector, qty, mv, wt = _parse_holding_row(row, isin_col)
                        if wt is not None:
                            all_holding_rows.append(
                                (current_scheme_code, isin, name, sector, qty, mv, wt)
                            )
                    else:
                        # Check if this row is a scheme header (new fund section)
                        first_cell = _norm(row[0]) if row[0] else ""
                        if first_cell and SCHEME_HEADER_RE.match(first_cell):
                            scheme_counter += 1
                            current_scheme_code = f"PDF_SCHEME_{scheme_counter}"
                            current_scheme_name = first_cell

    if not all_holding_rows:
        return [], {}, []

    # -- Group by scheme_code --
    from collections import defaultdict
    holdings_by_scheme: dict[str, list] = defaultdict(list)
    for row in all_holding_rows:
        sc = row[0]
        holdings_by_scheme[sc].append(row)

    funds = []
    holdings_out = []

    for sc, rows in holdings_by_scheme.items():
        fund = {
            "scheme_code": sc,
            "name": amc_name + (f" ({sc})" if scheme_counter > 1 else " Portfolio"),
            "amc": amc_name,
            "fund_type": "mutual_fund",
            "category": None,
            "as_of_date": as_of_date,
        }
        funds.append(fund)

        for _sc, isin, name, sector, qty, mv, wt in rows:
            if isin not in stocks:
                stocks[isin] = (_norm(name), _norm(sector))
            holdings_out.append((_sc, isin, qty, mv, round(float(wt), 4)))

    return funds, stocks, holdings_out
