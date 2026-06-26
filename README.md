# 🤖 AI 简讯增强版 — AI News Daily Enhanced

融合 [ai-news-daily](https://github.com/Zero-Lzy/ai-news-daily)（成熟管道架构）和 [ai-daily-brief](https://github.com/M-qiangZhu/ai-daily-brief)（丰富数据源）两大项目的优势。

每天自动抓取 25+ 个 AI 行业数据源，经过过滤和 AI 评分，输出精美的 **Markdown 日报**。

---

## ✨ 特性

| 特性 | 说明 |
|------|------|
| ⏰ **定时抓取** | 默认每天 8:00 + 20:00 自动执行 |
| 📡 **25+ 数据源** | 国内媒体、大厂官方、研究员博客、国际媒体 |
| 🔍 **4 道过滤** | 关键词 → 排除词 → 时效性 → 标题去重 |
| 🧠 **AI 评分** | LLM 智能评分排序 + 规则引擎降级（支持 5 家服务商） |
| 📝 **精美 Markdown** | 结构化排版、评分可视、分类分组 |
| 📊 **JSON 数据** | 按日期拆分，支持二次开发 |
| 🚀 **零成本部署** | GitHub Actions 自动运行，无需服务器 |
| 🔧 **灵活配置** | YAML + 环境变量覆盖 |

---

## 📡 数据源

| 分类 | 来源 |
|------|------|
| 🇨🇳 国内 AI 媒体 | 机器之心、量子位、InfoQ AI、新智元、智东西、PaperWeekly、36氪AI、少数派AI、AIbase |
| 🏢 国际公司官方 | OpenAI Blog、Anthropic、Google DeepMind、Meta AI、Mistral AI |
| 👨‍🔬 国际研究员 | Andrej Karpathy、Lilian Weng、Simon Willison、Dario Amodei |
| 📰 国际媒体 | Hacker News、TechCrunch、The Verge、ArsTechnica、The Register、VentureBeat |

---

## 🚀 快速开始

```bash
cd ai-news-daily-enhanced
pip install -r requirements.txt

# 立即执行一次抓取
python main.py

# 启动本地定时调度（每天 8:00 + 20:00 自动运行）
python main.py --schedule

# 指定标签执行
python main.py --label "晚报"
```

### 启用 AI 智能分析

```bash
export NEWS_AI_API_KEY="sk-xxxxxxxxxxxxxxxx"
python main.py
```

支持的 LLM：DeepSeek（默认）、OpenAI、通义千问、Kimi、零一万物。

---

## 📖 输出示例

```
# 🤖 AI 行业简讯日报

> **2026年06月26日 周五** · 🌅 早报 · AI News Daily Enhanced

---

## 📊 今日概览

| 指标 | 详情 |
|------|------|
| 📄 精选文章 | **20** 篇 |
| 📡 数据来源 | **13** 个 |
| ⭐ 最高评分 | **7.2** 分 |
| 🧠 分析引擎 | 🧠 AI 大模型分析（deepseek-chat）|

---

## 🇨🇳 国内 AI 媒体

> 共 **2** 篇

**1.** `7.2分` ★★★★  [文章标题](https://example.com)

> 📡 机器之心 · 🕐 2026-06-26 08:30
>
> 摘要内容...

> `███████░░░`

**2.** `5.8分` ★★★  [另一篇文章](https://example.com)
...
```

---

## 🔧 配置

编辑 `config/settings.yaml`：

```yaml
# 修改执行时间
schedule:
  morning_hour: 9
  evening_hour: 21

# 添加/禁用数据源
sources:
  rss_feeds:
    - name: "我的源"
      url: "https://example.com/feed.xml"
      enabled: true

# 调整 AI 分析
ai:
  api_key: ""                    # 留空则使用规则降级
  model: "deepseek-chat"
  top_n: 20

# 过滤关键词
filter:
  keywords_include: ["AI", "大模型", "LLM"]
  keywords_exclude: ["广告", "促销"]
```

环境变量覆盖：`NEWS_AI__TOP_N=30` → `ai.top_n = 30`

---

## 📂 项目结构

```
ai-news-daily-enhanced/
├── main.py                  # 主入口
├── requirements.txt
├── config/settings.yaml     # 全局配置
├── src/
│   ├── models.py            # Article dataclass
│   ├── config.py            # 配置管理器
│   ├── fetcher.py           # 增强抓取引擎
│   ├── filter.py            # 4 道过滤器
│   ├── ai_analyzer.py       # AI 智能评分
│   ├── writer.py            # Markdown 生成器
│   ├── json_writer.py       # JSON 输出器
│   └── scheduler.py         # 定时调度
├── .github/workflows/
│   └── fetch-news.yml       # CI/CD 自动运行
├── data/                    # JSON 数据输出
├── output/                  # Markdown 日报输出
└── logs/                    # 运行日志
```

---

## 📜 License

MIT License

## 🙏 致谢

- [ai-news-daily](https://github.com/Zero-Lzy/ai-news-daily) — 管道架构、AI 分析
- [ai-daily-brief](https://github.com/M-qiangZhu/ai-daily-brief) — 数据源覆盖、抓取策略
