# 🤖 AI 简讯增强版

每天自动抓取 28 个 AI 行业数据源 + GitHub 热门项目，生成适合消息推送的精简中文日报。

**核心设计**：Python 只做确定性抓取和过滤，AI 评分、翻译、摘要等智能任务由当前 Agent 通过 [skill](../../.claude/skills/ai-news-daily/SKILL.md) 完成。无需配置任何 API Key，适配 Claude Code / Codex / Cursor 等任意 Agent。

---

## ✨ 特性

| 特性 | 说明 |
|------|------|
| 📡 **28 个数据源** | 国内媒体、大厂官方、研究员博客、国际媒体 |
| 🔍 **4 道过滤** | 关键词 → 排除词 → 时效性 → 标题去重 |
| 🧠 **Agent 智能分析** | 当前 Agent 直接评分、翻译、摘要，无需 API Key |
| 🔥 **GitHub 热门** | 每周十大热门项目，含星数和中英文描述 |
| 📱 **消息格式输出** | 纯文本日报，适合钉钉/微信/飞书推送 |
| 🚀 **零配置** | 无需 API Key，Python 脚本零 AI 依赖 |
| 🔧 **灵活配置** | YAML + 环境变量覆盖 |

---

## 📡 数据源

| 分类 | 来源 |
|------|------|
| 🇨🇳 国内 AI 媒体 | 量子位、36氪、雷锋网、少数派、AIbase |
| 🏢 国际公司官方 | OpenAI Blog、Anthropic、Google DeepMind、Meta AI、Mistral AI、Hugging Face |
| 👨‍🔬 国际研究员 | Andrej Karpathy、Lilian Weng、Simon Willison、Dario Amodei、arXiv |
| 📰 国际媒体 | TechCrunch、The Verge、ArsTechnica、ZDNet、Hacker News、VentureBeat、MIT Tech Review |

---

## 🚀 快速开始

```bash
cd ai-news-daily-enhanced
pip install -r requirements.txt

# 抓取数据（纯确定性，无需 API Key）
python main.py

# 然后由 Agent 读取 data/latest.json 完成评分翻译输出
```

**完整流程**：`python main.py` 抓取 → Agent 读 JSON → 评分 + 翻译 + 格式化 → 输出日报

---

## 📖 输出格式

```
06月29日，农历六月十五，星期一
🤖 AI 简讯日报

  1、马斯克宣布 Grok 4.5 在 SpaceX 与特斯拉启动内部 Beta 测试...
  2、"物理 AI 第一股"Momenta 正式在港交所开启招股...
  ...
  12、arXiv 新论文提出统一智能体训练范式...

🤖 本周十大 GitHub 热门项目

  1、calesthio/OpenMontage  [Python] 总⭐27,480 周增⭐18,703
  全球首个开源智能体视频制作系统...

  2、DeusData/codebase-memory-mcp  [C] 总⭐20,231 周增⭐8,926
  高性能代码智能 MCP 服务器...
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
      category: "chinese_ai"
      enabled: true
      type: "rss"

# 过滤关键词
filter:
  keywords_include: ["AI", "大模型", "LLM"]
  keywords_exclude: ["广告", "促销"]
```

---

## 📂 项目结构

```
ai-news-daily-enhanced/
├── main.py                  # 主入口（抓取+过滤+保存）
├── requirements.txt
├── config/settings.yaml     # 全局配置（28 数据源）
├── src/
│   ├── models.py            # Article / Source dataclass
│   ├── config.py            # YAML 配置管理器
│   ├── fetcher.py           # 抓取引擎（RSS + Web + jina.ai 降级）
│   ├── filter.py            # 4 道过滤
│   └── github_trending.py   # GitHub Trending 抓取
├── .github/workflows/
│   └── fetch-news.yml       # CI/CD 定时运行
├── data/                    # 抓取数据（JSON）
├── output/                  # 日报输出（TXT）
└── logs/                    # 运行日志
```

---

## 📜 License

MIT License
