"""
AI 简讯增强版 — 主入口
======================
融合 ai-news-daily 和 ai-daily-brief 的优势：
25+ 数据源 · AI 智能评分 · 精美 Markdown 日报 · JSON 数据输出

使用方式:
  python main.py                 # 立即执行一次抓取
  python main.py --schedule      # 启动定时调度（常驻进程）
  python main.py --label 早报    # 执行一次并指定标签
"""
import os
import sys
import asyncio
import argparse

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger

from src.config import config
from src.scheduler import run_once, start_scheduler


def setup_logging():
    """配置日志"""
    log_cfg = config.get_section("logging")
    level = log_cfg.get("level", "INFO")
    log_file = log_cfg.get("file", "")

    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:^8}</level> | <cyan>{message}</cyan>",
        level=level,
    )

    if log_file:
        log_path = os.path.join(str(config.project_root), log_file)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        logger.add(log_path, rotation="5 MB", retention="30 days", level="DEBUG")


def main():
    parser = argparse.ArgumentParser(
        description="🤖 AI 简讯增强版 — 每日 AI 资讯聚合系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                  # 立即执行一次
  python main.py --schedule       # 启动定时任务（每天 8:00 + 20:00）
  python main.py --label 早报     # 指定标签立即执行
  python main.py --config path    # 指定配置文件路径
        """,
    )
    parser.add_argument(
        "--schedule", action="store_true",
        help="启动定时调度模式（常驻进程，按配置时间自动执行）",
    )
    parser.add_argument(
        "--label", type=str, default="",
        help="运行标签，如'早报'或'晚报'（为空则自动判断）",
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="自定义配置文件路径（默认: config/settings.yaml）",
    )

    args = parser.parse_args()

    setup_logging()

    # 自定义配置文件
    if args.config and os.path.exists(args.config):
        os.environ["NEWS_CONFIG_PATH"] = args.config
        logger.info(f"使用自定义配置: {args.config}")

    # 模式路由
    if args.schedule:
        start_scheduler()
    else:
        asyncio.run(run_once(args.label))


if __name__ == "__main__":
    main()
