# 数据模型

表结构以 `backend/app/modules/*/models.py` 为准；本文解释每张表为什么存在、和老系统的对应关系。

系统内也能看：设置页底部的“关于本系统：数据是怎么存的”打开 `/about/data-model`，表、列、关联和各产品线的自定义字段都从实时的表结构生成（`GET /api/meta/data-model`），只展示结构，不展示数据。表的中文说明在 `frontend/src/shared/i18n/*.json` 的 `dataModel.tables`，新增表时一起补上。

## 配置（业务的形状）

| 表 | 作用 | 老系统对应 |
| --- | --- | --- |
| `workspaces` | 产品线：`accounting`、`grants`。`settings` 存核心列的显示名、自动带入规则、Roll over 默认目标 | Smart Accounting / Smart Grants 两个模块 |
| `workspace_memberships` | 用户在某产品线的角色：viewer / member / manager / admin | `Smart Accounting User` / `Smart Grants User` 两个 Role |
| `boards` | 看板。可关联一个财年（`period_fiscal_year_id`），`settings` 存本看板可用的状态和字段 | `Project Type` |
| `field_definitions` | 自定义字段：`entity_kind` = item / client / task / entity / contact；`key` 不可改 | `Project.custom_*` 等 Custom Field |
| `statuses` | 状态，带颜色和**类别**（todo / active / waiting / done / cancelled）；`scope` = item / task | Property Setter 改的状态池 |
| `member_roles` | 团队角色（Preparer、Manager、Partner、Responsible Person…） | `Project Team Member.role` 的选项 |
| `fiscal_years` | 财年，7 月 1 日到次年 6 月 30 日 | `Fiscal Year` |
| `lookup_lists` / `lookup_values` | 主数据：Software、Company … 可停用、可设别名 | `Software`、`Company` |

## 业务数据

| 表 | 作用 | 老系统对应 |
| --- | --- | --- |
| `clients` | 客户，`data` 存客户级自定义字段（门户权限、地址、主要沟通方式…） | `Customer` |
| `client_entities` | 客户下的实体：类型、ABN、ACN、年结、是否主实体 | `Customer Entity` |
| `contacts` | 联系人，可标记主要、账单、推荐人 | `Contact` |
| `items` | 看板上的一行。核心列：名称、看板、客户、实体、财年、状态、截止日、归档信息、高亮；`data` 存自定义字段 | `Project` |
| `item_members` | 某人在某行上的角色和分配日期 | `Project Team Member` |
| `tasks` / `task_members` | 任务（可多级）和任务上的人 | `Task` |
| `saved_views` | 列、筛选、排序、搜索；个人或共享；可设默认 | `Saved View` |
| `comments` | Updates / 评论，可挂在 item、client、task 上；`mentions` 存被 @ 的人 | `Comment` |
| `notifications` | 站内通知 | `Notification Log` |
| `automation_rules` / `automation_runs` | 规则和每次执行；执行改了什么从审计表读 | `Board Automation` / `Automation Run Log` |

## 平台

| 表 | 作用 |
| --- | --- |
| `command_log` | 每条命令：谁、什么、来源、结果、耗时、幂等键 |
| `audit_entries` | 每个被改动的对象一行，含字段级前后值；活动记录、撤销、迁移回滚都读它 |
| `events` / `event_deliveries` | 事件出箱和每个订阅者的投递状态 |
| `job_runs` | 定时任务执行记录 |
| `auth_sessions` / `login_attempts` | 登录会话（只存令牌哈希）和登录限速 |
| `migration_runs` / `migration_rows` / `external_refs` | 迁移批次、逐行暂存与问题、外部 ID 映射（重复导入不重复创建） |

## 和老系统相比的结构变化

1. **看板 ≠ 财年 ≠ 归档。** 没有 `Archived (Holding)`。看板归档是软删除，它的行带着来源 `board_archived` 一起归档，恢复看板就原样恢复。
2. **客户事实只存一份。** 门户权限、ABN、地址、联系人存在客户 / 实体 / 联系人上，看板用**镜像列**（`mirror` 字段类型）显示，不再复制到每一行。
3. **日期就是日期。** Grants 的 AP 提交、行业批准、报税日期是 `date` 类型；导入时会把 `20260911`、`2026/9/11`、`11/09/2026` 都解析成同一天。
4. **人就是用户。** 合伙人、负责人、销售都指向 `users`；老数据里只有简称的人（Win、CL）导入为占位用户，带别名，之后可以补邮箱和密码转成正式账号。
5. **月度完成** 是 `period_grid` 字段（`{"1": "done", "2": "working"}`），不是一张独立单据。
6. **删除是软删除。** `deleted_at` 有值的行在所有查询里不可见，但仍可从活动记录恢复。
