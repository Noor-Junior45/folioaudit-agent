"""
AMC registry. Top 12 Indian Asset Management Companies by AUM.

Under SEBI regulations, each AMC discloses its full scheme portfolio as of
the end of each calendar month by the 15th of the following month.

`portal_url` is the verified official statutory download page.
`disclosure_url` supports template tokens (used as a best-effort direct link;
many AMCs use dynamic pages so the URL may need a manual override via --url):
  - {month}: full month name, e.g. "January"
  - {month_lower}: e.g. "january"
  - {month_upper}: e.g. "JANUARY"
  - {mon}: short 3-letter month, e.g. "Jan"
  - {mon_lower}: e.g. "jan"
  - {mon_upper}: e.g. "JAN"
  - {year}: 4-digit year, e.g. "2025"
  - {yy}: 2-digit year, e.g. "25"
  - {month_num}: 2-digit month number, e.g. "01"
"""
import calendar
from datetime import date

AMCS = {
    "nippon_india": {
        "display_name": "Nippon India Mutual Fund",
        "portal_url": "https://mf.nipponindiaim.com/investor-service/downloads/factsheet-portfolio-and-other-disclosures",
        "disclosure_url": "https://mf.nipponindiaim.com/InvestorServices/Downloads/NIMF-MONTHLY-PORTFOLIO-{month}-{year}.xls",
        "parser": "parse_nippon",
        "file_type": "xlsx",
    },
    "sbi": {
        "display_name": "SBI Mutual Fund",
        "portal_url": "https://www.sbimf.com/portfolios",
        "disclosure_url": "https://www.sbimf.com/en-us/downloads/portfolio-disclosures/monthly-portfolio-{month}-{year}.xlsx",
        "parser": "parse_nippon",
        "file_type": "xlsx",
    },
    "icici_pru": {
        "display_name": "ICICI Prudential Mutual Fund",
        "portal_url": "https://www.icicipruamc.com/news-and-media/downloads?currentTabFilter=OtherSchemeDisclosures&&subCatTabFilter=Monthly%20Portfolio%20Disclosures",
        "disclosure_url": "https://www.icicipruamc.com/docs/default-source/monthly-portfolio/monthly-portfolio-{month}-{year}.xlsx",
        "parser": "parse_nippon",
        "file_type": "xlsx",
    },
    "hdfc": {
        "display_name": "HDFC Mutual Fund",
        "portal_url": "https://www.hdfcfund.com/statutory-disclosure/portfolio/monthly-portfolio",
        "disclosure_url": "https://files.hdfcfund.com/s3fs-public/statutory-disclosures/monthly-portfolio-{month}-{year}.xlsx",
        "parser": "parse_nippon",
        "file_type": "xlsx",
    },
    "kotak": {
        "display_name": "Kotak Mahindra Mutual Fund",
        "portal_url": "https://www.kotakmf.com/Information/portfolios",
        "disclosure_url": "https://www.kotakmf.com/statutory-disclosure/monthly-portfolio-{month}-{year}.xlsx",
        "parser": "parse_nippon",
        "file_type": "xlsx",
    },
    "aditya_birla": {
        "display_name": "Aditya Birla Sun Life Mutual Fund",
        "portal_url": "https://mutualfund.adityabirlacapital.com/forms-and-downloads/portfolio",
        "disclosure_url": "https://mutualfund.adityabirlacapital.com/downloads/monthly-portfolio-{month}-{year}.xlsx",
        "parser": "parse_nippon",
        "file_type": "xlsx",
    },
    "uti": {
        "display_name": "UTI Mutual Fund",
        "portal_url": "https://www.utimf.com/downloads/consolidate-all-portfolio-disclosure",
        "disclosure_url": "https://www.utimf.com/downloads/monthly-portfolio-{month}-{year}.xlsx",
        "parser": "parse_nippon",
        "file_type": "xlsx",
    },
    "axis": {
        "display_name": "Axis Mutual Fund",
        "portal_url": "https://www.axismf.com/statutory-disclosures",
        "disclosure_url": "https://www.axismf.com/statutory-disclosures/monthly-portfolio-{month}-{year}.xlsx",
        "parser": "parse_nippon",
        "file_type": "xlsx",
    },
    "mirae_asset": {
        "display_name": "Mirae Asset Mutual Fund",
        "portal_url": "https://www.miraeassetmf.co.in/downloads/portfolio",
        "disclosure_url": "https://www.miraeassetmf.co.in/downloads/monthly-portfolio-{month}-{year}.xlsx",
        "parser": "parse_nippon",
        "file_type": "xlsx",
    },
    "dsp": {
        "display_name": "DSP Mutual Fund",
        "portal_url": "https://www.dspim.com/mandatory-disclosures/portfolio-disclosures",
        "disclosure_url": "https://www.dspim.com/mandatory-disclosures/monthly-portfolio-{month}-{year}.xlsx",
        "parser": "parse_nippon",
        "file_type": "xlsx",
    },
    "whiteoak": {
        "display_name": "WhiteOak Capital Mutual Fund",
        "portal_url": "https://mf.whiteoakamc.com/regulatory-disclosures/scheme-portfolios",
        "disclosure_url": "https://mf.whiteoakamc.com/downloads/monthly-portfolio-{month}-{year}.xlsx",
        "parser": "parse_nippon",
        "file_type": "xlsx",
    },
    "motilal_oswal": {
        "display_name": "Motilal Oswal Mutual Fund & ETF",
        "portal_url": "https://www.motilaloswalmf.com/downloads/scheme-portfolio-details",
        "disclosure_url": "https://www.motilaloswalmf.com/downloads/monthly-portfolio-{month}-{year}.xlsx",
        "parser": "parse_nippon",
        "file_type": "xlsx",
    },
}


def get_reporting_period(year: int = None, month: int = None):
    """
    Computes the reporting period (SEBI portfolios are published for the previous calendar month).
    Returns dict with tokens for URL formatting.
    """
    today = date.today()
    if year is None or month is None:
        # Default to previous month
        if today.month == 1:
            r_year = today.year - 1
            r_month = 12
        else:
            r_year = today.year
            r_month = today.month - 1
    else:
        r_year = int(year)
        r_month = int(month)

    month_name = calendar.month_name[r_month]
    short_month = calendar.month_abbr[r_month]

    return {
        "year": str(r_year),
        "yy": f"{r_year % 100:02d}",
        "month": month_name,
        "month_lower": month_name.lower(),
        "month_upper": month_name.upper(),
        "mon": short_month,
        "mon_lower": short_month.lower(),
        "mon_upper": short_month.upper(),
        "month_num": f"{r_month:02d}",
        "int_year": r_year,
        "int_month": r_month,
    }


def resolve_disclosure_url(amc_key: str, year: int = None, month: int = None) -> str:
    """Substitutes reporting period placeholders in the AMC's disclosure URL."""
    cfg = AMCS[amc_key]
    tokens = get_reporting_period(year=year, month=month)
    return cfg["disclosure_url"].format(**tokens)
