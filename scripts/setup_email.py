#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交互式邮件配置：逐项中文提问，写入 config.yaml 与 .env。"""
from __future__ import annotations

import getpass
import re
import smtplib
import ssl
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
ENV_PATH = ROOT / ".env"

PRESETS = {
    "1": ("QQ 邮箱", "smtp.qq.com", 587, True),
    "2": ("163 邮箱", "smtp.163.com", 587, True),
    "3": ("Gmail", "smtp.gmail.com", 587, True),
    "4": ("Outlook / Office365", "smtp.office365.com", 587, True),
    "5": ("自定义 / 企业邮", "", 587, True),
}


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _default_hint(default: str) -> str:
    return f"[默认 {default}，回车确认]"


def _ask(prompt: str, default: Optional[str] = None, required: bool = True) -> str:
    if default is not None and str(default) != "":
        line = f"{prompt} {_default_hint(default)}: "
    elif default == "":
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


def _ask_choice(
    prompt: str,
    options: List[tuple],
    default_key: str,
) -> str:
    for key, label in options:
        mark = "  ← 默认" if key == default_key else ""
        print(f"  {key}. {label}{mark}")
    while True:
        raw = _ask(prompt, default=default_key)
        if raw in {k for k, _ in options}:
            return raw
        print(f"  无效选项，请输入所列序号，或直接回车确认默认 {default_key}。")


def _parse_recipients(raw: str) -> List[str]:
    parts = re.split(r"[,;，；\s]+", raw.strip())
    return [p for p in parts if p]


