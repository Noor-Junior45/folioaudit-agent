"""Downloads an AMC's disclosure file to a local temp path and detects file type."""
import os
import sys
import requests

from src import browser_fetch


# Magic byte signatures for file type detection
_MAGIC = {
    b"%PDF": "pdf",
    b"PK\x03\x04": "xlsx",          # ZIP container = modern Office (xlsx/xlsm)
    b"\xd0\xcf\x11\xe0": "xls",     # OLE2 compound doc = legacy Excel (.xls)
}


def detect_file_type(path: str) -> str:
    """
    Detect actual file type from magic bytes (ignores file extension).
    Returns: 'pdf', 'xlsx', 'xls', or 'unknown'.
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return "unknown"
    with open(path, "rb") as f:
        header = f.read(8)
    for magic, ftype in _MAGIC.items():
        if header[: len(magic)] == magic:
            return ftype
    return "unknown"


def download_file(url: str, dest_path: str, timeout: int = 60) -> str:
    """
    Downloads `url` to `dest_path`. Raises on non-200 responses.
    Returns dest_path for chaining.
    """
    headers = {
        # Standard browser-like User-Agent to avoid immediate bot blocks
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, timeout=timeout, headers=headers)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(resp.content)
    return dest_path


def download_with_fallback(
    amc_key: str,
    direct_url: str,
    portal_url: str,
    dest_path: str,
    tokens: dict | None = None,
    timeout: int = 60,
) -> str | None:
    """
    1. Attempts direct HTTP download from direct_url.
    2. If that fails (e.g. 404 or 403), launches Playwright headless Chromium
       to scrape and interact with portal_url to retrieve the disclosure file.
    Returns dest_path on success, or None on failure.
    """
    # 1. Try direct HTTP download
    try:
        print(f"[{amc_key}] attempting direct download: {direct_url}")
        download_file(direct_url, dest_path, timeout=timeout)
        ftype = detect_file_type(dest_path)
        if ftype in ("xlsx", "pdf", "xls") and os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
            print(f"[{amc_key}] direct download succeeded ({os.path.getsize(dest_path)} bytes, format: {ftype})")
            return dest_path
        else:
            print(f"[{amc_key}] direct download returned non-portfolio file (format: {ftype})")
            if os.path.exists(dest_path):
                os.remove(dest_path)
    except Exception as e:
        print(f"[{amc_key}] direct download failed: {e}")

    # 2. Fall back to Playwright headless browser automation
    if portal_url:
        print(f"[{amc_key}] falling back to headless browser automation on portal: {portal_url}")
        res = browser_fetch.download_via_browser(
            amc_key=amc_key,
            portal_url=portal_url,
            dest_path=dest_path,
            tokens=tokens,
            timeout_sec=timeout,
        )
        if res and os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
            return res

    return None
