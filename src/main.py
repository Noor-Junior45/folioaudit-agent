"""
Entrypoint: python -m src.main --amc nippon_india

For the named AMC: download the disclosure file, parse it with the
deterministic parser, validate each fund's holdings, and write anything
that passes to Supabase. Funds that fail validation are logged and skipped
(not written) rather than silently accepted.
"""
import argparse
import importlib
import sys
import tempfile
from collections import defaultdict

from dotenv import load_dotenv

from src import db, fetch, validate
from src.config import AMCS, resolve_disclosure_url


def run_for_amc(
    amc_key: str,
    file_path: str = None,
    disclosure_url: str = None,
    year: int = None,
    month: int = None,
):
    if amc_key not in AMCS:
        print(f"Unknown AMC key '{amc_key}'. Known: {list(AMCS)}", file=sys.stderr)
        sys.exit(1)

    cfg = AMCS[amc_key]
    parser_module = importlib.import_module(f"src.{cfg['parser']}")

    if file_path:
        local_path = file_path
        print(f"[{amc_key}] using local file: {local_path}")
    else:
        url = disclosure_url or resolve_disclosure_url(amc_key, year=year, month=month)
        print(f"[{amc_key}] downloading {url}")
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            try:
                fetch.download_file(url, tmp.name)
            except Exception as e:
                print(f"[{amc_key}] download failed from {url}: {e}", file=sys.stderr)
                portal = cfg.get("portal_url", "AMC website")
                print(f"[{amc_key}] Visit statutory downloads portal: {portal}", file=sys.stderr)
                print(f"[{amc_key}] Once downloaded, run with: python -m src.main --amc {amc_key} --file <path>", file=sys.stderr)
                print(f"[{amc_key}] Or specify exact direct link: python -m src.main --amc {amc_key} --url <link>", file=sys.stderr)
                sys.exit(1)
            local_path = tmp.name

    print(f"[{amc_key}] parsing (deterministic)")
    funds, stocks, holdings = parser_module.parse_workbook(local_path, amc_name=cfg["display_name"])
    print(f"[{amc_key}] parsed {len(funds)} funds, {len(stocks)} stocks, {len(holdings)} holding rows")

    if not funds:
        print(f"[{amc_key}] deterministic parser found nothing — this is where "
              f"the LLM fallback (src/llm_fallback.py) would be wired in per-sheet. "
              f"Not auto-invoked here to avoid unbounded API spend without review.")
        return

    # Group holdings by scheme_code for per-fund validation.
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
    parser = argparse.ArgumentParser(description="FolioAudit AMC monthly portfolio disclosure scraper")
    parser.add_argument("--amc", required=True, help=f"Key from AMCS dict: {list(AMCS)}")
    parser.add_argument("--file", help="Optional local path to excel file (skips download)")
    parser.add_argument("--url", help="Optional override for direct disclosure file URL")
    parser.add_argument("--year", type=int, help="Optional 4-digit year (e.g. 2025). Defaults to last reporting period.")
    parser.add_argument("--month", type=int, help="Optional month number (1-12). Defaults to last reporting period.")
    args = parser.parse_args()
    run_for_amc(
        args.amc,
        file_path=args.file,
        disclosure_url=args.url,
        year=args.year,
        month=args.month,
    )
