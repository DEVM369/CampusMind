# CampusMind

CampusMind 是一个面向高校场景的智能知识与业务协同平台。它把 Hybrid RAG、GraphRAG、Agentic RAG、结构化校园工具和人工确认工作流放在同一套 FastAPI 服务中，并用 PostgreSQL 权限边界约束每一次检索和写操作。

当前仓库是 `1.2.1` 开发快照。它适合作为可运行的工程作品、架构演示和离线验证基线；公开展示不代表已经授予代码复用、修改或再分发权利，当前快照暂不附带开源许可证。

## 能力概览

| 领域 | 能力 | 约束 |
| --- | --- | --- |
| 知识检索 | Text RAG、Hybrid RAG、GraphRAG、Adaptive RAG | 引用必须回到当前身份可读的来源 |
| Agent | 规划、拆解、验证、纠错、Critic、Multi-Agent | 路由和工具调用有明确边界 |
| 校园工具 | 学生信息、课程、科研、图书、教室 | 结构化查询和写操作分离 |
| 受控动作 | 图书预约、教室预约 | `prepare -> human approval -> resume` |
| 安全 | Session、RBAC、Knowledge ACL、PostgreSQL RLS | actor 身份由服务端 Session 绑定 |
| 运行 | Vue 3 + TypeScript、FastAPI、Alembic、Docker | 前端构建产物可离线托管 |

## 架构

```text
Browser
   |
   v
Vue 3 / TypeScript  ----->  FastAPI /api/v1
                                  |
                +-----------------+-----------------+
                |                 |                 |
             Agent           Knowledge            Tools
       planner / critic   RAG / Graph / Hybrid   student / course
       multi-agent        evidence / ACL         research / HITL
                                  |
                                  v
              PostgreSQL  Neo4j  Redis  RustFS  Observability
```

后端采用模块化单体结构，生产领域保持在 `api`、`agent`、`knowledge`、`tools` 和 `platform` 五个边界内。前端只负责交互和展示，授权、证据过滤、RLS 与人工确认均由后端执行。

## 快速开始

环境要求：Python 3.12；重新构建前端或执行完整 CI 检查时需要 Node.js 22。服务端依赖独立的 PostgreSQL、Neo4j、Redis 和 RustFS。

```powershell
Set-Location 'E:\my_project\github\CampusMind'
conda activate campusmind
python -m pip install -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

编辑本地 `.env` 后，先迁移并创建合成演示账号：

```powershell
python -m alembic upgrade head
.\scripts\seed_demo.ps1
```

启动 API：

```powershell
.\scripts\run.ps1
```

打开以下地址：

- Web UI：`http://127.0.0.1:8000/ui/`
- OpenAPI：`http://127.0.0.1:8000/docs`
- Health：`http://127.0.0.1:8000/api/v1/system/health`

已经构建的 `frontend/dist/` 会由 FastAPI 直接托管，日常运行不需要单独启动前端或安装 Node.js。

## 配置模型

服务地址、数据库凭据、模型 endpoint 和 API key 只放在本地 `.env`，该文件已被 Git 忽略。默认问答模型为 DeepSeek，通过 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_BASE_URL` 配置；模型切换开关位于 `src/campusmind/config.py`。Embedding 单独配置，离线验证使用确定性 Embedding：

```powershell
$env:RAG_EMBEDDING_PROVIDER = 'deterministic'
```

确定性模式用于测试、镜像 smoke 和离线 benchmark，不代表在线模型质量，也不会替代生产模型配置。

已有 Ubuntu API 容器可使用 `scripts/deploy_deepseek.py` 同步本地已配置的 DeepSeek 凭证和已构建前端，流程包含备份、重启、真实模型检查和失败回滚。用法见 [部署说明](docs/DEPLOYMENT.md#update-an-existing-container-to-deepseek)。

## 验证与证据

本地和 CI 共用一个入口：

```powershell
python scripts/check_project.py --build-frontend
```

需要 Docker 时再追加 `--docker-image campusmind-api:check`，它会构建镜像并在 `--network none` 容器中验证 HTTP 启动和前端资源。

常用检查如下：

| 检查 | 命令 | 说明 |
| --- | --- | --- |
| 完整离线回归 | `python scripts/check_project.py` | 静态结构、pytest、benchmark、OpenAPI、前端 |
| 前端校验 | `npm run check --prefix frontend` | TypeScript 与构建产物 |
| 运行时只读检查 | `python scripts/check_runtime.py --base-url http://127.0.0.1:8000` | 健康状态、依赖、迁移和 UI 资源 |
| 离线功能评测 | `python scripts/run_offline_benchmark.py --output reports/offline/benchmark-v1.json` | 固定语料与确定性策略 |
| 清单生成 | `python scripts/build_manifest.py` | 生成源码和前端文件清单 |

当前验收记录包括：两账号登录、受控重启恢复、学生身份与 PostgreSQL RLS、HITL 重放和并发竞争、全新镜像 smoke、空数据库迁移到 `20260926_0011`、离线回归，以及 [GitHub Actions 的实际通过记录](https://github.com/DEVM369/CampusMind/actions/runs/43203146245)。完整边界和证据出处见 [验收记录](docs/ACCEPTANCE.md)。离线结果不能替代在线模型质量评估。

## 安全边界

- 匿名知识检索只能读取 `public` 内容；`campus` 和个人内容需要身份与 ACL。
- 学生查询由当前 Session 的 `actor_user_id` 绑定，客户端不能指定他人身份。
- PostgreSQL RLS 在运行时角色上强制执行，不能用 SQLite 测试结果代替生产 RLS 证据。
- 图谱关系只有在 PostgreSQL 来源仍然 active 且当前身份可读时才进入答案。
- 图书和教室写操作必须经过人工确认；重复确认是幂等的，最后资源竞争返回冲突。
- Prompt Injection Guard、审计、工具调用和 trace 记录保留在服务端边界内。

## 仓库导航

```text
src/campusmind/       FastAPI、Agent、RAG、校园工具与平台服务
frontend/              Vue 3 + TypeScript 源码和已构建 dist
migrations/            Alembic 迁移，当前 head 为 20260926_0011
scripts/               开发、种子、诊断、验收和 benchmark 命令
tests/                 离线回归、HTTP 安全和 HITL 测试
docs/                  架构、部署、安全与验收说明
datasets/              合成种子和离线 benchmark 语料
infra/                 Docker 与冻结的 PostgreSQL baseline 资产
release/               源码清单和快照说明
```

从 [文档入口](docs/README.md) 开始了解部署、架构和安全细节；脚本按用途整理在 [scripts/README.md](scripts/README.md)。贡献约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可与公开范围

作者选择暂不添加开源许可证。仓库可以被公开查看，但这不自动授予复制、修改、商用或再分发权限；如需对外协作或复用，应先补充明确许可证并重新审查发布内容。
