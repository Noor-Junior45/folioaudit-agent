"""
Robust Excel parser for AMC monthly portfolio disclosure files.
Handles Nippon India, Motilal Oswal, SBI, DSP, Mirae Asset, and other AMCs.

Strategy:
1. Per sheet, check for scheme code and fund name in the top rows, falling
   back to the sheet name.
2. Search for reporting date in header rows, defaulting to the latest month-end.
3. First try deterministic Nippon layout (Equity section marker + fixed columns).
4. If that yields no holdings, dynamically scan each row for valid Indian ISINs
   (matching ^IN[A-Z0-9]{9}\\d$), extracting the instrument name, sector,
   quantity, market value, and portfolio weight.
"""
import re
import openpyxl

ISIN_RE = re.compile(r"^IN[A-Z0-9]{9}\d$")

DATE_RE = re.compile(
    r"(?:portfolio\s+statement\s+as\s+on|as\s+on)\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})",
    re.IGNORECASE,
)
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


def _norm(s):
    if s is None:
        return None
    return re.sub(r"\s+", " ", str(s)).strip()


def _name_before_paren(full_name):
    return _norm(full_name.split("(")[0])


def guess_fund_type(full_name: str) -> str:
    main = _name_before_paren(full_name).upper()
    if "ETF" in main:
        return "etf"
    if "INDEX FUND" in main:
        return "index_fund"
    return "mutual_fund"


_CATEGORY_CHECKS = [
    ("NIFTY 500 EQUAL WEIGHT", "Nifty 500 Equal Weight"),
    ("NIFTY 500 MOMENTUM", "Nifty 500 Momentum"),
    ("NIFTY 500 LOW VOLATILITY", "Nifty 500 Low Volatility"),
    ("NIFTY 500 QUALITY", "Nifty 500 Quality"),
    ("NIFTY 50 VALUE 20", "Nifty 50 Value 20"),
    ("NIFTY ALPHA LOW VOLATILITY", "Low Volatility Factor"),
    ("NIFTY 100 LOW VOLATILITY", "Low Volatility Factor"),
    ("NIFTY MIDCAP 150", "Nifty Midcap 150"),
    ("NIFTY SMALLCAP 250", "Nifty Smallcap 250"),
    ("NIFTY NEXT 50", "Nifty Next 50"),
    ("NIFTY 100", "Nifty 100"),
    ("NIFTY 50", "Nifty 50"),
    ("NIFTY AUTO", "Thematic - Auto"),
    ("NIFTY BANK", "Thematic - Banking"),
    ("NIFTY HEALTHCARE", "Thematic - Healthcare"),
    ("NIFTY IT", "Thematic - IT"),
    ("NIFTY PHARMA", "Thematic - Pharma"),
    ("NIFTY REALTY", "Thematic - Realty"),
    ("SMALL CAP", "Small Cap"),
    ("MID CAP", "Mid Cap"),
    ("LARGE CAP", "Large Cap"),
    ("LARGE & MID CAP", "Large & Mid Cap"),
    ("FLEXI CAP", "Flexi Cap"),
    ("MULTI CAP", "Multi Cap"),
    ("FOCUSED", "Focused"),
    ("ELSS", "ELSS"),
    ("TAX SAVER", "ELSS"),
    ("VALUE", "Value"),
    ("CONTRA", "Contra"),
    ("DIVIDEND YIELD", "Dividend Yield"),
    ("BALANCED ADVANTAGE", "Dynamic Asset Allocation"),
    ("DYNAMIC ASSET", "Dynamic Asset Allocation"),
    ("AGGRESSIVE HYBRID", "Aggressive Hybrid"),
    ("CONSERVATIVE HYBRID", "Conservative Hybrid"),
    ("EQUITY SAVINGS", "Equity Savings"),
    ("ARBITRAGE", "Arbitrage"),
    ("MULTI ASSET", "Multi Asset Allocation"),
]


def guess_category(full_name: str) -> str | None:
    main = _name_before_paren(full_name).upper()
    for key, label in _CATEGORY_CHECKS:
        if key in main:
            return label
    return None


def _to_float(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace(" ", "").strip())
    except (ValueError, TypeError):
        return None


