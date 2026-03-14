# FusionRAG Enterprise — 全量详细设计文档（事无巨细）

> 适用仓库：`agentic-rag-enterprise`（从 `agentic-rag-for-dummies` 演进）
>
> 本文目标：把该项目从“代码仓库”变成一份可交付的**企业级系统设计说明书**：包含整体架构、模块拆分、数据流、关键算法/工程取舍、难点亮点、部署与运维、测试与演进方向。

---

## 0. 摘要（给忙人看的 30 秒）

本项目实现了一个企业级 Agentic RAG 平台：

- **文档侧**：支持 `.pdf/.md` 上传 →（PDF→Markdown / OCR→Markdown）→ **Parent/Child 分块** → **Qdrant Hybrid 检索**（dense + sparse/BM25）→ 回答时输出**结构化 citations**。
- **工具侧**：集成 OpenBB 工具（报价/历史行情/新闻），工具输出也以 `tool_output.v1` JSON + citations 形式入图，确保**可追溯**。
- **Agent 编排**：用 **LangGraph** 把 `summarize → rewrite/clarify → route_intent → 子图执行（document/market/fusion/general）→ 聚合输出` 编排成**可控工作流**，并加入 budgets/guardrails 防止死循环与成本失控。
- **企业 API**：FastAPI + Postgres + Redis/RQ worker，提供 `/v1/chat`、`/v1/documents/upload`、`/v1/jobs/{id}`、`/metrics` 等端点，支持异步入库、审计与可观测。
- **LLM Provider**：默认 Ollama，本增强版支持 **OpenAI-compatible 云模型**（通过环境变量切换）。

---

## 1. 目标、非目标与约束

### 1.1 目标（Goals）

1) **企业可部署**：API/worker/DB/队列/向量库可 compose/systemd 部署，可观测、可审计。

2) **Agentic RAG 可控**：
- 多步推理（rewrite、检索迭代、压缩上下文）
- 工具调用（OpenBB）
- 融合回答（Fusion：文档 + 市场数据）
- 强约束（budgets/guardrails）

3) **可追溯输出**：
- 回答附带结构化 citations（chunk 级别）
- 工具调用输出也附带 citations（endpoint/params_hash/时间戳）
- run_id 可复盘

4) **扫描件可入库**：
- 支持 OCR→Markdown 作为入库前置
- 保障最终可检索（points_count > 0）

### 1.2 非目标（Non-Goals）

- 不追求 SOTA 的多模态 PDF 理解（图表深度解释）——更复杂场景建议引入 VLM 流水线（可作为未来工作）。
- 不实现复杂的多租户权限体系（tenant-level ACL）——可作为未来工作。
- 不内置“上传 chunks”的专用 API（当前默认上传原始文件或 Markdown）。

### 1.3 约束（Constraints）

- 依赖尽量可选：没有某些库时测试可跳过或以 stub 方式导入（见 `edges.py` 中对 langgraph/langchain 的可选导入处理）。
- 不把任何 secret 写入仓库：API KEY 仅通过 env 注入。

---

## 2. 项目目录结构（Directory Map）

```
.
├── common/
│   ├── citations.py              # 结构化 citations + tool_output.v1 打包/解析
│   └── __init__.py
├── project/
│   ├── config.py                 # 全局配置（路径、budgets、OCR fallback、chunk 参数等）
│   ├── core/
│   │   ├── llm_factory.py        # LLM_PROVIDER 切换（ollama / openai-compatible）
│   │   ├── rag_system.py         # 组装 vector store + tools + langgraph
│   │   ├── document_manager.py   # 文档入库（调用 add_documents）
│   │   └── chat_interface.py     # UI/交互适配（简化接口）
│   ├── document_chunker.py       # Markdown → parent/child chunks
│   ├── db/
│   │   ├── vector_db_manager.py  # Qdrant collection 管理 + hybrid 检索
│   │   └── parent_store_manager.py # parent chunks 存储
│   ├── rag_agent/
│   │   ├── graph.py              # LangGraph 顶层图 + 子图构建
│   │   ├── nodes.py              # 节点实现（rewrite/route_intent/orchestrator/fusion 等）
│   │   ├── edges.py              # 条件边路由（clarify、fan-out、budgets guardrails）
│   │   ├── prompts.py            # prompt 集合
│   │   ├── schemas.py            # Pydantic 结构化输出 schema
│   │   ├── tools.py              # 检索工具（search_child_chunks/retrieve_parent_chunks）
│   │   └── graph_state.py        # State/AgentState 定义 + reducers
│   ├── openbb/
│   │   ├── client.py             # OpenBB HTTP client
│   │   ├── tools.py              # OpenBB tool wrappers（输出 pack_tool_output）
│   │   ├── storage.py            # cache + audit + stable_params_hash
│   │   └── openbb_tools_cache.sqlite
│   └── enterprise_api/
│       ├── app.py                # FastAPI 入口，路由/中间件/metrics
│       ├── auth.py               # X-API-Key 鉴权
│       ├── config.py             # DATABASE_URL、ENTERPRISE_API_KEY、metrics 等
│       ├── queue.py              # RQ 队列初始化
│       ├── tasks.py              # ingestion job（worker 执行）
│       ├── worker.py             # RQ worker 启动
│       ├── observability.py      # run_id、日志/trace
│       ├── audit_sync.py         # OpenBB audit 同步到 enterprise DB
│       ├── metrics.py            # Prometheus 指标
│       └── db/                   # SQLAlchemy models + session
├── deploy/enterprise/
│   ├── docker-compose.yml        # 企业部署 compose
│   └── ocr-service/              # 可选：OCR 微服务（本地 OCR / 或云 OCR 代理）
├── docs/
│   ├── design/
│   │   ├── enterprise_openbb_langgraph_rag.md
│   │   └── DETAILED_DESIGN.md    # （本文）
│   └── enterprise/
│       └── DEPLOYMENT.md         # 企业部署手册（含 env 变量）
├── scripts/
│   ├── pdf_to_md.py              # PDF→MD（auto/docling/pymupdf4llm/paddleocr）
│   └── pdf_paddleocr_gpu_to_md.py# GPU PaddleOCR 独立脚本
└── tests/
    ├── test_guardrails.py
    ├── test_openbb_tools_output.py
    ├── test_pdf_text_detection.py
    ├── test_ocr_table_detection.py
    └── test_llm_factory.py
```

