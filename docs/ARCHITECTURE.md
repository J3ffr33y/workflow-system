# 架构设计

> 本文是系统的总设计。改动架构层面的东西（新增一类实体、改变写入路径、换掉一个基础组件）之前，先改这里，并在 `docs/adr/` 里补一条决策记录。

## 0. 目标与原则

这套系统要先完整替代当前基于 ERPNext 的 Smart Board（Accounting + Grants 两条线），然后在不推倒重来的前提下持续扩张：CRM、邮件、shared drive、AI、报表、对外 API。

由此得出六条原则，后面所有设计都从这里来：

1. **业务形状由配置决定，不由代码决定。** 看板、列、状态、角色、自动化规则都是数据。新增一块看板或一列，不需要改代码、不需要改数据库结构。
2. **只有一条写入路径。** 所有改变数据的动作都是一条"命令"（Command），经过同一个命令总线。审计、活动记录、撤销、自动化、通知、实时刷新都从这条路径上自然产生，不靠每个功能各自记得去做。
3. **新功能以"模块"接入，不改核心。** 模块通过注册的方式贡献命令、事件订阅、字段类型、自动化触发器和动作、迁移目标。邮件、AI、CRM 都是将来的模块。
4. **数据只增不丢。** 删除默认是软删除；每次修改留有前后值；迁移可以整批回滚。
5. **失败要响亮。** 外部系统查不到不等于"没有"；后台任务失败要记录、重试、可见。
6. **一个人能维护。** 选最主流、最稳定的技术；约定写进 `CLAUDE.md`；关键约束用 CI 机械检查，而不是靠记性。

## 1. 技术栈

| 层 | 选型 | 理由（详见 ADR-0001） |
| --- | --- | --- |
| 数据库 | PostgreSQL 16 | 事务、JSONB、全文检索、行锁队列，一个数据库覆盖业务数据、事件队列和后台任务 |
| 后端 | Python 3.13 · FastAPI · SQLAlchemy 2.0（同步）· Alembic · Pydantic v2 | 生态最大、文档最多；同步 SQLAlchemy 比异步更简单、更好排错，这个规模下性能足够 |
| 后台任务 | 同一代码库的 worker 进程，基于 PostgreSQL 的事件出箱与任务表 | 不额外引入 Redis / 消息队列，少一个要运维的组件 |
| 前端 | React 18 · TypeScript · Vite · Mantine · TanStack Query · React Router · AG Grid Community | 都是各自领域的主流；AG Grid 自带虚拟滚动、列拖拽、列宽、单元格编辑，看板表格最关键的"顺滑"由它保证 |
| 前后端契约 | OpenAPI → `openapi-typescript` 生成前端类型 | 后端改了字段，前端编译直接报错 |
| 工具 | uv · pnpm · ruff · mypy · eslint · prettier · pytest · Vitest · Playwright · import-linter | |
| 部署 | Docker Compose（api / worker / web / postgres），澳洲区域主机 | 一台机器就能跑；以后可以平移到托管容器平台 |

## 2. 总体结构：模块化单体

```
┌──────────────────────────── Frontend (React) ────────────────────────────┐
│ shell · boards · clients · tasks · automations · activity · migration … │
│            field-type registry（每种字段的显示 / 编辑 / 筛选组件）            │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │ REST (OpenAPI) + SSE
┌──────────────────────────────────▼───────────────────────────────────────┐
│ api 层：路由、请求校验、把请求翻译成 Query 或 Command                        │
├──────────────────────────────────────────────────────────────────────────┤
│ modules：identity · workspaces · clients · items · tasks · views ·       │
│          collaboration · automations · migration · exports …            │
│   每个模块：models / commands / queries / schemas / api / manifest        │
├──────────────────────────────────────────────────────────────────────────┤
│ platform：command bus · audit · events(outbox) · jobs · fields ·          │
│           query DSL · permissions · module registry · (ai_gateway 预留)   │
├──────────────────────────────────────────────────────────────────────────┤
│ core：config · db engines · time · ids · errors · logging · security      │
└──────────────────────────────────────────────────────────────────────────┘
          │ 写：write engine                        │ 读：read-only engine
          ▼                                         ▼
                         PostgreSQL（业务表 + audit + outbox + jobs）
                                   ▲
                    worker 进程：事件分发 · 定时任务 · 导入 · 导出
```

