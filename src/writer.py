"""
精简日报生成器
==============
生成适合消息推送的精简中文文本日报。
包含 AI 简讯 + GitHub Trending 两个模块。

每篇资讯输出 1-3 句完整中文摘要，不截断。
"""
import os
from datetime import datetime
from pathlib import Path
from typing import List

from loguru import logger

from .config import config
from .models import Article
from .github_trending import fetch_trending, translate_descriptions, format_trending_section, TrendingRepo


class BriefWriter:
    """紧凑消息格式日报生成器"""

    def __init__(self):
        out_cfg = config.get_section("output")
        self._output_dir = Path(out_cfg.get("dir", "./output"))
        self._filename_format = out_cfg.get("filename_format", "AI简讯_{date}.md")

    async def write(self, articles: List[Article], label: str = "") -> str:
        """生成完整日报（AI 简讯 + GitHub Trending），返回文件路径"""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        filename = self._filename_format.format(date=date_str).replace(".md", ".txt")
        filepath = self._output_dir / filename

        # 并行获取两部分内容
        news_section = self._build_news(articles, now)

        # GitHub Trending
        logger.info("🔥 抓取 GitHub Trending...")
        trending_repos = await fetch_trending()
        trending_repos = await translate_descriptions(trending_repos)
        trending_section = format_trending_section(trending_repos)

        # 组合
        parts = [news_section]
        if trending_section:
            parts.append(trending_section)

        content = "\n".join(parts) + "\n"
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"📱 日报已保存 ({len(articles)} 条简讯 + {len(trending_repos)} 个热门项目): {filepath}")
        return str(filepath)

    # ------------------------------------------------------------------
    #  AI 简讯模块
    # ------------------------------------------------------------------

    def _build_news(self, articles: List[Article], now: datetime) -> str:
        lines = [self._header(now), "🤖 AI 简讯日报", ""]

        seen_keys: set = set()
        count = 0
        for art in articles[:15]:
            text = self._format_article(art)
            if not text or len(text) < 8:
                continue
            key = self._extract_key(text)
            if key and key in seen_keys:
                continue
            if key:
                seen_keys.add(key)
            count += 1
            lines.append(f"  {count}、{text}")
            if count >= 12:
                break

        return "\n".join(lines)

    def _format_article(self, art: Article) -> str:
        """格式化为 1-3 句完整中文摘要"""
        # 优先 AI 生成的中文摘要
        summary = art.ai_summary or ""
        if not summary or self._is_english(summary):
            summary = art.summary or ""

        if not summary:
            summary = art.title

        # 清洗
        text = summary.strip()
        for p in ["📝", "【原文标题】", "【原文】", "【摘要】"]:
            if text.startswith(p):
                text = text[len(p):].strip()

        # 垃圾过滤
        if self._is_junk(text):
            return ""

        # 英文未翻译的标记
        if self._is_english(text):
            title = art.title[:80]
            return f"[英] {title}"

        # 取前 2-3 句，保证完整性
        sentences = []
        remaining = text
        for _ in range(3):
            cut = -1
            for sep in ["。", "！", "？", "\n"]:
                idx = remaining.find(sep)
                if 5 < idx < 150:
                    cut = idx
                    break
            if cut > 0:
                sentences.append(remaining[:cut + 1])
                remaining = remaining[cut + 1:].strip()
            else:
                break

        if not sentences:
            # 没有找到句号分隔，直接取合理长度
            if len(text) > 150:
                # 尝试在空格处断开
                cut = text.rfind(" ", 80, 150)
                if cut > 80:
                    text = text[:cut]
                else:
                    text = text[:150]
            sentences = [text]

        # 取前 2-3 句（总长不超过 200 字）
        result = ""
        for s in sentences:
            if len(result) + len(s) > 200:
                break
            result += s
        if not result:
            result = sentences[0][:150]

        return result

    # ------------------------------------------------------------------
    #  工具
    # ------------------------------------------------------------------

    def _header(self, now: datetime) -> str:
        lunar = self._lunar(now)
        weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
        md = now.strftime("%m月%d日")
        if lunar:
            return f"{md}，{lunar}，{weekday}"
        return f"{md}，{weekday}"

    @staticmethod
    def _is_english(text: str) -> bool:
        if not text or len(text) < 5:
            return False
        ascii_alpha = sum(1 for c in text if c.isascii() and c.isalpha())
        total_alpha = sum(1 for c in text if c.isalpha())
        return total_alpha > 0 and ascii_alpha / total_alpha > 0.5

    @staticmethod
    def _is_junk(text: str) -> bool:
        junk = ["OpenAI News", "AI at Meta Blog", "Meta AI Blog",
                "Meta AI博客", "AI资讯_获取", "Essays", "404 -",
                "YouTube频道", "YouTube channel", "Gemini Omni 发布",
                "Gemini Omni", "Introducing Gemini Omni"]
        return any(p in text for p in junk) or len(text) < 10

    @staticmethod
    def _extract_key(text: str) -> str:
        """提取去重关键词：公司名 + 核心动作"""
        companies = ["OpenAI", "Anthropic", "Google", "DeepMind", "Meta", "Mistral",
                     "Tesla", "NVIDIA", "阿里巴巴", "阿里", "百度", "腾讯", "字节",
                     "DeepSeek", "HuggingFace", "Apple", "微软", "Amazon",
                     "白宫", "特朗普", "英伟达", "高通", "商汤"]
        # 核心事件词：同事件不同来源归为一类
        events = ["推迟", "发布", "融资", "收购", "起诉", "开源", "蒸馏", "芯片",
                  "delay", "release", "fund", "sue", "chip"]
        company = None
        for c in companies:
            if c.lower() in text.lower():
                company = c
                break
        if company:
            # 找到第一个事件词
            for ev in events:
                if ev in text:
                    return f"{company}:{ev}"
            return company
        return text[:10]

    @staticmethod
    def _lunar(dt: datetime) -> str:
        months = ["正月","二月","三月","四月","五月","六月",
                  "七月","八月","九月","十月","十一月","十二月"]
        days = ["初一","初二","初三","初四","初五","初六","初七","初八","初九","初十",
                "十一","十二","十三","十四","十五","十六","十七","十八","十九","二十",
                "廿一","廿二","廿三","廿四","廿五","廿六","廿七","廿八","廿九","三十"]
        first = {1:(1,19),2:(2,17),3:(3,19),4:(4,17),5:(5,17),6:(6,15),
                 7:(7,15),8:(8,13),9:(9,12),10:(10,11),11:(11,10),12:(12,10)}
        for m in range(12, 0, -1):
            fm, fd = first.get(m, (1,1))
            base = datetime(2026, fm, fd)
            cur = datetime(2026, dt.month, dt.day)
            if cur >= base:
                d = (cur - base).days + 1
                if d > 30: d = 30
                return f"农历{months[m-1]}{days[d-1]}"
        return ""
