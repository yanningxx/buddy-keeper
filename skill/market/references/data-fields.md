# 状态字段口径表

值守服务每天 09:00 跑完会把结果写成一份快照，`GET /status` 原样返回。下面逐字段说明取值含义与边界条件。

## 顶层结构

```json
{
  "ok": true,
  "state": {
    "date": "2026-10-28",
    "started": "09:00:03",
    "finished": "09:00:41",
    "attempts": {
      "checkin": [ { "ok": true, "reason": "...", "extra": { } } ],
      "travel":  [ { "ok": true, "reason": "...", "extra": { } } ]
    }
  },
  "log_tail": ["...最近 40 行日志..."]
}
```

| 字段 | 含义 | 判读要点 |
|---|---|---|
| `ok` | 本次查询本身是否成功 | `false` 时看 `detail`，此时 `state` 不可信 |
| `state` | 最近一次运行的快照 | 为 `null` 说明从没成功跑过，不是「今天没数据」 |
| `state.date` | 这次运行属于哪一天 | **和今天比对**，不一致就是任务没跑，不是签到失败 |
| `state.started` / `finished` | 起止时间 | 两者相差过大（>5 分钟）说明卡在重试里 |
| `attempts.<kind>` | 该项目的**尝试列表** | 数组，取**最后一项**作为最终结果 |
| `log_tail` | 日志尾部 | 只有日志，不参与判定，用来解释原因 |

## checkin 分支

`attempts.checkin[-1].extra`：

| 字段 | 类型 | 含义 | 坑 |
|---|---|---|---|
| `today_checked_in` | bool | 今日是否已签到 | **唯一可信的签到判据** |
| `action` | str | 本次动作结果 | 见下表 |
| `current_streak` | int | 当前**连续**天数 | 由本月签到日期序列实时算出 |
| `streak_days` | int | **累计**签到天数 | 不是连续！两者经常被混用 |
| `total_credits` | int | 积分总额 | 与 `balance` 口径可能差一笔，以 `balance` 为准 |
| `balance` | int | 积分余额 | 取不到时该字段缺失，改看 `balance_error` |
| `balance_error` | str | 余额获取失败原因 | 有它就别报数字 |
| `plan` | str | 当前订阅套餐名 | 可为空 |
| `milestone` | obj | 下一档「累计发放」奖励 | 含 `remaining`＝距下一档还差几天 |
| `growth.level` | int | 成长计划等级 | — |
| `growth.buddy` | str | 当前 Buddy 名称与品阶 | 形如「小沃 · 精英」 |
| `unfinished_tasks` | int | 未完成任务数 | `progress.current < target` 的条数 |

`action` 取值：

| 值 | 含义 | 是否算成功 |
|---|---|---|
| `clicked` | 本次真点了签到，成功后返回 | 是 |
| `skip_already_signed` | 今天已签，幂等跳过，**没有重复领取** | 是 |
| `skip_check_only` | 只读探测模式下跳过 | 是 |
| `failed` | 签到失败，原因在 `state.reason` 或 `checkin_result.msg` | 否 |

## travel 分支

`attempts.travel[-1].extra`：

| 字段 | 类型 | 含义 | 坑 |
|---|---|---|---|
| `state` | str | `traveling` / `arrived` / `idle` | 只有 `arrived` 才可领 |
| `state_text` | str | 客户端展示文案 | 口语化，不能当判据 |
| `reward_credit` | int | **预计**奖励 | 是预计，不是已到账 |
| `claimed_credit` | int | 本次实际领到的积分 | 从 `auto_log` 里解析出来 |
| `auto_log` | list[str] | 子操作流水 | 失败原因常藏在这里 |

判读顺序：先看 `state`，再看 `claimed_credit`，最后才看 `reward_credit`。
`state != "arrived"` 时，`reward_credit` 再大也只是预期，不能回答「能领多少」。

## 已确认的客户端行为（决定了上面这些坑）

1. 签到按钮的 UI 状态是 `today_checked_in ? "claimed" : "available"`，
   而服务端下发的文案**已签到时仍返回「立即领取」**（2026-10-28 实测）。
   → 只看文案会每天误报「有积分可领」。
2. 签到接口在已签到时直接 skip，所以重复执行安全，不会多领。
3. 成长任务可领 = 进度达标 **且** `accept_status != "claimed"` **且** `has_reward` 不为假 **且** `reward_credit > 0`。
   四个条件少一个就会误报。
