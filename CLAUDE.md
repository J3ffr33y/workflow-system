# CLAUDE.md — 工程约定

本文件在每次 Claude Code 会话开始时自动载入，是这个仓库的工程约束。对话里的临时要求如果和这里的硬规则冲突，先指出冲突，不要直接执行。

先读 `docs/ARCHITECTURE.md` 再动手；架构层面的改动先改文档并补一条 `docs/adr/`。

## 1. 系统是什么

公司内部的工作流系统，替代基于 ERPNext 的 Smart Board。两条产品线（Accounting、Grants）用同一套看板引擎，业务形状（看板、字段、状态、角色、自动化）是配置数据，不是代码。以后会加 CRM、邮件、shared drive、AI。

## 2. 硬规则

1. **写入只走命令总线。** 任何改变数据的操作都是 `platform/commands` 里注册的 Command，经过 `CommandBus.execute`。路由、查询、worker、迁移脚本都不得直接 `session.add / delete / execute(update…)`。查询使用只读连接，误写会被数据库拒绝。唯一例外是平台自身的队列记账（`event_deliveries`、`job_runs`），它们不是业务数据。
2. **业务逻辑依赖的字段放核心列，其余放 `data` JSONB，并通过字段类型注册表校验。** 不要绕过字段类型直接往 JSONB 里塞值。
3. **字段 key、状态 key、角色 key 一经创建不可改**，只改 label。迁移、自动化、视图都引用 key。
4. **时间：** 数据库只存带时区的 UTC（`timestamptz`）；业务"今天"按 `settings.business_timezone` 计算。禁止 naive datetime。日期字段用 `date`。
5. **删除默认软删除**（`deleted_at`）。硬删除只能由专门的清理命令执行，并且有审计。
6. **不引入新的硬编码密钥。** 配置从环境变量读取（`core/config.py`）。
7. **数据库结构变更只通过 Alembic 迁移**，每个迁移都要能 downgrade。不要修改已经合并的迁移文件。
8. **将来接 AI：** 所有模型调用只经 `platform/ai_gateway`（澳洲区域推理、客户同意校验、脱敏、留痕）。业务模块不得直接 import 模型 SDK。
9. **客户数据不进 git、不进日志、不贴进对话。** 测试用脱敏样本（`backend/tests/fixtures`）。

## 3. 分层与模块

- 依赖方向：`app.api → app.modules → app.platform → app.core`，由 import-linter 检查（`backend/.importlinter`）。不要为了通过检查去改契约；契约要改，单独提出并说明理由。
- 每个业务模块的结构一致：`models.py`、`commands.py`、`queries.py`、`schemas.py`、`api.py`、`manifest.py`。新功能先找最接近的现有模块，照着它的风格写。
- 跨模块调用只用对方的 `commands` / `queries` 公共函数，不直接改对方的模型。

## 4. 常用命令

`make help` 列出全部。改了后端命令或查询的入参，跑一次 `make openapi`（需要 API 在运行）重新生成前端类型；类型不匹配会让前端编译失败，这是故意的。

只能访问 GitHub、不能访问 PyPI / npm 的环境（例如云端代理环境）：运行 `.github/workflows/dev-deps-bundle.yml` 后执行 `scripts/install-offline.sh`。

## 5. 代码风格

- 后端：Python 3.13，ruff（格式 + lint），mypy（strict 级别对 `app/`）。
- 前端：TypeScript strict，eslint，prettier。界面文字一律走 i18n key（`shared/i18n`）。
- 标识符、日志、数据库字段一律英文；中文只出现在 i18n 字典和面向用户的文案里。
- 注释写"为什么"，不写"做了什么"。踩过的坑写在注释里。

## 6. 测试

- 改业务逻辑必须有测试；测试要能失败（先确认它对错误实现会红）。
- 覆盖：空集合、字段缺失、第一次出现的形态、跨财年、跨夏令时、并发冲突。
- 命令测试走真实 PostgreSQL（`flow_test` 库），不要 mock 数据库。
- 不要用 sleep 等待，用显式状态等待。

## 7. Git 与发布

- 主干 `main` 永远可部署。功能在短分支上开发：`feat/…`、`fix/…`、`docs/…`、`chore/…`，通过 PR 合并。
- 提交信息用 Conventional Commits：`feat(items): …`、`fix(automations): …`。正文说明**为什么**改、**什么现象**促成了改动。
- 版本号遵循 SemVer，发布打 tag `vX.Y.Z`，并更新 `CHANGELOG.md`。
- 不要跳过 hooks（`--no-verify`）；CI 红了就去修根因。
- 部署后检查 `/api/health` 返回的 git SHA 和迁移版本与预期一致。

## 8. 汇报

- 完成说完成，失败说失败，跳过的步骤讲出来；没验证过的不要说成验证过。
- 需要我决定时，给出推荐方案，不要只罗列选项。
