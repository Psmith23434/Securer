"""
Lightweight update checker.
Hosted version file: a simple JSON at a static URL (GitHub Pages, Gumroad, etc.)

Expected JSON format:
{
  "snippet_tool": {"latest": "1.2.0", "download_url": "https://..."}
}
"""
import urllib.request
import json
from typing import Optional

# Replace with your hosted versions endpoint
VERSIONS_URL = "https://raw.githubusercontent.com/Psmith23434/Securer/main/versions.json"
TIMEOUT = 3  # seconds — never block the UI


def check_for_update(app_name: str, current_version: str) -> Optional[dict]:
    """
    Returns None if no update or network error.
    Returns {"latest": str, "download_url": str} if an update is available.
    """
    try:
        with urllib.request.urlopen(VERSIONS_URL, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        app_data = data.get(app_name)
        if not app_data:
            return None
        latest = app_data.get("latest", "")
        if _version_tuple(latest) > _version_tuple(current_version):
            return {
                "latest": latest,
                "download_url": app_data.get("download_url", ""),
                "release_notes": app_data.get("release_notes", ""),
            }
    except Exception:
        pass  # Silent fail — update check must never crash the app
    return None


def _version_tuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)
