"""Downloads an AMC's disclosure file to a local temp path and detects file type."""
import requests


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
        # Some AMC servers reject requests without a browser-like User-Agent
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
