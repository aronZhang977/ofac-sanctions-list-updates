from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List

from .config import get_smtp_password


def email_ready(cfg: Dict[str, Any]) -> tuple[bool, str]:
    email = cfg.get("email") or {}
    if not email.get("enabled"):
        return False, "email.enabled=false，跳过发送"
    required = ["smtp_host", "from_addr"]
    for key in required:
        if not str(email.get(key) or "").strip():
            return False, f"email.{key} 未配置，跳过发送"
    to_list = [x.strip() for x in (email.get("to") or []) if str(x).strip()]
    if not to_list:
        return False, "email.to 为空，跳过发送"
    if not get_smtp_password(cfg):
        return False, f"环境变量 {email.get('password_env') or 'SMTP_PASSWORD'} 未设置，跳过发送"
    return True, "ok"


def send_excel(
    cfg: Dict[str, Any],
    *,
    excel_path: Path,
    date: str,
    title: str,
    count: int,
    source_url: str,
) -> None:
    ok, reason = email_ready(cfg)
    if not ok:
        raise RuntimeError(reason)

    email = cfg["email"]
    to_list: List[str] = [x.strip() for x in email.get("to") or [] if str(x).strip()]
    subject = (email.get("subject_template") or "OFAC update {date}").format(
        date=date, title=title, count=count, source_url=source_url
    )
    body = (email.get("body_template") or "").format(
        date=date, title=title, count=count, source_url=source_url
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email["from_addr"]
    msg["To"] = ", ".join(to_list)
    msg.set_content(body)

    data = excel_path.read_bytes()
    msg.add_attachment(
        data,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=excel_path.name,
    )

    host = email["smtp_host"]
    port = int(email.get("smtp_port") or 587)
    username = email.get("username") or email["from_addr"]
    password = get_smtp_password(cfg)
    use_tls = bool(email.get("use_tls", True))

    if use_tls:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=60) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            if password:
                server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as server:
            if password:
                server.login(username, password)
            server.send_message(msg)


def try_send(
    cfg: Dict[str, Any],
    *,
    excel_path: Path,
    date: str,
    title: str,
    count: int,
    source_url: str,
) -> str:
    ok, reason = email_ready(cfg)
    if not ok:
        return reason
    send_excel(
        cfg,
        excel_path=excel_path,
        date=date,
        title=title,
        count=count,
        source_url=source_url,
    )
    return f"已发送邮件至: {', '.join([x for x in cfg['email'].get('to') if str(x).strip()])}"