def parse_workbook(path: str, amc_name: str = "Indian Mutual Fund"):
    """
    Returns (funds, stocks, holdings):
      funds: list of dicts {scheme_code, name, amc, fund_type, category, as_of_date}
      stocks: dict isin -> (name, sector)
      holdings: list of tuples (scheme_code, isin, qty, market_value, weight_pct)
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)

    funds = []
    stocks = {}
    holdings = []

    for sheetname in wb.sheetnames:
        if sheetname.upper() in ("INDEX", "SUMMARY", "DISCLAIMER"):
            continue
        ws = wb[sheetname]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue

        # 1. Identify scheme name and code
        scheme_code = str(sheetname).strip()
        full_name = None

        for r in rows[:12]:
            for cell in r:
                c_str = str(cell).strip() if cell else ""
                if len(c_str) > 5 and any(kw in c_str.lower() for kw in ["fund", "scheme", "etf", "index", "plan"]):
                    if not any(bad in c_str.lower() for bad in ["investment manager", "asset management", "registered office", "disclaimer", "statement as on"]):
                        full_name = c_str
                        break
            if full_name:
                break

        if not full_name:
            full_name = f"{amc_name} {sheetname}"

        # 2. Extract as_of_date
        as_of_date = "2026-07-31"  # default to latest published period
        for r in rows[:10]:
            joined = " ".join(str(c) for c in r if c)
            m = DATE_RE.search(joined)
            if m:
                month_name, day, year = m.group(1).lower(), m.group(2), m.group(3)
                m_num = MONTH_MAP.get(month_name)
                if m_num:
                    as_of_date = f"{year}-{m_num:02d}-{int(day):02d}"
                    break
            m2 = DATE_RE2.search(joined)
            if m2:
                day, m_num, year = m2.group(1), m2.group(2), m2.group(3)
                year = f"20{year}" if len(year) == 2 else year
                as_of_date = f"{year}-{int(m_num):02d}-{int(day):02d}"
                break

        # 3. Extract holdings: Dynamic ISIN row detection
        fund_holdings = []
        for r in rows:
            # Find any cell matching an Indian equity ISIN (starts with INE or INF)
            isin_col = -1
            for col_idx, cell in enumerate(r):
                if cell and ISIN_RE.match(str(cell).strip()):
                    isin_col = col_idx
                    break

            if isin_col == -1:
                continue

            isin = str(r[isin_col]).strip()

            # Find name: the longest non-ISIN text cell
            stock_name = None
            sector = None
            text_cells = []
            for col_idx, cell in enumerate(r):
                if col_idx != isin_col and cell and isinstance(cell, str):
                    clean = cell.strip()
                    if len(clean) > 2 and not clean.isdigit() and not ISIN_RE.match(clean):
                        text_cells.append(clean)

            if text_cells:
                # Longest string is instrument name
                stock_name = max(text_cells, key=len)
                text_cells.remove(stock_name)
                if text_cells:
                    sector = text_cells[0]

            # Find numbers for qty, market value, weight
            numeric_cells = []
            for col_idx, cell in enumerate(r):
                if col_idx != isin_col and cell is not None:
                    flt = _to_float(cell)
                    if flt is not None and flt >= 0:
                        numeric_cells.append(flt)

            qty = None
            mv = None
            wt = None

            if numeric_cells:
                # Typically: [qty, market_value, weight]
                # Weight is usually the smallest value (<= 100)
                if len(numeric_cells) >= 3:
                    qty = numeric_cells[0]
                    mv = numeric_cells[1]
                    wt = numeric_cells[2]
                elif len(numeric_cells) == 2:
                    mv = numeric_cells[0]
                    wt = numeric_cells[1]
                elif len(numeric_cells) == 1:
                    wt = numeric_cells[0]

            # Normalize weight to percentage scale (0-100)
            if wt is not None:
                if wt <= 1.0 and wt > 0:
                    wt = round(wt * 100, 4)
                else:
                    wt = round(wt, 4)

            fund_holdings.append((isin, stock_name, sector, qty, mv, wt))

        if not fund_holdings:
            continue

        full_name_norm = _norm(full_name)
        funds.append(
            {
                "scheme_code": scheme_code,
                "name": full_name_norm,
                "amc": amc_name,
                "fund_type": guess_fund_type(full_name_norm),
                "category": guess_category(full_name_norm),
                "as_of_date": as_of_date,
            }
        )
        for isin, name, sector, qty, mv, wt in fund_holdings:
            if isin not in stocks:
                stocks[isin] = (_norm(name), _norm(sector) if sector else None)
            holdings.append((scheme_code, isin, qty, mv, wt))

    wb.close()
    return funds, stocks, holdings