---

## 3. 系统总体架构（Architecture）

### 3.1 部署拓扑（企业推荐）

```
                   +-------------------+
                   |   Client / UI     |
                   | (curl/gradio/...) |
                   +---------+---------+
                             |
                             v
+--------------------+   /v1/chat   +------------------------+
|  enterprise-api    | -----------> |  core.rag_system        |
|  FastAPI           |              |  LangGraph agent graph  |
|  auth/metrics/run  |              +-----------+------------+
+---------+----------+                          |
          |                                     |
          | /v1/documents/upload                | hybrid retrieval
          v                                     v
+--------------------+                 +--------------------+
| Redis (RQ queue)   |                 | Qdrant (embedded)  |
+---------+----------+                 | dense+sparse       |
          |                            +--------------------+
          v
+--------------------+                 +--------------------+
| worker (RQ)        |  parent chunks  | parent_store/      |
| ingest_document    | --------------> | (local KV/files)   |
+---------+----------+                 +--------------------+
          |
          | audit copy
          v
+--------------------+
| Postgres/SQLite    |
| runs/jobs/messages |
+--------------------+

(Optional)
+--------------------+
| ocr-service         |
| OCR -> Markdown     |
+--------------------+
```

### 3.2 为什么这样设计？

- **API 与 worker 解耦**：入库/OCR/切分/向量化都可能重 CPU/IO，放到 worker 避免阻塞在线请求。
- **Qdrant embedded path**：开发/单机演示简单稳定；未来可换成远程 Qdrant 服务。
- **LangGraph 编排**：把“agent loop + 工具调用 + 预算策略 + 并行 fan-out/join”做成可调可测的图结构。
- **结构化 citations**：企业使用最关心“证据在哪里”；同时便于审计与复盘。

---

## 4. 核心数据结构（State / Citation / Tool Output）

### 4.1 Structured citations（`common/citations.py`）

- `Citation` 字段（TypedDict）：`source/doc_id/chunk_id/parent_id/snippet/score/...`
- `pack_tool_output(text, citations)`：把工具输出封装为 JSON 字符串：

```json
{
  "format": "tool_output.v1",
  "text": "...human readable...",
  "answer_text": "...",
  "citations": [ {"source": "openbb", "endpoint": "/api/...", ...} ]
}
```

- `unpack_tool_output()`：在 graph 中把 ToolMessage 内容解析回 `(text, citations)`
- `merge_citations()`：reducer 合并 citations 去重

**好处**：
- 工具输出既对 LLM 友好（text readable）又对系统友好（citations 可解析）
- 统一 doc 与 tool 的“证据格式”，聚合层更简单

### 4.2 LangGraph State（`project/rag_agent/graph_state.py`）

顶层 `State` 主要字段（概念上）：
- `messages`：对话消息
- `conversation_summary`：压缩后的历史
- `originalQuery` / `rewrittenQuestions` / `questionIsClear`
- `intent_routes`：每个 rewritten question 的意图
- `agent_answers`：并行执行后的每个问题答案（带 citations）
- `citations`：全局 citations 合并

