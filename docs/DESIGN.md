# WorkBuddy 每日签到全勤值守 · 设计文档

> 版本 1.3.0 ｜ 最后更新 2026-10-28
> 配套文档：[接口文档](API.md) · [使用说明](USAGE.md) · [架构速览](ARCHITECTURE.md) · [运维手册](OPERATIONS.md)

## 1. 定位与边界

WorkBuddy 每日签到全勤值守 把 WorkBuddy 客户端里「每天点几下」的动作——签到、猫猫旅行、积分查询、成长计划查看——变成一台不需要人管的机器，每天定时跑一次，结果推到企业微信。

**它做什么**

- 每天 09:00 自动执行签到 → 旅行领取与派遣 → 积分余额查询 → 成长计划汇总
- 把结果整理成一段人话，推送到企业微信（群机器人或自建应用）
- 提供一个网页看板，随时查最近一次运行状态，也能手动触发一次

**它明确不做**

| 不做 | 原因 |
|---|---|
| 账号体系 / 多用户 | 单机单账号工具，引入用户体系只会增加密钥暴露面 |
| 存储任何个人数据 | 所有状态都是运行状态，不落用户隐私 |
| 修改或注入官方客户端 | 只调用公开 HTTP 接口，不碰客户端本体 |
| 代替客户端全部功能 | 只覆盖「每日重复动作」，不追求功能对齐 |

## 2. 整体架构

五层，自下而上：

```
┌─ 触发层 ─────────────────────────────────────────────┐
│  cron 09:00  ·  看板按钮 POST /run  ·  技能调用        │
└──────────────────────┬───────────────────────────────┘
┌─ 编排层 ─────────────▼───────────────────────────────┐
│  src/daily_runner.py   重试策略 · 单飞锁 · 状态落盘 · 播报文案 │
└──────────────────────┬───────────────────────────────┘
┌─ 能力层 ─────────────▼───────────────────────────────┐
│  lib/buddy_station.py  签到/旅行/成长计划/活动          │
│  src/balance_direct.py 积分余额（需网站会话）            │
│  lib/push_notify.py    推送（多通道）                   │
│  lib/rt_auth.py        长效令牌刷新                     │
│  lib/web_auth.py       网站会话兑换                     │
└──────────────────────┬───────────────────────────────┘
┌─ 接入层 ─────────────▼───────────────────────────────┐
│  WorkBuddy HTTP API (www.workbuddy.cn) · 企业微信 webhook │
└──────────────────────┬───────────────────────────────┘
┌─ 呈现层 ─────────────▼───────────────────────────────┐
│  src/wecom_echo_server.py   看板托管 + /status + /run   │
│  app/index.html  看板页面   site/index.html  发布页      │
└──────────────────────────────────────────────────────┘
```

关键设计取舍：**编排层不直接持有 HTTP 会话**。每个能力模块自己管自己的鉴权，因为它们需要的凭据完全不同（长效令牌 / 网站会话 / webhook key）。编排层只负责「按顺序调、失败重试、结果汇总」。

## 3. 模块划分

| 文件 | 职责 | 关键依赖 | 不负责 |
|---|---|---|---|
| `src/daily_runner.py` | 串起全部步骤，管重试、单飞锁、状态落盘、播报文案 | 下列所有能力模块 | 不直接发 HTTP |
| `lib/buddy_station.py` | 签到、成长计划、活动、旅行派遣；解析接口并生成播报块 | 长效令牌 | 不管推送、不管余额 |
| `src/balance_direct.py` | 只做积分余额查询 | 网站会话 cookie | 不管签到 |
| `lib/push_notify.py` | 多通道推送，失败判定看业务码 | 各通道配置 | 不管内容排版 |
| `lib/rt_auth.py` | 长效令牌读写与刷新 | `~/.workbuddy/checkin-rt.json` | 不管业务 |
| `lib/web_auth.py` | 用长效令牌换网站会话 cookie | 长效令牌 + 客户端 UA | 不管业务 |
| `src/wecom_echo_server.py` | HTTP 服务：托管看板、`/status`、`/run`、`/notify`、企微回调 | 无（标准库） | 不跑业务逻辑，只派生 `daily_runner` |
| `app/index.html` | 看板前端，同源 fetch | `/status` `/run` | 不做鉴权 |
| `site/index.html` | 对外发布页（纯静态） | 无 | 不连后端 |
| `scripts/deploy.py` | 上传代码、建目录、校验、重启服务 | SSH | 不构建 |
| `scripts/bind_domain.py` | 可选：绑自定义域名 + HTTPS，失败回滚 | SSH + nginx | 不是必需路径 |
| `skill/SKILL.md` | 技能定义，让 WorkBuddy 能问能查 | — | 不含逻辑 |

