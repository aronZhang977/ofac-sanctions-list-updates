#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量交互式配置助手：用对话方式完成 config.yaml / .env 配置。"""
from __future__ import annotations

import copy
import getpass
import re
import smtplib
import ssl
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
ENV_PATH = ROOT / ".env"

EMAIL_PRESETS = {
    "1": ("QQ 邮箱", "smtp.qq.com", 587, True),
    "2": ("163 邮箱", "smtp.163.com", 587, True),
    "3": ("Gmail", "smtp.gmail.com", 587, True),
    "4": ("Outlook / Office365", "smtp.office365.com", 587, True),
    "5": ("自定义 / 企业邮", "", 587, True),
}

ENTITY_CHOICES = [
    ("1", "individual", "个人"),
    ("2", "entity", "实体"),
    ("3", "vessel", "船舶"),
    ("4", "aircraft", "航空器"),
    ("5", "unknown", "未知类型"),
]

CHANGE_CHOICES = [
    ("1", "add", "新增"),
    ("2", "change", "变更"),
    ("3", "delete", "删除"),
]

COLUMN_CHOICES = [
    ("1", "change_type", "变更类型"),
    ("2", "entity_type", "主体类型"),
    ("3", "release_date", "发布日期"),
    ("4", "name", "姓名/名称"),
    ("5", "aliases", "别名"),
    ("6", "dob", "生日"),
    ("7", "pob", "出生地"),
    ("8", "nationality", "国籍"),
    ("9", "gender", "性别"),
    ("10", "passport", "护照号"),
    ("11", "national_id", "身份证号"),
    ("12", "other_ids", "其他证件"),
    ("13", "address", "地址"),
    ("14", "program", "制裁项目"),
    ("15", "remarks", "备注"),
    ("16", "source_url", "来源链接"),
    ("17", "notice_title", "公告标题"),
]

DEFAULT_COLUMNS = [c[1] for c in COLUMN_CHOICES]

HIGHLIGHT_PRESETS = {
    "1": ("浅黄（推荐）", "FFF2CC"),
    "2": ("浅绿", "C6EFCE"),
    "3": ("浅橙", "FCE4D6"),
    "4": ("自定义", ""),
}

