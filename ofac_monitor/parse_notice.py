from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape
from typing import Dict, List, Tuple

from bs4 import BeautifulSoup

from .http_client import fetch_text

SECTION_PATTERNS: List[Tuple[str, str, re.Pattern[str]]] = [
    (
        "add",
        "individual",
        re.compile(
            r"The following individuals? (?:has|have) been added to OFAC's SDN List\s*:",
            re.I,
        ),
    ),
    (
        "add",
        "entity",
        re.compile(
            r"The following (?:entity|entities) (?:has|have) been added to OFAC's SDN List\s*:",
            re.I,
        ),
    ),
    (
        "add",
        "vessel",
        re.compile(
            r"The following vessels? (?:has|have) been added to OFAC's SDN List\s*:",
            re.I,
        ),
    ),
    (
        "add",
        "aircraft",
        re.compile(
            r"The following aircraft (?:has|have) been added to OFAC's SDN List\s*:",
            re.I,
        ),
    ),
    (
        "delete",
        "unknown",
        re.compile(
            r"The following deletions? (?:has|have) been made to OFAC's SDN List\s*:",
            re.I,
        ),
    ),
    (
        "change",
        "unknown",
        re.compile(
            r"The following changes? (?:has|have) been made to OFAC's SDN List\s*:",
            re.I,
        ),
    ),
]

_FOOTER_CUT_RE = re.compile(
    r"\n\s*(?:Unrelated Administrative List Changes|Filter by Category|"
    r"Sign up for OFAC Recent Actions|Office of Terrorism and Financial Intelligence)\b",
    re.I,
)


@dataclass
class Record:
    change_type: str
    entity_type: str
    release_date: str
    name: str = ""
    aliases: str = ""
    dob: str = ""
    pob: str = ""
    nationality: str = ""
    gender: str = ""
    passport: str = ""
    national_id: str = ""
    other_ids: str = ""
    address: str = ""
    program: str = ""
    remarks: str = ""
    source_url: str = ""
    notice_title: str = ""
    raw_text: str = ""
    extra: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, str]:
        return {
            "change_type": self.change_type,
            "entity_type": self.entity_type,
            "release_date": self.release_date,
            "name": self.name,
            "aliases": self.aliases,
            "dob": self.dob,
            "pob": self.pob,
            "nationality": self.nationality,
            "gender": self.gender,
            "passport": self.passport,
            "national_id": self.national_id,
            "other_ids": self.other_ids,
            "address": self.address,
            "program": self.program,
            "remarks": self.remarks,
            "source_url": self.source_url,
            "notice_title": self.notice_title,
            "raw_text": self.raw_text,
        }


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Prefer the recent-action body field; fall back carefully to avoid nav chrome
    root = (
        soup.select_one(".field--name-field-body .field__item")
        or soup.select_one(".field--name-field-body")
        or soup.select_one("article .usa-prose")
        or soup.select_one("article")
        or soup.select_one("#block-ofac-content")
        or soup
    )
    text = root.get_text("\n")

    # Release Date often lives outside field-body; keep it if present in article
    article = soup.select_one("article")
    if article:
        date_m = re.search(
            r"Release Date\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})",
            article.get_text("\n"),
            re.I,
        )
        if date_m and "Release Date" not in text:
            text = f"Release Date\n{date_m.group(1)}\n\n{text}"

    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    cut = _FOOTER_CUT_RE.search(text)
    if cut:
        text = text[: cut.start()]
    return text.strip()


def extract_release_date(text: str) -> str:
    m = re.search(r"Release Date\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})", text, re.I)
    if m:
        return m.group(1)
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},\s+\d{4}",
        text,
    )
    return m.group(0) if m else ""


def _section_spans(text: str) -> List[Tuple[int, int, str, str]]:
    """Return (body_start, body_end, change_type, entity_type_hint)."""
    headers: List[Tuple[int, int, str, str]] = []
    for change_type, entity_type, pat in SECTION_PATTERNS:
        for m in pat.finditer(text):
            headers.append((m.start(), m.end(), change_type, entity_type))
    headers.sort(key=lambda x: x[0])

    spans: List[Tuple[int, int, str, str]] = []
    for i, (_, body_start, change_type, entity_type) in enumerate(headers):
        body_end = headers[i + 1][0] if i + 1 < len(headers) else len(text)
        spans.append((body_start, body_end, change_type, entity_type))
    return spans


_ENTRY_END_RE = re.compile(
    r"(?:\(individual\)|\(entity\)|\(vessel\)|\(aircraft\))"
    r"(?:\s*\[[^\]]+\])+"
    r"(?:\s*\(Linked To:[^)]+\))?"
    r"\."
    r"|"
    r"(?:\[[A-Z0-9][^\]]*\])+"
    r"(?:\s*\(Linked To:[^)]+\))?"
    r"\.",
    re.I,
)


