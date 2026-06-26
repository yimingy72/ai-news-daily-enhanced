"""
内容翻译器
==========
将英文资讯翻译为中文，确保输出可读性。

策略:
  1. 配置了 LLM API Key → 批量调用 LLM 翻译
  2. 未配置 → 保留原文（标记为英文来源）
"""
import os
import re
import json
import asyncio
from typing import Dict, List
from loguru import logger
import httpx

from .config import config
from .models import Article


TRANSLATE_PROMPT = """你是一位专业的科技翻译。请将以下英文资讯标题和摘要翻译成简洁通顺的中文。

## 要求
- 标题翻译要准确、简洁
- 摘要翻译控制在 80 字以内
- 保留专业术语（如 GPT、LLM、API 等不翻译）
- 公司名和产品名保持原文

## 输入（JSON 数组）

{items_json}

## 输出

请输出一个 JSON 数组，每个元素对应一条输入：
```json
[
  {{"id": 0, "title_zh": "中文标题", "summary_zh": "中文摘要80字内"}}
]
```
只输出 JSON，不要其他内容。"""


class Translator:
    """AI 驱动的英中翻译器"""

    def __init__(self):
        ai_cfg = config.get_section("ai")
        self._api_key = ai_cfg.get("api_key", "") or os.environ.get("NEWS_AI_API_KEY", "")
        self._base_url = ai_cfg.get("base_url", "https://api.deepseek.com/v1")
        self._model = ai_cfg.get("model", "deepseek-chat")
        self._timeout = ai_cfg.get("timeout", 60)
        self._enabled = bool(self._api_key)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def translate(self, articles: List[Article]) -> List[Article]:
        """翻译文章列表中的英文内容为中文"""
        if not self._enabled:
            logger.info("🌐 翻译未启用（未配置 API Key），保留原文")
            return articles

        # 筛选需要翻译的文章（英文标题或摘要）
        needs_translate = []
        for i, art in enumerate(articles):
            if self._is_english(art.title) or self._is_english(art.summary):
                needs_translate.append((i, art))

        if not needs_translate:
            logger.info("🌐 所有内容已是中文，无需翻译")
            return articles

        logger.info(f"🌐 开始翻译 {len(needs_translate)} 条英文资讯")

        # 分批翻译
        batch_size = 15
        all_results: Dict[int, dict] = {}

        for batch_start in range(0, len(needs_translate), batch_size):
            batch = needs_translate[batch_start:batch_start + batch_size]
            try:
                batch_results = await self._translate_batch(batch)
                all_results.update(batch_results)
            except Exception as e:
                logger.warning(f"翻译批次失败: {e}")

        # 应用翻译结果
        for idx, art in enumerate(articles):
            if idx in all_results:
                result = all_results[idx]
                if result.get("title_zh"):
                    art.title = result["title_zh"]
                if result.get("summary_zh"):
                    art.summary = result["summary_zh"]
                if art.ai_summary and self._is_english(art.ai_summary):
                    art.ai_summary = result.get("summary_zh", art.ai_summary)

        translated_count = len(all_results)
        logger.info(f"🌐 翻译完成: {translated_count}/{len(needs_translate)} 条")
        return articles

    async def _translate_batch(self, batch: List[tuple]) -> Dict[int, dict]:
        """翻译一批文章"""
        items = []
        for idx, art in batch:
            items.append({
                "id": idx,
                "title": art.title,
                "summary": (art.ai_summary or art.summary)[:300],
            })

        prompt = TRANSLATE_PROMPT.format(items_json=json.dumps(items, ensure_ascii=False, indent=2))

        response_text = await self._call_llm(prompt)
        if not response_text:
            return {}

        try:
            json_text = response_text
            if "```" in json_text:
                match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', json_text, re.DOTALL)
                if match:
                    json_text = match.group(1)
            results = json.loads(json_text.strip())
            return {item["id"]: item for item in results if "id" in item}
        except Exception as e:
            logger.warning(f"翻译结果解析失败: {e}")
            return {}

    async def _call_llm(self, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": "你是一位专业的科技翻译，请严格按照JSON格式输出。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 4096,
        }
        url = f"{self._base_url.rstrip('/')}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"翻译 API 失败: {e}")
            return ""

    @staticmethod
    def _is_english(text: str) -> bool:
        """判断文本是否主要是英文"""
        if not text or len(text) < 5:
            return False
        # 统计 ASCII 字母占比
        ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
        total_letters = sum(1 for c in text if c.isalpha())
        if total_letters == 0:
            return False
        return ascii_letters / total_letters > 0.5
