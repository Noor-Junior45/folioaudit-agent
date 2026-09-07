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
    with open(path, "rb") as f:
        content = f.read()

    is_legacy_xls = content.startswith(b"\xd0\xcf\x11\xe0")
    sheet_data = []

    if is_legacy_xls:
        import xlrd
        book = xlrd.open_workbook(file_contents=content)
        for s in book.sheets():
            rows = [s.row_values(rx) for rx in range(s.nrows)]
            sheet_data.append((s.name, rows))
    else:
        import io
        in_mem = io.BytesIO(content)
        wb = openpyxl.load_workbook(in_mem, read_only=True, data_only=True)
        for sname in wb.sheetnames:
            ws = wb[sname]
            sheet_data.append((sname, list(ws.iter_rows(values_only=True))))
        wb.close()

    funds = []
    stocks = {}
    holdings = []

    for sheetname, rows in sheet_data:
        s_upper = str(sheetname).strip().upper()
        if s_upper in ("INDEX", "SUMMARY", "DISCLAIMER", "BLANK", "DERIVATIVE", "DERIVATIVES"):
            continue
        if not rows:
            continue

        # 1. Identify scheme name and code
        scheme_code = str(sheetname).strip()
        full_name = None

        for r in rows[:15]:
            line = " ".join(str(c).strip() for c in r if c is not None and str(c).strip())
            m = re.search(r"SCHEME\s*NAME\s*[:\-]?\s*([^\n\r]+)", line, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                if len(cand) > 3 and not any(bad in cand.lower() for bad in ["investment manager", "registered office"]):
                    full_name = cand
                    break
            m2 = re.search(r"Portfolio\s+of\s+([^\n\r]+?)(?:\s+as\s+on|$)", line, re.IGNORECASE)
            if m2:
                cand = m2.group(1).strip()
                if len(cand) > 3:
                    full_name = cand
                    break

        if not full_name:
            for r in rows[:10]:
                for cell in r:
                    c_str = str(cell).strip() if cell else ""
                    if len(c_str) > 5 and any(kw in c_str.lower() for kw in ["fund", "scheme", "etf", "index", "plan", "opportunity", "opportunities"]):
                        if not any(bad in c_str.lower() for bad in ["investment manager", "asset management", "registered office", "disclaimer", "statement as on", "monthly portfolio"]):
                            if c_str.lower() not in [amc_name.lower(), "icici prudential mutual fund", "sbi mutual fund", "hdfc mutual fund", "nippon india mutual fund"]:
                                full_name = c_str
                                break
                if full_name:
                    break

        if not full_name:
            full_name = f"{amc_name} {sheetname}"

        full_name = re.sub(r"^(?:portfolio\s+of\s+|monthly\s+portfolio\s+)", "", full_name, flags=re.IGNORECASE).strip()

        # 2. Extract as_of_date
        as_of_date = "2026-07-31"
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

        # 3. Detect column headers across first 25 rows
        col_map = {}
        header_row_idx = None
        for r_idx, r in enumerate(rows[:25]):
            cells = [str(c).strip() if c is not None else "" for c in r]
            if any("ISIN" in c.upper() for c in cells):
                header_row_idx = r_idx
                for i, c in enumerate(cells):
                    cu = c.upper()
                    if "ISIN" in cu and "isin" not in col_map:
                        col_map["isin"] = i
                    elif any(k in cu for k in ["NAME", "INSTRUMENT", "COMPANY", "ISSUER"]) and not any(k in cu for k in ["YIELD", "DERIVATIVE", "RATING"]):
                        if "name" not in col_map:
                            col_map["name"] = i
                    elif any(k in cu for k in ["INDUSTRY", "RATING", "SECTOR"]) and "sector" not in col_map:
                        col_map["sector"] = i
                    elif any(k in cu for k in ["QUANTITY", "QTY"]) and "qty" not in col_map:
                        col_map["qty"] = i
                    elif any(k in cu for k in ["MARKET", "FAIR VALUE", "EXPOSURE", "RS."]) and "%" not in cu and "YIELD" not in cu:
                        if "market_value" not in col_map:
                            col_map["market_value"] = i
                    elif any(k in cu for k in ["% TO", "% OF", "PERCENTAGE", "%TO", "TO NAV", "TO AUM", "TO NET"]):
                        if "weight" not in col_map:
                            col_map["weight"] = i
                    elif "%" in cu and not any(k in cu for k in ["YTM", "YTC", "COUPON", "YIELD"]):
                        if "weight" not in col_map:
                            col_map["weight"] = i
                break

        # 4. Extract holdings
        fund_holdings_dict = {}  # isin -> (name, sector, qty, mv, wt)
        start_row = (header_row_idx + 1) if header_row_idx is not None else 0

        for r in rows[start_row:]:
            # Locate ISIN
            isin = None
            isin_col = col_map.get("isin")
            if isin_col is not None and isin_col < len(r) and r[isin_col] and ISIN_RE.match(str(r[isin_col]).strip()):
                isin = str(r[isin_col]).strip()
            else:
                for idx, c in enumerate(r):
                    if c and ISIN_RE.match(str(c).strip()):
                        isin = str(c).strip()
                        isin_col = idx
                        break

            if not isin:
                continue

            # Instrument Name
            stock_name = None
            if "name" in col_map and col_map["name"] < len(r) and r[col_map["name"]]:
                val = str(r[col_map["name"]]).strip()
                if len(val) > 2 and not ISIN_RE.match(val):
                    stock_name = val
            if not stock_name:
                candidates = [
                    str(c).strip() for idx, c in enumerate(r)
                    if c and idx != isin_col and isinstance(c, str)
                    and len(str(c).strip()) > 2 and not ISIN_RE.match(str(c).strip()) and not str(c).strip().isdigit()
                ]
                if candidates:
                    stock_name = max(candidates, key=len)

            # Sector
            sector = None
            if "sector" in col_map and col_map["sector"] < len(r) and r[col_map["sector"]]:
                val = str(r[col_map["sector"]]).strip()
                if len(val) > 1 and not val.isdigit() and not any(kw in val.lower() for kw in ["crisil", "icra", "care", "sovereign", "ind a", "ind aa", "ind aaa"]):
                    sector = val

            # Numbers: Quantity, Market Value, Weight
            qty = _to_float(r[col_map["qty"]]) if "qty" in col_map and col_map["qty"] < len(r) else None
            mv = _to_float(r[col_map["market_value"]]) if "market_value" in col_map and col_map["market_value"] < len(r) else None
            wt = _to_float(r[col_map["weight"]]) if "weight" in col_map and col_map["weight"] < len(r) else None

            # Fallback if col_map missed numbers
            if wt is None:
                numeric_cells = []
                for idx, cell in enumerate(r):
                    if idx != isin_col and cell is not None and (isin_col is None or idx > isin_col):
                        flt = _to_float(cell)
                        if flt is not None and flt >= 0:
                            numeric_cells.append(flt)
                if numeric_cells:
                    if len(numeric_cells) >= 3:
                        qty = qty or numeric_cells[0]
                        mv = mv or numeric_cells[1]
                        wt = numeric_cells[2]
                    elif len(numeric_cells) == 2:
                        mv = mv or numeric_cells[0]
                        wt = numeric_cells[1]
                    elif len(numeric_cells) == 1:
                        wt = numeric_cells[0]

            # Normalize weight
            if wt is not None:
                if 0 < wt <= 1.0:
                    wt = round(wt * 100, 4)
                elif wt > 100.0:
                    # Sanity check: single stock weight cannot exceed 100%
                    wt = round(wt / 100.0, 4) if wt <= 10000.0 else None
                else:
                    wt = round(wt, 4)
            else:
                wt = 0.0

            # Aggregate duplicate holding entries for the same fund & stock
            if isin in fund_holdings_dict:
                p_name, p_sector, p_qty, p_mv, p_wt = fund_holdings_dict[isin]
                new_qty = ((p_qty or 0) + (qty or 0)) if (p_qty is not None or qty is not None) else None
                new_mv = ((p_mv or 0) + (mv or 0)) if (p_mv is not None or mv is not None) else None
                new_wt = round((p_wt or 0) + (wt or 0), 4)
                fund_holdings_dict[isin] = (p_name or stock_name, p_sector or sector, new_qty, new_mv, new_wt)
            else:
                fund_holdings_dict[isin] = (stock_name, sector, qty, mv, wt)

        if not fund_holdings_dict:
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
        for isin, (name, sector, qty, mv, wt) in fund_holdings_dict.items():
            if isin not in stocks:
                stocks[isin] = (_norm(name) or isin, _norm(sector) if sector else None)
            holdings.append((scheme_code, isin, qty, mv, wt))

    return funds, stocks, holdings
