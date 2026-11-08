# 文档入口

CampusMind 的文档按使用目的组织。先看下面的入口，再进入对应的专题文件。

| 文档 | 适合回答的问题 |
| --- | --- |
| [架构说明](ARCHITECTURE.md) | 模块边界、数据流和前后端职责如何划分？ |
| [部署说明](DEPLOYMENT.md) | 如何准备依赖、迁移数据库、启动服务和执行验收？ |
| [安全说明](SECURITY.md) | Session、RBAC、ACL、RLS 和提示注入防护如何工作？ |
| [P0 安全报告](P0_SECURITY_REPORT.md) | 本次安全范围、证据要求和发布限制是什么？ |
| [验收记录](ACCEPTANCE.md) | 哪些检查已经完成，哪些仍需要 CI 或部署证据？ |

## 推荐阅读顺序

1. 根目录 [README](../README.md)：快速了解产品能力和运行方式。
2. [架构说明](ARCHITECTURE.md)：了解 `api`、`agent`、`knowledge`、`tools` 和 `platform` 的关系。
3. [部署说明](DEPLOYMENT.md)：按环境选择本地、Ubuntu 或隔离验收流程。
4. [验收记录](ACCEPTANCE.md)：核对证据的时间、范围和限制。

文档中的账号、数据库和容器名称只用于说明流程。不要把密码、Token、Cookie、`.env` 或 `test.env` 内容复制到文档、Issue 或聊天记录中。
