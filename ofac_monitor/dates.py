from __future__ import annotations

import re
from typing import Optional

_MONTHS = {
    "jan": "01",
    "january": "01",
    "feb": "02",
    "february": "02",
    "mar": "03",
    "march": "03",
    "apr": "04",
    "april": "04",
    "may": "05",
    "jun": "06",
    "june": "06",
    "jul": "07",
    "july": "07",
    "aug": "08",
    "august": "08",
    "sep": "09",
    "sept": "09",
    "september": "09",
    "oct": "10",
    "october": "10",
    "nov": "11",
    "november": "11",
    "dec": "12",
    "december": "12",
}

# 21 Mar 1966 / 21 March 1966
_FULL_RE = re.compile(
    r"^\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*$",
    re.I,
)
# Mar 1966 / March 1966
_MONTH_YEAR_RE = re.compile(
    r"^\s*([A-Za-z]+)\s+(\d{4})\s*$",
    re.I,
)
# 1966 / circa 1966 / c. 1966
_YEAR_RE = re.compile(
    r"^\s*(?:circa|c\.|approx\.?)?\s*(\d{4})\s*$",
    re.I,
)
# already ISO-ish: 1966-03-21 / 1966-00-00
_ISO_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")


def format_dob(value: str) -> str:
    """Normalize OFAC DOB text to YYYY-MM-DD; unknown month/day become 00."""
    raw = (value or "").strip()
    if not raw:
        return ""

    # Take first date token if multiple joined
    first = re.split(r"[;/]| and ", raw, maxsplit=1)[0].strip()

    m = _ISO_RE.match(first)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    m = _FULL_RE.match(first)
    if m:
        day = int(m.group(1))
        month = _MONTHS.get(m.group(2).lower())
        year = m.group(3)
        if month and 1 <= day <= 31:
            return f"{year}-{month}-{day:02d}"
        if month:
            return f"{year}-{month}-00"
        return f"{year}-00-00"

    m = _MONTH_YEAR_RE.match(first)
    if m:
        month = _MONTHS.get(m.group(1).lower())
        year = m.group(2)
        if month:
            return f"{year}-{month}-00"
        return f"{year}-00-00"

    m = _YEAR_RE.match(first)
    if m:
        return f"{m.group(1)}-00-00"

    # Fallback: extract a 4-digit year anywhere
    y = re.search(r"(19|20)\d{2}", first)
    if y:
        return f"{y.group(0)}-00-00"
    return raw


def address_matches_keywords(address: str, keywords: Optional[list] = None) -> bool:
    text = (address or "").lower()
    if not text:
        return False
    keys = keywords or ["china", "hong kong", "hongkong", "hong-kong"]
    normalized = text.replace("hong kong", "hongkong").replace("hong-kong", "hongkong")
    for key in keys:
        k = key.lower().replace("hong kong", "hongkong").replace("hong-kong", "hongkong")
        if k in normalized or k in text:
            return True
    return False