def _replace_email_section(text: str, email_cfg: Dict[str, Any]) -> str:
    dumped = yaml.dump(
        {"email": email_cfg},
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1000,
    ).rstrip() + "\n"
    pattern = re.compile(
        r"^email:\n.*?(?=^[a-zA-Z_][\w-]*:|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    if pattern.search(text):
        return pattern.sub(dumped + "\n", text, count=1)
    return text.rstrip() + "\n\n" + dumped + "\n"


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
        out.append(f"# OFAC Monitor 邮件密码（由 scripts/setup_email.py 写入）")
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


def main() -> int:
    print("=" * 56)
    print(" OFAC Monitor · 邮件配置向导")
    print("=" * 56)
    print("规则: 凡显示「默认 xxx，回车确认」的项，不输入直接回车即采用默认。")
    print(f"配置文件: {CONFIG_PATH}")
    print(f"密码文件: {ENV_PATH}  （已加入 .gitignore，勿提交）")
    print()

    cfg = _load_yaml(CONFIG_PATH)
    old = cfg.get("email") or {}

    enabled = _ask_yes("1) 是否启用邮件发送？", default=True)
    if not enabled:
        email_cfg = dict(old)
        email_cfg["enabled"] = False
        text = CONFIG_PATH.read_text(encoding="utf-8")
        CONFIG_PATH.write_text(_replace_email_section(text, email_cfg), encoding="utf-8")
        print("\n已关闭邮件发送（email.enabled=false）。")
        return 0

    old_host = (old.get("smtp_host") or "").strip()
    email_default = "5"
    for key, (_, host, _, _) in PRESETS.items():
        if host and host == old_host:
            email_default = key
            break
    print("\n2) 请选择邮箱类型：")
    choice = _ask_choice(
        "请输入序号",
        [
            (k, f"{name} → {host}:{port}" if host else name)
            for k, (name, host, port, _) in PRESETS.items()
        ],
        default_key=email_default,
    )
    preset = PRESETS.get(choice, PRESETS["5"])
    _, preset_host, preset_port, preset_tls = preset

    smtp_host = _ask(
        "3) SMTP 服务器地址（如 smtp.qq.com / 企业邮域名）",
        default=preset_host or old.get("smtp_host") or None,
        required=True,
    )
    smtp_port_raw = _ask(
        "4) SMTP 端口（常见 587 或 465）",
        default=str(old.get("smtp_port") or preset_port),
    )
    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        print("端口无效，使用默认 587。")
        smtp_port = 587

    use_tls = _ask_yes(
        "5) 是否启用 STARTTLS？（587 一般选是；部分 465 场景选否）",
        default=bool(old.get("use_tls", preset_tls)),
    )
    username = _ask(
        "6) SMTP 登录用户名（通常是完整邮箱）",
        default=old.get("username") or None,
        required=True,
    )
    from_addr = _ask(
        "7) 发件人地址 From（一般与登录用户名相同）",
        default=old.get("from_addr") or username,
        required=True,
    )

    old_to = [x for x in (old.get("to") or []) if str(x).strip()]
    to_default = ",".join(old_to) if old_to else None
    to_raw = _ask(
        "8) 收件人（多个用逗号或分号分隔）",
        default=to_default,
        required=True,
    )
    recipients = _parse_recipients(to_raw)
    if not recipients:
        print("收件人为空，已取消。")
        return 1

    password_env = _ask(
        "9) 密码对应的环境变量名",
        default=old.get("password_env") or "SMTP_PASSWORD",
        required=True,
    ).strip()

    print("\n10) SMTP 密码或授权码（输入不回显；此项无默认，必须填写）")
    print("    提示: QQ/163/Gmail 等通常需要「授权码」，不是网页登录密码。")
    password = _ask_password("请输入密码/授权码")

    keep_subject = _ask_yes(
        "11) 是否保留当前邮件主题模板？",
        default=True,
    )
    if keep_subject:
        subject_template = old.get("subject_template") or "OFAC 制裁名单更新 {date}（{count} 条）"
    else:
        subject_template = _ask(
            "请输入主题模板（可用 {date} {count} {title} {source_url}）",
            default="OFAC 制裁名单更新 {date}（{count} 条）",
        )

    body_template = old.get("body_template") or (
        "OFAC Sanctions List Updates 有新变动。\n\n"
        "发布日期: {date}\n"
        "标题: {title}\n"
        "记录数: {count}\n"
        "来源: {source_url}\n\n"
        "Excel 见附件。\n"
    )

    email_cfg: Dict[str, Any] = {
        "enabled": True,
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "use_tls": use_tls,
        "username": username,
        "password_env": password_env,
        "from_addr": from_addr,
        "to": recipients,
        "subject_template": subject_template,
        "body_template": body_template,
    }

    print("\n------ 即将写入的配置预览 ------")
    print(yaml.dump({"email": {**email_cfg, "password": "***已隐藏***"}}, allow_unicode=True, sort_keys=False))
    if not _ask_yes("确认保存？", default=True):
        print("已取消，未修改文件。")
        return 1

    text = CONFIG_PATH.read_text(encoding="utf-8")
    CONFIG_PATH.write_text(_replace_email_section(text, email_cfg), encoding="utf-8")
    _upsert_env(ENV_PATH, password_env, password)

    print(f"\n已写入: {CONFIG_PATH}")
    print(f"已写入: {ENV_PATH}  （变量名 {password_env}）")
    print("程序启动时会自动读取 .env；也可在终端手动导出：")
    if sys.platform.startswith("win"):
        print(f'  PowerShell: $env:{password_env} = "你的密码"')
        print(f"  CMD      : set {password_env}=你的密码")
    else:
        print(f'  export {password_env}="你的密码"')

    if _ask_yes("\n12) 是否现在测试 SMTP 登录？", default=True):
        _test_smtp(email_cfg, password)

    print("\n邮件配置完成。是否现在启动监控？")
    choice = _ask_choice(
        "请选择",
        [
            ("1", "立即检查一次（python main.py --once）"),
            ("2", "强制处理一条测试公告（--force-url）"),
            ("0", "暂不启动"),
        ],
        default_key="1",
    )
    if choice == "0":
        print("\n稍后可手动运行：")
        print("  python main.py --once")
        print('  python main.py --force-url "https://ofac.treasury.gov/recent-actions/20261009"')
        return 0

    main_py = ROOT / "main.py"
    if choice == "2":
        url = _ask(
            "公告 URL",
            default="https://ofac.treasury.gov/recent-actions/20261009",
        )
        argv = [sys.executable, str(main_py), "--force-url", url]
    else:
        argv = [sys.executable, str(main_py), "--once"]

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