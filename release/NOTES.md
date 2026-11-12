# CampusMind 1.2.1

这是一个可运行的开发快照，适合架构展示、离线回归和隔离环境验收。它不是经过 GitHub CI 发布流程签署的正式版本；源码清单只描述当前工作区文件，不代表部署、安全或模型质量认证。

## 本快照包含

- 默认使用 DeepSeek 问答；通过环境配置提供密钥，Embedding 独立配置。
- 聊天区适配短屏幕，消息与输入区独立布局，并提供 DeepSeek 与 UI 的 SSH 同步和失败回滚工具。
- FastAPI 模块化单体、Vue 3 + TypeScript 前端和 Alembic 迁移。
- Text/Hybrid/Graph/Adaptive/Agentic RAG 的离线可验证路径。
- 学生、课程、科研、图书和教室工具。
- 图书与教室的 `prepare -> human approval -> resume` 动作协议。
- Session、RBAC、Knowledge ACL、PostgreSQL RLS、Prompt Injection Guard、审计和 trace。
- 确定性 Embedding、固定合成语料 benchmark 和网络隔离 Docker image smoke。

## 已记录的验证

本次工作区已完成前端构建、静态架构检查、238 项离线回归、OpenAPI smoke、离线 benchmark、HITL 重放与并发验收、学生身份/RLS 验收、受控重启验收、全新镜像 smoke 和空数据库迁移到 `20260926_0011`。证据范围和限制见 [验收记录](../docs/ACCEPTANCE.md)。

后续提交 `e5eeb9d` 的 [GitHub Actions](https://github.com/DEVM369/CampusMind/actions/runs/43203146245) 已通过 245 项离线测试及镜像检查。在线模型质量需要单独验收。部署验收脚本使用隔离测试库和保留的合成数据，不能直接迁移到生产数据库。

DeepSeek 与 UI6 增量已通过 258 项本地离线测试，包含凭证配置、更新包隔离和失败回滚检查。真实 DeepSeek 短请求已在工作站配置下通过；Ubuntu 的更新结果以同步工具的现场检查为准。

## 发布前检查

```powershell
python scripts/check_project.py --build-frontend --docker-image campusmind-api:release-check
python scripts/build_manifest.py
python scripts/build_manifest.py --check
```

新提交继续通过共享检查入口和 GitHub Actions 验证。当前快照按作者决定暂不添加开源许可证。