依赖方向只能向下：`api → modules → platform → core`。这一条由 import-linter 在 CI 里强制（ADR-0003）。

为什么是单体而不是微服务：一个人维护、几十个用户、一套数据库，微服务只会带来部署和一致性成本。模块边界在代码里划清楚，将来真要拆，按模块拆即可。

## 3. 写入路径：命令总线（系统的脊柱）

### 3.1 一次写入发生了什么

```
UI / API / 自动化 / 迁移 / 定时任务
        │  Command(name, payload, actor, origin, reason, idempotency_key, batch_id)
        ▼
CommandBus.execute
  1. 幂等检查：同一个 idempotency_key 已成功 → 直接返回上次结果
  2. 权限检查：命令声明自己需要的权限，按 actor 在对应 workspace 的角色判定
  3. 开启写事务
  4. handler 执行业务逻辑（只通过 ORM 改数据）
  5. 变更捕获：flush 前自动读取每个被改对象的字段前后值 → audit_entries
  6. handler 发出的领域事件 + 自动生成的 entity 变更事件 → events（outbox）
  7. command_log 记一行（谁、什么、来源、耗时、结果）
  8. 提交；提交后 NOTIFY，唤醒 worker 和实时推送
```

要点：

- **审计不靠自觉。** 变更捕获挂在 SQLAlchemy 的 flush 钩子上，凡是被标记为 `Audited` 的模型，任何字段的修改都会被记录。不存在"忘了写日志"。
- **读和写用两个数据库连接池。** 查询走只读连接（PostgreSQL 层面 `default_transaction_read_only=on`）。在查询代码里误写数据，数据库会直接拒绝。
- **来源（origin）是一等字段：** `ui`、`api`、`automation`、`migration`、`system`、`undo`。活动记录、自动化防循环、迁移回滚都依赖它。
- **批次（batch_id）。** 一次批量编辑、一次 Roll over、一次迁移都共享一个 batch_id，可以整批撤销。
- **级联深度。** 自动化触发的命令带 `parent_command_id` 和 `depth`，超过 3 层直接拒绝，防止规则互相触发进入死循环。

### 3.2 并发冲突

多人同时改同一行是常态。单元格编辑的命令带上"我看到的旧值"（`expected`）。如果数据库里的当前值已经不是这个旧值，命令返回冲突，前端提示并刷新这一格，不会悄悄覆盖别人的修改。撤销用的是同一套机制。

### 3.3 撤销

撤销不是单独的功能，而是一条命令 `audit.revert`：

1. 读取目标 audit 记录（单条，或同一 command / batch 下的全部）；
2. 对每个字段，检查当前值仍等于当时改成的值，否则跳过并报告；
3. 写回旧值。这次写入本身也有审计记录，origin 为 `undo`，可以再撤销。

## 4. 事件与后台任务

### 4.1 事件出箱（outbox）

事件和业务数据在同一个事务里写入 `events` 表，所以"数据改了但事件丢了"这种情况不可能发生。worker 用 `SELECT … FOR UPDATE SKIP LOCKED` 取事件，分发给已注册的订阅者：

| 订阅者 | 现在 | 将来 |
| --- | --- | --- |
| automations | 事件型规则（状态变成…） | |
| notifications | @ 提及、规则通知 | 邮件、Teams 推送 |
| realtime | 推送给打开同一看板的浏览器 | |
| （预留） | | 邮件模块、AI 模块、Webhook、搜索索引、报表物化 |

