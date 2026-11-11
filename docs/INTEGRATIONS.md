# 对外接口（API token、Webhook、外部 ID）

给以后接邮件、Xero、网盘、报表工具、自动化平台（n8n / Power Automate）用。设计理由见 [ADR-0010](adr/0010-integration-interfaces.md)。

## 1. 用 API token 调用系统

1. 在浏览器登录后调用 `POST /api/commands/identity.create_api_token`（`{"name": "xero-sync", "expires_in_days": 90, "read_only": false}`），返回的 `token` 只显示这一次。
2. 之后所有请求带 `Authorization: Bearer flow_pat_…`，不需要 CSRF。
3. token 的权限 = 创建者本人的权限；活动记录里的来源显示为 `api`。

```bash
curl -H "Authorization: Bearer $FLOW_TOKEN" https://flow.example/api/auth/whoami
curl -H "Authorization: Bearer $FLOW_TOKEN" -H "Content-Type: application/json" \
     -d '{"name": "Acme Pty Ltd"}' https://flow.example/api/commands/clients.create
```

- 所有写操作仍是 `POST /api/commands/<命令名>`，命令清单和参数见 `/api/docs`。
- 带 `Idempotency-Key` 头可以安全重试（同一个 key 只执行一次）。
- 只读 token（`read_only: true`）适合报表工具：能查，不能写。
- 出于安全，token 不能：创建新 token、改密码、轮换 webhook 密钥。
- 查看 / 撤销自己的 token：`GET /api/auth/api-tokens`、`identity.revoke_api_token`。停用用户会同时撤销他的所有 token。
- 通过 API 新建项目时，工作区的 `required_on_create` 会在服务端检查（浏览器表单原本就检查）。

## 2. Webhook：系统里有变化时通知别的系统

仅超级管理员可配置。

| 操作 | 接口 |
| --- | --- |
| 可订阅的事件 | `GET /api/integrations/events` |
| 新建 / 修改 | `integrations.save_webhook`（新建时返回 `secret`，只显示一次） |
| 轮换密钥 | `integrations.rotate_webhook_secret` |
| 删除 | `integrations.delete_webhook` |
| 列表 / 投递记录 | `GET /api/integrations/webhooks`、`GET /api/integrations/webhooks/{id}/deliveries` |

事件类型是 `<实体>.<created|updated|deleted>`，例如 `item.updated`、`comment.created`。订阅时可用通配符 `item.*`；只开放业务数据（项目、任务、评论、客户、实体、联系人、看板、文件），用户、token、权限相关事件不会外发。可以限定某个工作区；撤销、迁移、级联产生的"安静"变更默认不发（`include_quiet: true` 可打开）。

请求体：

```json
{"id": 1234, "type": "item.updated", "occurred_at": "2026-11-10T03:00:00+00:00",
 "workspace_id": "…", "entity_type": "item", "entity_id": "…", "origin": "ui", "actor_id": "…",
 "data": {"changes": [{"field": "status", "before": "not_started", "after": "completed"}], "parent": null, "quiet": false}}
```

请求头：`X-Flow-Event`、`X-Flow-Event-Id`（用于去重，投递至少一次）、`X-Flow-Signature: t=<秒>,v1=<hex>`。

校验签名（Python）：

```python
t, v1 = (p.split("=", 1)[1] for p in request.headers["X-Flow-Signature"].split(","))
expected = hmac.new(secret.encode(), f"{t}.".encode() + raw_body, hashlib.sha256).hexdigest()
ok = hmac.compare_digest(v1, expected) and abs(time.time() - int(t)) < 300
```

返回 2xx 视为成功；其他状态或超时（10 秒）会按事件出箱的退避策略重试（5 秒到 4 小时，共 8 次），只重试失败的那个地址。生产环境只接受 https。

## 3. 外部 ID 映射

记录"对方系统的 ID ↔ 本系统的记录"，同步可以反复跑而不产生重复。迁移用的也是这张表（`external_refs`）。

- 关联：`external_refs.link`，`{"system": "xero", "external_type": "Contact", "external_id": "…", "entity_type": "client", "entity_id": "…"}`。同一个外部 ID 再次关联到别的记录会移动过去。可关联 `item`、`task`、`client`、`client_entity`、`contact`。
- 查询：`GET /api/integrations/external-refs?system=xero&external_id=…`（按外部 ID 找本系统记录），或 `?entity_id=…`（看一条记录有哪些外部 ID）。

## 4. 字段默认值

字段配置里加 `"default"`（`fields.update` 的 `config`），新建项目时没填这个字段就用默认值。可以写存储值（`top_grants`）或显示文字（`Top Grants`），保存时校验。只对"新建项目"生效，Roll over 和迁移不套默认值。

## 5. 已有的其他扩展点（不需要新接口）

| 想做的事 | 怎么接 |
| --- | --- |
| 新的通知渠道（邮件、Teams） | 订阅 `notify.requested` 事件，写一个新的 subscriber（见 `collaboration/subscribers.py`） |
| 新的自动化触发器 / 动作 | `automations/registry.py` 加一个类 |
| 新的字段类型 | `platform/fields/types.py` 加一个类 + 前端组件 |
| 新的业务模块 | `app/modules/<name>/`，加入 `ENABLED` |
| 调用 AI | 只经 `platform/ai_gateway` |