子图 `AgentState` 主要字段：
- `question` / `question_index`
- `messages`（子图内部的消息与 tool messages）
- `context_summary`（压缩上下文）
- `iteration_count` / `tool_call_count`（budgets）

reducers：
- `agent_answers`：支持 accumulate 或 reset
- `citations`：`merge_citations`

---

## 5. 文档入库（Ingestion）设计

### 5.1 入库入口

两条主要入口：

1) **企业 API 异步入库**：`project/enterprise_api/tasks.py::ingest_document()`
- API 上传生成 job_id → RQ worker 消费 → 调 `core.document_manager.DocumentManager.add_documents()`
- 进度回写 DB：`_set_progress()`

2) **本地脚本/手动入库**：直接把 markdown 放到 `project/markdown_docs/`，调用 chunker + qdrant 写入。

### 5.2 PDF → Markdown

- 文本型 PDF：`pymupdf4llm.to_markdown()`（快）
- 扫描件：OCR→Markdown（可选）

增强版提供本地工具链：
- `scripts/pdf_to_md.py`：auto/docling/pymupdf4llm/paddleocr
- `scripts/pdf_paddleocr_gpu_to_md.py`：GPU OCR 独立脚本

为什么强调 Markdown？
- 便于按标题分块（`MarkdownHeaderTextSplitter`）
- 表格可表达（Markdown table）
- 对 LLM 与检索更友好

### 5.3 分块策略：Parent/Child

文件：`project/document_chunker.py`

- 先按 Markdown header 分段（保留语义结构）
- 再对子段落做 child chunk（小块，高召回）
- parent chunk（更大上下文，减少碎片）存入 parent_store

为什么 parent/child？
- **child** 用于精确检索定位
- **parent** 用于补上下文，降低幻觉
- 检索时先搜 child，再按需 retrieve parent（且有去重/压缩避免重复）

### 5.4 向量化与存储

- Qdrant path：`project/qdrant_db/`
- Collection：`document_child_chunks`
- dense model：`sentence-transformers/all-mpnet-base-v2`
- sparse model：`Qdrant/bm25`

---

## 6. 检索与回答（Retrieval + Answering）设计

### 6.1 核心：LangGraph 编排（`project/rag_agent/graph.py`）

顶层链路：

1) `summarize_history`：把对话历史压缩（避免 context 爆炸）
2) `rewrite_query`：结构化输出（QueryAnalysis）
3) `route_intent`：结构化输出（IntentRouting）
4) `fan-out`：按 intent 把每个 rewritten question Send 到不同子图
5) `aggregate_answers`：聚合回答 + sources

### 6.2 Intent Routing

`intent ∈ {document, market, fusion, general}`

- document：严格走文档检索子图（强制先 search）
- market：只走 OpenBB tools 子图（不文档检索）
- fusion：doc+market 并行，fusion prompt 合并
- general：无工具回答（避免胡乱调用工具），并明确 no sources

为什么要路由？
- 提升效率：market 问题无需文档检索
- 提升可靠性：工具隔离减少误用
- 支持融合：并行执行后统一合成

### 6.3 Doc 子图（RAG loop）

节点（概念）：
- orchestrator（LLM+tools）
- tools（ToolNode 执行 search/retrieve）
- should_compress_context / compress_context
- collect_answer / fallback_response

关键机制：
- **强制第一步检索**（`YOU MUST CALL search_child_chunks...`）降低无证据回答
- budgets：`MAX_ITERATIONS/MAX_TOOL_CALLS` 防死循环
- 压缩上下文：避免重复 retrieve parent，减少 token 消耗

### 6.4 Market 子图（OpenBB loop）

- 工具集仅 openbb_*
- budgets：额外 `MAX_OPENBB_CALLS`
- 工具输出统一 pack_tool_output，最后被 fusion/aggregate 收集 citations

### 6.5 Fusion 子图

`fusion_run()`：
- doc_subgraph.invoke() + market_subgraph.invoke()
- 输入 fusion prompt 合并为最终答案
- citations 合并（doc + market）

### 6.6 聚合输出（Aggregation）

- 合并每个子问题答案
- sources 从 citations 提取 file names（仅保留有扩展名的真实文件）
- 保证最终回答可追溯

---

## 7. OpenBB 工具设计（`project/openbb/tools.py`）

提供三个默认 tools：
- `openbb_equity_price_quote`
- `openbb_equity_price_historical`
- `openbb_news_company`

关键设计点：
1) **输入约束**：provider 只允许 yfinance（避免外部 key）
2) **范围约束**：日期范围/limit clamp，防止“拉全历史/全量新闻”
3) **缓存与审计**：
- `stable_params_hash` 形成请求 fingerprint
- `storage` 记录 audit，企业 API 可同步到 Postgres
4) **结构化 tool_output.v1**：
- citations: source=openbb + endpoint + params_hash + created_at

