"""
Entrypoint: python -m src.main --amc nippon_india

For the named AMC: download the disclosure file, detect whether it is an
Excel workbook or a PDF, parse it with the appropriate deterministic parser,
validate each fund's holdings, and write anything that passes to Supabase.
Funds that fail validation are logged and skipped (not written) rather than
silently accepted.

Supported file types
--------------------
  .xlsx / .xls — parsed by the AMC-specific parser (e.g. parse_nippon.py)
  .pdf         — parsed by parse_pdf.py; falls back to LLM if deterministic
                 extraction yields no results
"""
import argparse
import importlib
import sys
import tempfile
from collections import defaultdict

from dotenv import load_dotenv

from src import db, fetch, validate
from src.config import AMCS, resolve_disclosure_url


def _select_parser(detected_type: str, cfg: dict):
    """Return the appropriate parser module based on detected file type."""
    if detected_type == "pdf":
        return importlib.import_module("src.parse_pdf")
    # xlsx / xls / unknown → use the AMC-configured parser
    return importlib.import_module(f"src.{cfg['parser']}")


def run_for_amc(
    amc_key: str,
    file_path: str = None,
    disclosure_url: str = None,
    year: int = None,
    month: int = None,
    strict: bool = False,
):
    if amc_key not in AMCS:
        print(f"Unknown AMC key '{amc_key}'. Known: {list(AMCS)}", file=sys.stderr)
        sys.exit(1)

    cfg = AMCS[amc_key]

    if file_path:
        local_path = file_path
        print(f"[{amc_key}] using local file: {local_path}")
    else:
        url = disclosure_url or resolve_disclosure_url(amc_key, year=year, month=month)
        print(f"[{amc_key}] downloading {url}")
        # Use a suffix-less temp file; real type is detected from magic bytes.
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
            try:
                fetch.download_file(url, tmp.name)
            except Exception as e:
                print(f"[{amc_key}] download failed from {url}: {e}", file=sys.stderr)
                portal = cfg.get("portal_url", "AMC website")
                print(f"[{amc_key}] Visit statutory downloads portal: {portal}", file=sys.stderr)
                print(
                    f"[{amc_key}] Once downloaded, run with: "
                    f"python -m src.main --amc {amc_key} --file <path>",
                    file=sys.stderr,
                )
                print(
                    f"[{amc_key}] Or specify exact direct link: "
                    f"python -m src.main --amc {amc_key} --url <link>",
                    file=sys.stderr,
                )
                if strict:
                    sys.exit(1)
                print(f"[{amc_key}] Skipped: no file available at automated URL.", file=sys.stderr)
                return
            local_path = tmp.name

    # Auto-detect file format from magic bytes (ignores extension / Content-Type)
    detected_type = fetch.detect_file_type(local_path)
    print(f"[{amc_key}] detected file type: {detected_type}")

    parser_module = _select_parser(detected_type, cfg)
    print(f"[{amc_key}] parsing with {parser_module.__name__} (deterministic)")

    funds, stocks, holdings = parser_module.parse_workbook(local_path, amc_name=cfg["display_name"])
    print(f"[{amc_key}] parsed {len(funds)} funds, {len(stocks)} stocks, {len(holdings)} holding rows")

    if not funds:
        # --- LLM fallback ---
        from src import llm_fallback
        print(f"[{amc_key}] deterministic parser found nothing — attempting LLM fallback")
        try:
            if detected_type == "pdf":
                raw_rows = parser_module.get_raw_rows_for_llm(local_path)
            else:
                # For Excel, get raw rows from the first sheet as a list-of-lists
                import openpyxl
                wb = openpyxl.load_workbook(local_path, read_only=True, data_only=True)
                ws = wb.active
                raw_rows = [list(r) for r in ws.iter_rows(values_only=True)]

            llm_results = llm_fallback.extract_holdings_via_llm(raw_rows)
            print(f"[{amc_key}] LLM fallback extracted {len(llm_results)} holding rows")

            if not llm_results:
                print(f"[{amc_key}] LLM also returned nothing — skipping this AMC", file=sys.stderr)
                return

            # Build a single synthetic fund from LLM output
            from src.config import get_reporting_period
            period = get_reporting_period(year=year, month=month)
            as_of_date = f"{period['year']}-{period['month_num']}-28"

            scheme_code = f"{amc_key.upper()}_LLM"
            fund = {
                "scheme_code": scheme_code,
                "name": cfg["display_name"] + " (LLM parsed)",
                "amc": cfg["display_name"],
                "fund_type": "mutual_fund",
                "category": None,
                "as_of_date": as_of_date,
            }
            funds = [fund]
            for row in llm_results:
                isin = row.get("isin", "")
                if isin not in stocks:
                    stocks[isin] = (row.get("name"), row.get("sector"))
                holdings.append((
                    scheme_code,
                    isin,
                    row.get("quantity"),
                    row.get("market_value"),
                    row.get("weight_pct"),
                ))

        except Exception as llm_err:
            print(
                f"[{amc_key}] LLM fallback failed: {llm_err} — skipping this AMC",
                file=sys.stderr,
            )
            return

    # Group holdings by scheme_code for per-fund validation
    holdings_by_scheme = defaultdict(list)
    for scheme_code, isin, qty, mv, wt in holdings:
        holdings_by_scheme[scheme_code].append((isin, qty, mv, wt))

    good_funds = []
    for fund in funds:
        issues = validate.validate_fund_holdings(fund, holdings_by_scheme[fund["scheme_code"]])
        if issues:
            print(f"[{amc_key}] SKIPPING {fund['scheme_code']} ({fund['name'][:50]}): {issues}")
            continue
        good_funds.append(fund)

    print(f"[{amc_key}] {len(good_funds)}/{len(funds)} funds passed validation")

    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            db.upsert_stocks(cur, stocks)
            isin_to_stock_id = db.get_stock_id_map(cur, list(stocks.keys()))

            for fund in good_funds:
                fund_id = db.upsert_fund(cur, fund)
                fund_holdings = [
                    (fund["scheme_code"], isin, qty, mv, wt)
                    for isin, qty, mv, wt in holdings_by_scheme[fund["scheme_code"]]
                ]
                db.insert_holdings(cur, fund_id, fund_holdings, isin_to_stock_id)
        conn.commit()
        print(f"[{amc_key}] committed {len(good_funds)} funds to the database")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="FolioAudit AMC monthly portfolio disclosure scraper"
    )
    parser.add_argument("--amc", required=True, help=f"Key from AMCS dict: {list(AMCS)}")
    parser.add_argument("--file", help="Optional local path to Excel or PDF file (skips download)")
    parser.add_argument("--url", help="Optional override for direct disclosure file URL")
    parser.add_argument("--year", type=int, help="Optional 4-digit year (e.g. 2025)")
    parser.add_argument("--month", type=int, help="Optional month number (1-12)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero error code if download fails",
    )
    args = parser.parse_args()
    run_for_amc(
        args.amc,
        file_path=args.file,
        disclosure_url=args.url,
        year=args.year,
        month=args.month,
        strict=args.strict,
    )
