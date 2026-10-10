from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .config import resolve_path
from .discover import Notice, list_sanctions_updates
from .excel_export import export_records
from .http_client import build_session
from .mailer import try_send
from .parse_notice import fetch_and_parse_notice, filter_records
from .state import load_state, mark_processed, processed_set, save_state

logger = logging.getLogger("ofac_monitor")


def _select_notices(
    notices: List[Notice],
    state: Dict[str, Any],
    cfg: Dict[str, Any],
) -> List[Notice]:
    done = processed_set(state)
    runtime = cfg.get("runtime") or {}
    first_run_done = bool(state.get("first_run_done"))
    process_existing = bool(runtime.get("process_existing_on_first_run"))
    max_n = int(runtime.get("max_notices_per_run") or 0)

    pending = [n for n in notices if n.url not in done]

    if not first_run_done and not process_existing:
        # 首次运行：只把当前列表记为已处理，避免历史邮件轰炸
        for n in notices:
            mark_processed(state, n.url)
        state["first_run_done"] = True
        logger.info(
            "首次运行：已标记 %s 条历史公告为已处理，本次不导出。下次检测到新公告再处理。",
            len(notices),
        )
        return []

    # 从旧到新处理，便于按时间顺序发邮件
    pending.sort(key=lambda n: n.date_key)
    if max_n > 0:
        pending = pending[:max_n]
    return pending


def process_notice(session, cfg: Dict[str, Any], notice: Notice) -> Optional[str]:
    logger.info("处理公告: %s (%s)", notice.title, notice.url)
    records = filter_records(fetch_and_parse_notice(session, cfg, notice), cfg)
    if not records:
        logger.warning("未解析到符合 scope 的记录: %s", notice.url)
        return None

    excel_path = export_records(
        records,
        cfg,
        date_key=notice.date_key,
        title_slug=notice.title[:30],
    )
    logger.info("已生成 Excel: %s（%s 条）", excel_path, len(records))

    mail_msg = try_send(
        cfg,
        excel_path=excel_path,
        date=notice.release_date or notice.date_key,
        title=notice.title,
        count=len(records),
        source_url=notice.url,
    )
    logger.info(mail_msg)
    return str(excel_path)


def run_once(cfg: Dict[str, Any], *, force_url: Optional[str] = None) -> int:
    session = build_session(cfg)
    state_path = resolve_path(cfg, (cfg.get("paths") or {}).get("state_file") or "data/state.json")
    state = load_state(state_path)

    if force_url:
        notice = Notice(
            url=force_url,
            path=force_url.replace((cfg.get("ofac") or {}).get("base_url", ""), ""),
            title="manual",
            release_date="",
            date_key=force_url.rstrip("/").split("/")[-1],
        )
        process_notice(session, cfg, notice)
        mark_processed(state, notice.url)
        state["first_run_done"] = True
        save_state(state_path, state)
        return 0

    notices = list_sanctions_updates(session, cfg)
    logger.info("列表页共发现 %s 条 Sanctions List Updates", len(notices))
    pending = _select_notices(notices, state, cfg)

    if not pending:
        save_state(state_path, state)
        logger.info("无待处理公告")
        return 0

    for notice in pending:
        try:
            process_notice(session, cfg, notice)
            mark_processed(state, notice.url)
            state["first_run_done"] = True
            save_state(state_path, state)
        except Exception:
            logger.exception("处理失败，保留未处理状态: %s", notice.url)
            save_state(state_path, state)
            raise

    return 0


def run_loop(cfg: Dict[str, Any]) -> int:
    interval = int((cfg.get("schedule") or {}).get("interval_minutes") or 60)
    interval = max(1, interval)
    logger.info("进入循环模式，每 %s 分钟检查一次", interval)
    while True:
        try:
            run_once(cfg)
        except Exception:
            logger.exception("本轮执行出错，将在下一轮重试")
        time.sleep(interval * 60)