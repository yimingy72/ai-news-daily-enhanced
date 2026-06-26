"""
Markdown 日报生成器
===================
将精选资讯生成为结构精美的 Markdown 日报。

格式特色：
  - Hero 头部区域（日期、标签）
  - 统计概览表格
  - 按分类分组的文章列表
  - 星级评分可视化
  - 干净的版面设计
"""
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from loguru import logger

from .config import config
from .models import Article


def score_stars(score: float) -> str:
    """将 0-10 的评分转为星级表示"""
    if score >= 9.0:   return "★★★★★"
    if score >= 8.0:   return "★★★★☆"
    if score >= 7.0:   return "★★★★"
    if score >= 6.0:   return "★★★☆"
    if score >= 5.0:   return "★★★"
    if score >= 4.0:   return "★★☆"
    if score > 0:      return "★★"
    return "★"


def score_bar(score: float) -> str:
    """评分条 """
    filled = min(10, max(0, int(score)))
    empty = 10 - filled
    return "█" * filled + "░" * empty


class MarkdownWriter:
    """Markdown 日报生成器"""

    def __init__(self):
        out_cfg = config.get_section("output")
        self._output_dir = Path(out_cfg.get("dir", "./output"))
        self._filename_format = out_cfg.get("filename_format", "AI简讯_{date}.md")
        self._append = out_cfg.get("append_if_exists", True)

    # ------------------------------------------------------------------
    #  公共接口
    # ------------------------------------------------------------------

    def write(self, articles: List[Article], label: str = "") -> str:
        """生成 Markdown 日报，返回文件路径"""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        label_text = label or self._guess_label(now)

        filename = self._filename_format.format(date=date_str)
        filepath = self._output_dir / filename

        sections = [
            self._build_hero(date_str, label_text, now),
            self._build_stats(articles),
            self._build_articles(articles),
            self._build_footer(now),
        ]

        content = "\n\n".join(sections) + "\n"

        if self._append and filepath.exists() and "晚报" in label_text:
            existing = filepath.read_text(encoding="utf-8")
            body = "\n\n".join([
                self._build_section_divider("🌙 晚报更新", now),
                self._build_articles(articles),
            ])
            filepath.write_text(f"{existing.rstrip()}\n\n{body}\n", encoding="utf-8")
        else:
            filepath.write_text(content, encoding="utf-8")

        logger.info(f"📄 Markdown 日报已保存: {filepath}")
        return str(filepath)

    # ------------------------------------------------------------------
    #  Hero 头部
    # ------------------------------------------------------------------

    def _build_hero(self, date_str: str, label: str, now: datetime) -> str:
        today = datetime.now()
        weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][today.weekday()]
        date_display = today.strftime("%Y年%m月%d日")

        return (
            f"# 🤖 AI 行业简讯日报\n\n"
            f"> **{date_display} {weekday}**　·　{label}　·　AI News Daily Enhanced\n\n"
            f"---"
        )

    def _build_section_divider(self, label: str, now: datetime) -> str:
        return (
            f"## {label}\n\n"
            f"> 更新时间：{now.strftime('%H:%M')}\n\n"
            f"---"
        )

    # ------------------------------------------------------------------
    #  统计概览
    # ------------------------------------------------------------------

    def _build_stats(self, articles: List[Article]) -> str:
        if not articles:
            return ""

        total = len(articles)
        sources = set(a.source_name for a in articles)
        categories = set(a.category for a in articles)
        scores = [a.ai_score for a in articles if a.ai_score > 0]
        avg_score = sum(scores) / len(scores) if scores else 0
        max_score = max(scores) if scores else 0

        api_key = config.get("ai.api_key", "") or __import__("os").environ.get("NEWS_AI_API_KEY", "")
        has_ai = bool(api_key and api_key.strip())
        ai_status = "🧠 AI 大模型分析" if has_ai else "📋 规则引擎评分"
        ai_model = config.get("ai.model", "N/A")

        # 来源分布
        source_list = sorted(sources)

        return (
            f"## 📊 今日概览\n\n"
            f"| 指标 | 详情 |\n"
            f"|------|------|\n"
            f"| 📄 精选文章 | **{total}** 篇 |\n"
            f"| 📡 数据来源 | **{len(sources)}** 个（{', '.join(list(source_list)[:6])}{'...' if len(source_list) > 6 else ''}）|\n"
            f"| 📂 覆盖分类 | **{len(categories)}** 类 |\n"
            f"| ⭐ 最高评分 | **{max_score:.1f}** 分 |\n"
            f"| 📊 平均评分 | **{avg_score:.1f}** 分 |\n"
            f"| 🧠 分析引擎 | {ai_status}（`{ai_model}`）|\n\n"
            f"---"
        )

    # ------------------------------------------------------------------
    #  文章列表（按分类分组）
    # ------------------------------------------------------------------

    def _build_articles(self, articles: List[Article]) -> str:
        grouped = self._group_by_category(articles)
        categories_config = config.get_section("categories")

        sections = []
        for cat_key, cat_articles in grouped.items():
            display = categories_config.get(cat_key, cat_key)
            sections.append(self._build_category(cat_key, display, cat_articles))

        return "\n\n".join(sections)

    def _build_category(
        self, cat_key: str, display: str, articles: List[Article]
    ) -> str:
        lines = [
            f"## {display}",
            "",
            f"> 共 **{len(articles)}** 篇",
            "",
        ]

        for i, art in enumerate(articles, 1):
            lines.append(self._build_card(i, art))

        return "\n".join(lines)

    def _build_card(self, index: int, art: Article) -> str:
        # ── 标题 + 评分徽章 ──
        score = art.ai_score
        if score > 0:
            badge = f"`{score:.1f}分` {score_stars(score)}"
            title_line = f"**{index}.** {badge}  [{art.title}]({art.url})"
        else:
            title_line = f"**{index}.** [{art.title}]({art.url})"

        # ── 元信息 ──
        meta_parts = [f"📡 {art.source_name}"]
        if art.display_published:
            meta_parts.append(f"🕐 {art.display_published}")
        if art.ai_category and art.ai_category != "其他":
            meta_parts.append(f"📂 {art.ai_category}")
        if art.author:
            meta_parts.append(f"✍️ {art.author}")

        meta_line = "  ·  ".join(meta_parts)

        # ── 摘要 ──
        summary = self._clean_summary(art.ai_summary or art.summary)

        # ── 评分条（仅高分显示） ──
        bar = ""
        if score >= 6.0:
            bar = f"\n> `{score_bar(score)}`"

        lines = [
            "",
            title_line,
            "",
            f"> {meta_line}",
        ]

        if summary:
            lines.append(">")
            lines.append(f"> {summary}")

        if bar:
            lines.append(bar)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    #  页脚
    # ------------------------------------------------------------------

    def _build_footer(self, now: datetime) -> str:
        return (
            f"\n---\n\n"
            f"<sub align=\"center\">"
            f"🤖 AI News Daily Enhanced 自动生成 · {now.strftime('%Y-%m-%d %H:%M')} · MIT License"
            f"</sub>\n"
        )

    # ------------------------------------------------------------------
    #  工具方法
    # ------------------------------------------------------------------

    def _clean_summary(self, text: str) -> str:
        """清洗摘要文本，去除抓取残留"""
        if not text:
            return ""

        text = text.strip()

        # 移除 jina.ai 和网页抓取的残留标记行
        junk_prefixes = [
            "URL Source:", "Markdown Content:", "Crawled:",
            "Published Time:", "Published:", "Warning:",
            "Error:", "Image:", "Images:",
        ]
        for prefix in junk_prefixes:
            if prefix in text:
                idx = text.find(prefix)
                if idx > 80:
                    text = text[:idx].strip()
                elif idx <= 5:
                    # 整行都是垃圾，跳过前缀后继续
                    rest = text[idx + len(prefix):].strip()
                    if len(rest) > 20:
                        text = rest
                    else:
                        return ""

        # 移除 "📝" 前缀
        if text.startswith("📝"):
            text = text[2:].strip()

        # 移除前导的 "URL Source:" 变体（以 "http" 开头说明是 URL 残留）
        if text.startswith("http"):
            return ""

        if not text or len(text) < 15:
            return ""

        # 截断到合理长度（优先在句号处断开）
        if len(text) > 280:
            for sep in ("。", ". ", "\n", "！", "？"):
                cut = text.rfind(sep, 100, 280)
                if cut > 100:
                    text = text[:cut + 1]
                    break
            else:
                text = text[:280] + "…"

        return text

    def _group_by_category(self, articles: List[Article]) -> Dict[str, List[Article]]:
        """按分类分组，保持优先级顺序"""
        grouped: Dict[str, List[Article]] = {}

        for art in articles:
            cat = art.category or "other"
            grouped.setdefault(cat, []).append(art)

        for cat in grouped:
            grouped[cat].sort(key=lambda x: x.ai_score, reverse=True)

        # 按 categories 配置的优先级排序
        categories_config = config.get_section("categories")
        ordered: Dict[str, List[Article]] = {}
        for cat_key in categories_config:
            if cat_key in grouped and grouped[cat_key]:
                ordered[cat_key] = grouped[cat_key]
        for cat_key, arts in grouped.items():
            if cat_key not in ordered and arts:
                ordered[cat_key] = arts

        return ordered

    @staticmethod
    def _guess_label(now: datetime) -> str:
        hour = now.hour
        if 5 <= hour < 12:
            return "🌅 早报"
        elif 12 <= hour < 18:
            return "☀️ 午报"
        else:
            return "🌙 晚报"
