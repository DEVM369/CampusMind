# CampusMind 1.2.1

这是一个可运行的开发快照，适合架构展示、离线回归和隔离环境验收。它不是经过 GitHub CI 发布流程签署的正式版本；源码清单只描述当前工作区文件，不代表部署、安全或模型质量认证。

## 本快照包含

- FastAPI 模块化单体、Vue 3 + TypeScript 前端和 Alembic 迁移。
- Text/Hybrid/Graph/Adaptive/Agentic RAG 的离线可验证路径。
- 学生、课程、科研、图书和教室工具。
- 图书与教室的 `prepare -> human approval -> resume` 动作协议。
- Session、RBAC、Knowledge ACL、PostgreSQL RLS、Prompt Injection Guard、审计和 trace。
- 确定性 Embedding、固定合成语料 benchmark 和网络隔离 Docker image smoke。

## 已记录的验证

本次工作区已完成前端构建、静态架构检查、238 项离线回归、OpenAPI smoke、离线 benchmark、HITL 重放与并发验收、学生身份/RLS 验收、受控重启验收、全新镜像 smoke 和空数据库迁移到 `20260926_0011`。证据范围和限制见 [验收记录](../docs/ACCEPTANCE.md)。

这些结果不等同于真实 GitHub Actions 运行记录，也不代表在线大模型质量。部署验收脚本使用隔离测试库和保留的合成数据，不能直接迁移到生产数据库。

## 发布前检查

```powershell
python scripts/check_project.py --build-frontend --docker-image campusmind-api:release-check
python scripts/build_manifest.py
python scripts/build_manifest.py --check
```

发布前还需要完成公开文件复核、实际 CI 运行和远端仓库配置。当前快照按作者决定暂不添加开源许可证。
