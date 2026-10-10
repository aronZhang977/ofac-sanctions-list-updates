from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Set


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"processed_urls": [], "first_run_done": False}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("processed_urls", [])
    data.setdefault("first_run_done", False)
    return data


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def processed_set(state: Dict[str, Any]) -> Set[str]:
    return set(state.get("processed_urls") or [])


def mark_processed(state: Dict[str, Any], url: str) -> None:
    urls = state.setdefault("processed_urls", [])
    if url not in urls:
        urls.append(url)