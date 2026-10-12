# Workflow System

公司内部的工作流系统：Accounting 和 Grants 两条产品线的看板、客户、任务、自动化和数据迁移。用来替代基于 ERPNext 的 Smart Board，并作为以后 CRM、邮件、AI 等功能的底座。

- 架构设计：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- 数据模型：[docs/DATA-MODEL.md](docs/DATA-MODEL.md)
- 从老系统迁移：[docs/MIGRATION.md](docs/MIGRATION.md)
- 与老系统的功能对照和后续计划：[docs/ROADMAP.md](docs/ROADMAP.md)
- 部署与运维：[docs/OPERATIONS.md](docs/OPERATIONS.md)
- 架构决策记录：[docs/adr/](docs/adr/)
- 工程约定（Claude Code 每次会话自动读取）：[CLAUDE.md](CLAUDE.md)

## 技术栈

PostgreSQL 16 · Python 3.13 / FastAPI / SQLAlchemy 2 / Alembic · React 18 / TypeScript / Vite / Mantine / AG Grid / TanStack Query

## 本地开发

需要：Python 3.13 + [uv](https://docs.astral.sh/uv/)，Node 22 + pnpm，PostgreSQL 16。

```bash
# 1. 数据库（任选其一）
createdb flow && createuser flow --pwprompt          # 本机 PostgreSQL
# 或 docker run -d -p 5432:5432 -e POSTGRES_USER=flow -e POSTGRES_PASSWORD=flow -e POSTGRES_DB=flow postgres:16

# 2. 依赖
make install

# 3. 建表 + 写入 Accounting / Grants 的初始配置 + 第一个管理员
export FLOW_BOOTSTRAP_ADMIN_EMAIL=you@example.com FLOW_BOOTSTRAP_ADMIN_PASSWORD='Choose-a-pass1'
make db

# 4. 三个进程，各开一个终端
make dev-api      # http://localhost:8000/api/docs
make dev-worker   # 自动化、通知、迁移在这里执行
make dev-web      # http://localhost:5173
```

测试需要一个单独的库：`createdb flow_test`（测试会清空它）。

```bash
make check        # lint + 类型检查 + 全部测试，和 CI 一致
```

## 用 Docker 部署

```bash
cp deploy/.env.example deploy/.env      # 改密码
GIT_SHA=$(git rev-parse --short HEAD) docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
docker compose -f deploy/docker-compose.yml exec api python -m app.cli bootstrap
```

打开 `http://<服务器>:8080`。部署后检查 `/api/health` 返回的 `git_sha` 和 `db_revision` 是否是这次部署的版本，详见 [OPERATIONS](docs/OPERATIONS.md)。

## 目录

```
backend/
  app/core/        配置、数据库连接、时间、错误、安全
  app/platform/    命令总线、审计、事件出箱、定时任务、字段类型、筛选语言、权限
  app/modules/     业务模块：identity workspaces clients items tasks views
                   collaboration activity automations migration system
  app/api/         HTTP：每个命令自动成为 POST /api/commands/<name>；查询路由
  alembic/         数据库迁移
  tests/           pytest（真实 PostgreSQL）
frontend/
  src/app/         外壳、路由、主题
  src/shared/      API 客户端（类型由 OpenAPI 生成）、字段类型注册表、通用组件、i18n
  src/features/    boards items clients automations activity migration settings …
deploy/            docker-compose 和环境变量样例
docs/              设计文档与 ADR
```

## 新增一个功能，通常要改哪里

| 想做的事 | 改哪里 |
| --- | --- |
| 看板上加一列 | 不用改代码：Workspace setup → Fields |
| 新的一条产品线 | 不用改代码：新建 workspace（`workspaces.create`）+ 字段、状态、看板 |
| 新的字段类型 | `backend/app/platform/fields/types.py` 一个类 + `frontend/src/shared/fields/` 的显示和输入 |
| 新的自动化动作或触发器 | `backend/app/modules/automations/registry.py` 一个类 + `RuleEditor.tsx` 的配置表单 |
| 一个全新的业务模块（例如邮件） | `backend/app/modules/<name>/`（models、commands、queries、subscribers），加入 `ENABLED`；写 Alembic 迁移；前端加 `features/<name>/` |

## 分支与版本

见 [CONTRIBUTING.md](CONTRIBUTING.md)。
