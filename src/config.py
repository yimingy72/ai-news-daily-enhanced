"""
配置管理器
==========
从 YAML 文件加载配置，支持环境变量覆盖和默认值回退。

特性：
  - YAML 格式配置文件
  - 环境变量覆盖（NEWS_ 前缀，双下划线表示层级）
  - 点号路径访问：config.get("ai.top_n")
  - 默认值回退（配置文件缺失不崩溃）
"""
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


# 默认配置（当配置文件不存在时使用）
DEFAULT_CONFIG = {
    "schedule": {
        "morning_hour": 8,
        "morning_minute": 0,
        "evening_hour": 20,
        "evening_minute": 0,
        "timezone": "Asia/Shanghai",
    },
    "output": {
        "dir": "./output",
        "data_dir": "./data",
        "filename_format": "AI简讯_{date}.md",
        "append_if_exists": True,
    },
    "sources": {
        "request_timeout": 30,
        "max_articles_per_source": 15,
        "user_agent": "Mozilla/5.0",
        "rss_feeds": [],
        "web_scrape": [],
    },
    "categories": {
        "chinese_ai": "🇨🇳 国内 AI 媒体",
        "foreign_official": "🏢 国际公司官方",
        "foreign_researcher": "👨‍🔬 国际研究员",
        "foreign_media": "📰 国际媒体",
    },
    "filter": {
        "keywords_include": ["AI", "人工智能", "machine learning"],
        "keywords_exclude": ["广告"],
        "max_age_hours": 72,
        "deduplicate": True,
    },
    "ai": {
        "api_key": "",
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-haiku-4-5-20251001",
        "top_n": 20,
        "batch_size": 10,
        "timeout": 60,
        "max_retries": 2,
        "weights": {"relevance": 0.4, "importance": 0.4, "recency": 0.2},
    },
    "logging": {
        "level": "INFO",
        "file": "./logs/ai-news-daily.log",
    },
}


class Config:
    """
    全局配置管理器（单例模式）

    用法:
        from config import config
        top_n = config.get("ai.top_n", 20)
        src_cfg = config.get_section("sources")
    """

    _instance: Optional["Config"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.project_root = self._find_project_root()
        self._data: Dict[str, Any] = {}
        self._load()
        self._apply_env_overrides()
        self._initialized = True

    # ------------------------------------------------------------------
    #  公共 API
    # ------------------------------------------------------------------

    def get(self, path: str, default: Any = None) -> Any:
        """
        通过点号路径获取配置值

        Args:
            path: 点号分隔的路径，如 "ai.top_n"
            default: 默认值

        Returns:
            配置值
        """
        keys = path.split(".")
        node = self._data
        for key in keys:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                # 也尝试从默认配置查找
                d_node = DEFAULT_CONFIG
                for k in keys:
                    if isinstance(d_node, dict) and k in d_node:
                        d_node = d_node[k]
                    else:
                        return default
                return d_node
        return node

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        获取整个配置区块

        Args:
            section: 区块名

        Returns:
            配置字典
        """
        return self._data.get(section, DEFAULT_CONFIG.get(section, {}))

    # ------------------------------------------------------------------
    #  内部方法
    # ------------------------------------------------------------------

    def _find_project_root(self) -> Path:
        """查找项目根目录"""
        return Path(__file__).parent.parent

    def _load(self):
        """加载 YAML 配置文件"""
        config_path = self.project_root / "config" / "settings.yaml"

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self._data = yaml.safe_load(f) or {}
            except Exception as e:
                print(f"⚠️ 配置文件加载失败: {e}，使用默认配置")
                self._data = dict(DEFAULT_CONFIG)
        else:
            print("⚠️ 配置文件不存在，使用默认配置")
            self._data = dict(DEFAULT_CONFIG)

    def _apply_env_overrides(self):
        """
        应用环境变量覆盖

        支持格式:
          NEWS_SCHEDULE__MORNING_HOUR=9
          NEWS_AI__API_KEY=sk-xxx
          (双下划线表示层级，单下划线保留在键名中)
        """
        for key, value in os.environ.items():
            if not key.startswith("NEWS_"):
                continue

            # 去掉 NEWS_ 前缀，双下划线分隔层级
            suffix = key[5:].lower()
            parts = suffix.split("__")

            # 类型转换
            typed_value = self._convert_value(value)

            # 写入嵌套字典
            self._set_nested(self._data, parts, typed_value)

    @staticmethod
    def _set_nested(data: dict, keys: list, value: Any):
        """向嵌套字典写入值"""
        for key in keys[:-1]:
            if key not in data:
                data[key] = {}
            if not isinstance(data[key], dict):
                data[key] = {}
            data = data[key]
        data[keys[-1]] = value

    @staticmethod
    def _convert_value(value: str) -> Any:
        """尝试将环境变量字符串转换为合适的类型"""
        # 布尔值
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # 整数
        try:
            return int(value)
        except ValueError:
            pass

        # 浮点数
        try:
            return float(value)
        except ValueError:
            pass

        return value


# 全局单例
config = Config()
