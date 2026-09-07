import os
import sys
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.parse_nippon import parse_workbook

SUPABASE_URL = "https://esuxjsthnzbjvfkutzpt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVzdXhqc3RobnpianZma3V0enB0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODg2ODY1MjUsImV4cCI6MjEwNDI2MjUyNX0.gqab4kcwvOdVl3JHD22x222Y9wehR5uy0eYrK2NUeDM"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

def call_rpc(func_name, payload):
    url = f"{SUPABASE_URL}/rest/v1/rpc/{func_name}"
    resp = requests.post(url, headers=HEADERS, json={"payload": payload}, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"RPC {func_name} failed with {resp.status_code}: {resp.text}")
    return resp.json()

def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    groww_file = os.path.join(repo_root, "Monthly Portfolio- July 31 2026.xlsx")
    
    if not os.path.exists(groww_file):
        raise FileNotFoundError(f"Cannot find {groww_file}")
        
    print(f"Parsing {os.path.basename(groww_file)} for Groww Mutual Fund...")
    funds, stocks, holdings = parse_workbook(groww_file, amc_name="Groww Mutual Fund")
    
    print(f"Raw parsed: {len(funds)} funds, {len(stocks)} stocks, {len(holdings)} holdings")
    
    # Filter useful holdings: INE (equities) and INF (mutual funds/ETFs)
    useful_holdings = []
    useful_isins = set()
    for sc, isin, qty, mv, wt in holdings:
        if isin and isin.startswith(("INE", "INF")):
            useful_holdings.append((sc, isin, qty, mv, wt))
            useful_isins.add(isin)
            
    # Filter stocks
    useful_stocks = {
        isin: stocks.get(isin, (isin, None))
        for isin in useful_isins
    }
    
    # Filter funds that have useful holdings
    active_schemes = {sc for sc, _, _, _, _ in useful_holdings}
    useful_funds = [f for f in funds if f["scheme_code"] in active_schemes]
    
    print(f"\nFiltered Useful Dataset for Groww:")
    print(f"  - Unique Stocks & ETFs (INE/INF): {len(useful_stocks)}")
    print(f"  - Active Funds / Schemes:        {len(useful_funds)}")
    print(f"  - Portfolio Holdings:            {len(useful_holdings)}")
    
    # 1. Upsert Stocks
    print("\n=== STEP 1: UPLOADING STOCKS TO SUPABASE ===")
    stock_payload = [
        {"isin": isin, "name": name or isin, "sector": sector}
        for isin, (name, sector) in useful_stocks.items()
    ]
    stock_batch_size = 500
    stocks_upserted = 0
    for i in range(0, len(stock_payload), stock_batch_size):
        batch = stock_payload[i : i + stock_batch_size]
        cnt = call_rpc("bulk_upsert_stocks", batch)
        stocks_upserted += cnt
        print(f"  Stocks batch {i//stock_batch_size + 1}: upserted {cnt} rows")
        time.sleep(0.2)
    print(f"Total stocks upserted: {stocks_upserted}")
    
    # 2. Upsert Funds
    print("\n=== STEP 2: UPLOADING FUNDS TO SUPABASE ===")
    fund_payload = [
        {
            "scheme_code": f["scheme_code"],
            "name": f["name"],
            "amc": f["amc"],
            "fund_type": f["fund_type"],
            "category": f["category"],
            "as_of_date": f["as_of_date"],
        }
        for f in useful_funds
    ]
    fund_batch_size = 100
    funds_upserted = 0
    for i in range(0, len(fund_payload), fund_batch_size):
        batch = fund_payload[i : i + fund_batch_size]
        cnt = call_rpc("bulk_upsert_funds", batch)
        funds_upserted += cnt
        print(f"  Funds batch {i//fund_batch_size + 1}: upserted {cnt} rows")
        time.sleep(0.2)
    print(f"Total funds upserted: {funds_upserted}")
    
    # 3. Upsert Holdings
    print("\n=== STEP 3: UPLOADING HOLDINGS TO SUPABASE ===")
    holding_payload = [
        {
            "amc": "Groww Mutual Fund",
            "scheme_code": sc,
            "as_of_date": "2026-07-31",
            "isin": isin,
            "qty": qty,
            "mv": mv,
            "wt": wt or 0.0,
        }
        for sc, isin, qty, mv, wt in useful_holdings
    ]
    holding_batch_size = 1000
    holdings_upserted = 0
    for i in range(0, len(holding_payload), holding_batch_size):
        batch = holding_payload[i : i + holding_batch_size]
        cnt = call_rpc("bulk_upsert_holdings", batch)
        holdings_upserted += cnt
        print(f"  Holdings batch {i//holding_batch_size + 1}: upserted {cnt} rows")
        time.sleep(0.2)
    print(f"Total holdings upserted: {holdings_upserted}")
    
    print("\n=== GROWW AMC DATA SUCCESSFULLY UPLOADED TO SUPABASE ===")

if __name__ == "__main__":
    main()
