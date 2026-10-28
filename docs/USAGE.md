# WorkBuddy 每日签到全勤值守 · 使用说明

> 版本 1.3.0 ｜ 最后更新 2026-10-28
> 配套文档：[设计文档](DESIGN.md) · [接口文档](API.md) · [架构速览](ARCHITECTURE.md) · [运维手册](OPERATIONS.md)

## 1. 环境准备

### 1.1 服务器

| 项 | 要求 | 实测环境 |
|---|---|---|
| 系统 | Ubuntu 22.04 / 24.04 | Ubuntu 24.04.4 LTS |
| Python | 3.10+ | 3.13.14 |
| 公网端口 | 80（可选 443） | 80 |
| 部署目录 | `/opt/buddy-keeper` | 同左 |

无需数据库、无需 Redis，所有依赖为 Python 标准库。

### 1.2 本机（执行部署的机器）

```bash
python -c "import paramiko; print(paramiko.__version__)"   # 需要 paramiko
```

Windows 下同样可用；注意 `daily_runner.py` 里 `import fcntl` 仅 Linux 存在，**本机不要直接运行它**，只在服务器上跑。

### 1.3 需要你自己准备的三类凭据

| 文件 | 放哪 | 内容 |
|---|---|---|
| `config/config.json` | 服务器 `config/` | 推送通道配置（企业微信 webhook / 自建应用） |
| `config/notify_token.txt` | 服务器 `config/` | `/notify` 的鉴权令牌，自己定一个随机串 |
| `config/wecom_echo_conf.json` | 服务器 `config/` | 企微回调的 Token / EncodingAESKey / CorpID |

外加强制要求的一项：**长效令牌**放在 `/home/ubuntu/.workbuddy/checkin-rt.json`，字段 `rt`，权限 600。这个文件由客户端登录后产生，不手工写。

以上全部不进版本库，`.gitignore` 已覆盖。

## 2. 安装与配置

### 2.1 配置部署凭据

在本机仓库根目录建 `config/deploy.local.json`（已 gitignore）：

```json
{ "host": "你的服务器IP", "user": "ubuntu", "pass": "你的SSH密码" }
```

也可用环境变量 `BK_HOST` / `BK_USER` / `BK_PASS` 覆盖，优先级高于文件。

### 2.2 部署代码

```bash
python scripts/deploy.py
```

它会：上传代码 → 建目录并 chown → 编译校验 → 重启 `wecom-echo.service` → 余额自检。看到 `COMPILE_OK` 与 `rc=0` 即成功。

### 2.3 安装定时任务

```bash
ssh ubuntu@<服务器> sudo bash /opt/buddy-keeper/scripts/setup_cron.sh
```

写入 `0 9 * * *`（每天 09:00）。装完确认：

```bash
crontab -l | grep daily_runner
ls -l /opt/buddy-keeper/logs/cron.log     # 权限应为 -rw-rw-rw-
```

`cron.log` 必须是 0666，否则 ubuntu 的 cron 写不进去，日志会降级到 `cron.log.1000` 之类的位置。

### 2.4 放置密钥文件

把 1.3 里那三个文件放到服务器 `/opt/buddy-keeper/config/`，权限 600。放好后重启一次：

```bash
sudo systemctl restart wecom-echo
```

## 3. 典型使用流程

### 3.1 每天自动跑（无需操作）

cron 09:00 触发 → 签到 → 旅行 → 余额 → 推送企业微信。查看结果：

```bash
tail -40 /opt/buddy-keeper/logs/cron.log
cat /opt/buddy-keeper/logs/last_run_state.json
```

### 3.2 打开看板

浏览器访问 `http://<服务器地址>/`。首次进入会要求输入访问令牌，填 `config/notify_token.txt` 里的内容，令牌只存在本机浏览器 localStorage。

看板能看到：积分余额、签到天数、旅行状态、成长计划、未完成任务、最近运行日志。

### 3.3 手动跑一次

看板上点「立即执行一次」，等约 10 秒刷新。或命令行：

```bash
curl -s -X POST http://<服务器地址>/run -H 'Content-Type: application/json' -d '{}'
```

若返回「已有运行在进行中，本次触发已合并」，说明上一条还在跑，等它结束即可，不必重复点。

### 3.4 只用本机验证余额链路

```bash
ssh ubuntu@<服务器> python3 /opt/buddy-keeper/src/balance_direct.py
```

