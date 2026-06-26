"""
GitHub Trending 抓取器
======================
从 GitHub Trending 页面抓取本周十大热门项目，并翻译描述为中文。
"""
import json
import os
import re
from dataclasses import dataclass
from typing import List

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from .config import config


@dataclass
class TrendingRepo:
    """GitHub 热门项目"""
    owner: str
    name: str
    full_name: str
    description: str
    description_zh: str          # 中文翻译
    language: str
    stars_week: int              # 本周新增 star 数
    stars_total: int             # 总 star 数
    url: str


def _parse_stars(text: str) -> int:
    """解析 '15,793' 或 '15,793 stars this week' 为整数"""
    if not text:
        return 0
    m = re.search(r'[\d,]+', str(text))
    if m:
        return int(m.group().replace(',', ''))
    return 0


async def fetch_trending(language: str = "", since: str = "weekly") -> List[TrendingRepo]:
    """抓取 GitHub Trending 页面"""
    url = f"https://github.com/trending{('/' + language) if language else ''}?since={since}"
    logger.info(f"🔥 抓取 GitHub Trending: {url}")

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html",
            })
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        articles = soup.select("article.Box-row")
        repos: List[TrendingRepo] = []

        for art in articles[:10]:
            try:
                h2 = art.select_one("h2")
                if not h2:
                    continue
                full_name = h2.get_text(strip=True).replace("\n", "").replace(" ", "")
                parts = full_name.split("/")
                if len(parts) != 2:
                    continue

                desc_el = art.select_one("p")
                description = desc_el.get_text(strip=True) if desc_el else ""

                lang_el = art.select_one('[itemprop="programmingLanguage"]')
                lang_name = lang_el.get_text(strip=True) if lang_el else ""

                # 本周 star
                stars_el = art.select("span.d-inline-block.float-sm-right")
                week_stars = 0
                for s in stars_el:
                    week_stars = _parse_stars(s.get_text(strip=True))
                    if week_stars > 0:
                        break

                # 总 star
                total = 0
                for a in art.select('a[href*="/stargazers"]'):
                    n = _parse_stars(a.get_text(strip=True))
                    if n > total:
                        total = n

                repos.append(TrendingRepo(
                    owner=parts[0].strip(), name=parts[1].strip(),
                    full_name=full_name, description=description,
                    description_zh="", language=lang_name,
                    stars_week=week_stars, stars_total=total,
                    url=f"https://github.com/{full_name}",
                ))
            except Exception as e:
                logger.debug(f"解析 trending 条目失败: {e}")

        logger.info(f"🔥 GitHub Trending: {len(repos)} 个项目")
        return repos

    except Exception as e:
        logger.error(f"GitHub Trending 抓取失败: {e}")
        return []


async def translate_descriptions(repos: List[TrendingRepo]) -> List[TrendingRepo]:
    """用 DeepSeek 翻译项目描述为中文"""
    if not repos:
        return repos

    # 获取 API 配置
    ai_cfg = config.get_section("ai")
    api_key = ai_cfg.get("api_key", "") or os.environ.get("NEWS_AI_API_KEY", "")
    if not api_key:
        logger.info("🔥 翻译未启用（无 API Key），保留英文描述")
        return repos

    base_url = ai_cfg.get("base_url", "https://api.deepseek.com/v1")
    model = ai_cfg.get("model", "deepseek-chat")

    # 构建翻译请求
    items = [{"id": i, "desc": r.description} for i, r in enumerate(repos) if r.description]
    if not items:
        return repos

    prompt = f"""将以下 GitHub 项目描述翻译为简洁的中文（每条约40字以内，保留技术术语不翻译）：

{json.dumps(items, ensure_ascii=False, indent=2)}

输出 JSON 数组：[{{"id":0, "zh":"中文描述"}}, ...] 只输出 JSON。"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是专业的技术翻译，请只输出JSON数组。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 2048,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()

            # 提取 JSON
            if "```" in content:
                m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
                if m:
                    content = m.group(1)
            results = json.loads(content)

            for item in results:
                idx = item.get("id", -1)
                if 0 <= idx < len(repos):
                    repos[idx].description_zh = item.get("zh", "")

            logger.info(f"🔥 翻译完成: {len(results)} 条描述")
    except Exception as e:
        logger.warning(f"GitHub 描述翻译失败: {e}")

    return repos


def format_trending_section(repos: List[TrendingRepo]) -> str:
    """格式化热门项目为消息文本"""
    if not repos:
        return ""

    lines = ["🤖 本周十大 GitHub 热门项目", ""]
    for i, r in enumerate(repos, 1):
        # 优先用中文描述，清理英文描述
        desc = r.description_zh or r.description.strip()
        if not r.description_zh and len(desc) > 140:
            cut = desc.rfind(". ", 60, 130)
            if cut < 0:
                cut = desc.rfind(" — ", 80, 130)
            if cut < 0:
                cut = desc.rfind(" ", 100, 140)
            if cut > 60:
                desc = desc[:cut + 1]
            else:
                desc = desc[:140]

        lang_tag = f"[{r.language}] " if r.language else ""
        stars = f"总⭐{r.stars_total:,} 周增⭐{r.stars_week:,}" if r.stars_total else f"⭐{r.stars_week:,}"

        lines.append(f"  {i}、{r.full_name}  {lang_tag}{stars}")
        lines.append(f"  {desc}")
        lines.append("")

    return "\n".join(lines)
