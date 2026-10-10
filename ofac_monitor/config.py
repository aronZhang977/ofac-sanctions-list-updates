from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"
DEFAULT_ENV_PATH = ROOT / ".env"


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env into os.environ (do not override existing)."""
    env_path = path or DEFAULT_ENV_PATH
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value

COLUMN_LABELS = {
    "change_type": "变更类型",
    "entity_type": "主体类型",
    "release_date": "发布日期",
    "name": "姓名/名称",
    "aliases": "别名",
    "dob": "生日",
    "pob": "出生地",
    "nationality": "国籍",
    "gender": "性别",
    "passport": "护照号",
    "national_id": "身份证号",
    "other_ids": "其他证件",
    "address": "地址",
    "program": "制裁项目",
    "remarks": "备注",
    "source_url": "来源链接",
    "notice_title": "公告标题",
    "raw_text": "原始文本",
}


def load_config(path: str | Path | None = None) -> Dict[str, Any]:
    load_dotenv()
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    cfg["_config_path"] = str(config_path.resolve())
    cfg["_root"] = str(ROOT)

    proxy = (cfg.get("ofac") or {}).get("proxy")
    if proxy:
        os.environ.setdefault("HTTP_PROXY", proxy)
        os.environ.setdefault("HTTPS_PROXY", proxy)

    return cfg


def resolve_path(cfg: Dict[str, Any], relative: str) -> Path:
    p = Path(relative)
    if p.is_absolute():
        return p
    return Path(cfg["_root"]) / p


def get_smtp_password(cfg: Dict[str, Any]) -> str:
    env_name = ((cfg.get("email") or {}).get("password_env") or "SMTP_PASSWORD").strip()
    return os.environ.get(env_name, "")


def enabled_columns(cfg: Dict[str, Any]) -> List[str]:
    cols = (cfg.get("excel") or {}).get("columns") or list(COLUMN_LABELS.keys())
    return [c for c in cols if c in COLUMN_LABELS]