# 运维手册

## 日常检查

```bash
# 定时任务内容
sudo cat /etc/cron.d/buddy-keeper

# 最近一次运行结果
tail -40 /opt/buddy-keeper/logs/cron.log

# 服务状态
systemctl is-active wecom-echo cron
```

## 手动触发一次完整流程

```bash
cd /opt/buddy-keeper && WB_MAX_RETRIES=0 /usr/bin/python3 src/daily_runner.py
```

`WB_MAX_RETRIES=0` 关闭重试，便于快速看到真实结果；不加则按生产重试策略执行。

## 只验证余额链路

```bash
cd /opt/buddy-keeper && /usr/bin/python3 src/balance_direct.py --test
```

输出 `HIT 积分余额：<数值>` 表示会话兑换与接口调用均正常。

## 常见故障

### 播报里出现「积分余额：获取失败」

按顺序排查：

1. `--test` 看具体报错。
2. 若提示 `device/auth/code` 401 / code 10034：长效 rt 失效，需重新授权后更新 `checkin-rt.json`。
3. 若提示 `余额接口 HTTP 401`：UA 常量可能与当前客户端版本不匹配（客户端升级后 UA 里的版本号会变），更新 `src/balance_direct.py` 的 `CLIENT_UA`。
4. 若提示 `client-login 未下发 session cookie`：会话兑换链路变动，需重新抓取客户端实现。

### 播报没有到达

1. `tail logs/cron.log` 看是否执行。
2. 若日志无记录：`systemctl is-active cron`，并确认 `/etc/cron.d/buddy-keeper` 的用户字段是 `ubuntu`（写在命令之前，写错会导致任务永不执行）。
3. 若推送报 `errcode`：检查企业微信机器人 webhook 是否被移除、自建应用 secret 是否重置。

### 日志目录权限报错

`logs/` 必须属于 ubuntu：

```bash
sudo chown -R ubuntu:ubuntu /opt/buddy-keeper
```

## 密钥文件清单（不进版本库）

| 文件 | 用途 | 权限 |
|---|---|---|
| `config/config.json` | 推送通道配置（webhook / corpid / secret） | 600 |
| `config/notify_token.txt` | `/notify` 端点鉴权 | 600 |
| `config/wecom_echo_conf.json` | 回调验证 Token 与 AESKey | 600 |
| `/home/ubuntu/.workbuddy/checkin-rt.json` | 长效 rt 令牌 | 600 |

## 更换服务器

1. 新服务器安装：`python3`、`python3-pip`、`pip3 install curl_cffi --break-system-packages`、`python3-pycryptodome`。
2. 执行 `python scripts/deploy.py` 上传代码。
3. 手工放置上表中的密钥文件。
4. 执行 `scripts/setup_cron.sh` 安装定时任务。
5. 跑一次手动流程验证，再等次日 09:00 自然触发。
