import os
import sys
import glob
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.parse_nippon import parse_workbook

NOISE_KEYWORDS = [
    "average_assets",
    "risk-o-meter",
    "divmast",
    "fut disclo",
    "sebi exposure",
    "fortnightly",
]

def get_amc_name(filename):
    f_lower = filename.lower()
    if any(k in f_lower for k in ["absl", "aditya", "birla"]):
        return "Aditya Birla Sun Life Mutual Fund"
    elif any(k in f_lower for k in ["sbi", "all-schemes"]):
        return "SBI Mutual Fund"
    elif any(k in f_lower for k in ["consolidatedsebi", "kotak"]):
        return "Kotak Mahindra Mutual Fund"
    elif "dsp" in f_lower:
        return "DSP Mutual Fund"
    elif "hdfc" in f_lower:
        return "HDFC Mutual Fund"
    elif any(k in f_lower for k in ["nimf", "nippon"]):
        return "Nippon India Mutual Fund"
    elif any(k in f_lower for k in ["woc", "whiteoak"]):
        return "WhiteOak Capital Mutual Fund"
    elif any(k in f_lower for k in ["icici", "bharat 22 etf"]):
        return "ICICI Prudential Mutual Fund"
    elif "uti" in f_lower:
        return "UTI Mutual Fund"
    return "Indian Mutual Fund"

def run_parse_all():
    folder = "Monthly-Portfolio-Disclosure-July-2026"
    all_files = sorted(os.listdir(folder))
    
    valid_files = []
    skipped_files = []
    
    for f in all_files:
        f_lower = f.lower()
        if any(kw in f_lower for kw in NOISE_KEYWORDS):
            skipped_files.append((f, "Noise / Non-portfolio file"))
            continue
        # Check duplicate (1) files
        if " (1)." in f:
            base_f = f.replace(" (1).", ".")
            if base_f in all_files:
                skipped_files.append((f, f"Duplicate copy of {base_f}"))
                continue
        valid_files.append(f)

    print(f"Total files in folder: {len(all_files)}")
    print(f"Skipped noise/duplicate files: {len(skipped_files)}")
    print(f"Valid portfolio files to process: {len(valid_files)}")
    
    all_funds = {}    # (amc, scheme_code, as_of_date) -> fund_dict
    all_stocks = {}   # isin -> (name, sector)
    all_holdings = {} # (amc, scheme_code, as_of_date, isin) -> (qty, mv, wt)
    
    amc_stats = {}
    
    for idx, fname in enumerate(valid_files, 1):
        fpath = os.path.join(folder, fname)
        amc = get_amc_name(fname)
        try:
            funds, stocks, holdings = parse_workbook(fpath, amc_name=amc)
            
            # Stock updates
            for isin, (name, sector) in stocks.items():
                if isin not in all_stocks:
                    all_stocks[isin] = (name, sector)
                else:
                    cur_name, cur_sec = all_stocks[isin]
                    all_stocks[isin] = (cur_name or name, cur_sec or sector)
            
            # Fund updates
            file_fund_count = 0
            file_holding_count = 0
            for fund in funds:
                f_key = (fund["amc"], fund["scheme_code"], fund["as_of_date"])
                if f_key not in all_funds:
                    all_funds[f_key] = fund
                    file_fund_count += 1
                else:
                    # Update if better name
                    if len(fund["name"]) > len(all_funds[f_key]["name"]):
                        all_funds[f_key]["name"] = fund["name"]
            
            # Holding updates
            for scheme_code, isin, qty, mv, wt in holdings:
                # Find the matching fund's as_of_date
                fund_as_of = "2026-07-31"
                f_key = (amc, scheme_code, fund_as_of)
                h_key = (amc, scheme_code, fund_as_of, isin)
                
                if h_key in all_holdings:
                    p_qty, p_mv, p_wt = all_holdings[h_key]
                    n_qty = ((p_qty or 0) + (qty or 0)) if (p_qty is not None or qty is not None) else None
                    n_mv = ((p_mv or 0) + (mv or 0)) if (p_mv is not None or mv is not None) else None
                    n_wt = round((p_wt or 0) + (wt or 0), 4)
                    all_holdings[h_key] = (n_qty, n_mv, n_wt)
                else:
                    all_holdings[h_key] = (qty, mv, wt)
                    file_holding_count += 1
                    
            amc_stats.setdefault(amc, {"files": 0, "funds": 0, "holdings": 0})
            amc_stats[amc]["files"] += 1
            amc_stats[amc]["funds"] += file_fund_count
            amc_stats[amc]["holdings"] += file_holding_count
            
            if idx % 20 == 0 or idx == len(valid_files):
                print(f"  Processed {idx:3d}/{len(valid_files)} files... (Unique funds: {len(all_funds)}, Stocks: {len(all_stocks)}, Holdings: {len(all_holdings)})")
                
        except Exception as e:
            print(f"  ERROR processing {fname}: {e}")

    print("\n=== PARSE SUMMARY BY AMC ===")
    for amc, stats in sorted(amc_stats.items()):
        print(f"  {amc:35s}: {stats['files']:3d} files, {stats['funds']:3d} funds, {stats['holdings']:5d} holdings")
        
    print("\n=== TOTALS ===")
    print(f"Unique Funds:    {len(all_funds)}")
    print(f"Unique Stocks:   {len(all_stocks)}")
    print(f"Unique Holdings: {len(all_holdings)}")
    
    return all_funds, all_stocks, all_holdings

if __name__ == "__main__":
    run_parse_all()
