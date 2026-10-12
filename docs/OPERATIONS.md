# 部署与运维

## 组成

| 进程 | 作用 | 可以多开吗 |
| --- | --- | --- |
| `db` | PostgreSQL 16，全部数据、事件队列、任务记录 | 主库一个；可加只读副本 |
| `api` | FastAPI，启动时自动执行数据库迁移 | 可以 |
| `worker` | 事件投递（自动化、通知、迁移）和定时任务 | 可以（行锁 + advisory lock 保证不重复） |
| `web` | nginx：前端静态文件 + 反向代理 `/api` | 可以 |

数据和备份都应放在澳洲区域的主机或云服务上。

## 部署

```bash
git pull
GIT_SHA=$(git rev-parse --short HEAD) docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --build
```

### 部署后必须验证

```bash
curl -s https://<host>/api/health   # git_sha 应等于刚部署的提交；db_revision 应等于 alembic 最新版本
curl -s https://<host>/api/ready    # worker: true；event_backlog 不应持续增长
```

改了代码不等于跑的是新代码；不验证就不算部署完成。

## 备份与恢复

- 每日 `pg_dump`（或托管数据库的自动快照）+ WAL 归档，保留至少 35 天；ATO 相关记录按公司留存政策（通常 5 年）另做长期归档。
- **备份要定期演练恢复**：每季度把最近的备份恢复到一台临时机器上，打开系统抽查。

```bash
# 备份
docker compose -f deploy/docker-compose.yml exec -T db pg_dump -U flow -Fc flow > backup-$(date +%F).dump
# 恢复到空库
docker compose -f deploy/docker-compose.yml exec -T db pg_restore -U flow -d flow --clean < backup-YYYY-MM-DD.dump
```

## 日常检查

- 侧边栏 **System health**（管理员）：后台进程是否在运行、失败的事件投递（可重试）、定时任务记录。
- **Automation logs**：失败的规则执行及原因。

## 常见操作

```bash
# 首次部署：初始配置 + 管理员（幂等，可重复执行）
docker compose -f deploy/docker-compose.yml exec api python -m app.cli bootstrap
# 立即执行一次日期型自动化
docker compose -f deploy/docker-compose.yml exec worker python -m app.cli run-job automations.date_rules
```

## 安全设置

- `FLOW_ENV=prod` 时，系统要求 `FLOW_COOKIE_SECURE=true` 并拒绝默认管理员密码。
- 必须在 HTTPS 后面运行（在 nginx 前面放负载均衡或 Caddy / Traefik 终止 TLS）。
- 登录失败超过 8 次锁定 15 分钟；管理员重置密码会让该用户所有会话失效。
