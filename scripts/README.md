# Scripts

脚本按用途分组。所有命令都应从仓库根目录执行，依赖必须先安装；脚本不会替用户打印密码、Token、Cookie 或环境文件内容。

## 开发与运行

| 脚本 | 用途 |
| --- | --- |
| `run.ps1` | 启动本地 API |
| `test.ps1` | 运行普通 pytest |
| `validate.ps1` / `validate.py` | 调用共享项目检查 |
| `check_project.py` | 本地与 CI 的统一检查入口 |
| `test_p0_offline.py` | 阻断外部网络的离线 pytest 入口 |

## 种子和演示数据

| 脚本 | 用途 |
| --- | --- |
| `seed_demo.ps1` / `seed_core.py` | 创建合成账号和基础数据 |
| `seed_courses.py` | 导入课程和课表合成数据 |
| `seed_research.py` | 导入科研领域合成数据 |
| `seed_library.py` | 创建图书和库存合成数据 |
| `seed_rag.py` | 导入 RAG 合成文档 |
| `show_seed_users.ps1` / `show_seed_users.py` | 只读查看合成账号 UUID |
| `reset_demo_passwords.py` | 交互式重置合成账号密码并撤销旧 Session |

## 诊断与运行时检查

| 脚本 | 用途 |
| --- | --- |
| `check_runtime.py` | 只读检查运行中的 API、依赖和迁移 head |
| `diagnose_runtime.ps1` / `diagnose_runtime.py` | 只读检查课程路由和 GraphRAG 证据链 |
| `diagnose_hitl_audit.py` | 只读诊断 `audit_logs` 插入契约 |
| `audit_p0_rls.py` | 只读审计数据库身份和 RLS 上下文 |
| `check_infrastructure.ps1` | 检查本地基础服务可达性 |

## 运行时更新

| 脚本 | 用途 |
| --- | --- |
| `deploy_deepseek.py` | 通过 SSH 同步 DeepSeek 配置和前端，备份并重启现有 API 容器，检查真实模型响应，失败时回滚 |

运行环境需要已安装项目 Python 依赖及 OpenSSH。凭证从本地环境或 `.env` 读取，更新包只携带 DeepSeek 的两个配置项，不携带数据库配置。具体边界见 [部署说明](../docs/DEPLOYMENT.md#update-an-existing-container-to-deepseek)。

## 部署验收

这些脚本面向已明确隔离的测试环境，可能创建保留的合成数据；执行前阅读 [部署说明](../docs/DEPLOYMENT.md)。

| 脚本 | 用途 |
| --- | --- |
| `accept_restart.py` | 验证指定 API 容器的受控重启恢复 |
| `accept_student_security.py` | 验证学生身份、ACL、HTTP 权限和 PostgreSQL RLS |
| `accept_hitl.py` | 验证人工确认、重放、幂等和 PostgreSQL 并发竞争 |
| `smoke_api_image.py` | 在隔离网络中验证镜像启动和 UI 资源 |

## Benchmark 与发布清单

| 脚本 | 用途 |
| --- | --- |
| `run_offline_benchmark.py` | 运行固定合成语料的离线功能评测 |
| `build_manifest.py` | 生成或检查前端与源码清单 |

`reports/`、本地环境文件和运行时日志属于工作区产物，不应作为公开源码提交。脚本名称保持稳定，因为部署说明和 CI 会直接调用它们。
