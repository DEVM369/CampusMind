# Architecture

CampusMind 1.2.1 继续采用 Final Slim 的单体模块化后端，不改变五个生产领域；保留仓库根目录 Vue 3 + TypeScript Web Frontend，并强化检索可靠性。

```text
Browser
  │
  ▼
frontend/  ───────────────►  /ui/
  │
  │ HTTP /api/v1/*
  ▼
API
 │
 ├── Knowledge ── RAG / Graph / Hybrid / Adaptive
 ├── Agent ────── Planner / Decomposer / Validator / Critic / Multi-Agent
 └── Tools ────── Student / Course / Research / Classroom / Library
        │
        ▼
Platform ─────── PostgreSQL / Neo4j / Redis / RustFS / Security / Observability
```

## Frontend

`frontend/src/` 是 Vue 3 + TypeScript 源码；`npm run check --prefix frontend` 会编译并验证 `frontend/dist/`。部署时 FastAPI 在 `/ui/` 直接托管已构建的 `dist`，运行容器不需要 Node.js。

前端只消费现有 API，不包含业务授权逻辑；RBAC、ACL、RLS、HITL 和写操作约束继续由后端强制执行。

## Knowledge

`knowledge/rag.py` 负责文本检索主链，包括 embedding、pgvector、keyword、RRF、rerank、evidence selection、answer 与 citation。

`knowledge/graph.py` 负责图谱本体和 Neo4j 基础访问；`graph_ingestion.py` 负责知识图谱构建；`graph_rag.py` 负责查询分析和多跳检索；`hybrid.py` 将图谱证据与文本证据融合。

`knowledge/adaptive.py` 是统一检索路由层，在 Text、Graph、Hybrid、SQL 与 Tool 能力之间做受控选择。

## Agent

`agent/runtime.py` 包含单 Agent 工作流的规划、拆解、检索编排、验证、自纠错、写作和 critic。

`agent/multi.py` 负责 Supervisor/Specialist 协作和跨 Agent 有界上下文。

## Tools

只读查询与业务动作分离：

- `student.py`：用户身份绑定的学生 SQL。
- `course.py`：课程结构化查询，只读。
- `research.py`：科研结构化查询，只读。
- `actions.py`：教室/图书需要人工确认的 HITL action。

## Platform

`platform/` 统一承载数据库模型/Session、外部基础设施、授权/ACL/RLS、安全治理和观测能力，避免业务代码直接散落基础设施细节。
