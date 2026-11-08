# CampusMind Vue 3 Frontend

Vue 前端源码位于 `frontend/src/`，正式运行文件位于 `frontend/dist/`。FastAPI 直接托管已构建的 `dist`。

## 技术

- Vue 3（随项目本地打包，不依赖公网 CDN）
- TypeScript
- 原生 Fetch API
- 企业级响应式 UI

为了保证 CampusMind 在离线/内网环境也能直接运行，正式包已经包含：

```text
frontend/dist/
frontend/vendor/vue.global.prod.js
```

因此日常运行 **不需要安装 Node.js，也不需要单独启动前端**。

## 正式运行

在项目根目录：

```powershell
.\scripts\run.ps1
```

浏览器访问：

```text
http://127.0.0.1:8000/ui/
```

FastAPI 直接把 `frontend/dist/` 挂载到 `/ui/`，没有二次跳转。

## 修改前端源码

如果以后需要改前端：

```powershell
cd frontend
npm install
npm run build
```

构建后重新启动/刷新 CampusMind 即可。