依赖方向单向：呈现层 → 编排层 → 能力层 → 接入层。能力层之间互不调用。

## 4. 数据模型

### 4.1 运行状态 `logs/last_run_state.json`

看板与 `/status` 的唯一数据源。结构：

```json
{
  "date": "2026-10-28",
  "started": "2026-10-28 09:00:01",
  "finished": "2026-10-28 09:00:14",
  "attempts": {
    "checkin": [ { "status": "ok", "extra": { "...": "步骤相关字段" } } ],
    "travel":  [ { "status": "ok" } ],
    "balance": [ { "status": "ok", "extra": { "balance": 297.73 } } ]
  }
}
```

- `attempts` 按步骤名分桶，每桶是**尝试数组**（同一步骤可能重试多次，最后一元素为最终结果）
- `extra` 是自由结构，各步骤自己定义；`checkin` 的 `extra` 会带 `growth`（等级、伙伴）与 `unfinished_tasks`（未完成任务数）
- 该文件**每次运行整体覆写**，不做历史累积；历史在日志里

### 4.2 日志

| 文件 | 写入方 | 用途 |
|---|---|---|
| `logs/cron.log` | cron 与 `/run` 派生的子进程 | 全量运行日志，权限位需 0666 让 ubuntu 的 cron 可写 |
| `logs/run.log` | 手动运行 | 被 `/status` 优先读取（存在则用，否则回退 cron.log） |

`/status` 只返回最后 40 行，避免看板被大日志拖垮。

### 4.3 凭据（全部不进版本库）

| 文件 | 内容 | 权限 |
|---|---|---|
| `~/.workbuddy/checkin-rt.json` | 长效令牌字段 `rt` | 600，ubuntu 属主 |
| `config/config.json` | 推送通道配置 | 600 |
| `config/notify_token.txt` | `/notify` 的鉴权令牌 | 600 |
| `config/wb_session_cookie.txt` | 网站会话降级缓存 | 600 |
| `config/deploy.local.json` | 部署凭据（SSH） | 600，已 gitignore |

### 4.4 外部接口契约（易变，重点标注）

| 字段 | 语义 | 陷阱 |
|---|---|---|
| `progress.current` / `progress.target` | 任务进度 | 完成标记**不在** `status`（实测恒为 null） |
| `accept_status` | `claimed` / `accepted` | 只有 `claimed` 表示奖励已领 |
| `reward_credit` | 奖励积分数 | 可能缺失，缺失按 0 处理 |
| `has_reward` | 是否有奖励 | 为 `false` 时即使达标也不可领 |
| **`claim_button_text`** | **服务端下发的静态 UI 文案** | **已签到时仍返回「立即领取」，绝不能当可领判据** |

最后一条是 v1.2.8 修复的假阳性根因，代码里 `claimable_credit()` 的注释保留了这个反例，改动前务必先读。

## 5. 关键流程

### 5.1 每日自动运行

```
cron 09:00 (ubuntu)
  └─ daily_runner.py
       ├─ 读长效令牌 → 签到 + 成长计划 + 活动
       ├─ 旅行领取 → 派遣
       ├─ 兑换网站会话 → 积分余额
       ├─ 汇总成播报文案
       ├─ save_state() 覆写 last_run_state.json
       └─ push_notify → 企业微信
```

