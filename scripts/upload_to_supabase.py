import os
import sys
import json
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.batch_ingest_all import run_parse_all

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
    print("=== STEP 1: PARSING FILES AND FILTERING USEFUL DATA ===")
    all_funds, all_stocks, all_holdings = run_parse_all()
    
    # Filter only useful holdings (INE equity shares and INF ETF/fund units)
    # Exclude sovereign debt / G-Secs / state development loans
    useful_holdings = {}
    for (amc, sc, dt, isin), (qty, mv, wt) in all_holdings.items():
        if isin.startswith(("INE", "INF")):
            useful_holdings[(amc, sc, dt, isin)] = (qty, mv, wt)
            
    # Keep only stocks referenced in useful holdings
    useful_isins = {isin for (_, _, _, isin) in useful_holdings.keys()}
    useful_stocks = {
        isin: all_stocks.get(isin, (isin, None))
        for isin in useful_isins
    }
    
    # Keep only funds that have useful holdings
    useful_fund_keys = {(amc, sc, dt) for (amc, sc, dt, _) in useful_holdings.keys()}
    useful_funds = [
        all_funds[k] for k in useful_fund_keys if k in all_funds
    ]
    
    print(f"\nFiltered Useful Dataset:")
    print(f"  - Unique Stocks & ETFs (INE/INF): {len(useful_stocks)}")
    print(f"  - Active Funds / Schemes:        {len(useful_funds)}")
    print(f"  - Portfolio Holdings:            {len(useful_holdings)}")
    
    # Step 2: Upload Stocks in batches
    print("\n=== STEP 2: UPLOADING STOCKS TO SUPABASE ===")
    stock_payload = [
        {"isin": isin, "name": name or isin, "sector": sector}
        for isin, (name, sector) in useful_stocks.items()
    ]
    stock_batch_size = 1000
    stocks_upserted = 0
    for i in range(0, len(stock_payload), stock_batch_size):
        batch = stock_payload[i : i + stock_batch_size]
        cnt = call_rpc("bulk_upsert_stocks", batch)
        stocks_upserted += cnt
        print(f"  Stocks batch {i//stock_batch_size + 1}: upserted {cnt} rows")
        time.sleep(0.2)
    print(f"Total stocks upserted: {stocks_upserted}")

    # Step 3: Upload Funds in batches
    print("\n=== STEP 3: UPLOADING FUNDS TO SUPABASE ===")
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
    fund_batch_size = 250
    funds_upserted = 0
    for i in range(0, len(fund_payload), fund_batch_size):
        batch = fund_payload[i : i + fund_batch_size]
        cnt = call_rpc("bulk_upsert_funds", batch)
        funds_upserted += cnt
        print(f"  Funds batch {i//fund_batch_size + 1}: upserted {cnt} rows")
        time.sleep(0.2)
    print(f"Total funds upserted: {funds_upserted}")

    # Step 4: Upload Holdings in batches
    print("\n=== STEP 4: UPLOADING HOLDINGS TO SUPABASE ===")
    holding_payload = [
        {
            "amc": amc,
            "scheme_code": sc,
            "as_of_date": dt,
            "isin": isin,
            "qty": qty,
            "mv": mv,
            "wt": wt or 0.0,
        }
        for (amc, sc, dt, isin), (qty, mv, wt) in useful_holdings.items()
    ]
    holding_batch_size = 2000
    holdings_upserted = 0
    for i in range(0, len(holding_payload), holding_batch_size):
        batch = holding_payload[i : i + holding_batch_size]
        cnt = call_rpc("bulk_upsert_holdings", batch)
        holdings_upserted += cnt
        print(f"  Holdings batch {i//holding_batch_size + 1:2d}/{(len(holding_payload)+holding_batch_size-1)//holding_batch_size:2d}: upserted {cnt} rows")
        time.sleep(0.2)
    print(f"Total holdings upserted: {holdings_upserted}")
    
    print("\n=== ALL DATA SUCCESSFULLY UPLOADED TO SUPABASE ===")

if __name__ == "__main__":
    main()
