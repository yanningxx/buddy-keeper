---
name: buddy-keeper
version: "1.2.9"
display_name: "WorkBuddy 每日签到全勤值守"
display_name_en: "WorkBuddy Daily Check-in & Streak Watch"
description: "值守 WorkBuddy 每日签到与全勤（Buddy加油站签到、今日礼包、猫猫旅行派遣、积分余额、成长计划）。当用户说「帮我签到」「今天签到了吗」「我是不是要断签了」「连续签了几天」「全勤还差多少」「设置每天自动签到」「以后不用我点了」，或提到 WorkBuddy 积分不够、断签、连续签到天数、全勤奖励、活动剩余天数时使用。在服务器上每天 09:00 无人值守执行：不依赖本机与客户端、不碰界面、无需扫码；签到与领取幂等不重复，并发只跑一份，失败按网络类与业务类分类重试且绝不静默失败，结果推送到企业微信，可在看板随时查状态并一键补跑。"
description_zh: "值守 WorkBuddy 每日签到与全勤（Buddy加油站签到、今日礼包、猫猫旅行派遣、积分余额、成长计划）。触发词：帮我签到、今天签到了吗、是不是要断签了、连续签了几天、全勤还差多少、设置每天自动签到、以后不用我点了、断签、连续签到天数、全勤奖励。服务器端每天 09:00 无人值守执行，不依赖本机、不碰界面、无需扫码，幂等不重复，并发只跑一份，失败分类重试且不静默，结果推送企业微信，可在看板查看并一键补跑。"
description_en: "Watches your daily WorkBuddy check-in and streak (Buddy Gas Station check-in, daily gift, buddy travel dispatch, credit balance, growth plan). Use when the user says \"help me check in\", \"did I check in today\", \"am I about to break my streak\", \"how many days in a row\", \"how far from full attendance\", or \"set up a daily auto check-in\", or mentions missed check-ins, streak days, full-attendance rewards, or remaining activity days. Runs unattended on a server at 09:00 daily: no local client, no UI tapping, no QR scan; idempotent claims, single-flight lock, classified retries, never fails silently, pushes results to WeCom, and supports dashboard review plus one-click re-run."
author: yanningxx
category: productivity
---

# WorkBuddy 每日签到全勤值守（BuddyKeeper）

把 WorkBuddy 的每日签到 / 猫猫旅行 / 积分播报这套流程，做成**服务器上每天 09:00 自己跑、可问、可查、可诊断、可补跑**的技能。
与「本机签到类」技能的区别只有一条：它不依赖你的电脑开着，也不依赖你说话——**全勤是连续扣分项，断一天补不回来，所以它必须自己跑**。

## 什么时候用

- 「今天签到 / 旅行跑了吗」「昨天的播报呢」
- 「帮我跑一次签到旅行」「看下积分余额」
- 「定时任务是不是又没执行」「看板打不开」
- 「为什么会显示待领 N 积分」「活动那里为什么提示可领」

## 系统事实（先读，避免误判）

| 项 | 值 |
|---|---|
| 服务器部署路径 | `/opt/buddy-keeper` |
| 唯一入口 | `src/daily_runner.py`（签到 → 旅行 → 推送） |
| 定时任务 | `/etc/cron.d/buddy-keeper`，`0 9 * * *` 以 `ubuntu` 身份执行 |
| 日志 | `logs/cron.log`（cron 重定向）、`logs/run.log`（应用日志） |
| 状态文件 | `logs/last_run_state.json`（结构：`date` / `started` / `finished` / `attempts`） |
| 权限要求 | `logs/cron.log` 必须对 `ubuntu` 可写（0666）。若被 root 改成 644，cron 会在启动 Python **之前** 就因 `>>` 重定向失败，表现为「触发了但什么都没发生」 |
| 单飞锁 | `logs/run.lock`，看板「立即执行一次」与 cron 并发时只跑一个 |

## 常用操作

### 1. 只看状态（只读，零副作用）

```bash
ssh "$BK_USER@$BK_HOST" 'cat /opt/buddy-keeper/logs/last_run_state.json'
ssh "$BK_USER@$BK_HOST" 'tail -n 40 /opt/buddy-keeper/logs/cron.log'
```

### 2. 立即跑一次（有副作用：会签到、派旅行、发推送）

```bash
ssh "$BK_USER@$BK_HOST" 'cd /opt/buddy-keeper && WB_MAX_RETRIES=0 /usr/bin/python3 src/daily_runner.py'
```

### 3. 只读查积分 / 旅行状态（不写、不推送）

在服务器上执行：

```bash
cd /opt/buddy-keeper && /usr/bin/python3 lib/buddy_station.py --json --no-toast --no-push
```

该命令只调用 GET 接口与签到状态查询，`--travel-auto` 未加时**不会**派遣或领取。

### 4. 诊断「定时任务没跑」

按这个顺序查，不要跳步：

1. `systemctl is-active cron` —— 服务是否活着
2. `grep buddy /etc/cron.d/buddy-keeper` —— 行格式是否为「分 时 日 月 周 用户 命令」，用户字段在命令之前
3. `ls -l logs/cron.log` —— 属主与权限；必须 `ubuntu` 可写
4. `grep "$(date +%F)" logs/cron.log` —— 当日是否有执行记录
5. 若 1-3 正常但 4 为空：查 `logs/cron.<uid>.log`（降级日志），说明主日志当时不可写

## 概念澄清（被问到时按这个口径回答）

- **「旅行：待领 N」**：`travel.reward_credit`，是本次旅行的**预计**奖励。只有 `state == "arrived"`（已到达）才可领取；`traveling` 状态下点任何按钮都领不到。到达后下次运行会自动先领再派。
- **「活动：有积分可领（立即领取）」**：`claim_button_text` 是服务端下发的**静态文案**，已签到时它依然返回「立即领取」。真正可领判据是 `today_checked_in == false`（每日签到奖励）或任务进度达成且 `accept_status != claimed`。不要拿按钮文案当可领依据。
- **任务奖励**：目前在客户端包与日志中均未发现独立的领取接口，重复扣问时不要编造接口。

## 文档索引（答不上来时去这里查，不要猜）

| 问题类型 | 看哪份 |
|---|---|
| 「它整体怎么设计的」「想加个功能改哪里」 | `docs/DESIGN.md`（设计文档） |
| 「这个接口怎么调」「返回什么字段」「错误码含义」 | `docs/API.md`（接口文档） |
| 「怎么装」「怎么配」「XX 报错怎么办」 | `docs/USAGE.md`（使用说明） |
| 「鉴权怎么走的」「余额为什么要 UA」 | `docs/ARCHITECTURE.md`（架构速览） |
| 「给看板配个域名 / 上 HTTPS」 | `docs/DOMAIN-SETUP.md` |
| 「这作品有什么亮点 / 怎么向别人介绍」 | `docs/ESSAY-1024.md`（1024 造物挑战参赛征文） |
| 「怎么投稿到灵感社区 / 官方案例」 | `docs/INSPIRATION-SUBMISSION.md`（策展制，需走官方通道） |

接口速查：`GET /status`（看状态，免鉴权）、`POST /run`（触发一次，免鉴权）、`POST /notify`（推送，需 token）、`GET /`（看板页面）。

## 边界

- 不要在没有用户确认时执行第 2 项（有真实副作用：真的会签到、派旅行、发微信推送）。
- 不要在技能里写入任何服务器密码、token、cookie；凭据一律用环境变量 `BK_HOST` / `BK_USER` / `BK_PASS`。
- 源码与版本：<https://github.com/yanningxx/buddy-keeper>
