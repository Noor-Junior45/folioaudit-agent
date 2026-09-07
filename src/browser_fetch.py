"""
Headless browser automation using Playwright to download monthly portfolio
disclosures from dynamic Single-Page Application (SPA) AMC portals.

Under SEBI regulations, Indian AMCs disclose their full scheme portfolio as
of the end of each calendar month by the 15th of the following month. Because
most AMC websites use Angular/React frontends with dropdown selectors and dynamic
download triggers, this module loads the portal in a headless browser, waits
for DOM hydration, interacts with selectors, and intercepts the file download.
"""
import os
import re
import sys
import time
from urllib.parse import urljoin


def _matches_period(text: str, tokens: dict | None) -> bool:
    """Check if text matches the target month/year."""
    if not tokens or not text:
        return True
    t_lower = text.lower()
    month = tokens.get("month", "").lower()
    mon = tokens.get("mon", "").lower()
    year = tokens.get("year", "")
    yy = tokens.get("yy", "")

    has_month = month in t_lower or mon in t_lower
    has_year = year in t_lower or yy in t_lower
    return has_month and has_year


def download_via_browser(
    amc_key: str,
    portal_url: str,
    dest_path: str,
    tokens: dict | None = None,
    timeout_sec: int = 60,
) -> str | None:
    """
    Launches headless Chromium, visits portal_url, interacts with the portal,
    and intercepts the downloaded file to dest_path.

    Returns dest_path on success, or None on failure.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        print(
            f"[{amc_key}] Playwright is not installed. Install via: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return None

    print(f"[{amc_key}] launching headless browser to scrape portal: {portal_url}")
    downloaded_files = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        # 1. Listen for browser download events
        def handle_download(download):
            try:
                print(f"[{amc_key}] intercepted browser download: {download.suggested_filename}")
                download.save_as(dest_path)
                downloaded_files.append(dest_path)
            except Exception as dl_err:
                print(f"[{amc_key}] error saving download: {dl_err}", file=sys.stderr)

        page.on("download", handle_download)

        # 2. Listen for direct network responses carrying excel or pdf files
        def handle_response(response):
            try:
                if downloaded_files or response.status != 200:
                    return
                ct = response.headers.get("content-type", "").lower()
                cd = response.headers.get("content-disposition", "").lower()
                r_url = response.url.lower()

                # Exclude ad/tracker networks
                if any(tracker in r_url for tracker in ["doubleclick", "googlead", "facebook", "analytics", "gtm"]):
                    return

                is_file = (
                    "spreadsheet" in ct
                    or "excel" in ct
                    or "pdf" in ct
                    or r_url.endswith(".xlsx")
                    or r_url.endswith(".xls")
                    or r_url.endswith(".pdf")
                    or "attachment" in cd
                )
                if is_file and "html" not in ct and "json" not in ct:
                    body = response.body()
                    if len(body) > 4096 and (body.startswith(b"PK\x03\x04") or body.startswith(b"%PDF") or body.startswith(b"\xd0\xcf\x11\xe0")):
                        print(f"[{amc_key}] intercepted binary file response from {response.url[:80]} ({len(body)} bytes)")
                        with open(dest_path, "wb") as f:
                            f.write(body)
                        downloaded_files.append(dest_path)
            except Exception:
                pass

        page.on("response", handle_response)

        try:
            # Navigate to the portal
            page.goto(portal_url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
            page.wait_for_timeout(4000)  # allow Angular/React SPA to hydrate

            # 3. Strategy A: Look for direct anchor tags with xlsx / xls / pdf
            anchors = page.query_selector_all("a[href]")
            target_href = None
            target_anchor = None
            best_score = -1

            for a in anchors:
                href = a.get_attribute("href") or ""
                text = (a.inner_text() or "").strip()
                title = a.get_attribute("title") or ""
                combined = f"{href} {text} {title}".lower()

                if any(ext in combined for ext in [".xlsx", ".xls", ".pdf"]):
                    score = 0
                    if ".xlsx" in combined or ".xls" in combined:
                        score += 3
                    elif ".pdf" in combined:
                        score += 2

                    if "monthly" in combined or "portfolio" in combined:
                        score += 2

                    if tokens:
                        m_name = tokens.get("month", "").lower()
                        y_val = tokens.get("year", "")
                        if m_name and m_name in combined:
                            score += 4
                        if y_val and y_val in combined:
                            score += 2

                    if score > best_score:
                        best_score = score
                        target_href = href
                        target_anchor = a

            if target_href and best_score >= 2:
                full_url = urljoin(portal_url, target_href)
                print(f"[{amc_key}] found matching disclosure link on portal: {full_url}")
                try:
                    # Attempt click to trigger download
                    with page.expect_download(timeout=12000):
                        target_anchor.click(force=True)
                except Exception:
                    # Fallback: direct browser context request
                    try:
                        resp = context.request.get(full_url)
                        if resp.status == 200 and len(resp.body()) > 4096:
                            with open(dest_path, "wb") as f:
                                f.write(resp.body())
                            downloaded_files.append(dest_path)
                    except Exception as req_err:
                        print(f"[{amc_key}] direct request to link failed: {req_err}", file=sys.stderr)

            # 4. Strategy B: Dynamic Dropdowns (Year / Month / Category)
            if not downloaded_files:
                selects = page.query_selector_all("select")
                for sel in selects:
                    options = sel.query_selector_all("option")
                    for opt in options:
                        opt_text = (opt.inner_text() or "").strip().lower()
                        opt_val = (opt.get_attribute("value") or "").strip().lower()
                        if tokens:
                            m_name = tokens.get("month", "").lower()
                            y_val = tokens.get("year", "")
                            if (m_name and m_name in opt_text) or (y_val and y_val in opt_text):
                                try:
                                    sel.select_option(value=opt.get_attribute("value"))
                                    page.wait_for_timeout(1000)
                                    break
                                except Exception:
                                    pass

                # Look for download or submit buttons
                buttons = page.query_selector_all("button, input[type='button'], input[type='submit'], a.btn, a.download")
                for btn in buttons:
                    btn_text = (btn.inner_text() or btn.get_attribute("value") or "").strip().lower()
                    if any(kw in btn_text for kw in ["download", "apply", "submit", "view portfolio", "generate"]):
                        try:
                            with page.expect_download(timeout=10000):
                                btn.click(force=True)
                            if downloaded_files:
                                break
                        except Exception:
                            pass

            # Wait a few extra seconds if a download is in progress
            start_wait = time.time()
            while not downloaded_files and time.time() - start_wait < 8:
                page.wait_for_timeout(1000)

        except PlaywrightTimeoutError:
            print(f"[{amc_key}] browser navigation timed out after {timeout_sec}s", file=sys.stderr)
        except Exception as e:
            print(f"[{amc_key}] browser scraping error: {e}", file=sys.stderr)
        finally:
            browser.close()

    if downloaded_files and os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
        print(f"[{amc_key}] successfully retrieved {os.path.getsize(dest_path)} bytes via browser automation")
        return dest_path

    print(f"[{amc_key}] browser automation could not locate an automatic download file on {portal_url}", file=sys.stderr)
    return None