每个订阅者对每个事件有独立的投递记录（`event_deliveries`）。一个订阅者出错只会重试它自己，不会卡住其他订阅者。重试有退避；超过次数进入失败状态，在管理页可见、可重放。

### 4.2 定时任务

定时任务在代码里声明（例如"每小时评估日期型自动化规则""每天清理过期会话"），由 worker 里的调度器执行。用 PostgreSQL advisory lock 保证多台 worker 时只有一个在调度。每次执行写入 `job_runs`，失败可见。

日期判断一律按业务时区（默认 `Australia/Sydney`）计算"今天"，数据库只存带时区的 UTC 时间（ADR-0006）。

## 5. 领域模型概览

完整字段见 [DATA-MODEL.md](DATA-MODEL.md)。这里只讲结构上的决定。

```
Workspace（产品线：Accounting / Grants / 将来的 CRM…）
 ├── FieldDefinition（这个工作区里每类实体可用的字段）
 ├── StatusSet / Status（状态池，带"类别"）
 ├── MemberRole（Preparer / Manager / Partner / Salesperson …）
 ├── Board（看板：Accounting 的作业类型；Grants 的财年）
 │     └── settings：启用哪些字段、哪些状态、Roll over 规则
 ├── Item（看板上的一行，旧系统的 Project）
 │     ├── core 列：name, board, client, entity, status, archive…
 │     ├── data JSONB：本工作区自定义字段的值
 │     ├── ItemMember（人 + 角色）
 │     ├── Task（任务，可多级）
 │     └── Comment（Updates）
 ├── SavedView
 └── AutomationRule → AutomationRun

Client（全局，不属于某个工作区）
 ├── ClientEntity（实体：类型、ABN、年结、是否主实体）
 ├── Contact
 └── data JSONB：客户自定义字段（门户权限、地址…）

LookupList / LookupValue（主数据：Software、Company、Referral、Industry…）
FiscalYear · User · WorkspaceMembership
AuditEntry · CommandLog · Event · Notification · ExternalRef（外部系统 ID 映射）
```

关键决定（对照旧系统的问题）：

| 旧系统 | 新系统 |
| --- | --- |
| 两条线的几十个 `custom_*` 字段挤在一张 `Project` 上 | 每个工作区有自己的字段定义；值存在 `items.data`（JSONB），由字段类型校验 |
| `Project Type` 同时代表看板和财年，另有 `Archived (Holding)` | 看板是看板；财年是 `fiscal_years`，看板可以关联一个财年；归档是行上的状态，看板删除是软删除 |
| 一个全局 26 项状态池，每块看板勾选子集 | 每个工作区一个状态集，状态有**类别**（未开始 / 进行中 / 等待 / 完成 / 取消），看板选子集；报表和规则可以按类别工作 |
| Grants 的 ABN、地址、联系人存成项目上的快照 | 回到客户、实体、联系人上；看板通过**镜像列**显示客户字段 |
| 门户权限在客户和项目上各一份，靠保存时复制 | 只存在客户上，看板用镜像列显示 |
| 日期存成文字、合伙人有时是文字 | 字段类型是真类型；人一律指向用户 |
| `project_name` 全局唯一，Roll over 要编号去重 | 用 ID 寻址，名字只是显示 |
| 活动记录从 Version / Deleted Document / Comment 三处拼 | 统一来自 audit_entries |
| 月度完成状态是一张独立单据 | 一种字段类型 `period_grid`，任何工作区都能用 |

### 5.1 为什么自定义字段用 JSONB，而不是每列一个数据库列

- 新增一列是"加一条字段定义"，不需要数据库迁移，也不需要发版；
- 两个工作区的字段互不干扰；
- 校验由字段类型统一完成，类型仍然是真类型（日期就是 ISO 日期，人就是用户 ID）；
- PostgreSQL 对 JSONB 有 GIN 索引和表达式索引；常用筛选字段可以单独加表达式索引。

