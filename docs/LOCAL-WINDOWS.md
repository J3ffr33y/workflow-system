# 在自己的 Windows 电脑上运行（Docker Desktop）

给不熟悉命令行的人用的速查。服务器上的正式部署见 [OPERATIONS.md](OPERATIONS.md)。

下面的命令都在 **PowerShell** 里执行，并且先进入项目里的 `deploy` 文件夹（路径按你自己的改）：

```powershell
cd "D:\Projects\Workflow System\deploy"
```

在这个文件夹里，`docker compose` 会自动读取 `docker-compose.yml` 和 `.env`，所以不用再写 `-f` 和 `--env-file`。

## 第一次运行

```powershell
copy .env.example .env          # 然后用记事本打开 .env，改两个密码
docker compose up -d --build    # 第一次要下载和构建，几分钟
docker compose exec api python -m app.cli bootstrap   # 写入初始配置和管理员账号
```

本机试用时 `.env` 里保持 `FLOW_ENV=dev`、`FLOW_COOKIE_SECURE=false`。管理员密码至少 10 位，要有大写、小写和数字。

打开 <http://localhost:8080>，用 `.env` 里的 `FLOW_BOOTSTRAP_ADMIN_EMAIL` 和密码登录。

## 每天：启动和停止

先打开 Docker Desktop，等它左下角显示正在运行（Engine running），再执行：

```powershell
docker compose up -d     # 启动（已经在运行也可以执行，不会有影响）
docker compose stop      # 停止，数据保留
```

`docker compose down` 也会停止并删除容器，数据仍然保留。**不要加 `-v`**，`down -v` 会删掉整个数据库。

## 合并了新功能后更新

在 GitHub 上合并 PR 之后，本机还是旧代码，要拉下来并重新构建：

```powershell
git pull
docker compose up -d --build
```

数据库结构变化（迁移）会在 api 启动时自动执行，不需要额外操作。之后在浏览器里按 `Ctrl+F5` 强制刷新页面。

想确认跑的是不是新代码：

```powershell
$env:GIT_SHA = git rev-parse --short HEAD    # 构建前设置，版本号就会写进镜像
docker compose up -d --build
curl.exe http://localhost:8080/api/health    # 返回里的 git_sha 应该等于上面的版本号
```

不设置 `GIT_SHA` 也能正常运行，只是 `git_sha` 会显示 `unknown`。

`git pull` 如果提示有本地改动冲突，先执行 `git status` 看改了什么。`deploy/.env` 不会被 git 管，不会冲突。

## 查看状态和日志

```powershell
docker compose ps                  # 四个服务 db、api、worker、web 都应该是 running / healthy
docker compose logs api --tail 50  # 看 api 最后 50 行日志，报错一般在这里
docker compose logs -f worker      # 持续看 worker 日志，Ctrl+C 退出
```

## 常见问题

### 页面显示 502 Bad Gateway

意思是网页服务（web）在运行，但后端（api）没起来。刚启动后的十几秒内出现是正常的，等一下再刷新。一直这样的话：

```powershell
docker compose ps
docker compose logs api --tail 50
```

看日志最后的报错，对照下面两种情况。

**日志里有 `password authentication failed for user "flow"`**

数据库的密码只在**第一次**创建数据库时设定。之后再改 `.env` 里的 `POSTGRES_PASSWORD`，数据库不会跟着改，api 就连不上了。

- 有数据要保留：把 `.env` 里的 `POSTGRES_PASSWORD` 改回第一次用的密码，然后 `docker compose up -d`。
- 只是试用、数据可以不要：执行下面三行，会**删除全部数据**，用新密码重建：

  ```powershell
  docker compose down -v
  docker compose up -d --build
  docker compose exec api python -m app.cli bootstrap
  ```

**日志里有 `FLOW_COOKIE_SECURE must be true in prod`**

`.env` 里写了 `FLOW_ENV=prod`。本机用 `http://localhost` 时改成 `FLOW_ENV=dev`、`FLOW_COOKIE_SECURE=false`，再 `docker compose up -d`。

### 命令报错 `error during connect` 或 `cannot find the file specified`

Docker Desktop 没有打开或还没启动完成。打开它，等显示 Engine running 后再执行。

### 报错 `no configuration file provided`

当前不在 `deploy` 文件夹。先 `cd "D:\Projects\Workflow System\deploy"`。

### 报错 `set POSTGRES_PASSWORD`

`deploy` 文件夹里没有 `.env`，按“第一次运行”复制一份。

### 端口 8080 被占用

把 `.env` 里的 `WEB_PORT` 改成别的，例如 `8081`，`docker compose up -d` 后打开 <http://localhost:8081>。

### 登录不了 / 没有管理员

再执行一次 `docker compose exec api python -m app.cli bootstrap`，可以重复执行。管理员只在第一次创建，之后改 `.env` 里的管理员密码不会更新已有账号。
