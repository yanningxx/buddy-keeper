# 架构与接口说明

## 数据流

```
cron (09:00, ubuntu)
   └─> daily_runner.py
         ├─ buddy_station.py  --json checkin        签到 + 成长计划 + 活动
         ├─ buddy_station.py  --travel-auto         旅行领取 + 派遣
         ├─ balance_direct.py                       积分余额
         └─ push_notify.py                          企业微信 x2 通道
```

任一步失败按策略重试（网络类 20s×3，业务类 60s×2，其后 30 分钟轮询），最终结果都会记录到 `logs/cron.log` 并推送。

## 鉴权体系

### 长效令牌（签到/成长/旅行）

存放于 `/home/ubuntu/.workbuddy/checkin-rt.json`（600，ubuntu 属主），字段 `rt`。调用时以 `Authorization: Bearer <rt>` 访问 `www.workbuddy.cn`。

### 网站会话（积分余额）

余额接口不接受长效令牌，需要网站会话 cookie。兑换链路（实测有效）：

1. `POST /v2/plugin/device/auth/code`
   头部同时携带：
   - `Authorization: Bearer <accessToken>`（由 rt 刷新得到）
   - `X-Refresh-Token: <rt>`（缺此项返回 code 10034「refresh token is empty」）
   返回 `data.deviceCode`，有效期 300 秒。
2. `GET /console/client-login?code=<deviceCode>&target=/`
   下发 `session` cookie（httpOnly）。
3. `POST /billing/meter/get-user-resource-summary`
   携带该 cookie，且 **User-Agent 必须是客户端 UA**：
   `Mozilla/5.0 ... WorkBuddy/5.9.2 Chrome/138.0.7204.251 Electron/37.10.3 Safari/537.36`
   使用其他 UA 会被网关按会话绑定策略拒绝（401）。

返回示例字段：`data.TotalCredits`、`data.SubscriptionPackageName`、`data.CreditGroups[]`。

> 会话每次运行时重新兑换，不做长期缓存；只有兑换失败时才回退到上次保存的 cookie 文件。

## 成长计划任务完成判定

`GET /v2/activity/growth/tasks` 返回任务数组，完成标记不在 `status`（实测恒为 null），而在：

- `progress.current` 与 `progress.target`：`current >= target` 视为完成
- `accept_status`：`claimed` / `accepted`

播报中的「未完成任务 N 项」= 统计 `current < target` 的条数。

## 推送通道

| 通道 | 协议 | 说明 |
|---|---|---|
| `wecom` | 群机器人 webhook + markdown | 企业内部群可见，支持加粗 |
| `wecom_app` | 自建应用 message/send | 个人微信经「微信插件」看全文，无条数限制；内容含 `**` 时用 markdown 类型 |

失败判定不看 HTTP 200，而看业务码（企业微信 `errcode`、PushPlus `code`），避免假成功。

## 通知端点

`wecom_echo_server.py` 常驻 80 端口：

- `GET /wecom_callback` 企业微信回调 URL 验证（SHA1 签名 + AES 解密 echostr）
- `POST /notify` 内部通知入口，`token` 鉴权后经 `push_notify` 推送 `wecom_app`
