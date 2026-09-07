-- Supabase PostgreSQL Schema for FolioAudit

-- Funds table: Stores metadata for mutual fund and ETF schemes as of each disclosure date
CREATE TABLE IF NOT EXISTS funds (
    id BIGSERIAL PRIMARY KEY,
    scheme_code TEXT NOT NULL,
    name TEXT NOT NULL,
    amc TEXT NOT NULL,
    fund_type TEXT,
    category TEXT,
    as_of_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_funds_amc_scheme_date UNIQUE (amc, scheme_code, as_of_date)
);

-- Stocks table: Stores unique stocks/securities identified by ISIN
CREATE TABLE IF NOT EXISTS stocks (
    id BIGSERIAL PRIMARY KEY,
    isin TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    sector TEXT
);

-- Holdings table: Stores individual portfolio stock holdings for each fund
CREATE TABLE IF NOT EXISTS holdings (
    id BIGSERIAL PRIMARY KEY,
    fund_id BIGINT NOT NULL REFERENCES funds(id) ON DELETE CASCADE,
    stock_id BIGINT NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
    quantity NUMERIC,
    market_value_lacs NUMERIC,
    weight_pct NUMERIC,
    CONSTRAINT uq_holdings_fund_stock UNIQUE (fund_id, stock_id)
);

-- Indexes for optimal lookup and overlap calculations
CREATE INDEX IF NOT EXISTS idx_funds_scheme_code ON funds(scheme_code);
CREATE INDEX IF NOT EXISTS idx_funds_amc ON funds(amc);
CREATE INDEX IF NOT EXISTS idx_funds_as_of_date ON funds(as_of_date);
CREATE INDEX IF NOT EXISTS idx_stocks_isin ON stocks(isin);
CREATE INDEX IF NOT EXISTS idx_holdings_fund_id ON holdings(fund_id);
CREATE INDEX IF NOT EXISTS idx_holdings_stock_id ON holdings(stock_id);

-- Enable Row Level Security (RLS)
ALTER TABLE funds ENABLE ROW LEVEL SECURITY;
ALTER TABLE stocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE holdings ENABLE ROW LEVEL SECURITY;

-- Allow public read access (for Repo 2 frontend using anon key)
CREATE POLICY "Allow public read access on funds" ON funds FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow public read access on stocks" ON stocks FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "Allow public read access on holdings" ON holdings FOR SELECT TO anon, authenticated USING (true);

-- Allow postgres / service_role write access for Repo 1 scraper
CREATE POLICY "Allow write access for postgres on funds" ON funds FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
CREATE POLICY "Allow write access for postgres on stocks" ON stocks FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);
CREATE POLICY "Allow write access for postgres on holdings" ON holdings FOR ALL TO postgres, service_role USING (true) WITH CHECK (true);

-- View for Repo 2 (Frontend)
-- Used when the frontend requests all funds with full stock holdings for comparison
CREATE OR REPLACE VIEW fund_holdings_view AS
SELECT 
    f.id,
    f.name,
    f.amc,
    f.category,
    f.fund_type,
    f.scheme_code,
    f.as_of_date,
    COALESCE(
        json_agg(
            json_build_object(
                'isin', s.isin,
                'name', s.name,
                'sector', s.sector,
                'weight', h.weight_pct
            ) ORDER BY h.weight_pct DESC
        ) FILTER (WHERE s.id IS NOT NULL),
        '[]'::json
    ) AS holdings
FROM funds f
LEFT JOIN holdings h ON f.id = h.fund_id
LEFT JOIN stocks s ON h.stock_id = s.id
GROUP BY f.id
ORDER BY f.name;
