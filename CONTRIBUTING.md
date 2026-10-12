# 开发流程

## 分支

- `main` 永远可部署，受保护：只能通过 Pull Request 合并，CI 必须通过。
- 每件事一个短分支，命名 `feat/…`、`fix/…`、`docs/…`、`chore/…`、`refactor/…`。
- 分支尽量一两天内合并；大功能拆成多个可独立合并的 PR。

## 提交信息

[Conventional Commits](https://www.conventionalcommits.org/)：

```
feat(automations): add "create task" action

Grants needed a reminder task when the AP is submitted; doing it with a
rule keeps the board as the single place of truth.
```

- 类型：`feat` `fix` `docs` `refactor` `test` `chore` `build` `ci` `perf`
- 范围用模块名：`items`、`clients`、`automations`、`migration`、`platform`、`frontend` …
- 正文写为什么改、什么现象促成了改动。

## Pull Request

- 用模板填写：做了什么、怎么验证的、有没有数据库迁移、有没有需要手工操作的部署步骤。
- 数据库结构变化必须附 Alembic 迁移，且能 downgrade。
- 涉及业务规则的改动必须有测试。

## 发布

- 版本号 [SemVer](https://semver.org/)：`MAJOR.MINOR.PATCH`。上线前的演示阶段用 `0.x`。
- 发布 = 在 `main` 上打 tag `vX.Y.Z` 并更新 `CHANGELOG.md`。
- 部署后检查 `/api/health` 的 `git_sha` 与 tag 对应的提交一致。

## 建议在 GitHub 上打开的设置

- Settings → Branches → 给 `main` 加保护规则：需要 PR、需要 CI（backend、frontend）通过、禁止 force push。
- Settings → General → 只允许 squash merge（历史更干净），合并后自动删除分支。
