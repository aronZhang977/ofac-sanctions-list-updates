from __future__ import annotations

from typing import Any, Dict, Optional

import requests


def build_session(cfg: Dict[str, Any]) -> requests.Session:
    ofac = cfg.get("ofac") or {}
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": ofac.get("user_agent") or "OFACMonitor/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    proxy = ofac.get("proxy")
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    return session


def fetch_text(session: requests.Session, url: str, timeout: Optional[int] = 60) -> str:
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text