输出 `HIT 积分余额：xxx` 说明网站会话兑换与余额接口都通。

### 3.5 启用 HTTPS（可选）

不用买域名也能跑，`http://<IP>/` 已经可用。若要让访问令牌不再明文传输，有两种做法：

- **有已备案域名**：双击仓库根目录 `绑定域名.cmd`，按提示输入域名与邮箱。它会装 Nginx + certbot、把后端迁到 `127.0.0.1:8080`、签证书、配置强制跳转；任一步失败自动回滚。
- **没有域名**：至少把服务限制为本机访问——在 systemd unit 里设 `Environment=BK_ECHO_HOST=127.0.0.1`，再通过带鉴权的反向代理暴露。

详细步骤见 [域名与 HTTPS 上线手册](DOMAIN-SETUP.md)。

## 4. 常见问题

### Q1 看板打开是空白 / 「dashboard missing」

`app/index.html` 没上传成功。重跑 `python scripts/deploy.py`，然后

```bash
ls -l /opt/buddy-keeper/app/index.html
```

### Q2 看板显示的数据是昨天的

`last_run_state.json` 没更新，说明当天没跑成。先看 cron 是否触发：

```bash
grep daily_runner /var/log/syslog | tail -5
tail -40 /opt/buddy-keeper/logs/cron.log
```

判断「今天跑没跑」必须比对 `state.date` 与当天日期，HTTP 200 不代表有数据。

### Q3 播报里显示「⚠️ 有积分可领」但其实领不了

v1.2.8 已修。如果还出现，确认版本：`cat /opt/buddy-keeper/VERSION` 应为 `1.3.0`（或 ≥1.2.8）。

根因是 `claim_button_text` 是服务端静态文案，已签到仍返回「立即领取」。现在只看 `claimable_credit()` 算出的数据事实。

### Q4 日志写到奇怪的文件名（如 `cron.log.1000`）

`cron.log` 权限不对，ubuntu 的 cron 写不进去，降级到了备选路径。修：

```bash
sudo chmod 666 /opt/buddy-keeper/logs/cron.log
```

### Q5 点了「立即执行一次」没反应

大概率是上个任务还在跑，单飞锁生效。看返回文案是否含「已合并」。另外手动触发设了 `WB_MAX_RETRIES=0`，网络差的时候会直接失败而不是重试，看 `cron.log` 末尾的失败原因。

### Q6 余额查不到，签到却正常

余额接口不接受长效令牌，需要网站会话。见 [架构速览](ARCHITECTURE.md) 的「网站会话」一节：兑换链路三步，且**必须带客户端 UA**，其他 UA 会被 401。

### Q7 80 端口被占用 / Nginx 起不来

服务器上 `wecom-echo.service` 默认直接监听 `0.0.0.0:80`。要上 Nginx 必须先把它迁到 8080：

```bash
sudo systemctl cat wecom-echo | grep -i environment
```

unit 里应有 `BK_ECHO_PORT=8080` 与 `BK_ECHO_HOST=127.0.0.1`。没有就跑 `绑定域名.cmd` 或手工加上后 `daemon-reload && restart`。

### Q8 在 Windows 上直接跑 `daily_runner.py` 报 `No module named fcntl`

正常。`fcntl` 是 Linux 专有模块。这个脚本只在服务器上运行。

### Q9 换了服务器要改什么

1. 改 `config/deploy.local.json` 的 `host`
2. 重跑 `python scripts/deploy.py`
3. 重跑 `sudo bash /opt/buddy-keeper/scripts/setup_cron.sh`
4. 重新放置那三个密钥文件
5. 如启用过域名，把 DNS 的 A 记录指到新 IP

### Q10 想确认服务是不是活着

```bash
systemctl is-active wecom-echo
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/status
```

两个都应正常：前者 `active`，后者 `200`。

## 5. 相关文档

| 文档 | 什么时候看 |
|---|---|
| [设计文档](DESIGN.md) | 想改架构、加模块、理解数据模型 |
| [接口文档](API.md) | 要调接口、写脚本对接 |
| [架构速览](ARCHITECTURE.md) | 快速了解鉴权体系与外部接口契约 |
| [运维手册](OPERATIONS.md) | 日常检查命令清单 |
| [域名与 HTTPS 上线手册](DOMAIN-SETUP.md) | 要给看板配域名和证书 |
| [变更记录](../CHANGELOG.md) | 查某版本改了什么 |
