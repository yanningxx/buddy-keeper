# WorkBuddy 每日签到全勤值守 · 接口文档

> 版本 1.3.0 ｜ 最后更新 2026-10-28
> 配套文档：[设计文档](DESIGN.md) · [使用说明](USAGE.md) · [架构速览](ARCHITECTURE.md)

## 1. 通用约定

| 项 | 说明 |
|---|---|
| Base URL | `http://<服务器地址>` 或 `https://<自定义域名>`（启用 HTTPS 后） |
| 默认端口 | 80；由 Nginx 接管后对外仍是 80/443，后端内网 8080 |
| 内容类型 | 请求 `application/json`，响应 `application/json; charset=utf-8` |
| 字符编码 | UTF-8 |
| 鉴权 | **仅 `POST /notify` 需要 token**，其余接口无鉴权（见第 4 节风险说明） |
| CORS | 看板相关接口返回 `Access-Control-Allow-Origin: *`，预检 `OPTIONS` 返回 204 |
| 业务错误码 | **无自定义业务码**，只用 HTTP 状态码 + 响应体 `detail` 字段描述原因 |

## 2. 接口清单

| 方法 | 路径 | 用途 | 鉴权 | 幂等 |
|---|---|---|---|---|
| GET | `/` `/app` `/app/` `/index.html` | 返回看板 HTML | 无 | 是 |
| GET | `/status` | 返回最近一次运行状态与日志尾部 | 无 | 是 |
| POST | `/run` | 异步触发一次完整流程 | 无 | 否（有单飞锁） |
| POST | `/notify` | 经企业微信自建应用推送一条通知 | token | 否 |
| GET | `/wecom_callback` | 企业微信回调 URL 验证 | 签名 | 是 |
| OPTIONS | `*` | CORS 预检 | 无 | 是 |

## 3. 接口详情

### 3.1 GET `/` — 看板页面

返回 `app/index.html` 的内容，`Cache-Control: no-cache`。

- **请求参数**：无
- **成功响应**：`200`，`Content-Type: text/html; charset=utf-8`
- **失败响应**：`500`，`text/plain`，内容 `dashboard missing: <原因>`

```bash
curl -s http://<服务器地址>/ -o dashboard.html && open dashboard.html
```

### 3.2 GET `/status` — 运行状态

看板的数据来源。**只读，不改任何状态。**

**请求参数**：无（实现中接受 `?token=`，但当前版本不校验）

**成功响应** `200`：

```json
{
  "ok": true,
  "state": {
    "date": "2026-10-28",
    "started": "2026-10-28 09:00:01",
    "finished": "2026-10-28 09:00:14",
    "attempts": {
      "checkin": [{"status": "ok", "extra": {"growth": {"level": 12, "buddy": "糯糯 金色"}, "unfinished_tasks": 1}}],
      "travel":  [{"status": "ok"}],
      "balance": [{"status": "ok", "extra": {"balance": 297.73}}]
    }
  },
  "log_tail": ["2026-10-28 09:00:01 ==== 开始 ====", "..."]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `ok` | bool | 读取过程是否成功；`false` 时带 `detail` |
| `state` | object \| null | `last_run_state.json` 内容；文件不存在时为 `null` |
| `log_tail` | string[] | 日志最后 40 行；`run.log` 存在则用，否则 `cron.log` |
| `detail` | string | 仅 `ok:false` 时出现，截断到 200 字符 |

**注意**：即使返回 `200`，`state` 也可能为 `null`（从未运行过）。判断「今天跑没跑」要比较 `state.date` 与当天日期，不能只看 HTTP 200。

```bash
curl -s http://<服务器地址>/status | jq '.state.date, .state.finished'
```

### 3.3 POST `/run` — 触发一次完整流程

派生一个 `daily_runner` 子进程后**立即返回**，不等执行完。

**请求体**：可为空；若带 body 必须是合法 JSON，否则 400。

```json
{}
```

**成功响应** `200`：

```json
{"ok": true, "detail": "已触发，约 10 秒后可刷新查看"}
```

已有实例在跑时（单飞锁命中），同样 `200` 但不派生进程：

```json
{"ok": true, "detail": "已有运行在进行中，本次触发已合并（单飞锁）"}
```

**错误响应**

| 状态码 | 场景 | 响应体 |
|---|---|---|
| 400 | body 不是合法 JSON | `{"ok":false,"detail":"bad json"}` |
| 500 | `src/daily_runner.py` 不存在 | `{"ok":false,"detail":"runner missing"}` |
| 500 | 派生进程失败 | `{"ok":false,"detail":"<异常信息前200字>"}` |

**行为细节**

- 子进程环境：`WB_MAX_RETRIES=0`（不重试，尽快出结果）、`HOME=/home/ubuntu`（保证凭据路径正确）
- 子进程输出追加到 `logs/cron.log`，且会尝试把该文件权限设为 0666
- `start_new_session=True`，因此断开 HTTP 连接不会杀掉子进程

```bash
curl -s -X POST http://<服务器地址>/run -H 'Content-Type: application/json' -d '{}'
sleep 12 && curl -s http://<服务器地址>/status | jq '.state.finished'
```

### 3.4 POST `/notify` — 推送一条通知

唯一需要鉴权的接口。经企业微信**自建应用**通道推送。

**请求体**

```json
{
  "token": "<config/notify_token.txt 的内容>",
  "title": "标题，最长 64 字",
  "content": "正文，最长 8000 字"
}
```

| 字段 | 类型 | 必填 | 约束 |
|---|---|---|---|
| `token` | string | 是 | 必须与服务器 `config/notify_token.txt` 完全一致 |
| `title` | string | 否 | 缺省 `WorkBuddy 通知`；超过 64 字截断 |
| `content` | string | 是 | 去空白后不能为空；超过 8000 字截断 |

**成功响应** `200`：

```json
{"ok": true, "detail": "wecom_app:success"}
```

**错误响应**

| 状态码 | 场景 | 响应体 |
|---|---|---|
| 400 | body 非法 JSON | `{"ok":false,"detail":"bad json"}` |
| 400 | `content` 为空 | `{"ok":false,"detail":"empty content"}` |
| 403 | token 不匹配或服务端未配置 token | `{"ok":false,"detail":"bad token"}` |
| 502 | 推送通道返回业务失败 | `{"ok":false,"detail":"wecom_app:<业务码或原因>"}` |
| 500 | 内部异常 | `{"ok":false,"detail":"<异常前200字>"}` |

**注意**：`502` 表示 HTTP 通了但业务失败（例如 `errcode != 0`），这是刻意设计——不把「HTTP 200 但没送达」当成功。

```bash
curl -s -X POST http://<服务器地址>/notify \
  -H 'Content-Type: application/json' \
  -d "{\"token\":\"$(cat config/notify_token.txt)\",\"title\":\"测试\",\"content\":\"来自 curl 的测试通知\"}"
