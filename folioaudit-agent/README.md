# FolioAudit Agent (Repo 1)

Data-fetching agent for the MF & ETF Holdings Overlap Tool. This repo is
independent from the frontend (FolioAudit) repo — it only talks to the shared
Supabase Postgres database.

## How it works (hybrid agent design)

For each AMC, the pipeline tries two layers, in order:

1. **Deterministic parser** (`src/parse_nippon.py` etc.) — fast, free, no AI
   calls. Handles the AMC's file format using known rules (equity section
   markers, ISIN regex, column positions) validated against real files.
2. **LLM fallback agent** (`src/llm_fallback.py`) — only triggered when the
   deterministic parser finds zero holdings or fails a validation check
   (e.g. the AMC changed its file layout). Sends the raw sheet content to
   Claude with instructions to extract `{isin, name, sector, weight_pct}`
   rows in a fixed JSON schema. This keeps routine runs cheap and fast, and
   only spends AI calls on the format-drift edge case, which is exactly
   where a rigid script would otherwise silently break.

Every row — from either layer — passes through `src/validate.py` before
being written to the database (weights are sanity-checked, ISIN format is
checked, nothing gets written on a failed check).

## Repo layout

```
schema.sql         # PostgreSQL schema definition for Supabase SQL Editor
src/
  config.py          # AMC registry: name, disclosure URL, parser to use
  fetch.py           # Downloads the disclosure file for a given AMC
  parse_nippon.py    # Deterministic parser for Nippon India's file format
  llm_fallback.py    # Claude-based extraction, used only on parser failure
  validate.py        # Sanity checks before writing to DB
  db.py              # Supabase Postgres connection + upsert logic
  main.py            # Orchestrates one AMC end-to-end
.github/workflows/
  monthly_scrape.yml # Runs main.py for every AMC in config.py, monthly
```

## Supported AMCs (Top 10 by AUM)

| Key | AMC Name | Statutory Disclosure Portal |
| :--- | :--- | :--- |
| `sbi` | SBI Mutual Fund | [sbimf.com](https://www.sbimf.com/en-us/downloads/portfolio-disclosures) |
| `icici_pru` | ICICI Prudential Mutual Fund | [icicipruamc.com](https://www.icicipruamc.com/downloads/monthly-portfolio-disclosure) |
| `hdfc` | HDFC Mutual Fund | [hdfcfund.com](https://www.hdfcfund.com/statutory-disclosure/monthly-portfolio) |
| `nippon_india` | Nippon India Mutual Fund | [nipponindiaim.com](https://mf.nipponindiaim.com/investor-services/downloads/factsheets-monthly-portfolios) |
| `kotak` | Kotak Mahindra Mutual Fund | [kotakmf.com](https://www.kotakmf.com/downloads/statutory-disclosure/monthly-portfolio) |
| `aditya_birla` | Aditya Birla Sun Life Mutual Fund | [mutualfund.adityabirlacapital.com](https://mutualfund.adityabirlacapital.com/forms-and-downloads/monthly-portfolio) |
| `uti` | UTI Mutual Fund | [utimf.com](https://www.utimf.com/forms-and-downloads/monthly-portfolio-disclosure) |
| `axis` | Axis Mutual Fund | [axismf.com](https://www.axismf.com/statutory-disclosures) |
| `mirae_asset` | Mirae Asset Mutual Fund | [miraeassetmf.co.in](https://www.miraeassetmf.co.in/downloads/statutory-disclosure/monthly-portfolio-disclosures) |
| `dsp` | DSP Mutual Fund | [dspim.com](https://www.dspim.com/mandatory-disclosures/portfolio-disclosures) |
| `whiteoak` | WhiteOak Capital Mutual Fund | [whiteoakamc.com](https://mf.whiteoakamc.com/downloads/portfolio-disclosures) |
| `motilal_oswal` | Motilal Oswal Mutual Fund & ETF | [motilaloswalmf.com](https://www.motilaloswalmf.com/downloads/mutual-fund/scheme-portfolio) |

## Setup & Running

1. `pip install -r requirements.txt`
2. **Database Setup (Supabase)**:
   - Create a project in [Supabase](https://supabase.com).
   - Go to the **SQL Editor** in your Supabase dashboard, paste the contents of `schema.sql`, and click **Run** to create the tables, RLS policies, and frontend views.
   - Go to **Project Settings** → **Database** → **Connection string** → **URI**. Copy your connection string (session pooler on port 5432/6543 or direct connection on port 5432).
3. Copy `.env.example` to `.env` and fill in:
   - `SUPABASE_DATABASE_URL` — connection string with write access from Supabase
   - `ANTHROPIC_API_KEY` — only needed for the LLM fallback path
4. **Run locally**:
   ```bash
   # Automatically resolves previous month's reporting date
   python -m src.main --amc sbi

   # Or specify a particular month/year:
   python -m src.main --amc hdfc --year 2025 --month 1

   # Or run against a locally downloaded portfolio spreadsheet:
   python -m src.main --amc nippon_india --file "path/to/portfolio.xlsx"

   # Or override with a direct file URL:
   python -m src.main --amc icici_pru --url "https://.../portfolio.xlsx"
   ```
5. **For production**:
   GitHub Actions runs this on the 10th of every month across all 10 AMCs automatically (`.github/workflows/monthly_scrape.yml`). Add `SUPABASE_DATABASE_URL` and `ANTHROPIC_API_KEY` as **repo secrets** in GitHub.
3. Add an entry to `src/config.py`.
4. The LLM fallback in `llm_fallback.py` requires zero changes per AMC —
   it's format-agnostic by design.