代价是：跨字段的数据库约束较弱。所以**业务逻辑依赖的字段放核心列**（名称、看板、客户、状态、归档），其余放 JSONB。这条边界写在 ADR-0004。

### 5.2 字段类型注册表（最重要的扩展点之一）

每种字段类型在后端和前端各有一份实现，用同一个 `type` 键对应：

| 后端负责 | 前端负责 |
| --- | --- |
| 校验 / 规范化（含迁移时从脏数据解析） | 单元格显示 |
| 筛选运算符及其 SQL | 单元格编辑器 |
| 排序表达式 | 筛选条件输入 |
| CSV 导出格式 | 批量编辑输入 |
| 自动化条件的比较 | |

首批类型：`text` `long_text` `number` `money` `percent` `date` `datetime` `month` `year_month` `checkbox` `select` `multi_select` `user` `users` `lookup` `lookup_multi` `email` `phone` `url` `color` `period_grid` `mirror`（显示关联客户 / 实体的字段，只读）。

新增一种字段类型 = 后端一个类 + 前端一个组件，看板、筛选、批量编辑、导出、自动化、迁移全部自动支持。

### 5.3 统一的筛选语言

看板筛选、Saved View、自动化条件、导出、将来的报表，用同一套 JSON 筛选树：

```json
{"op": "and", "rules": [
  {"field": "status", "operator": "in", "value": ["waiting_client"]},
  {"field": "data.lodgement_due", "operator": "before", "value": {"relative": "today+14d"}}
]}
```

后端把它编译成 SQL（每个运算符由字段类型提供）。一套语言，一套测试。

## 6. 权限

- 用户在每个工作区有一个角色：`viewer`、`member`、`manager`、`admin`；另有全局 `superadmin`。
- 权限点是字符串（`items.update`、`automations.manage`、`users.manage`、`audit.view_values` …），角色到权限点的映射在代码里集中定义。
- **只在命令总线和查询入口判定权限**，不散落在路由里。前端只是根据 `/me` 返回的权限隐藏按钮，不作为安全边界。
- 预留：自定义角色表；行级规则（例如"只看分配给我的"）作为查询入口的策略钩子。

旧系统"活动记录的具体值要输入密码才显示"，新系统改为权限点 `audit.view_values`，避免共享密码。

## 7. 认证与会话

- 邮箱 + 密码，Argon2id 哈希；服务端会话表，Cookie 为 `HttpOnly; Secure; SameSite=Lax`；写操作带 CSRF 令牌。
- 登录失败限速；会话可在管理页强制下线。
- 预留：Microsoft 365 / Google OIDC 单点登录（认证提供者是可插拔接口）；两步验证。

## 8. 模块与扩展点

每个模块在 `manifest.py` 里声明自己贡献了什么：

```python
manifest = ModuleManifest(
    key="items",
    commands=[CreateItem, UpdateItemField, ArchiveItems, ...],
    event_subscribers=[...],
    field_types=[...],
    automation_triggers=[...],
    automation_actions=[...],
    migration_targets=[...],
    permissions=[...],
    scheduled_jobs=[...],
)
```

启用哪些模块由配置决定。下表是已经预留的扩展点：

| 扩展点 | 用法举例 |
| --- | --- |
| 新工作区 | CRM 线、State Grants 线：加一条 workspace + 字段 + 状态 + 看板，零代码 |
| 新实体上的自定义字段 | 客户、实体、联系人、任务都能挂字段定义 |
| 字段类型 | 文件、公式、关联另一行（item link）、评分 |
| 自动化触发器 / 条件 / 动作 | 收到邮件、文件上传、"创建任务""发邮件""调用 AI 起草" |
| 事件订阅者 | 邮件通知、Webhook、搜索索引、AI 分析 |
| 定时任务 | 截止日扫描、周报、数据质量检查 |
| 迁移来源 | CSV、ERPNext API、将来的其他系统 |
| 外部系统 ID（`external_refs`） | ERPNext、Xero、邮件线程、网盘文件，与本系统对象一一对应，可重复同步 |
| 通知渠道 | 站内 → 邮件 → Teams / 微信企业号 |
| AI 网关（预留） | 所有模型调用只经 `platform/ai_gateway`：数据驻留（澳洲推理档）、客户同意校验、脱敏、计费、留痕；CI 禁止其他模块直接引用模型 SDK |
| 文件存储（预留） | 抽象接口：本地磁盘 / 澳洲区域 S3 兼容存储 |
| 对外 API（预留） | 个人 API token + 同一套命令总线，权限和审计完全一致 |