好处：
- 工具结果可以被 LLM 使用，也可以被系统审计与复盘

---

## 8. Guardrails（预算治理）

配置在 `project/config.py`：
- `MAX_ITERATIONS`（默认 10）
- `MAX_TOOL_CALLS`（默认 8）
- `MAX_OPENBB_CALLS`（默认 4）

实现位置：`project/rag_agent/edges.py::route_after_orchestrator_call()`

逻辑：
- iteration 超限 → fallback
- tool_call_count 超限 → fallback
- openbb 调用超限 → fallback

为什么要做？
- Agentic RAG 很容易出现“检索-失败-再检索”的长循环
- 工具调用容易失控（成本、延迟、配额）

---

## 9. 云模型支持（LLM Factory）

文件：`project/core/llm_factory.py`

- `LLM_PROVIDER=ollama`（默认）
- `LLM_PROVIDER=openai`（OpenAI-compatible）

openai provider env：
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_BASE_URL`（可选，支持 vLLM/OpenRouter/代理）
- `OPENAI_TEMPERATURE`（可选）

好处：
- 本地开发可用 ollama
- 企业部署可切云模型（稳定、性能更可控）

---

## 10. 企业 API 设计（FastAPI）

入口：`project/enterprise_api/app.py`

### 10.1 核心端点（概念）
- `POST /v1/chat`：在线问答
- `POST /v1/documents/upload`：上传文档并创建 ingestion job
- `GET /v1/jobs/{job_id}`：查询入库进度与结果
- `GET /healthz`：健康检查
- `GET /metrics`：Prometheus 指标

### 10.2 鉴权
- `X-API-Key` header
- env：`ENTERPRISE_API_KEY`

### 10.3 异步入库任务
- RQ queue：`project/enterprise_api/queue.py`
- worker：`project/enterprise_api/worker.py`
- task：`project/enterprise_api/tasks.py::ingest_document`

### 10.4 审计与可观测
- run_id：`enterprise_api/observability.py`
- OpenBB audit sync：`enterprise_api/audit_sync.py`
- metrics：`enterprise_api/metrics.py`

---

## 11. OCR 设计与取舍

### 11.1 本地 OCR（推荐成本敏感）
- Windows 本地用 PaddleOCR GPU 脚本把 PDF→MD，再上传 `.md`

优点：
- 成本可控、数据不出本地

缺点：
- 本地环境复杂（CUDA/paddle 版本匹配）

### 11.2 OCR 微服务（可选）
- 可作为 worker 的 fallback：当 PDF 文字层不足时调用 OCR 服务

优点：
- 自动化入库

缺点：
- 资源占用大（需要更强机器）

---

## 12. 测试策略

- 单元测试：unittest
- 重点覆盖：
  - budgets/guardrails
  - OpenBB tool_output.v1 可解析
  - OCR 表格检测逻辑
  - LLM provider factory 选择逻辑

---

## 13. 难点、亮点与经验

### 13.1 难点
- Agent loop 容易发散：需要 budgets + 强制检索 + 上下文压缩
- 证据统一：doc 与 tools 输出格式不一致，需要 pack/unpack
- 扫描 PDF：文字层缺失导致 points_count=0，需要 OCR→Markdown

### 13.2 亮点
- Intent routing + 子图工具隔离（document/market/fusion/general）
- tool_output.v1：可机器解析的 citations，把工具也纳入证据体系
- 企业级异步入库（RQ + job progress），可观测可审计

---

## 14. 未来改进（Roadmap）

1) 多租户隔离（tenant/doc namespace）
2) 更强的 PDF 表格结构化（Docling/PP-Structure 更深 integration）
3) VLM pipeline（复杂图表理解）
4) 更完善的评测与回归（smoke/e2e + golden set）

---

## 15. 附录：关键配置（env 速查）

### 15.1 LLM
- `LLM_PROVIDER=ollama|openai`
- `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` / `OPENAI_TEMPERATURE`

### 15.2 Budgets
- `MAX_ITERATIONS`
- `MAX_TOOL_CALLS`
- `MAX_OPENBB_CALLS`

### 15.3 OCR fallback（如果启用）
- `ENTERPRISE_OCR_ENABLED=0|1`
- `ENTERPRISE_OCR_URL`
- `ENTERPRISE_OCR_TEXT_THRESHOLD`

### 15.4 Enterprise API
- `DATABASE_URL`
- `ENTERPRISE_API_KEY`
- `ENTERPRISE_METRICS_ENABLED`

---

> 注：本文是“全量设计说明”。如果你希望我再补充“按代码逐行注释式”的超详细版（例如把每个 node/edge 的输入输出字段、每个 Tool 的参数与返回 JSON 都列出来），我可以继续扩展为 v2。