def split_entries(body: str, change_type: str = "") -> List[str]:
    body = body.strip()
    if not body:
        return []

    # Change blocks: keep "old -to- new" as one record (do not split on program tags)
    if change_type == "change" and re.search(r"(?i)-to-", body):
        normalized = re.sub(r"\s*-to-\s*", " -to- ", body, flags=re.I)
        parts = [p.strip() for p in re.split(r"\n\s*\n+", normalized) if p.strip()]
        parts = [p for p in parts if not re.match(r"^The following ", p, re.I)]
        if not parts:
            return [normalized.strip()]
        merged: List[str] = []
        buf = ""
        for part in parts:
            if not buf:
                buf = part
            elif " -to- " in buf and not buf.strip().endswith("-to-"):
                merged.append(buf)
                buf = part
            else:
                buf = f"{buf} {part}"
        if buf:
            merged.append(buf)
        return merged

    # Prefer blank-line separated paragraphs (OFAC Drupal pages usually do this)
    paras = [p.strip() for p in re.split(r"\n\s*\n+", body) if p.strip()]
    paras = [p for p in paras if not re.match(r"^The following ", p, re.I)]
    if len(paras) > 1:
        return paras

    # Fallback: walk by entry-ending markers
    chunks: List[str] = []
    start = 0
    for m in _ENTRY_END_RE.finditer(body):
        end = m.end()
        piece = body[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end
    tail = body[start:].strip()
    if tail:
        chunks.append(tail)
    return chunks if chunks else [body]


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" ;,.")


def _clean_field_value(value: str) -> str:
    value = _clean(value)
    # Drop trailing type/program/linked-to noise that often sticks to last field
    value = re.sub(
        r"\s*\((?:individual|entity|vessel|aircraft)\).*$",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"\s*(?:\[[^\]]+\])+(?:\s*\(Linked To:[^)]+\))?\.?$",
        "",
        value,
    )
    value = re.sub(r"\s*\(Linked To:[^)]+\)\.?$", "", value, flags=re.I)
    return _clean(value)


def _field(text: str, label: str) -> str:
    pat = re.compile(
        rf"(?:^|;\s*){re.escape(label)}\s+([^;]+)",
        re.I,
    )
    m = pat.search(text)
    return _clean_field_value(m.group(1)) if m else ""


def _all_fields(text: str, label: str) -> List[str]:
    pat = re.compile(
        rf"(?:^|;\s*)(?:alt\.\s*)?{re.escape(label)}\s+([^;]+)",
        re.I,
    )
    return [_clean_field_value(m.group(1)) for m in pat.finditer(text)]


def infer_entity_type(raw: str, default: str) -> str:
    low = raw.lower()
    if "(individual)" in low:
        return "individual"
    if "(entity)" in low:
        return "entity"
    if "(vessel)" in low:
        return "vessel"
    if "(aircraft)" in low:
        return "aircraft"
    if default != "unknown":
        return default
    if re.search(r"\bDOB\b|\bGender\b|\bnationality\b", raw):
        return "individual"
    return "entity"


