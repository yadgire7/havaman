"""HTTPS GET with certificate checks and a timeout. Nothing else is fetched."""
from __future__ import annotations

import urllib.error
import urllib.request

USER_AGENT = "havaman/0.1 (Shetkari Shala weather pages)"
TIMEOUT_S = 30


def urllib_fetch(url: str) -> tuple[int, bytes]:
    """GET over HTTPS. urllib verifies certificates by default."""
    if not url.startswith("https://"):
        raise ValueError("only https URLs are fetched")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()
