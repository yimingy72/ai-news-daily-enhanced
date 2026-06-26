"""
核心数据模型
============
Article、ScoreData、Source 等 dataclass 定义，
贯穿整个数据处理流水线。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class ScoreData:
    """AI 评分数据"""
    relevance: int = 5       # 相关性评分 0-10
    importance: int = 5      # 重要性评分 0-10
    summary_zh: str = ""     # AI 生成的中文摘要
    category: str = "其他"   # AI 分类标签


@dataclass
class Article:
    """单篇资讯"""
    title: str                               # 标题
    url: str                                 # 原文链接
    source_name: str                         # 来源名称（如"机器之心"）
    source_url: str = ""                     # 来源网址
    category: str = ""                       # 来源分类（chinese_ai / foreign_official 等）
    summary: str = ""                        # 摘要/正文片段
    published: Optional[datetime] = None     # 发布时间
    author: Optional[str] = None             # 作者
    tags: List[str] = field(default_factory=list)

    # AI 分析结果（由 AIAnalyzer 填充）
    ai_score: float = 0.0
    ai_relevance: int = 0
    ai_importance: int = 0
    ai_summary: str = ""
    ai_category: str = ""
    ai_display_score: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于 JSON 输出）"""
        return {
            "title": self.title,
            "url": self.url,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "category": self.category,
            "summary": self.summary,
            "published": self.published.isoformat() if self.published else "",
            "author": self.author,
            "tags": self.tags,
            "ai_score": self.ai_score,
            "ai_relevance": self.ai_relevance,
            "ai_importance": self.ai_importance,
            "ai_summary": self.ai_summary,
            "ai_category": self.ai_category,
            "ai_display_score": self.ai_display_score,
        }

    @property
    def display_published(self) -> str:
        """格式化的发布时间"""
        if self.published:
            return self.published.strftime("%Y-%m-%d %H:%M")
        return ""

    @property
    def has_ai_score(self) -> bool:
        """是否有 AI 评分"""
        return self.ai_score > 0


@dataclass
class Source:
    """数据源配置"""
    name: str
    url: str
    type: str = "rss"         # "rss" | "web"
    category: str = ""
    selector: Optional[str] = None   # CSS 选择器（web 类型）
    link_selector: Optional[str] = None
    rss_url: Optional[str] = None    # RSS URL（如与 url 不同）
    enabled: bool = True


@dataclass
class FetchResult:
    """单次抓取结果"""
    articles: List[Article]
    source_name: str
    source_url: str = ""
    success: bool = True
    error: Optional[str] = None