## 9. 前端结构

```
frontend/src/
  app/            应用外壳、路由、Provider、布局、导航
  shared/
    api/          生成的 OpenAPI 类型 + fetch 客户端 + 错误处理
    fields/       字段类型注册表：每种类型的 Cell / Editor / FilterInput
    ui/           通用组件
    i18n/         en / zh-CN 字典（界面文字都走 key）
  features/
    boards/       看板表格（AG Grid）、列管理、筛选器、Saved View、批量编辑、Roll over
    items/        行详情抽屉：字段、团队、任务、Updates、活动记录
    clients/  users/  automations/  activity/  notifications/  settings/  migration/
```

- 服务端状态全部由 TanStack Query 管理；单元格编辑采用乐观更新，冲突时回滚并提示。
- 看板数据目前分页拉取到浏览器后由 AG Grid 排序，几千行以内很流畅；接口已支持服务端排序和分页，行数更大时切换为服务端模式即可。
- 实时：SSE 接收"某块看板有变化"，触发局部刷新。

## 10. 风险清单与对策

| 风险 | 对策 |
| --- | --- |
| 数据丢失 | 软删除；审计保留前后值；每日备份 + WAL 归档（时间点恢复）；备份必须实际恢复演练过 |
| 迁移出错 | 迁移先预览、后提交；按外部 ID 幂等，可重复跑；整批可回滚；导入后自动对账（源行数、成功、跳过、错误） |
| 多人同时编辑覆盖 | 字段级乐观并发（expected 旧值），冲突明确提示 |
| 自动化死循环或误伤 | 级联深度上限；每条规则每行的去重键（日期型规则每天最多一次）；规则可以"试运行"看会命中哪些行；每次执行都可撤销 |
| 时区与夏令时 | 只存 aware UTC；"今天"按业务时区计算；跨财年、跨夏令时有测试 |
| 中文编码 | 导出 CSV 用 UTF-8 带 BOM（Excel 打开不乱码）；导入自动识别 UTF-8 / GBK / GB18030 / CP1252 |
| 性能退化 | 服务端分页、JSONB 索引、慢查询日志；请求路径上不放慢任务（导出、导入、批量操作走 worker） |
| 安全 | Argon2、会话、CSRF、限速、最小权限、审计；密钥只从环境变量读取 |
| 合规（澳洲） | 数据库、文件、备份都在澳洲区域；将来接 AI 必须经 AI 网关，执行驻留和客户同意校验 |
| 字段改名 / 改类型 | 字段 key 不可变，label 可改；改类型走专门的转换命令，先预览转换结果 |
| 部署后跑的不是新代码 | `/api/health` 返回 git SHA 和迁移版本；部署脚本部署后自动比对 |
| 单人维护 | 约定写进 `CLAUDE.md` 和 ADR；CI 强制格式、类型、测试、分层契约；每个模块结构一致 |

## 11. 观测

- 结构化 JSON 日志，每个请求和命令带 `request_id` / `command_id`；
- `/api/health`（存活）、`/api/ready`（数据库、迁移版本、worker 心跳）；
- 管理页能看到：失败的事件投递、失败的定时任务、自动化运行日志、迁移运行；
- 预留：Sentry 错误上报、Prometheus 指标。
