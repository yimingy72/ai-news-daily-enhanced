"""
内容过滤器
==========
对抓取到的原始资讯进行过滤和排序。

过滤规则（依次执行）:
  1. 关键词包含过滤 — 标题/摘要中必须包含至少一个 AI 关键词
  2. 关键词排除过滤 — 标题/摘要中不得包含任何排除关键词
  3. 时效性过滤     — 超过 max_age_hours 的旧闻自动丢弃
  4. 标题去重       — Jaccard 相似度 > 80% 视为重复

适配 Article dataclass。
"""
import re
from datetime import datetime, timedelta
from typing import List

from loguru import logger

from .config import config
from .models import Article


class Filter:
    """资讯过滤器"""

    def __init__(self):
        flt = config.get_section("filter")
        self._include = [kw.lower() for kw in flt.get("keywords_include", [])]
        self._exclude = [kw.lower() for kw in flt.get("keywords_exclude", [])]
        self._max_age_hours = flt.get("max_age_hours", 72)
        self._deduplicate = flt.get("deduplicate", True)

    def apply(self, articles: List[Article]) -> List[Article]:
        """
        执行全部过滤流程

        Args:
            articles: 原始 Article 列表

        Returns:
            过滤并排序后的 Article 列表
        """
        before = len(articles)

        # 1. 关键词包含
        articles = [a for a in articles if self._match_include(a)]

        # 2. 关键词排除
        articles = [a for a in articles if not self._match_exclude(a)]

        # 3. 时效性
        articles = [a for a in articles if self._is_recent(a)]

        # 4. 标题去重
        if self._deduplicate:
            articles = self._dedup_by_title(articles)

        # 5. 按发布时间倒序
        articles.sort(key=lambda a: a.published or datetime.min, reverse=True)

        after = len(articles)
        logger.info(f"过滤完成: {before} → {after} 条（过滤 {before - after} 条）")
        return articles

    def _match_include(self, article: Article) -> bool:
        """检查是否包含至少一个目标关键词"""
        if not self._include:
            return True

        title = article.title.lower()
        summary = article.summary.lower()
        source = article.source_name.lower()

        # 综合类源（36氪、雷锋网等含大量非AI内容）需要标题命中
        general_feeds = ["36氪", "雷锋网", "少数派"]
        is_general = any(g in source for g in general_feeds)

        if is_general:
            # 标题必须包含 AI 关键词
            if any(kw in title for kw in self._include):
                return True
            return False

        # 专用 AI 源：标题或摘要命中即可
        text = f"{title} {summary}"
        return any(kw in text for kw in self._include)

    def _match_exclude(self, article: Article) -> bool:
        """检查是否包含排除关键词"""
        if not self._exclude:
            return False
        text = f"{article.title} {article.summary}".lower()
        return any(kw in text for kw in self._exclude)

    def _is_recent(self, article: Article) -> bool:
        """检查时效性"""
        if not article.published:
            return True

        try:
            pub_dt = article.published
            if pub_dt.tzinfo:
                pub_dt = pub_dt.replace(tzinfo=None)
            cutoff = datetime.now() - timedelta(hours=self._max_age_hours)
            return pub_dt >= cutoff
        except Exception:
            return True

    @staticmethod
    def _dedup_by_title(articles: List[Article]) -> List[Article]:
        """基于标题的模糊去重（Jaccard 相似度）"""
        seen_titles: List[str] = []
        unique: List[Article] = []

        for art in articles:
            title = art.title.strip()
            normalized = re.sub(r"[\s\W]+", "", title).lower()

            is_dup = False
            for seen in seen_titles:
                if len(normalized) > 5 and len(seen) > 5:
                    # 包含关系去重
                    shorter = min(normalized, seen, key=len)
                    longer = max(normalized, seen, key=len)
                    if shorter in longer:
                        is_dup = True
                        break

                    # Jaccard 字符级相似度
                    set_a = set(normalized)
                    set_b = set(seen)
                    intersection = len(set_a & set_b)
                    union = len(set_a | set_b)
                    if union > 0 and intersection / union > 0.8:
                        is_dup = True
                        break

            if not is_dup:
                seen_titles.append(normalized)
                unique.append(art)

        return unique
