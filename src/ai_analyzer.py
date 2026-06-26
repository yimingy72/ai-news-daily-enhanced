"""
AI 智能分析器
=============
利用大语言模型对资讯进行深度分析、评分排序和内容精炼。

功能:
  1. 相关性评分 — 判断资讯与 AI 行业的相关程度 (0-10)
  2. 重要性评分 — 判断资讯的行业影响力和价值 (0-10)
  3. 内容精炼   — 生成精简的中文摘要
  4. 智能分类   — 自动归类
  5. 智能排序   — 综合评分排序，输出 Top N 精选

支持的 LLM 服务（OpenAI 兼容接口）:
  - DeepSeek (deepseek-chat)  [默认]
  - OpenAI (gpt-4o-mini)
  - 阿里通义千问 (qwen-plus)
  - Kimi (moonshot-v1-8k)
  - 零一万物 (yi-large)

优雅降级:
  - 未配置 API Key → 跳过 AI 分析，使用规则评分回退
  - API 调用失败 → 单批跳过，使用规则评分
  - 超时/限流 → 自动重试 + 降级

适配 Article dataclass。
"""
import json
import os
import re
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

import httpx
from loguru import logger

from .config import config
from .models import Article


# ======================================================================
#  Prompt 模板
# ======================================================================

BATCH_ANALYSIS_PROMPT = """你是一位资深的 AI 行业分析师。请对以下 AI 行业资讯进行分析评估。

## 评估标准

**相关性 (relevance, 0-10)**:
- 10: 核心 AI 技术突破、重大产品发布（如新模型发布、重要开源项目）
- 7-9: AI 行业重要动态（融资、政策、应用落地）
- 4-6: 与 AI 相关的科技新闻
- 1-3: 仅边缘提及 AI
- 0: 与 AI 无关

**重要性 (importance, 0-10)**:
- 10: 改变行业格局的里程碑事件
- 7-9: 影响广泛的重要事件（大厂新品、重大融资、政策法规）
- 4-6: 值得关注的行业动态
- 1-3: 一般性新闻
- 0: 无价值信息

## 待分析资讯

{articles_text}

## 输出要求

请以 JSON 数组格式输出，每条资讯对应一个对象：
```json
[
  {{
    "id": 0,
    "relevance": 8,
    "importance": 7,
    "summary_zh": "不超过80字的中文精炼摘要",
    "category": "技术突破|产品发布|行业动态|融资并购|政策法规|研究论文|开源项目|应用落地|人物观点|其他"
  }}
]
```

注意：
- id 对应资讯序号（从 0 开始）
- summary_zh 必须是中文，简洁概括核心信息
- 只输出 JSON 数组，不要其他内容"""


# ======================================================================
#  AI 分析器
# ======================================================================

