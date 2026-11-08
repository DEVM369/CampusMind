# Security

CampusMind 的安全模型以“读取与动作分离”为核心。

## 1. 身份与权限

RBAC 与知识 ACL 在 `platform/security.py` 中统一实现。个人学生数据必须绑定 actor identity；公开知识检索运行在受限知识作用域中。

## 2. 数据库

ORM 事务会切换到非超级用户 `campusmind_runtime`，并对 `document_chunks` 强制启用 PostgreSQL RLS。迁移由 Alembic 管理，当前 head 为 `20260926_0011`。应用连接账号仍可能是管理员账号，因此部署前应单独审查登录账号与直连数据库的权限边界。

## 3. Agent Action

教室和图书业务动作采用：

```text
intent → prepare → pending approval → explicit human decision → execute
```

FAQ、解释性问题和状态说明不能直接创建业务动作。Safety Guard 不因为 Agent 方便而放宽。

## 4. RAG 输入

检索内容视为不可信数据，不作为系统指令。Prompt Injection Guard 对证据和用户指令进行边界隔离。

## 5. Secrets

源码不包含生产 API Key、数据库密码或远端服务密码。所有环境值通过 `.env` 或进程环境提供。
