#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys

from ofac_monitor.config import load_config
from ofac_monitor.runner import run_loop, run_once


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OFAC Sanctions List Updates 监控")
    parser.add_argument("-c", "--config", default=None, help="配置文件路径，默认 ./config.yaml")
    parser.add_argument("--once", action="store_true", help="只跑一次（默认）")
    parser.add_argument("--loop", action="store_true", help="按配置间隔循环检查")
    parser.add_argument(
        "--force-url",
        default=None,
        help="强制处理指定公告 URL（用于测试，例如 https://ofac.treasury.gov/recent-actions/20250930）",
    )
    parser.add_argument(
        "--process-existing",
        action="store_true",
        help="覆盖配置：首次也处理列表中尚未记录的公告",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    cfg = load_config(args.config)

    if args.process_existing:
        cfg.setdefault("runtime", {})["process_existing_on_first_run"] = True

    if args.loop or ((cfg.get("runtime") or {}).get("mode") == "loop" and not args.once):
        if args.force_url:
            logging.error("--force-url 仅支持单次运行")
            return 2
        return run_loop(cfg)

    return run_once(cfg, force_url=args.force_url)


if __name__ == "__main__":
    sys.exit(main())