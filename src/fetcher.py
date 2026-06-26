"""
增强型数据抓取引擎
==================
从多个数据源并发获取 AI 行业资讯。

支持的数据源类型:
  1. RSS 订阅源 — 通过 feedparser 解析
  2. 网页抓取   — 通过 BeautifulSoup 解析 + jina.ai 降级

降级策略:
  RSS 失败 → 跳过
  网页抓取失败 → jina.ai 降级 → 跳过（永不阻塞）

每条资讯输出为 Article dataclass。
"""
import asyncio
import hashlib
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from .config import config
from .models import Article, FetchResult

# 尝试导入 feedparser
try:
    import feedparser
except ImportError:
    feedparser = None
    logger.warning("feedparser 未安装，RSS 抓取将不可用")


class ContentFetcher:
    """
    增强型资讯抓取引擎

    特性:
      - RSS + 网页抓取双模式
      - jina.ai 三级降级
      - 多策略标题提取
      - 正文内容增强抓取
      - 错误隔离（单源失败不影响其他）
    """

    def __init__(self):
        src_cfg = config.get_section("sources")
        self._timeout = src_cfg.get("request_timeout", 30)
        self._max_per_source = src_cfg.get("max_articles_per_source", 15)
        self._user_agent = src_cfg.get("user_agent", "Mozilla/5.0")
        self._seen_urls: Set[str] = set()

        # 分类映射
        self.categories = config.get_section("categories")

    # ------------------------------------------------------------------
    #  公共接口
    # ------------------------------------------------------------------

    async def fetch_all(self, days_back: int = 2) -> List[Article]:
        """
        从所有已启用数据源并发抓取

        Args:
            days_back: 向前抓取天数

        Returns:
            去重后的 Article 列表
        """
        src_cfg = config.get_section("sources")
        tasks = []

        # RSS 源
        for feed in src_cfg.get("rss_feeds", []):
            if feed.get("enabled", True):
                tasks.append(self._safe_fetch_source(feed, "rss", days_back))

        # 网页抓取源
        for target in src_cfg.get("web_scrape", []):
            if target.get("enabled", True):
                tasks.append(self._safe_fetch_source(target, "web", days_back))

        # 并发执行
        results: List[FetchResult] = await asyncio.gather(*tasks, return_exceptions=True)

        # 合并结果
        all_articles: List[Article] = []
        success_count = 0
        fail_count = 0

        for result in results:
            if isinstance(result, Exception):
                fail_count += 1
                logger.error(f"抓取任务异常: {result}")
            elif isinstance(result, FetchResult):
                if result.success:
                    all_articles.extend(result.articles)
                    success_count += 1
                else:
                    fail_count += 1

        # 去重
        unique = self._deduplicate(all_articles)
        logger.info(
            f"抓取完成: {len(all_articles)} 条原始 → {len(unique)} 条去重 "
            f"(成功 {success_count} 源, 失败 {fail_count} 源)"
        )
        return unique

    # ------------------------------------------------------------------
    #  安全抓取包装器
    # ------------------------------------------------------------------

    async def _safe_fetch_source(
        self, source_cfg: Dict, source_type: str, days_back: int
    ) -> FetchResult:
        """带错误保护的源抓取"""
        name = source_cfg.get("name", source_cfg.get("url", ""))
        url = source_cfg.get("url", "")
        try:
            if source_type == "rss":
                articles = await self._fetch_rss(source_cfg, days_back)
            else:
                articles = await self._fetch_web(source_cfg, days_back)
            return FetchResult(articles=articles, source_name=name, source_url=url, success=True)
        except Exception as e:
            logger.error(f"[{name}] 抓取失败: {e}")
            return FetchResult(
                articles=[], source_name=name, source_url=url, success=False, error=str(e)
            )

    # ------------------------------------------------------------------
    #  RSS 抓取
    # ------------------------------------------------------------------

    async def _fetch_rss(self, feed_cfg: Dict, days_back: int) -> List[Article]:
        """抓取单个 RSS 源"""
        if feedparser is None:
            raise RuntimeError("feedparser 未安装")

        url = feed_cfg.get("rss_url") or feed_cfg.get("url", "")
        name = feed_cfg.get("name", url)
        source_url = feed_cfg.get("url", url)
        category = feed_cfg.get("category", "")
        cutoff_date = datetime.now() - timedelta(days=days_back)

        # 获取 RSS 内容
        async with httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True
        ) as client:
            resp = await client.get(url, headers={"User-Agent": self._user_agent})
            resp.raise_for_status()

        # 在线程池中解析（feedparser 是同步的）
        feed = await asyncio.to_thread(feedparser.parse, resp.text)

        if feed.bozo:
            logger.debug(f"[RSS] {name} 解析警告: {feed.bozo_exception}")

        articles: List[Article] = []
        for entry in feed.entries[: self._max_per_source]:
            try:
                title = (entry.get("title") or "").strip()
                link = (entry.get("link") or "").strip()
                if not title or len(title) < 5 or not link:
                    continue

                # 解析发布时间
                published = self._parse_rss_date(entry)
                if published and published < cutoff_date:
                    continue

                # 提取摘要
                summary = self._extract_rss_summary(entry)

                # 提取标签
                tags = []
                if hasattr(entry, "tags"):
                    tags = [t.get("term", "") for t in entry.tags if t.get("term")]

                articles.append(Article(
                    title=self._clean_text(title),
                    url=link,
                    source_name=name,
                    source_url=source_url,
                    category=category,
                    summary=summary,
                    published=published or datetime.now(),
                    author=entry.get("author"),
                    tags=tags,
                ))
            except Exception as e:
                logger.debug(f"[RSS] {name} 条目解析失败: {e}")
                continue

        logger.info(f"[RSS] {name}: 获取 {len(articles)} 条")
        return articles

    # ------------------------------------------------------------------
    #  网页抓取
    # ------------------------------------------------------------------

    async def _fetch_web(self, target: Dict, days_back: int) -> List[Article]:
        """抓取单个网页源（含 jina.ai 降级）"""
        url = target.get("url", "")
        name = target.get("name", url)
        category = target.get("category", "")
        selector = target.get("selector", "article, .post, .entry, [class*='article']")
        link_selector = target.get("link_selector", "a[href]")

        if not url:
            return []

        # --- 第一级: 直接抓取列表页 ---
        articles = await self._scrape_listing_page(url, name, category, selector, link_selector)

        # --- 第二级: 降级到 jina.ai ---
        if not articles:
            logger.info(f"[Web] {name}: 直接抓取为空，尝试 jina.ai 降级")
            articles = await self._fetch_jina_fallback(url, name, category)

        logger.info(f"[Web] {name}: 获取 {len(articles)} 条")
        return articles

    async def _scrape_listing_page(
        self, url: str, name: str, category: str, selector: str, link_selector: str
    ) -> List[Article]:
        """抓取列表页，提取文章链接和信息"""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout), follow_redirects=True
        ) as client:
            try:
                resp = await client.get(url, headers={"User-Agent": self._user_agent})
                if resp.status_code != 200:
                    logger.debug(f"[Web] {name} HTTP {resp.status_code}")
                    return []
            except Exception as e:
                logger.debug(f"[Web] {name} 请求失败: {e}")
                return []

        soup = BeautifulSoup(resp.text, "lxml")

        # 查找文章元素
        article_elements = self._find_article_elements(soup, selector)

        # 提取文章信息
        article_infos = []
        for elem in article_elements[: self._max_per_source]:
            try:
                info = self._extract_article_info(elem, url, link_selector)
                if info:
                    article_infos.append(info)
            except Exception:
                continue

        if not article_infos:
            return []

        # 获取正文摘要（并发请求前 5 篇）
        is_foreign = category in ("foreign_official", "foreign_researcher", "foreign_media")
        articles: List[Article] = []

        # 限制并发数
        detail_tasks = []
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15), follow_redirects=True
        ) as client:
            for info in article_infos[:8]:
                detail_tasks.append(
                    self._fetch_article_detail(client, info, name, url, category, is_foreign)
                )
            results = await asyncio.gather(*detail_tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Article):
                articles.append(result)
            elif isinstance(result, Exception):
                logger.debug(f"[Web] {name} 详情抓取异常: {result}")

        return articles

    async def _fetch_article_detail(
        self,
        client: httpx.AsyncClient,
        info: Dict,
        source_name: str,
        source_url: str,
        category: str,
        is_foreign: bool,
    ) -> Optional[Article]:
        """获取单篇文章的详细内容（摘要+正文）"""
        article_url = info.get("url", "")
        title = info.get("title", "")

        if not title or len(title) < 5:
            return None

        # 尝试获取正文摘要
        content = ""
        if article_url:
            content = await self._fetch_jina_content(client, article_url)

        # 如果 jina 没拿到，尝试从页面直接提取
        if not content and "summary" in info:
            content = info.get("summary", "")

        # 过滤无效内容
        if not content or len(content) < 80:
            logger.debug(f"[Web] {source_name}: 内容太短 ({len(content) if content else 0} 字符) -> {title[:40]}")
            # 仍然保留，但标记
            content = info.get("summary", "") or title

        # 国外来源加标记
        if is_foreign and content:
            summary_text = f"📝 {content[:400]}"
        else:
            summary_text = content[:400]

        return Article(
            title=self._clean_text(title),
            url=article_url,
            source_name=source_name,
            source_url=source_url,
            category=category,
            summary=summary_text,
            published=datetime.now(),
        )

    # ------------------------------------------------------------------
    #  jina.ai 降级方案
    # ------------------------------------------------------------------

    async def _fetch_jina_content(
        self, client: httpx.AsyncClient, url: str, max_length: int = 500
    ) -> str:
        """使用 jina.ai 获取文章内容（清洗后返回纯净正文）"""
        if not url:
            return ""

        try:
            jina_url = f"https://r.jina.ai/{url}"
            resp = await client.get(jina_url)
            if resp.status_code == 200:
                text = resp.text
                lines = text.split("\n")
                content_lines = []

                # 跳过的元数据行
                skip_prefixes = (
                    "Title:", "URL Source:", "URL:", "Markdown Content:",
                    "---", "Published:", "Author:", "Crawled:", "Published Time:",
                    "Warning:", "Error:",
                )

                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if any(stripped.startswith(p) for p in skip_prefixes):
                        continue
                    content_lines.append(stripped)

                content = " ".join(content_lines)
                # 清理多余的空白
                content = " ".join(content.split())
                return content[:max_length] if len(content) > 50 else ""
        except Exception:
            pass

        return ""

    async def _fetch_jina_fallback(
        self, url: str, name: str, category: str
    ) -> List[Article]:
        """降级：用 jina.ai 提取整页内容"""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15), follow_redirects=True
        ) as client:
            try:
                jina_url = f"https://r.jina.ai/{url}"
                resp = await client.get(jina_url)
                if resp.status_code != 200:
                    return []

                text = resp.text
                lines = text.split("\n")
                title = ""
                content_lines = []

                skip_prefixes = (
                    "URL Source:", "Markdown Content:", "Published:",
                    "Author:", "Crawled:", "URL:", "Published Time:",
                    "Warning:", "Error:", "Image:", "Images:",
                )

                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if stripped.startswith("Title: "):
                        title = stripped[7:].strip()
                    elif stripped.startswith("---"):
                        continue
                    elif any(stripped.startswith(p) for p in skip_prefixes):
                        continue
                    else:
                        content_lines.append(stripped)

                if not title or len(title) < 5:
                    return []

                content = " ".join(content_lines)
                content = " ".join(content.split())  # 清理多余空白
                if len(content) < 80:
                    return []

                is_foreign = category in ("foreign_official", "foreign_researcher", "foreign_media")
                if is_foreign and content:
                    summary_text = f"📝 {content[:400]}"
                else:
                    summary_text = content[:400]

                return [Article(
                    title=self._clean_text(title),
                    url=url,
                    source_name=name,
                    source_url=url,
                    category=category,
                    summary=summary_text,
                    published=datetime.now(),
                )]
            except Exception:
                return []

    # ------------------------------------------------------------------
    #  HTML 解析工具方法
    # ------------------------------------------------------------------

    def _find_article_elements(self, soup: BeautifulSoup, selector: str) -> List:
        """查找文章元素（多策略）"""
        elements = []
        if selector:
            elements = soup.select(selector)

        if not elements:
            # 尝试常见选择器
            for sel in [
                "article", ".post", ".entry", ".blog-post",
                '[class*="post"]', '[class*="article"]', ".card", ".item",
                ".news-item", ".story", '[class*="story"]',
            ]:
                elements = soup.select(sel)
                if elements:
                    break

        return elements

    def _extract_article_info(
        self, elem: BeautifulSoup, base_url: str, link_selector: str
    ) -> Optional[Dict]:
        """从 HTML 元素中提取文章信息（多策略标题提取）"""
        # 多策略标题提取
        title = ""
        # 策略 1: 查找标题标签
        for tag in ["h1", "h2", "h3", "h4"]:
            heading = elem.find(tag)
            if heading:
                title = heading.get_text(strip=True)
                if len(title) > 5:
                    break

        # 策略 2: 查找标题 class
        if not title or len(title) < 5:
            for cls in ["title", "headline", "entry-title", "post-title"]:
                title_elem = elem.find(class_=lambda x: x and cls in x.lower())
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if len(title) > 5:
                        break

        # 策略 3: 查找链接文本
        if not title or len(title) < 5:
            link = elem.find("a")
            if link:
                title = link.get_text(strip=True)

        if not title or len(title) < 5:
            return None

        # 查找链接
        link_elem = None
        if link_selector:
            link_elem = elem.select_one(link_selector)
        if not link_elem:
            link_elem = elem.find("a", href=True)

        article_url = ""
        if link_elem:
            article_url = link_elem.get("href", "")
            if article_url and not article_url.startswith("http"):
                article_url = urljoin(base_url, article_url)

        # 跳过非文章链接
        if article_url:
            skip_patterns = ["/page/", "/tag/", "/category/", "/author/", "#"]
            if any(p in article_url for p in skip_patterns):
                article_url = ""

        # 查找摘要
        summary = ""
        for sel in ["p", ".summary", ".excerpt", ".description", '[class*="desc"]']:
            desc_elem = elem.select_one(sel)
            if desc_elem:
                summary = desc_elem.get_text(strip=True)
                if len(summary) > 20:
                    break

        return {
            "title": title,
            "url": article_url,
            "summary": summary[:300],
        }

    # ------------------------------------------------------------------
    #  RSS 解析工具
    # ------------------------------------------------------------------

    def _parse_rss_date(self, entry: Dict) -> Optional[datetime]:
        """从 RSS entry 解析发布时间"""
        # 优先使用结构化时间
        for field in ["published_parsed", "updated_parsed", "created_parsed"]:
            if field in entry and entry[field]:
                try:
                    return datetime(*entry[field][:6])
                except Exception:
                    continue

        # 尝试字符串时间
        for field in ["published", "updated", "created", "pubDate"]:
            if field in entry and entry[field]:
                try:
                    from dateutil import parser as dp
                    return dp.parse(str(entry[field]))
                except Exception:
                    continue

        return None

    def _extract_rss_summary(self, entry: Dict) -> str:
        """从 RSS entry 提取摘要"""
        for field in ["summary", "description", "content", "subtitle"]:
            if field in entry:
                text = entry[field]
                if isinstance(text, list) and text:
                    text = text[0].get("value", str(text[0]))

                # 去除 HTML 标签
                clean = re.sub(r"<[^>]+>", "", str(text))
                clean = re.sub(r"\s+", " ", clean).strip()
                return clean[:500]

        return ""

    # ------------------------------------------------------------------
    #  通用工具
    # ------------------------------------------------------------------

    def _deduplicate(self, articles: List[Article]) -> List[Article]:
        """基于 URL + 标题的去重"""
        unique: List[Article] = []
        for art in articles:
            key = hashlib.md5(f"{art.url}|{art.title}".encode()).hexdigest()
            if key not in self._seen_urls:
                self._seen_urls.add(key)
                unique.append(art)
        return unique

    @staticmethod
    def _clean_text(text: str) -> str:
        """清洗文本"""
        if not text:
            return ""
        text = " ".join(text.split())
        text = text.replace("\x00", "")
        return text.strip()
