---
name: buddy-keeper
version: "1.2.8"
display_name: BuddyKeeper 值守助手
display_name_en: BuddyKeeper Daily Watch
description: 查看与触发 WorkBuddy 每日自动值守（签到、猫猫旅行、积分余额、成长计划），并诊断定时任务是否正常执行。
description_zh: 查看与触发 WorkBuddy 每日自动值守（签到、猫猫旅行、积分余额、成长计划），并诊断定时任务是否正常执行。
description_en: Inspect and trigger the WorkBuddy daily watch (check-in, buddy travel, credits, growth plan) and diagnose cron health.
author: yanningxx
category: productivity
---

# BuddyKeeper 值守助手

把 WorkBuddy 的每日签到 / 猫猫旅行 / 积分播报这套无人值守流程，做成可问、可查、可诊断的技能。

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

## 边界

- 不要在没有用户确认时执行第 2 项（有真实副作用：真的会签到、派旅行、发微信推送）。
- 不要在技能里写入任何服务器密码、token、cookie；凭据一律用环境变量 `BK_HOST` / `BK_USER` / `BK_PASS`。
- 源码与版本：<https://github.com/yanningxx/buddy-keeper>