def parse_entry(
    raw: str,
    change_type: str,
    entity_type_hint: str,
    release_date: str,
    source_url: str,
    notice_title: str,
) -> Record:
    text = _clean(raw)
    remarks = ""
    if " -to- " in text:
        remarks = "变更前 -> 变更后（见原始文本）"
        after = text.split(" -to- ", 1)[1].strip()
        after = re.sub(r"^-\s*to-\s*", "", after, flags=re.I).strip()
        working = after
    else:
        working = text

    entity_type = infer_entity_type(working, entity_type_hint)

    programs = re.findall(r"\[([^\]]+)\]", working)
    program = "; ".join(dict.fromkeys(programs))

    # Strip trailing type/program/linked-to for name/address parsing
    core = re.sub(
        r"\s*\((?:individual|entity|vessel|aircraft)\)\s*(?:\[[^\]]+\])*\s*"
        r"(?:\(Linked To:[^)]+\))?\s*\.?$",
        "",
        working,
        flags=re.I,
    )
    core = re.sub(r"\s*(?:\[[^\]]+\])+\s*(?:\(Linked To:[^)]+\))?\s*\.?$", "", core)

    aliases_list = []
    for m in re.finditer(
        r"\((?:a\.k\.a\.|f\.k\.a\.|n\.k\.a\.)\s*([^)]+)\)",
        core,
        flags=re.I,
    ):
        inner = m.group(1)
        for part in re.split(r"\s*;\s*", inner):
            part = re.sub(r"^(?:a\.k\.a\.|f\.k\.a\.|n\.k\.a\.)\s*", "", part, flags=re.I)
            part = _clean(part)
            if part:
                aliases_list.append(part)
    aliases = "; ".join(dict.fromkeys(aliases_list))

    # Chinese/Arabic script annotations are not aliases for export primary fields
    core_no_aka = re.sub(
        r"\((?:a\.k\.a\.|f\.k\.a\.|n\.k\.a\.)\s*[^)]+\)",
        "",
        core,
        flags=re.I,
    )
    core_no_aka = re.sub(
        r"\((?:Chinese Simplified|Chinese Traditional|Arabic|Cyrillic)[^)]*\)",
        "",
        core_no_aka,
        flags=re.I,
    )
    core_no_aka = re.sub(r"\s+", " ", core_no_aka).strip()

    # Split name vs address: first comma-separated chunk is usually NAME; rest until first ';' is address
    name = ""
    address = ""
    if ";" in core_no_aka:
        head, _rest = core_no_aka.split(";", 1)
        parts = [p.strip() for p in head.split(",") if p.strip()]
        if parts:
            if entity_type == "individual" and len(parts) >= 2 and not re.search(r"\d", parts[1]) and len(parts[1].split()) <= 4:
                name = f"{parts[0]}, {parts[1]}"
                address = ", ".join(parts[2:])
            else:
                name = parts[0]
                address = ", ".join(parts[1:])
    else:
        name = core_no_aka
    name = re.sub(r"^\s*-to-\s*", "", name, flags=re.I)

    passports = _all_fields(working, "Passport")
    national_ids = _all_fields(working, "National ID No.")
    # also "National ID No" without period variants already covered

    other_id_labels = [
        "Identification Number",
        "Cedula No.",
        "Passport",
        "Driver's License No.",
        "Residency Number",
        "Registration Number",
        "Tax ID No.",
        "V.A.T. Number",
        "Business Registration Number",
        "Unified Social Credit Code (USCC)",
        "Legal Entity Number",
        "Chamber of Commerce Number",
        "Organization Established Date",
    ]
    other_bits = []
    for label in other_id_labels:
        if label.lower() == "passport":
            continue
        vals = _all_fields(working, label)
        for v in vals:
            other_bits.append(f"{label} {v}")

    linked = re.search(r"\(Linked To:\s*([^)]+)\)", working, re.I)
    if linked:
        remarks = (remarks + "; " if remarks else "") + f"Linked To: {_clean(linked.group(1))}"

    return Record(
        change_type=change_type,
        entity_type=entity_type,
        release_date=release_date,
        name=_clean(name),
        aliases=aliases,
        dob=_field(working, "DOB"),
        pob=_field(working, "POB"),
        nationality=_field(working, "nationality"),
        gender=_field(working, "Gender"),
        passport="; ".join(passports),
        national_id="; ".join(national_ids),
        other_ids="; ".join(other_bits),
        address=_clean(address),
        program=program,
        remarks=_clean(remarks),
        source_url=source_url,
        notice_title=notice_title,
        raw_text=text,
    )


def parse_notice_html(
    html: str,
    source_url: str,
    notice_title: str,
    release_date_fallback: str = "",
) -> List[Record]:
    text = html_to_text(html)
    release_date = extract_release_date(text) or release_date_fallback
    records: List[Record] = []

    spans = _section_spans(text)
    if not spans:
        return records

    for start, end, change_type, entity_type_hint in spans:
        body = text[start:end].strip()
        cut = _FOOTER_CUT_RE.search(body)
        if cut:
            body = body[: cut.start()].strip()
        body = re.split(r"\n\s*Press Release\b|\n\s*Recent Actions\b", body, maxsplit=1)[0]
        for entry in split_entries(body, change_type=change_type):
            if len(entry) < 8:
                continue
            if re.match(r"^The following ", entry, re.I):
                continue
            # Skip leftover nav/ui fragments
            if not re.search(
                r"(?:\b(?:DOB|POB|nationality|Passport|National ID|Registration Number|"
                r"Organization Established|Organization Type|V\.A\.T\.|Tax ID|Gender|"
                r"Business Registration|Unified Social Credit|Target Type)\b|"
                r"\[|\(individual\)|\(entity\)|\(vessel\)|\(aircraft\))",
                entry,
                re.I,
            ):
                continue
            records.append(
                parse_entry(
                    entry,
                    change_type=change_type,
                    entity_type_hint=entity_type_hint,
                    release_date=release_date,
                    source_url=source_url,
                    notice_title=notice_title,
                )
            )
    return records


def fetch_and_parse_notice(session, cfg, notice) -> List[Record]:
    ofac = cfg.get("ofac") or {}
    html = fetch_text(session, notice.url, timeout=ofac.get("timeout_seconds", 60))
    return parse_notice_html(
        html,
        source_url=notice.url,
        notice_title=notice.title,
        release_date_fallback=notice.release_date,
    )


def filter_records(records: List[Record], cfg) -> List[Record]:
    scope = cfg.get("scope") or {}
    entity_types = set(scope.get("entity_types") or [])
    change_types = set(scope.get("change_types") or [])
    out = []
    for r in records:
        if entity_types and r.entity_type not in entity_types:
            continue
        if change_types and r.change_type not in change_types:
            continue
        out.append(r)
    return out