class AIAnalyzer:
    """
    基于 LLM 的资讯智能分析器

    使用 OpenAI 兼容 API，支持多种国内外大模型服务。
    未配置 API Key 时自动降级为规则评分。
    """

    def __init__(self):
        ai_cfg = config.get_section("ai")
        self._api_key = ai_cfg.get("api_key", "") or os.environ.get("NEWS_AI_API_KEY", "")
        self._base_url = ai_cfg.get("base_url", "https://api.deepseek.com/v1")
        self._model = ai_cfg.get("model", "deepseek-chat")
        self._top_n = ai_cfg.get("top_n", 20)
        self._batch_size = ai_cfg.get("batch_size", 10)
        self._timeout = ai_cfg.get("timeout", 60)
        self._max_retries = ai_cfg.get("max_retries", 2)
        self._enabled = bool(self._api_key)

        # 权重配置
        weights = ai_cfg.get("weights", {})
        self._w_relevance = weights.get("relevance", 0.4)
        self._w_importance = weights.get("importance", 0.4)
        self._w_recency = weights.get("recency", 0.2)

    @property
    def enabled(self) -> bool:
        """是否启用 AI 分析（需要配置 API Key）"""
        return self._enabled

    # ------------------------------------------------------------------
    #  公共接口
    # ------------------------------------------------------------------

    async def analyze_and_rank(self, articles: List[Article]) -> List[Article]:
        """
        对资讯列表进行 AI 分析、评分、排序，返回 Top N 精选

        Args:
            articles: 过滤后的 Article 列表

        Returns:
            评分排序后的 Top N Article 列表
        """
        if not self._enabled:
            logger.info("🤖 AI 分析未启用（未配置 API Key），使用规则评分降级")
            return self._fallback_rank(articles)

        if not articles:
            return []

        logger.info(f"🧠 开始 AI 智能分析: {len(articles)} 条资讯 → 精选 Top {self._top_n}")

        # 分批调用 LLM
        all_scores: Dict[int, Dict] = {}
        batches = [
            articles[i:i + self._batch_size]
            for i in range(0, len(articles), self._batch_size)
        ]

        for batch_idx, batch in enumerate(batches):
            global_start = batch_idx * self._batch_size
            logger.info(f"   📊 分析批次 {batch_idx + 1}/{len(batches)} ({len(batch)} 条)")
            try:
                batch_scores = await self._analyze_batch(batch, global_start)
                all_scores.update(batch_scores)
            except Exception as e:
                logger.warning(f"   ⚠️ 批次 {batch_idx + 1} 分析失败: {e}")
                # 对失败批次使用规则评分
                for i in range(len(batch)):
                    global_idx = global_start + i
                    if global_idx not in all_scores:
                        all_scores[global_idx] = self._rule_score(batch[i])

        # 填充评分到 Article
        for idx, art in enumerate(articles):
            score_data = all_scores.get(idx, self._rule_score(art))
            art.ai_relevance = score_data.get("relevance", 5)
            art.ai_importance = score_data.get("importance", 5)
            art.ai_summary = score_data.get("summary_zh", art.summary[:80])
            art.ai_category = score_data.get("category", "其他")

            # 综合评分
            recency_score = self._calc_recency_score(art)
            art.ai_score = round(
                art.ai_relevance * self._w_relevance
                + art.ai_importance * self._w_importance
                + recency_score * self._w_recency,
                2,
            )

            # 显示用评分
            art.ai_display_score = f"⭐{art.ai_score:.1f}"

        # 按综合评分排序
        articles.sort(key=lambda a: a.ai_score, reverse=True)

        # 取 Top N
        top_n = articles[:self._top_n]
        if top_n:
            logger.info(
                f"🏆 AI 精选完成: {len(articles)} → {len(top_n)} 条 "
                f"(评分范围 {top_n[-1].ai_score:.1f} ~ {top_n[0].ai_score:.1f})"
            )
        return top_n

    # ------------------------------------------------------------------
    #  LLM 调用
    # ------------------------------------------------------------------

    async def _analyze_batch(
        self, batch: List[Article], start_idx: int
    ) -> Dict[int, Dict]:
        """分析一批资讯"""
        # 构造输入文本
        articles_text = ""
        for i, art in enumerate(batch):
            articles_text += f"\n---\n**[{i}] {art.title}**\n"
            articles_text += f"来源: {art.source_name} | 时间: {art.display_published}"
            if art.tags:
                articles_text += f" | 标签: {', '.join(art.tags[:5])}"
            articles_text += f"\n摘要: {art.summary[:300]}\n"

        prompt = BATCH_ANALYSIS_PROMPT.format(articles_text=articles_text)

        # 调用 LLM
        response_text = await self._call_llm(prompt)
        if not response_text:
            return {}

        # 解析结果
        results: Dict[int, Dict] = {}
        try:
            json_text = response_text
            # 提取 JSON（处理 markdown 代码块包裹）
            if "```" in json_text:
                match = re.search(
                    r'```(?:json)?\s*\n?(.*?)\n?```', json_text, re.DOTALL
                )
                if match:
                    json_text = match.group(1)

            scores_list = json.loads(json_text.strip())

            for item in scores_list:
                local_id = item.get("id", -1)
                if 0 <= local_id < len(batch):
                    global_id = start_idx + local_id
                    results[global_id] = {
                        "relevance": min(10, max(0, item.get("relevance", 5))),
                        "importance": min(10, max(0, item.get("importance", 5))),
                        "summary_zh": item.get("summary_zh", ""),
                        "category": item.get("category", "其他"),
                    }
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"   ⚠️ LLM 返回解析失败: {e}")

        return results

    async def _call_llm(self, prompt: str) -> Optional[str]:
        """调用 OpenAI 兼容 API"""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一位专业的AI行业资讯分析师，擅长评估新闻的价值和重要性。请严格按照JSON格式输出。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        url = f"{self._base_url.rstrip('/')}/chat/completions"

        for attempt in range(1, self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()

                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return content.strip()

            except httpx.TimeoutException:
                logger.warning(f"   ⏱️ LLM 请求超时 (尝试 {attempt}/{self._max_retries})")
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 429:
                    wait = min(2**attempt, 10)
                    logger.warning(
                        f"   🚦 LLM 限流，等待 {wait}s (尝试 {attempt}/{self._max_retries})"
                    )
                    await asyncio.sleep(wait)
                elif status in (401, 403):
                    logger.error(f"   🔑 API Key 无效或权限不足 (HTTP {status})")
                    return None
                else:
                    logger.warning(
                        f"   ❌ LLM 请求失败: HTTP {status} (尝试 {attempt}/{self._max_retries})"
                    )
            except Exception as e:
                logger.warning(
                    f"   ❌ LLM 调用异常: {e} (尝试 {attempt}/{self._max_retries})"
                )

        return None

    # ------------------------------------------------------------------
    #  规则评分（降级方案）
    # ------------------------------------------------------------------

    def _fallback_rank(self, articles: List[Article]) -> List[Article]:
        """无 LLM 时的规则评分降级方案"""
        for art in articles:
            score_data = self._rule_score(art)
            art.ai_relevance = score_data["relevance"]
            art.ai_importance = score_data["importance"]
            art.ai_summary = art.summary[:80]
            art.ai_category = "其他"

            recency_score = self._calc_recency_score(art)
            art.ai_score = round(
                art.ai_relevance * self._w_relevance
                + art.ai_importance * self._w_importance
                + recency_score * self._w_recency,
                2,
            )
            art.ai_display_score = f"⭐{art.ai_score:.1f}"

        articles.sort(key=lambda a: a.ai_score, reverse=True)
        top_n = articles[:self._top_n]
        logger.info(f"📋 规则评分完成: {len(articles)} → {len(top_n)} 条（降级模式）")
        return top_n

    @staticmethod
    def _rule_score(article: Article) -> Dict:
        """基于规则的评分（不依赖 LLM）"""
        title = article.title.lower()
        summary = article.summary.lower()
        text = f"{title} {summary}"
        source = article.source_name.lower()

        # 相关性评分
        relevance = 3  # 基线（已通过关键词过滤）

        high_relevance_kw = [
            "大模型", "llm", "gpt", "claude", "gemini", "transformer",
            "openai", "deepseek", "大语言模型", "language model",
            "neural network", "深度学习", "deep learning",
            "agi", "多模态", "multimodal", "开源模型",
        ]
        mid_relevance_kw = [
            "ai", "人工智能", "artificial intelligence", "机器学习",
            "machine learning", "agent", "算力", "芯片", "gpu",
            "nvidia", "机器人", "自动驾驶",
        ]

        for kw in high_relevance_kw:
            if kw in text:
                relevance = min(10, relevance + 2)
                break
        for kw in mid_relevance_kw:
            if kw in text:
                relevance = min(10, relevance + 1)
                break

        # 重要性评分
        importance = 3

        # 权威来源加分
        authority_sources = [
            "机器之心", "量子位", "36氪", "techcrunch", "the verge",
            "openai", "anthropic", "deepmind", "新智元",
        ]
        for src in authority_sources:
            if src in source:
                importance += 2
                break

        # 重大事件关键词加分
        importance_kw = [
            "发布", "发布了", "推出", "launch", "release", "announce",
            "融资", "收购", "亿", "billion", "million",
            "突破", "首次", "最新", "重大", "里程碑",
            "开源", "open source", "免费",
        ]
        for kw in importance_kw:
            if kw in text:
                importance = min(10, importance + 1)

        importance = min(10, importance)

        return {
            "relevance": relevance,
            "importance": importance,
            "summary_zh": "",
            "category": "其他",
        }

    @staticmethod
    def _calc_recency_score(article: Article) -> float:
        """计算时效性评分 (0-10)"""
        if not article.published:
            return 5.0
        try:
            pub_dt = article.published
            if pub_dt.tzinfo:
                pub_dt = pub_dt.replace(tzinfo=None)
            hours_ago = (datetime.now() - pub_dt).total_seconds() / 3600
            if hours_ago <= 2:
                return 10.0
            elif hours_ago <= 6:
                return 8.0
            elif hours_ago <= 12:
                return 6.0
            elif hours_ago <= 24:
                return 4.0
            elif hours_ago <= 48:
                return 2.0
            else:
                return 1.0
        except Exception:
            return 5.0
