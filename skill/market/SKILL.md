---
name: buddy-keeper-watch
version: "1.3.0"
display_name: "WorkBuddy 每日签到全勤值守"
display_name_en: "WorkBuddy Check-in & Streak Watch"
description: "查询 WorkBuddy 每日签到与全勤状态（今日是否已签、连续天数、积分余额、成长计划进度、活动剩余天数、猫猫旅行状态）。当用户说「今天签到了吗」「连续签了几天」「全勤还差多少」「积分还剩多少」「猫猫到哪了」「昨天的播报怎么没来」时使用。只读查询：不修改账号状态、不代领任何奖励、不接触客户端界面、不索取任何凭据；同时可读取值守服务每天 09:00 生成的状态与日志，用来解读播报、定位漏跑原因，并在存在断签风险时给出提醒。"
description_zh: "查询 WorkBuddy 每日签到与全勤状态（今日是否已签、连续天数、积分余额、成长计划进度、活动剩余天数、猫猫旅行状态）。触发词：今天签到了吗、连续签了几天、全勤还差多少、积分还剩多少、猫猫到哪了、播报怎么没来。只读查询，不修改账号状态、不代领奖励、不接触客户端界面、不索取凭据；可读取值守服务每天 09:00 生成的状态与日志，用于解读播报与定位漏跑，并在有断签风险时提醒。"
description_en: "Check WorkBuddy daily check-in and streak status (checked in today, streak days, credit balance, growth plan progress, remaining activity days, buddy travel status). Use when the user asks \"did I check in today\", \"how many days in a row\", \"how far from full attendance\", \"how many credits left\", \"where is my buddy\", or \"why didn't today's report arrive\". Read-only: it never changes account state, never claims rewards, never touches the client UI, and never asks for credentials. It can also read the status and logs produced by the watch service at 09:00 daily to explain reports, diagnose missed runs, and warn about streak-break risk."
author: yanningxx
category: productivity
---

# WorkBuddy 每日签到全勤值守（查询与提醒版）

帮你随时看清 WorkBuddy 的签到与全勤状态，并解释每天 09:00 那条播报到底在说什么。
**这个版本只读**：不签到、不领奖、不派旅行、不改任何账号状态。

## 什么时候用

- 「今天签到了吗」「连续签了几天」「全勤还差多少」
- 「积分还剩多少」「成长计划还差什么」「活动还有几天」
- 「猫猫到哪了」「待领的那笔是多少」
- 「昨天的播报怎么没来」「为什么提示有积分可领却领不到」

## 数据口径（答之前先对齐，避免误判）

| 项 | 正确口径 |
|---|---|
| 今日签到 | 看 `today_checked_in` 布尔值。**不要**用按钮文案判断 |
| 可领积分 | 签到：`active && !today_checked_in`；任务：进度达标 且 `accept_status != claimed` 且 `has_reward` |
| 「立即领取」文案 | 服务端下发的静态 UI 文案，已签到时**依然**返回「立即领取」，不能当可领依据 |
| 旅行「待领 N」 | `travel.reward_credit` 是预计奖励；只有 `state == "arrived"` 才算真可领 |
| 全勤缺口 | 连续天数 + 活动剩余天数一起看，单看一个数会误判 |

## 只读查询怎么做

需要两个环境变量，由使用者自己配置，技能不读取、不回显、不落盘：

- `BK_BASE`：值守服务的访问地址
- `BK_TOKEN`：只读查询令牌

```bash
curl -s "$BK_BASE/status?token=$BK_TOKEN" | head -c 2000
```

返回 JSON 里的 `state` 与 `log_tail` 足够回答上面所有问题。**不要**在对话里打印 `BK_TOKEN` 的值。

## 排查「播报没来」

按顺序看三处，不要跳步：

1. 状态文件时间戳：`state.date` 是不是今天；
2. 日志尾部有没有当天 09:00 的执行记录；
3. 若有降级日志（`cron.<uid>.log`），说明主日志当时不可写，任务被记录到了别处。

三条都空 → 大概率是定时任务没触发，属于服务端运维问题，不在本技能范围内。

## 边界（重要）

- **不做**：签到、领取奖励、派遣旅行、修改成长计划——一次都不做。
- **不碰**：客户端界面、扫码、任何人机验证流程。
- **不索取**：账号密码、cookie、长效令牌。只接受使用者已配置好的只读查询令牌。
- **不承诺**：不保证连续签到不断，不承诺任何积分收益；本技能只负责"看清状态 + 提醒风险"。
