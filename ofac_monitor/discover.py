from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from typing import Any, Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .http_client import fetch_text


@dataclass
class Notice:
    url: str
    path: str
    title: str
    release_date: str  # e.g. October 09, 2026
    date_key: str  # YYYYMMDD from path when possible


_DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}"
)


def list_sanctions_updates(session, cfg: Dict[str, Any]) -> List[Notice]:
    ofac = cfg.get("ofac") or {}
    list_url = ofac["list_url"]
    base_url = ofac.get("base_url") or "https://ofac.treasury.gov"
    html = fetch_text(session, list_url, timeout=ofac.get("timeout_seconds", 60))
    soup = BeautifulSoup(html, "lxml")

    notices: List[Notice] = []
    seen = set()

    for row in soup.select(".search-result.views-row, .views-row"):
        link = row.select_one('a[href^="/recent-actions/"]')
        if not link:
            continue
        href = link.get("href") or ""
        if not re.fullmatch(r"/recent-actions/\d+", href):
            continue
        row_text = row.get_text(" ", strip=True)
        if "Sanctions List Updates" not in row_text:
            continue
        if href in seen:
            continue
        seen.add(href)

        title = unescape(link.get_text(" ", strip=True))
        date_match = _DATE_RE.search(row_text)
        release_date = date_match.group(0) if date_match else ""
        date_key = href.rsplit("/", 1)[-1]
        notices.append(
            Notice(
                url=urljoin(base_url, href),
                path=href,
                title=title,
                release_date=release_date,
                date_key=date_key,
            )
        )

    # 列表页通常已是新到旧；再按 date_key 稳定排序（新在前）
    notices.sort(key=lambda n: n.date_key, reverse=True)
    return notices