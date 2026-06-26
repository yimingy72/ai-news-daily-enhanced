"""
定时调度器
==========
管理资讯抓取的调度和执行。

支持模式:
  - 立即执行一次（完整流水线）
  - 本地定时运行（每天早/晚报）
"""
import asyncio
from datetime import datetime
from typing import List

import pytz
from loguru import logger

try:
    import schedule
    HAS_SCHEDULE = True
except ImportError:
    HAS_SCHEDULE = False

from .config import config
from .fetcher import ContentFetcher
from .filter import Filter
from .ai_analyzer import AIAnalyzer
from .translator import Translator
from .writer import BriefWriter
from .markdown_writer import MarkdownWriter
from .json_writer import JSONWriter
from .models import Article


async def run_once(label: str = "") -> List[Article]:
    """
    执行一次完整的抓取流水线

    1. 从 24+ 数据源并发抓取
    2. 4 道内容过滤
    3. AI 智能评分排序
    4. AI 翻译英文内容
    5. 精简文本 + Markdown + JSON 输出

    Args:
        label: 标签（如"早报"、"晚报"）

    Returns:
        精选后的文章列表
    """
    start_time = datetime.now()
    tz = _get_timezone()
    now_str = start_time.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")

    logger.info("=" * 50)
    logger.info(f"🤖 AI 简讯增强版 v2.0")
    logger.info(f"🚀 开始执行资讯抓取 [{now_str}]")
    logger.info("=" * 50)

    # ── Step 1: 抓取 ──
    logger.info("[1/4] 📡 数据抓取中...")
    fetcher = ContentFetcher()
    articles = await fetcher.fetch_all(days_back=2)
    logger.info(f"      ✅ 抓取完成: {len(articles)} 条原始资讯")

    if not articles:
        logger.warning("⚠️ 未抓取到任何资讯，请检查网络和数据源配置")
        return []

    # ── Step 2: 过滤 ──
    logger.info("[2/4] 🔍 内容过滤中...")
    content_filter = Filter()
    articles = content_filter.apply(articles)
    logger.info(f"      ✅ 过滤完成: {len(articles)} 条有效资讯")

    if not articles:
        logger.warning("⚠️ 所有资讯被过滤，请检查关键词配置")
        return []

    # ── Step 3: AI 分析 + 精选 ──
    logger.info("[3/4] 🧠 AI 分析中...")
    analyzer = AIAnalyzer()
    articles = await analyzer.analyze_and_rank(articles)
    logger.info(f"      ✅ AI 分析完成: {len(articles)} 条精选")

    # ── Step 4: 翻译 ──
    logger.info("[4/5] 🌐 翻译英文内容...")
    translator = Translator()
    articles = await translator.translate(articles)
    logger.info(f"      ✅ 翻译完成")

    # ── Step 5: 输出 ──
    logger.info("[5/5] 📝 生成输出文件...")

    # 精简文本日报（含 AI 简讯 + GitHub Trending）
    brief_writer = BriefWriter()
    brief_path = await brief_writer.write(articles, label)
    logger.info(f"      📄 精简日报: {brief_path}")

    # Markdown 详细版（备用）
    md_writer = MarkdownWriter()
    md_path = md_writer.write(articles, label)
    logger.info(f"      📄 Markdown: {md_path}")

    # JSON 数据
    json_writer = JSONWriter()
    json_writer.write(articles)
    logger.info(f"      📊 JSON: data/ 目录")

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info("=" * 50)
    logger.info(f"✅ 任务完成 · 耗时 {elapsed:.1f}s · 精选 {len(articles)} 条")
    logger.info(f"📱 推送内容: {brief_path}")
    logger.info("=" * 50)
    return articles


def start_scheduler():
    """
    启动本地定时调度器

    在配置的时间（默认 8:00 + 20:00）自动执行。
    常驻进程，按 Ctrl+C 退出。
    """
    if not HAS_SCHEDULE:
        logger.error("schedule 库未安装，无法启动定时调度")
        return

    sched_cfg = config.get_section("schedule")
    morning_hour = sched_cfg.get("morning_hour", 8)
    morning_min = sched_cfg.get("morning_minute", 0)
    evening_hour = sched_cfg.get("evening_hour", 20)
    evening_min = sched_cfg.get("evening_minute", 0)
    tz_name = sched_cfg.get("timezone", "Asia/Shanghai")

    morning_time = f"{morning_hour:02d}:{morning_min:02d}"
    evening_time = f"{evening_hour:02d}:{evening_min:02d}"

    schedule.every().day.at(morning_time, tz_name).do(
        lambda: asyncio.run(run_once("🌅 早报"))
    )
    schedule.every().day.at(evening_time, tz_name).do(
        lambda: asyncio.run(run_once("🌙 晚报"))
    )

    tz = _get_timezone()
    now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"⏰ 定时调度已启动 [{now_str} {tz_name}]")
    logger.info(f"   🌅 早报: 每天 {morning_time}")
    logger.info(f"   🌙 晚报: 每天 {evening_time}")
    logger.info(f"   按 Ctrl+C 停止")

    try:
        while True:
            schedule.run_pending()
            import time
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("👋 定时调度已停止")


def _get_timezone():
    """获取配置的时区"""
    tz_name = config.get("schedule.timezone", "Asia/Shanghai")
    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.timezone("Asia/Shanghai")
