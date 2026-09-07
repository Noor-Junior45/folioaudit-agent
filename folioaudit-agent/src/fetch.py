"""Downloads an AMC's disclosure file to a local temp path."""
import requests


def download_file(url: str, dest_path: str, timeout: int = 60) -> str:
    """Downloads `url` to `dest_path`. Raises on non-200 responses."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(resp.content)
    return dest_path