任一步失败按分级策略重试，最终无论成败都落盘 + 推送，避免「静默失败」。

### 5.2 看板手动触发

```
浏览器 → POST /run
  └─ 建议性单飞检查（flock logs/run.lock，非阻塞）
       ├─ 已有实例在跑 → 直接返回「已合并」，不派生进程
       └─ 空闲 → Popen(daily_runner)，start_new_session=True，stdout 重定向到 cron.log
             → 立即返回 200「约 10 秒后可刷新查看」
```

真正的排他保证在 `daily_runner` 内部的文件锁，`/run` 的检查只是为了避免无谓派生进程。

### 5.3 可领积分判定 `claimable_credit()`

两条独立判据，都基于**数据事实**而非文案：

- **签到**：`active == true` 且 `today_checked_in == false` → 可领 `today_credit`
- **任务**：`current >= target` 且 `accept_status != "claimed"` 且 `has_reward != false` 且 `reward_credit > 0`

输出结构 `{credit, checkin_credit, tasks[], task_count}`，播报与看板都只消费这个结果。

## 6. 异常处理

| 场景 | 策略 |
|---|---|
| 网络类失败 | 20 秒间隔重试 3 次 |
| 业务类失败 | 60 秒间隔重试 2 次 |
| 前述均失败 | 进入 30 分钟轮询，直到成功或当日结束 |
| 并发触发 | `logs/run.lock` 文件锁，第二实例直接退出 |
| 推送失败 | 判定**业务码**（企业微信 `errcode`、PushPlus `code`），不看 HTTP 200，避免假成功 |
| 网站会话过期 | 每次运行重新兑换；兑换失败才回退到 `wb_session_cookie.txt` 缓存 |
| 状态文件写失败 | 不影响退出码，但会在播报里标出，避免看板显示上一次的旧数据却以为是最新 |
| 看板文件缺失 | `GET /` 返回 500 + `dashboard missing: <原因>`，不抛栈 |

重试次数可用环境变量 `WB_MAX_RETRIES` 覆盖（`/run` 派生时设为 0，让手动触发尽快返回结果）。

## 7. 扩展性

| 要加什么 | 改哪里 |
|---|---|
| 新推送通道 | `lib/push_notify.py` 增加 channel 实现 + `config.json` 增加配置段；失败判定沿用业务码模式 |
| 新的每日任务 | `daily_runner.py` 的 `attempts` 增加一个 step 桶，按「采集 → 组装播报块 → 落盘」三步写 |
| 换服务器 | 改 `config/deploy.local.json` 的 host，重跑 `deploy.py`，再按需跑 `bind_domain.py` |
| 上自定义域名 | 跑 `scripts/bind_domain.py`，它把后端从 `0.0.0.0:80` 迁到 `127.0.0.1:8080` 由 Nginx 接管；端口通过 `BK_ECHO_HOST` / `BK_ECHO_PORT` 注入，源码不需改 |
| 改看板样式 | 只动 `app/index.html`，它是同源托管，不需要改服务端 |

**不做水平扩展的说明**：文件锁、cron、状态文件都假设单机。要多实例得先把锁和状态挪到外部存储，这是另一个量级的改造，当前明确不支持。

## 8. 已知限制

1. **`/status` 与 `POST /run` 免令牌**。这是为了让看板即开即用（同源 fetch、不弹登录），代价是任何知道地址的人都能读状态、触发运行。缓解手段是部署在内网或加反向代理鉴权，代码层面未内置。
2. **单机单账号**。不适合多用户或多服务器。
3. **依赖官方接口与客户端 UA**。余额接口要求特定 UA，官方改版会失效，需同步调整。
4. **`/status` 只回 40 行日志**，排查长历史问题要看 `cron.log` 全文。
5. **不改客户端**，因此无法覆盖客户端独有的交互（例如需要图形验证的流程）。