TZ_PRESETS = {
    "1": "Asia/Shanghai",
    "2": "UTC",
    "3": "America/New_York",
    "4": "Europe/London",
    "5": "自定义",
}


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_get(cfg: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = cfg
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _default_hint(default: str) -> str:
    """统一默认值提示：标明默认，并说明回车即确认。"""
    return f"[默认 {default}，回车确认]"


def _ask(prompt: str, default: Optional[str] = None, required: bool = True) -> str:
    if default is not None and str(default) != "":
        line = f"{prompt} {_default_hint(default)}: "
    elif default == "":
        # 允许空默认（回车得到空字符串），但仍提示可回车跳过
        line = f"{prompt} [可回车跳过]: "
    else:
        line = f"{prompt}: "
    while True:
        try:
            raw = input(line).strip()
        except EOFError:
            print("\n已取消。")
            sys.exit(1)
        if not raw and default is not None:
            return str(default)
        if raw or not required:
            return raw
        print("  （必填，请重新输入；有默认时可直接回车）")


def _ask_yes(prompt: str, default: bool = True) -> bool:
    label = "是" if default else "否"
    hint = "Y/n" if default else "y/N"
    while True:
        try:
            raw = input(f"{prompt} {_default_hint(label)} ({hint}): ").strip()
        except EOFError:
            print("\n已取消。")
            sys.exit(1)
        if not raw:
            return default
        low = raw.lower()
        if low in {"y", "yes", "是", "1", "true"}:
            return True
        if low in {"n", "no", "否", "0", "false"}:
            return False
        print("  请输入 y/n，或直接回车确认默认。")


def _ask_int(prompt: str, default: int, minimum: Optional[int] = None) -> int:
    while True:
        raw = _ask(prompt, default=str(default))
        try:
            value = int(raw)
        except ValueError:
            print("  请输入整数，或直接回车确认默认。")
            continue
        if minimum is not None and value < minimum:
            print(f"  不能小于 {minimum}。")
            continue
        return value


def _ask_password(prompt: str) -> str:
    while True:
        try:
            value = getpass.getpass(f"{prompt}: ")
        except EOFError:
            print("\n已取消。")
            sys.exit(1)
        if value:
            confirm = getpass.getpass("请再输入一次确认: ")
            if value == confirm:
                return value
            print("  两次输入不一致，请重试。")
        else:
            print("  （必填，请重新输入）")


def _parse_list(raw: str) -> List[str]:
    parts = re.split(r"[,;，；\s]+", raw.strip())
    return [p for p in parts if p]


def _print_options(
    options: Sequence[Tuple[str, str]],
    default_key: str,
) -> None:
    """打印带「← 默认」标记的选项列表。"""
    for key, label in options:
        mark = "  ← 默认" if key == default_key else ""
        print(f"  {key}. {label}{mark}")


def _ask_choice(
    prompt: str,
    options: Sequence[Tuple[str, str]],
    default_key: str,
) -> str:
    _print_options(options, default_key)
    while True:
        raw = _ask(prompt, default=default_key)
        if raw in {k for k, _ in options}:
            return raw
        print(f"  无效选项，请输入所列序号，或直接回车确认默认 {default_key}。")


def _ask_multi(
    title: str,
    choices: Sequence[Tuple[str, str, str]],
    selected: Sequence[str],
) -> List[str]:
    default_keys = [k for k, v, _ in choices if v in selected]
    default_text = ",".join(default_keys) if default_keys else ""
    print(f"\n{title}")
    print(f"  输入序号，多个用逗号分隔；直接回车确认默认: {default_text or '（当前为空）'}")
    for key, value, label in choices:
        mark = "✓" if value in selected else " "
        print(f"  [{mark}] {key}. {label} ({value})")
    raw = _ask("请选择", default=default_text, required=False)
    if not raw:
        return list(selected)
    picked: List[str] = []
    lookup = {k: v for k, v, _ in choices}
    for token in _parse_list(raw):
        if token in lookup:
            val = lookup[token]
            if val not in picked:
                picked.append(val)
        else:
            print(f"  忽略无效选项: {token}")
    if not picked:
        print("  未选到有效项，保留默认选择。")
        return list(selected)
    return picked


def _upsert_env(path: Path, key: str, value: str) -> None:
    lines: List[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    out: List[str] = []
    found = False
    for line in lines:
        if line.startswith(f"{key}=") or line.startswith(f"export {key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append("# OFAC Monitor 邮件密码（由 scripts/setup_config.py 写入）")
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _test_smtp(email_cfg: Dict[str, Any], password: str) -> None:
    host = email_cfg["smtp_host"]
    port = int(email_cfg.get("smtp_port") or 587)
    username = email_cfg.get("username") or email_cfg.get("from_addr")
    use_tls = bool(email_cfg.get("use_tls", True))
    print(f"\n正在测试连接 {host}:{port} ...")
    try:
        if use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(username, password)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.login(username, password)
        print("SMTP 登录成功。")
    except Exception as exc:
        print(f"SMTP 测试失败: {exc}")
        print("配置已保存；请核对服务器、端口、授权码后重试。")


def _default_cfg() -> Dict[str, Any]:
    return {
        "schedule": {"interval_minutes": 60, "timezone": "Asia/Shanghai"},
        "ofac": {
            "list_url": "https://ofac.treasury.gov/recent-actions/sanctions-list-updates",
            "base_url": "https://ofac.treasury.gov",
            "user_agent": "OFACMonitor/1.0 (+local compliance check; contact=ops@example.com)",
            "timeout_seconds": 60,
            "proxy": None,
        },
        "scope": {
            "entity_types": ["individual", "entity", "vessel", "aircraft", "unknown"],
            "change_types": ["add", "change", "delete"],
        },
        "excel": {
            "output_dir": "output",
            "overwrite_by_date": True,
            "max_files": 30,
            "keep_days": 0,
            "highlight_china_hk": {
                "enabled": True,
                "keywords": ["china", "hong kong", "hongkong", "hong-kong"],
                "fill_color": "FFF2CC",
            },
            "columns": list(DEFAULT_COLUMNS),
        },
        "email": {
            "enabled": False,
            "smtp_host": "",
            "smtp_port": 587,
            "use_tls": True,
            "username": "",
            "password_env": "SMTP_PASSWORD",
            "from_addr": "",
            "to": [""],
            "subject_template": "OFAC 制裁名单更新 {date}（{count} 条）",
            "body_template": (
                "OFAC Sanctions List Updates 有新变动。\n\n"
                "发布日期: {date}\n"
                "标题: {title}\n"
                "记录数: {count}\n"
                "来源: {source_url}\n\n"
                "Excel 见附件。\n"
            ),
        },
        "paths": {"state_file": "data/state.json"},
        "runtime": {
            "mode": "once",
            "process_existing_on_first_run": False,
            "max_notices_per_run": 0,
        },
    }


def _merge_cfg(base: Dict[str, Any], loaded: Dict[str, Any]) -> Dict[str, Any]:
    cfg = copy.deepcopy(base)
    for section, value in loaded.items():
        if section.startswith("_"):
            continue
        if isinstance(value, dict) and isinstance(cfg.get(section), dict):
            merged = dict(cfg[section])
            for k, v in value.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    nested = dict(merged[k])
                    nested.update(v)
                    merged[k] = nested
                else:
                    merged[k] = v
            cfg[section] = merged
        else:
            cfg[section] = value
    return cfg


def _print_summary(cfg: Dict[str, Any]) -> None:
    email = cfg.get("email") or {}
    excel = cfg.get("excel") or {}
    hl = excel.get("highlight_china_hk") or {}
    scope = cfg.get("scope") or {}
    schedule = cfg.get("schedule") or {}
    ofac = cfg.get("ofac") or {}
    runtime = cfg.get("runtime") or {}
    print("\n------ 当前配置摘要 ------")
    print(f"  检查间隔     : {schedule.get('interval_minutes')} 分钟 / {schedule.get('timezone')}")
    print(f"  代理         : {ofac.get('proxy') or '未使用'}")
    print(f"  主体类型     : {', '.join(scope.get('entity_types') or [])}")
    print(f"  变更类型     : {', '.join(scope.get('change_types') or [])}")
    print(f"  Excel 目录   : {excel.get('output_dir')}  保留 {excel.get('max_files')} 个")
    print(f"  中港高亮     : {'开' if hl.get('enabled') else '关'}  色 {hl.get('fill_color')}")
    print(f"  邮件         : {'启用' if email.get('enabled') else '关闭'}")
    if email.get("enabled"):
        print(f"  SMTP         : {email.get('smtp_host')}:{email.get('smtp_port')}")
        print(f"  发件人       : {email.get('from_addr')}")
        tos = [t for t in (email.get("to") or []) if str(t).strip()]
        print(f"  收件人       : {', '.join(tos) if tos else '（空）'}")
    print(f"  首次策略     : {'处理历史' if runtime.get('process_existing_on_first_run') else '仅建基线'}")
    print(f"  运行模式     : {runtime.get('mode')}")
    print("--------------------------")


def configure_schedule(cfg: Dict[str, Any]) -> None:
    print("\n【1/6】检查频率")
    print("  有默认值的项可直接回车确认；服务器上更推荐 cron / 计划任务调用 --once。")
    schedule = cfg.setdefault("schedule", {})
    schedule["interval_minutes"] = _ask_int(
        "检查间隔（分钟，用于 --loop）",
        default=int(schedule.get("interval_minutes") or 60),
        minimum=1,
    )
    current_tz = schedule.get("timezone") or "Asia/Shanghai"
    tz_default = "1"
    for key, tz in TZ_PRESETS.items():
        if tz == current_tz:
            tz_default = key
            break
    else:
        tz_default = "5"
    print("\n时区预设：")
    choice = _ask_choice(
        "请选择时区序号",
        [(k, v) for k, v in TZ_PRESETS.items()],
        default_key=tz_default,
    )
    if choice == "5" or TZ_PRESETS.get(choice) == "自定义":
        schedule["timezone"] = _ask("请输入时区（如 Asia/Shanghai）", default=current_tz)
    else:
        schedule["timezone"] = TZ_PRESETS[choice]


def configure_network(cfg: Dict[str, Any]) -> None:
    print("\n【2/6】网络与代理")
    ofac = cfg.setdefault("ofac", {})
    ofac["timeout_seconds"] = _ask_int(
        "请求超时（秒）",
        default=int(ofac.get("timeout_seconds") or 60),
        minimum=5,
    )
    use_proxy = _ask_yes(
        "是否使用 HTTP 代理访问 OFAC？（国内网络常需要）",
        default=bool(ofac.get("proxy")),
    )
    if use_proxy:
        ofac["proxy"] = _ask(
            "代理地址（如 http://127.0.0.1:7890）",
            default=ofac.get("proxy") or "http://127.0.0.1:7890",
            required=True,
        )
    else:
        ofac["proxy"] = None

    if _ask_yes("是否修改 User-Agent 联系邮箱？（一般可跳过）", default=False):
        ua = ofac.get("user_agent") or ""
        contact = _ask("联系邮箱（写入 User-Agent）", default="ops@example.com")
        ofac["user_agent"] = (
            f"OFACMonitor/1.0 (+local compliance check; contact={contact})"
            if "OFACMonitor" in ua or not ua
            else ua
        )


def configure_scope(cfg: Dict[str, Any]) -> None:
    print("\n【3/6】监控范围")
    scope = cfg.setdefault("scope", {})
    scope["entity_types"] = _ask_multi(
        "选择要监控的主体类型",
        ENTITY_CHOICES,
        scope.get("entity_types") or ["individual", "entity"],
    )
    scope["change_types"] = _ask_multi(
        "选择要监控的变更类型",
        CHANGE_CHOICES,
        scope.get("change_types") or ["add", "change", "delete"],
    )


def configure_excel(cfg: Dict[str, Any]) -> None:
    print("\n【4/6】Excel 导出")
    excel = cfg.setdefault("excel", {})
    excel["output_dir"] = _ask(
        "输出目录（相对项目根目录）",
        default=excel.get("output_dir") or "output",
    )
    excel["overwrite_by_date"] = _ask_yes(
        "同一天公告是否覆盖写入？（推荐是，避免文件堆积）",
        default=bool(excel.get("overwrite_by_date", True)),
    )
    excel["max_files"] = _ask_int(
        "最多保留多少个 Excel 文件",
        default=int(excel.get("max_files") or 30),
        minimum=1,
    )
    excel["keep_days"] = _ask_int(
        "按天保留（0=不按天删，仅按文件数）",
        default=int(excel.get("keep_days") or 0),
        minimum=0,
    )

    hl = excel.setdefault("highlight_china_hk", {})
    hl["enabled"] = _ask_yes(
        "地址/国籍/出生地含 China、Hong Kong 时是否整行高亮？",
        default=bool(hl.get("enabled", True)),
    )
    if hl["enabled"]:
        current_color = (hl.get("fill_color") or "FFF2CC").lstrip("#").upper()
        color_default = "1"
        for key, (_, color) in HIGHLIGHT_PRESETS.items():
            if color and color.upper() == current_color:
                color_default = key
                break
        else:
            if current_color and current_color != "FFF2CC":
                color_default = "4"
        print("\n高亮颜色：")
        choice = _ask_choice(
            "请选择颜色",
            [
                (k, f"{name} → {color}" if color else name)
                for k, (name, color) in HIGHLIGHT_PRESETS.items()
            ],
            default_key=color_default,
        )
        preset = HIGHLIGHT_PRESETS.get(choice, HIGHLIGHT_PRESETS["1"])
        if choice == "4" or not preset[1]:
            color = _ask(
                "请输入 Excel 十六进制颜色（不带 #）",
                default=current_color or "FFF2CC",
            ).lstrip("#").upper()
            hl["fill_color"] = color
        else:
            hl["fill_color"] = preset[1]
        if _ask_yes("是否自定义高亮关键词？（通常用默认 China / Hong Kong）", default=False):
            kw_default = ", ".join(
                hl.get("keywords") or ["china", "hong kong", "hongkong", "hong-kong"]
            )
            raw = _ask("关键词（逗号分隔）", default=kw_default)
            words = [w.lower() for w in _parse_list(raw)]
            if words:
                hl["keywords"] = words
        else:
            hl.setdefault(
                "keywords",
                ["china", "hong kong", "hongkong", "hong-kong"],
            )

    if _ask_yes("是否调整 Excel 列？（通常直接回车保留默认列）", default=False):
        excel["columns"] = _ask_multi(
            "选择要导出的列（顺序按你输入的序号）",
            COLUMN_CHOICES,
            excel.get("columns") or DEFAULT_COLUMNS,
        )
    else:
        excel.setdefault("columns", list(DEFAULT_COLUMNS))


def configure_email(cfg: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """返回 (password_env, password) 若需写入 .env，否则 None。"""
    print("\n【5/6】邮件通知（可选）")
    email = cfg.setdefault("email", {})
    enabled = _ask_yes("是否启用邮件发送？", default=bool(email.get("enabled")))
    email["enabled"] = enabled
    if not enabled:
        print("  已关闭邮件；仍会正常生成 Excel。")
        return None

    old_host = (email.get("smtp_host") or "").strip()
    email_default = "5"
    for key, (_, host, _, _) in EMAIL_PRESETS.items():
        if host and host == old_host:
            email_default = key
            break
    print("\n请选择邮箱类型：")
    choice = _ask_choice(
        "请输入序号",
        [
            (k, f"{name} → {host}:{port}" if host else name)
            for k, (name, host, port, _) in EMAIL_PRESETS.items()
        ],
        default_key=email_default,
    )
    preset = EMAIL_PRESETS.get(choice, EMAIL_PRESETS["5"])
    _, preset_host, preset_port, preset_tls = preset

    host_default = preset_host or old_host
    email["smtp_host"] = _ask(
        "SMTP 服务器",
        default=host_default,
        required=True,
    )
    email["smtp_port"] = _ask_int(
        "SMTP 端口（常见 587 或 465）",
        default=int(email.get("smtp_port") or preset_port),
        minimum=1,
    )
    email["use_tls"] = _ask_yes(
        "是否启用 STARTTLS？（587 一般选是）",
        default=bool(email.get("use_tls", preset_tls)),
    )
    user_default = email.get("username") or ""
    email["username"] = _ask(
        "登录用户名（通常是完整邮箱）",
        default=user_default if user_default else None,
        required=True,
    )
    from_default = email.get("from_addr") or email["username"]
    email["from_addr"] = _ask(
        "发件人 From",
        default=from_default,
        required=True,
    )
    old_to = [x for x in (email.get("to") or []) if str(x).strip()]
    to_raw = _ask(
        "收件人（多个用逗号分隔）",
        default=",".join(old_to) if old_to else None,
        required=True,
    )
    recipients = _parse_list(to_raw)
    if not recipients:
        print("  收件人为空，已关闭邮件。")
        email["enabled"] = False
        return None
    email["to"] = recipients

    password_env = _ask(
        "密码环境变量名",
        default=email.get("password_env") or "SMTP_PASSWORD",
    ).strip()
    email["password_env"] = password_env

    print("\nSMTP 密码或授权码（输入不回显；此项无默认，必须填写）")
    print("  提示: QQ/163/Gmail 等通常需要「授权码」，不是网页登录密码。")
    password = _ask_password("请输入密码/授权码")

    if not _ask_yes("是否保留当前邮件主题模板？", default=True):
        email["subject_template"] = _ask(
            "主题模板（可用 {date} {count} {title} {source_url}）",
            default=email.get("subject_template")
            or "OFAC 制裁名单更新 {date}（{count} 条）",
        )
    else:
        email.setdefault(
            "subject_template",
            "OFAC 制裁名单更新 {date}（{count} 条）",
        )
    email.setdefault(
        "body_template",
        (
            "OFAC Sanctions List Updates 有新变动。\n\n"
            "发布日期: {date}\n"
            "标题: {title}\n"
            "记录数: {count}\n"
            "来源: {source_url}\n\n"
            "Excel 见附件。\n"
        ),
    )
    return password_env, password


def configure_runtime(cfg: Dict[str, Any]) -> None:
    print("\n【6/6】首次运行与模式")
    runtime = cfg.setdefault("runtime", {})
    first_default = "2" if runtime.get("process_existing_on_first_run") else "1"
    print("\n首次运行策略：")
    first = _ask_choice(
        "请选择",
        [
            ("1", "仅建立基线（推荐，不处理历史公告、不刷屏）"),
            ("2", "处理列表里尚未记录的公告"),
        ],
        default_key=first_default,
    )
    runtime["process_existing_on_first_run"] = first.strip() == "2"

    mode_default = "2" if runtime.get("mode") == "loop" else "1"
    print("\n运行模式（可被命令行 --once / --loop 覆盖）：")
    mode = _ask_choice(
        "请选择",
        [
            ("1", "once — 跑一轮就退出（推荐给 cron / 计划任务）"),
            ("2", "loop — 按间隔循环"),
        ],
        default_key=mode_default,
    )
    runtime["mode"] = "loop" if mode.strip() == "2" else "once"

    runtime["max_notices_per_run"] = _ask_int(
        "每轮最多处理多少条公告（0=不限制）",
        default=int(runtime.get("max_notices_per_run") or 0),
        minimum=0,
    )
    paths = cfg.setdefault("paths", {})
    paths.setdefault("state_file", "data/state.json")


def _yaml_list(items: Sequence[str], indent: int = 4) -> str:
    pad = " " * indent
    if not items:
        return f"{pad}[]\n"
    return "".join(f"{pad}- {item}\n" for item in items)


def _escape_double(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def render_config(cfg: Dict[str, Any]) -> str:
    schedule = cfg["schedule"]
    ofac = cfg["ofac"]
    scope = cfg["scope"]
    excel = cfg["excel"]
    hl = excel.get("highlight_china_hk") or {}
    email = cfg["email"]
    paths = cfg.get("paths") or {"state_file": "data/state.json"}
    runtime = cfg["runtime"]

    proxy = ofac.get("proxy")
    proxy_line = "null" if not proxy else f'"{proxy}"'
    keywords = hl.get("keywords") or ["china", "hong kong", "hongkong", "hong-kong"]
    to_list = [t for t in (email.get("to") or []) if str(t).strip()] or [""]
    body = (email.get("body_template") or "").rstrip("\n") + "\n"
    body_indented = "\n".join(
        ("    " + line if line else "") for line in body.splitlines()
    )

    return f"""# OFAC Sanctions List Updates 监控配置
# 由 scripts/setup_config.py 生成/更新

schedule:
  # 检查间隔（分钟）。本机可用: python main.py --loop
  # 迁到服务器后也可用 cron，例如每小时: 0 * * * * cd /path && python main.py
  interval_minutes: {int(schedule.get("interval_minutes") or 60)}
  timezone: {schedule.get("timezone") or "Asia/Shanghai"}

ofac:
  list_url: "https://ofac.treasury.gov/recent-actions/sanctions-list-updates"
  base_url: "https://ofac.treasury.gov"
  user_agent: "{_escape_double(ofac.get("user_agent") or "OFACMonitor/1.0 (+local compliance check; contact=ops@example.com)")}"
  timeout_seconds: {int(ofac.get("timeout_seconds") or 60)}
  # 可选代理，例如 http://127.0.0.1:7890；不需要则保持 null
  proxy: {proxy_line}

scope:
  # individual / entity / vessel / aircraft / unknown
  entity_types:
{_yaml_list(scope.get("entity_types") or [c[1] for c in ENTITY_CHOICES], 4).rstrip()}
  # add / change / delete
  change_types:
{_yaml_list(scope.get("change_types") or [c[1] for c in CHANGE_CHOICES], 4).rstrip()}

excel:
  output_dir: {excel.get("output_dir") or "output"}
  # 同一公告按日期覆盖写入（ofac_YYYYMMDD.xlsx），避免时间戳文件堆积
  overwrite_by_date: {"true" if excel.get("overwrite_by_date", True) else "false"}
  # 最多保留多少个 ofac_*.xlsx；超出删除最旧的
  max_files: {int(excel.get("max_files") or 30)}
  # 按天保留（0=不按天删，仅按 max_files）
  keep_days: {int(excel.get("keep_days") or 0)}
  # 地址/国籍/出生地含 China、Hong Kong 时整行高亮
  highlight_china_hk:
    enabled: {"true" if hl.get("enabled", True) else "false"}
    keywords:
{_yaml_list(keywords, 6).rstrip()}
    fill_color: "{(hl.get("fill_color") or "FFF2CC").lstrip("#")}"
  # 可增删、调顺序；未知字段会被忽略
  columns:
{_yaml_list(excel.get("columns") or DEFAULT_COLUMNS, 4).rstrip()}

email:
  enabled: {"true" if email.get("enabled") else "false"}
  smtp_host: "{email.get("smtp_host") or ""}"
  smtp_port: {int(email.get("smtp_port") or 587)}
  use_tls: {"true" if email.get("use_tls", True) else "false"}
  username: "{email.get("username") or ""}"
  # 密码请用环境变量，不要写在这里
  password_env: {email.get("password_env") or "SMTP_PASSWORD"}
  from_addr: "{email.get("from_addr") or ""}"
  to:
{_yaml_list(to_list, 4).rstrip()}
  subject_template: "{_escape_double(email.get("subject_template") or "OFAC 制裁名单更新 {date}（{count} 条）")}"
  body_template: |
{body_indented}

paths:
  state_file: {paths.get("state_file") or "data/state.json"}

runtime:
  # once: 跑一次退出；loop: 按 schedule.interval_minutes 循环
  mode: {runtime.get("mode") or "once"}
  # 首次运行是否处理历史条目。false=只记录已存在条目、不发历史邮件
  process_existing_on_first_run: {"true" if runtime.get("process_existing_on_first_run") else "false"}
  # 调试时可设为最近 N 条未处理的更新；0 表示不限制
  max_notices_per_run: {int(runtime.get("max_notices_per_run") or 0)}
"""


def save_config(cfg: Dict[str, Any]) -> None:
    CONFIG_PATH.write_text(render_config(cfg), encoding="utf-8")


def run_full(cfg: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    configure_schedule(cfg)
    configure_network(cfg)
    configure_scope(cfg)
    configure_excel(cfg)
    secret = configure_email(cfg)
    configure_runtime(cfg)
    return secret


def run_menu(cfg: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    secret: Optional[Tuple[str, str]] = None
    while True:
        _print_summary(cfg)
        print("\n请选择要配置的部分：")
        choice = _ask_choice(
            "请输入序号",
            [
                ("1", "检查频率"),
                ("2", "网络与代理"),
                ("3", "监控范围"),
                ("4", "Excel 导出"),
                ("5", "邮件通知"),
                ("6", "首次运行与模式"),
                ("7", "全部重新走一遍"),
                ("0", "完成并保存"),
            ],
            default_key="0",
        )
        if choice == "0":
            break
        if choice == "1":
            configure_schedule(cfg)
        elif choice == "2":
            configure_network(cfg)
        elif choice == "3":
            configure_scope(cfg)
        elif choice == "4":
            configure_excel(cfg)
        elif choice == "5":
            secret = configure_email(cfg) or secret
        elif choice == "6":
            configure_runtime(cfg)
        elif choice == "7":
            secret = run_full(cfg) or secret
    return secret


def main() -> int:
    print("=" * 56)
    print(" OFAC Monitor · 配置助手")
    print("=" * 56)
    print("规则: 凡显示「默认 xxx，回车确认」的项，不输入直接回车即采用默认。")
    print(f"配置文件: {CONFIG_PATH}")
    print(f"密码文件: {ENV_PATH}  （已加入 .gitignore，勿提交）")

    loaded = _load_yaml(CONFIG_PATH)
    cfg = _merge_cfg(_default_cfg(), loaded)
    _print_summary(cfg)

    print("\n开始方式：")
    mode = _ask_choice(
        "请选择",
        [
            ("1", "新手引导 — 按步骤配置全部（推荐）"),
            ("2", "分项菜单 — 只改某一块"),
            ("3", "仅配置邮件"),
            ("0", "退出"),
        ],
        default_key="1",
    )
    if mode == "0":
        print("已退出，未修改。")
        return 0

    secret: Optional[Tuple[str, str]] = None
    if mode == "2":
        secret = run_menu(cfg)
    elif mode == "3":
        secret = configure_email(cfg)
    else:
        secret = run_full(cfg)

    _print_summary(cfg)
    if not _ask_yes("确认保存以上配置？", default=True):
        print("已取消，未修改文件。")
        return 1

    save_config(cfg)
    print(f"\n已写入: {CONFIG_PATH}")

    if secret:
        env_key, password = secret
        _upsert_env(ENV_PATH, env_key, password)
        print(f"已写入: {ENV_PATH}  （变量名 {env_key}）")
        if _ask_yes("是否现在测试 SMTP 登录？", default=True):
            _test_smtp(cfg["email"], password)

    return offer_launch(cfg)


def offer_launch(cfg: Dict[str, Any]) -> int:
    """配置完成后可选直接启动监控。"""
    loop_default = "2" if (cfg.get("runtime") or {}).get("mode") == "loop" else "1"
    print("\n配置完成。是否现在启动？")
    choice = _ask_choice(
        "请选择",
        [
            ("1", "立即检查一次（python main.py --once）"),
            ("2", "按间隔循环运行（python main.py --loop）"),
            ("3", "强制处理一条测试公告（--force-url）"),
            ("0", "暂不启动"),
        ],
        default_key=loop_default,
    )
    if choice == "0":
        print("\n稍后可手动运行：")
        print("  python main.py --once")
        print('  python main.py --force-url "https://ofac.treasury.gov/recent-actions/20261009"')
        print("  python main.py --loop")
        return 0

    main_py = ROOT / "main.py"
    if choice == "1":
        argv = [sys.executable, str(main_py), "--once"]
    elif choice == "2":
        argv = [sys.executable, str(main_py), "--loop"]
    else:
        url = _ask(
            "公告 URL",
            default="https://ofac.treasury.gov/recent-actions/20261009",
        )
        argv = [sys.executable, str(main_py), "--force-url", url]

    print(f"\n正在启动: {' '.join(argv[1:])}")
    print("-" * 56)
    try:
        result = subprocess.run(argv, cwd=str(ROOT))
        return int(result.returncode)
    except KeyboardInterrupt:
        print("\n已中断。")
        return 130


if __name__ == "__main__":
    sys.exit(main())
