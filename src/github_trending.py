"""
GitHub Trending 抓取器
======================
纯确定性抓取 GitHub Trending 本周热门项目。
翻译由 Agent 在 skill 中完成。
"""
import re
from dataclasses import dataclass
from typing import List

import httpx
from bs4 import BeautifulSoup
from loguru import logger


@dataclass
class TrendingRepo:
    owner: str
    name: str
    full_name: str
    description: str
    language: str
    stars_week: int
    stars_total: int
    url: str


def _parse_stars(text: str) -> int:
    if not text:
        return 0
    m = re.search(r'[\d,]+', str(text))
    return int(m.group().replace(',', '')) if m else 0


async def fetch_trending(language: str = "", since: str = "weekly") -> List[TrendingRepo]:
    url = f"https://github.com/trending{('/' + language) if language else ''}?since={since}"
    logger.info(f"🔥 GitHub Trending: {url}")

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html",
            })
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        repos = []
        for art in soup.select("article.Box-row")[:10]:
            try:
                h2 = art.select_one("h2")
                if not h2: continue
                fn = h2.get_text(strip=True).replace("\n", "").replace(" ", "")
                p = fn.split("/")
                if len(p) != 2: continue

                desc = art.select_one("p")
                desc_text = desc.get_text(strip=True) if desc else ""
                lang_el = art.select_one('[itemprop="programmingLanguage"]')
                lang = lang_el.get_text(strip=True) if lang_el else ""

                week = 0
                for s in art.select("span.d-inline-block.float-sm-right"):
                    week = _parse_stars(s.get_text(strip=True))
                    if week > 0: break

                total = 0
                for a in art.select('a[href*="/stargazers"]'):
                    n = _parse_stars(a.get_text(strip=True))
                    if n > total: total = n

                repos.append(TrendingRepo(
                    owner=p[0].strip(), name=p[1].strip(), full_name=fn,
                    description=desc_text, language=lang,
                    stars_week=week, stars_total=total,
                    url=f"https://github.com/{fn}",
                ))
            except Exception as e:
                logger.debug(f"解析 trending 失败: {e}")

        logger.info(f"🔥 GitHub Trending: {len(repos)} 个项目")
        return repos
    except Exception as e:
        logger.error(f"GitHub Trending 抓取失败: {e}")
        return []
