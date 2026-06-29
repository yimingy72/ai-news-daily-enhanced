"""
AI 简讯增强版 — 主入口
======================
纯确定性的数据抓取 + 过滤 + GitHub Trending。
AI 评分、翻译等智能任务由当前 Agent 通过 skill 完成。

使用方式:
  python main.py              # 抓取 + 过滤 + 保存数据
  python main.py --schedule   # 本地定时调度
  python main.py --label 早报 # 指定标签
"""
import os
import sys
import asyncio
import argparse
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger
from src.config import config
from src.fetcher import ContentFetcher
from src.filter import Filter
from src.github_trending import fetch_trending, TrendingRepo


def setup_logging():
    log_cfg = config.get_section("logging")
    level = log_cfg.get("level", "INFO")
    log_file = log_cfg.get("file", "")
    logger.remove()
    logger.add(sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:^8}</level> | <cyan>{message}</cyan>",
        level=level)
    if log_file:
        p = Path(config.project_root) / log_file
        p.parent.mkdir(parents=True, exist_ok=True)
        logger.add(str(p), rotation="5 MB", retention="30 days", level="DEBUG")


async def run_once(label: str = ""):
    """执行抓取 + 过滤 + 保存（不调用任何 AI）"""
    start = datetime.now()
    tz_name = config.get("schedule.timezone", "Asia/Shanghai")
    import pytz
    tz = pytz.timezone(tz_name)
    logger.info("=" * 50)
    logger.info(f"🤖 AI 简讯增强版 v3.0 | {start.astimezone(tz).strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 50)

    # ── Step 1: 抓取 ──
    logger.info("[1/3] 📡 数据抓取中...")
    fetcher = ContentFetcher()
    articles = await fetcher.fetch_all(days_back=2)
    logger.info(f"      ✅ {len(articles)} 条原始")

    if not articles:
        logger.warning("⚠️ 未抓取到资讯")
        return

    # ── Step 2: 过滤 ──
    logger.info("[2/3] 🔍 过滤中...")
    f = Filter()
    articles = f.apply(articles)
    logger.info(f"      ✅ {len(articles)} 条有效")

    # ── Step 3: 保存数据 ──
    logger.info("[3/3] 💾 保存数据...")

    # 按日期保存原始数据（给 Agent 读取用）
    data_dir = Path(config.project_root) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    raw_data = [a.to_dict() for a in articles]
    raw_path = data_dir / f"raw_{today}.json"
    raw_path.write_text(json.dumps(raw_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 同时更新 latest.json（方便 agent 读取最新数据）
    latest_path = data_dir / "latest.json"
    latest_path.write_text(json.dumps(raw_data, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"      📊 数据: {raw_path} ({len(articles)} 条)")

    # ── GitHub Trending ──
    logger.info("🔥 GitHub Trending 抓取中...")
    repos = await fetch_trending()
    if repos:
        trending_data = [
            {"owner": r.owner, "name": r.name, "full_name": r.full_name,
             "description": r.description, "language": r.language,
             "stars_week": r.stars_week, "stars_total": r.stars_total, "url": r.url}
            for r in repos
        ]
        trending_path = data_dir / "trending.json"
        trending_path.write_text(json.dumps(trending_data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"      🔥 GitHub: {trending_path} ({len(repos)} 个项目)")

    elapsed = (datetime.now() - start).total_seconds()
    logger.info("=" * 50)
    logger.info(f"✅ 完成 · {elapsed:.1f}s · {len(articles)} 条有效")
    logger.info(f"📊 数据文件: {raw_path}")
    logger.info("🤖 AI 评分/翻译请由当前 Agent 完成")
    logger.info("=" * 50)


def start_scheduler():
    import pytz
    try:
        import schedule as sched
    except ImportError:
        logger.error("schedule 未安装")
        return

    sc = config.get_section("schedule")
    tz_name = sc.get("timezone", "Asia/Shanghai")
    mh, mm = sc.get("morning_hour", 8), sc.get("morning_minute", 0)
    eh, em = sc.get("evening_hour", 20), sc.get("evening_minute", 0)

    sched.every().day.at(f"{mh:02d}:{mm:02d}", tz_name).do(lambda: asyncio.run(run_once()))
    sched.every().day.at(f"{eh:02d}:{em:02d}", tz_name).do(lambda: asyncio.run(run_once()))

    tz = pytz.timezone(tz_name)
    logger.info(f"⏰ 调度已启动 [{datetime.now(tz).strftime('%Y-%m-%d %H:%M')}]")
    logger.info(f"   {mh:02d}:{mm:02d} / {eh:02d}:{em:02d} {tz_name}  |  Ctrl+C 停止")

    import time
    try:
        while True:
            sched.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("👋 已停止")


def main():
    parser = argparse.ArgumentParser(description="🤖 AI 简讯增强版")
    parser.add_argument("--schedule", action="store_true", help="定时调度")
    parser.add_argument("--label", type=str, default="", help="标签")
    args = parser.parse_args()

    setup_logging()

    if args.schedule:
        start_scheduler()
    else:
        asyncio.run(run_once(args.label))


if __name__ == "__main__":
    main()