```

### 3.5 GET `/wecom_callback` — 企业微信回调验证

企业微信配置回调 URL 时的一次性验证请求（SHA1 签名 + AES 解密 echostr）。

**Query 参数**

| 参数 | 必填 | 说明 |
|---|---|---|
| `msg_signature` | 是 | 企业微信签名 |
| `timestamp` | 否 | 时间戳（缺省空串） |
| `nonce` | 是 | 随机串 |
| `echostr` | 是 | 加密的回显串 |

**响应**

| 状态码 | 响应体 | 说明 |
|---|---|---|
| 200 | 解密后的明文 | 验证通过，企业微信会把这段明文当作校验结果 |
| 403 | 空 | 签名不匹配 |
| 400 | 空 | 参数缺失或解密异常 |

**已知限制**：`POST /wecom_callback`（接收消息推送）**当前未实现**，会落到 404。本服务只用于 URL 验证，不接收企业微信上行消息。

### 3.6 OPTIONS `*` — CORS 预检

固定返回 `204` 无内容，供浏览器跨域调用 `/status`、`/run` 前预检。

### 3.7 兜底行为

| 方法 | 路径 | 响应 |
|---|---|---|
| GET | 上述之外任意路径 | `200`，纯文本 `ok` |
| POST | 上述之外任意路径 | `404`，`{"ok":false,"detail":"not found"}` |

GET 兜底返回 `ok`（而非 404）是为了兼容企业微信对回调地址的探测请求。

## 4. 安全说明（必读）

**`/status` 与 `POST /run` 无鉴权。** 任何能访问到地址的人都可以：

- 读取最近一次运行状态、积分余额摘要和 40 行日志
- 触发一次完整流程（会真实执行签到与推送）

这是为了「看板即开即用、不弹登录」做的取舍，代码层面没有内置防护。缓解方式：

1. 部署在内网或仅本机访问（`BK_ECHO_HOST=127.0.0.1`）
2. 前面加一层带鉴权的反向代理（如 Nginx `auth_basic`）
3. 启用 HTTPS，避免访问令牌在公网明文传输

**当前默认部署是 HTTP + 裸 IP**，访问令牌走明文。若需长期对外使用，建议按 [使用说明](USAGE.md) 的「启用 HTTPS」一节处理。

## 5. 错误码汇总

| HTTP | 含义 | 出现在 | 客户端该怎么做 |
|---|---|---|---|
| 200 | 成功（含「已合并」这类成功的业务提示） | 全部 | 读 `detail` 判断语义 |
| 204 | 预检成功 | OPTIONS | 继续正式请求 |
| 400 | 请求体不合法 / 参数缺失 | `/run` `/notify` `/wecom_callback` | 修请求，不要重试 |
| 403 | 令牌或签名不匹配 | `/notify` `/wecom_callback` | 核对令牌，不要重试 |
| 404 | 路径不存在 | POST 兜底 | 检查方法是否用错 |
| 500 | 服务端内部异常 | 全部 | 查 `cron.log`，可重试一次 |
| 502 | 下游业务失败 | `/notify` | 查推送配置，不要盲目重试 |
