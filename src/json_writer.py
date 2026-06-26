"""
JSON 数据输出器
===============
将资讯保存为 JSON 格式，供 Web 页面读取。

输出文件:
  - data/articles.json    全量文章列表
  - data/dates.json       可用日期索引
  - data/YYYY-MM-DD.json  按日期拆分的文件

适配 Article dataclass。
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from loguru import logger

from .config import config
from .models import Article


class JSONWriter:
    """JSON 数据输出器"""

    def __init__(self):
        out_cfg = config.get_section("output")
        self._data_dir = Path(out_cfg.get("data_dir", "./data"))
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def write(self, articles: List[Article]):
        """
        保存 JSON 数据

        Args:
            articles: 文章列表
        """
        today = datetime.now().strftime("%Y-%m-%d")
        articles_data = [a.to_dict() for a in articles]

        # 1. 按日期保存
        date_file = self._data_dir / f"{today}.json"
        date_file.write_text(
            json.dumps(articles_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 2. 更新全量聚合
        all_articles = self._load_all_articles()
        # 去重合并
        existing_urls = {a["url"] for a in all_articles}
        for art_data in articles_data:
            if art_data["url"] not in existing_urls:
                all_articles.append(art_data)
                existing_urls.add(art_data["url"])

        articles_file = self._data_dir / "articles.json"
        articles_file.write_text(
            json.dumps(all_articles, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 3. 更新日期索引
        dates = self._load_dates()
        if today not in dates:
            dates.append(today)
            dates.sort(reverse=True)
        dates_file = self._data_dir / "dates.json"
        dates_file.write_text(
            json.dumps(dates, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info(
            f"JSON 数据保存完成: {date_file} ({len(articles_data)} 条), "
            f"全量 {len(all_articles)} 条"
        )

    def _load_all_articles(self) -> List[Dict]:
        """加载全量文章"""
        articles_file = self._data_dir / "articles.json"
        if articles_file.exists():
            try:
                return json.loads(articles_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _load_dates(self) -> List[str]:
        """加载日期索引"""
        dates_file = self._data_dir / "dates.json"
        if dates_file.exists():
            try:
                return json.loads(dates_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []
