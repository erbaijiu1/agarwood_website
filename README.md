# 沉香品牌官网 V1.0

前台 Vue 3 / Vite 静态 SPA + 后台 Vue 3 / Element Plus SPA + FastAPI + MySQL 8 + Nginx。商品、文章和品牌资料经 API 实时更新，修改内容不需重新构建前端。

## 快速开始（Docker Compose）

```bash
cp .env.example /data/toc_service/env/agarwood_website.env
# 必须修改统一 env 文件中的密码/密钥，并确保 DATABASE_URL 与 MYSQL_PASSWORD 一致
cd frontend && npm install && npm run build && cd ..
cd admin && npm install && npm run build && cd ..
cd /data/toc_service
docker compose build agarwood_backend
docker compose up -d agarwood_backend nginx
```

后端源码以只读方式挂载到容器 `/app/app`，镜像基于 `python:3.10-slim` 并安装锁定版本的 Python 依赖。首次安装或依赖变化时才需要 `docker compose build agarwood_backend`。普通后端代码修改后执行：

```bash
cd /data/toc_service
docker compose restart agarwood_backend
```

- 官网：https://www.yjhcai.cn/agarwood/
- 管理后台：https://www.yjhcai.cn/agarwood/admin/
- API 健康检查：https://www.yjhcai.cn/agarwood/api/health
- OpenAPI 文档：https://www.yjhcai.cn/agarwood/api/docs

后台账号来自 `/data/toc_service/env/agarwood_website.env` 中的 `ADMIN_USERNAME` / `ADMIN_PASSWORD`；仅首次初始化无管理员时创建。

## 本地前端开发

后端可先使用 SQLite（`DATABASE_URL=sqlite:///./agarwood.db`）和启动环境变量，运行 `uvicorn app.main:app --reload --port 8000`（工作目录为 backend）；官网 `cd frontend && npm run dev`；后台 `cd admin && npm run dev`。Vite 将 `/agarwood/api` 和 `/agarwood/uploads` 代理到 8000。

## 部署事项

本项目按 `/data/toc_service/README.md` 的模块化规范接入共享 `nginx_proxy`、`mysql_db` 和 `web` 网络，不重复部署 Nginx 或 MySQL。公开路径统一使用 `/agarwood/` 前缀。不要将 MySQL、FastAPI 或本项目演示管理账号暴露到公网。

`/agarwood/admin/` 仅是前端入口，后台 API 由 JWT 验证。上传图片保存在绑定目录 `backend/uploads/`。需要为数据库和上传目录建立定期备份。

## 注意

- 演示商品/品牌均是假数据，务必替换；SVG 是示意素材。
- V1.0 商品价格模式是**每个商品**固定价或询价，不包含 SKU 多规格独立定价；后续可增加 product_variants。
- 公开网站为 SPA，搜索引擎抓取内容有局限；见 docs/设计文档_V1.0.md 的 SEO 方案，正式推广前需进行按 URL 预渲染或动态 HTML 方案。
- 生产环境应增加登录限速、咨询反垃圾、隐私说明/同意机制、数据库迁移（Alembic）、监控告警、安全头和审计日志。


## 页面展示素材
`素材/images/` 收录首页、产品分类和品香场景的 14 张 WebP 图片，已同步到 `assets/` 供 Nginx 静态服务，首页已接入分类画廊与场景卡片。首次使用全新数据库时，会初始化六款商品和三篇知识文章。已有数据库需手动编辑原记录或重建开发数据，不应删除生产数据。
