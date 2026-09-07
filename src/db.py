"""
Supabase Postgres connection + upsert logic. Mirrors the schema:

  funds(id, scheme_code, name, amc, fund_type, category, as_of_date, created_at)
  stocks(id, isin, name, sector)
  holdings(id, fund_id, stock_id, quantity, market_value_lacs, weight_pct)

All writes are upserts (ON CONFLICT DO NOTHING / DO UPDATE) so re-running
the agent for a month that's already loaded is safe.
"""
import os

import psycopg2
import psycopg2.extras


def get_connection():
    url = (
        os.getenv("SUPABASE_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or os.getenv("NEON_DATABASE_URL")
    )
    if not url:
        raise KeyError(
            "SUPABASE_DATABASE_URL (or DATABASE_URL) environment variable is required"
        )
    return psycopg2.connect(url)


def upsert_fund(cur, fund: dict) -> int:
    cur.execute(
        """
        INSERT INTO funds (scheme_code, name, amc, fund_type, category, as_of_date)
        VALUES (%(scheme_code)s, %(name)s, %(amc)s, %(fund_type)s, %(category)s, %(as_of_date)s)
        ON CONFLICT (amc, scheme_code, as_of_date)
        DO UPDATE SET name = EXCLUDED.name,
                      fund_type = EXCLUDED.fund_type,
                      category = EXCLUDED.category
        RETURNING id
        """,
        fund,
    )
    return cur.fetchone()[0]


def upsert_stocks(cur, stocks: dict):
    """stocks: dict isin -> (name, sector)"""
    rows = [(isin, name, sector) for isin, (name, sector) in stocks.items()]
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO stocks (isin, name, sector) VALUES %s
        ON CONFLICT (isin) DO UPDATE
          SET name   = EXCLUDED.name,
              sector = EXCLUDED.sector
        """,
        rows,
    )


def get_stock_id_map(cur, isins: list) -> dict:
    if not isins:
        return {}
    cur.execute("SELECT isin, id FROM stocks WHERE isin = ANY(%s)", (isins,))
    return dict(cur.fetchall())


def insert_holdings(cur, fund_id: int, fund_holdings: list, isin_to_stock_id: dict):
    """fund_holdings: list of (scheme_code, isin, qty, mv, weight_pct)"""
    rows = [
        (fund_id, isin_to_stock_id[isin], qty, mv, wt)
        for (_scheme_code, isin, qty, mv, wt) in fund_holdings
        if isin in isin_to_stock_id
    ]
    if not rows:
        return
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO holdings (fund_id, stock_id, quantity, market_value_lacs, weight_pct)
        VALUES %s
        ON CONFLICT (fund_id, stock_id) DO UPDATE
          SET quantity = EXCLUDED.quantity,
              market_value_lacs = EXCLUDED.market_value_lacs,
              weight_pct = EXCLUDED.weight_pct
        """,
        rows,
    )
