# WorldMonitor 项目分析报告

## 1. 项目概述

**WorldMonitor** 是一个实时全球情报仪表板，AI 驱动的新闻聚合、地缘政治监控和基础设施追踪系统。

- **GitHub**: koala73/worldmonitor (46.7k stars)
- **技术栈**: TypeScript + Vite + Preact + Tauri 2
- **许可证**: AGPL-3.0 (非商用)

## 2. 核心功能

### 2.1 情报聚合
- 435+ 精选新闻源，15 个类别
- AI 合成新闻简报
- 跨流关联分析（军事、经济、灾害、升级信号收敛）

### 2.2 可视化
- 双地图引擎：3D 地球仪 (globe.gl) + WebGL 平面地图 (deck.gl + MapLibre GL)
- 45 个数据图层
- 实时飞行数据 (ADS-B via Wingbits)

### 2.3 金融雷达
- 92 个股票交易所
- 大宗商品、加密货币
- 7 信号市场综合指标

### 2.4 国家情报指数
- 12 个信号类别的综合风险评分

### 2.5 本地 AI
- 支持 Ollama（无需 API key）
- 支持 Groq / OpenRouter
- Transformers.js 浏览器端推理

### 2.6 多变体
- 5 个站点变体：world / tech / finance / commodity / happy
- 单代码库驱动

### 2.7 桌面应用
- Tauri 2 原生应用 (macOS / Windows / Linux)

## 3. 架构

```
src/                 # 浏览器 SPA (86 个面板组件)
  ├── app/          # 数据加载、刷新调度、面板布局
  ├── components/   # UI 面板 (Panel 子类)
  ├── services/    # 业务逻辑 (120+ 服务文件)
  ├── workers/     # Web Workers (分析、ML/ONNX、向量数据库)
  └── config/      # 变体配置、面板/图层定义

api/                # Vercel Edge Functions (60+)
  └── <domain>/    # 领域端点 (aviation/, climate/, 等)

server/             # 服务端共享代码
  ├── _shared/    # Redis、限流、LLM、缓存
  └── worldmonitor/<domain>/  # RPC 处理器

proto/              # Protobuf 定义 (92 protos, 22 服务)
src-tauri/         # Tauri 桌面壳 (Rust + Node.js sidecar)
```

## 4. 部署

- **Web**: Vercel (main 分支自动部署)
- **Relay/Seeds**: Railway (Docker, cron 服务)
- **Desktop**: Tauri via GitHub Actions
- **Docs**: Mintlify (通过 Vercel /docs 代理)

## 5. 与你 EDT 项目的关联

| WorldMonitor 功能 | 对应 EDT 模块 |
|-----------------|--------------|
| 新闻聚合 + AI 简报 | A 侧 (NewsIngestion) |
| 地缘监控 + 信号关联 | B 侧 (ConductionMapper) |
| 金融雷达 | B 侧 (OpportunityScorer) |
| 地图可视化 | C 侧 (canvas/index.html) |
| 多源数据接入 | A 侧 (DataAdapter) |
| 实时推送 | C 侧 (event_bus.py + WebSocket) |

## 6. 可借鉴之处

1. **Protocol Buffers 定义 API 契约** — 92 个 proto 文件，22 个服务
2. **三层缓存** — fast(5m) / medium(10m) / slow(30m) / static(2h) / daily(24h)
3. **变体系统** — 单代码库多站点配置
4. **Circuit Breaker** — 客户端防级联失败
5. **Edge Functions** — 无服务器计算层

## 7. AI 分析能力

WorldMonitor 使用以下 AI/ML 能力：

### 7.1 本地浏览器端 (Transformers.js ONNX)

| 模型 | 功能 | HuggingFace 模型 |
|------|------|-----------------|
| **all-MiniLM-L6-v2** | 向量嵌入 (Embeddings) | Xenova/all-MiniLM-L6-v2 (23MB) |
| **DistilBERT-SST2** | 情感分类 (Sentiment) | Xenova/distilbert-base-uncased-finetuned-sst-2-english (65MB) |
| **Flan-T5-base** | 摘要生成 (Summarization) | Xenova/flan-t5-base (250MB) |
| **Flan-T5-small** | 摘要生成 (轻量版) | Xenova/flan-t5-small (60MB) |
| **BERT-NER** | 命名实体识别 (NER) | Xenova/bert-base-NER (65MB) |

### 7.2 远程 API 服务

| 提供商 | 用途 | 配置位置 |
|--------|------|----------|
| **Ollama** | 本地 LLM 推理 | `OLLAMA_API_URL` |
| **Groq** | 快速 LLM 推理 | `GROQ_API_KEY` |
| **OpenRouter** | 多模型路由 | `OPENROUTER_API_KEY` |

### 7.3 AI 能力覆盖

- ✅ 向量化语义搜索
- ✅ 情感分析 (正面/负面/中性)
- ✅ 新闻摘要生成
- ✅ 命名实体识别 (NER)
- ✅ 语义聚类
- ✅ 向量数据库存储
- ✅ LLM 问答/生成 (可选 Ollama/Groq/OpenRouter)

### 7.4 与你 EDT 项目的对比

| WorldMonitor AI 能力 | 对应 EDT 模块 |
|---------------------|--------------|
| Transformers.js 情感分析 | B 侧 SignalScorer |
| 向量嵌入 + 语义搜索 | C 侧 event_bus 记忆 |
| 摘要生成 | A 侧 NewsIngestion |
| Ollama/Groq 本地 LLM | 你的 OpenClaw 记忆系统 |