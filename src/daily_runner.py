#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WorkBuddy 云端自动化编排器（daily_runner）。

职责：
  1. 每日 9:00（由 crontab 触发，本脚本被调用时即执行首跑）运行两项核心操作：
       - 账号每日签到   (buddy_station.py checkin)
       - 触发猫猫旅行   (buddy_station.py --travel-auto，内含「先领取待领积分、后派遣」)
  2. 收集两次执行的 JSON 结果，判定每个项目的成功/失败与具体原因。
  3. 若首跑有任意项目失败，按固定间隔重试该项目：
       - 间隔 30 分钟；
       - 同一项目累计最多重试 3 次；
       - 该项目重试成功则立即停止其后续重试；
       - 全部重试结束后，把「首跑 + 所有重试」的结果统一汇总成一份报告。
  4. 把当日全量报告通过企业微信（push_notify.py 的 wecom 渠道）推送。

数据正确性说明（重要）：
  buddy_station.py --json 的顶层输出里，真正可靠的字段是：
    - total_credits    : 总积分余额（即日常说的「余额」）
    - streak_days      : 连续签到天数（即日常说的「连续签到」）
    - today_checked_in : 今日是否已签到
    - travel           : 旅行状态对象（含 state / reward_credit / auto_log 等）
  而 checkin_result.balance 与 checkin_result.detail.streak_days 仅在特定分支填充、
  且 balance 由 _extract_balance 尽力匹配，不可靠，故本编排器一律以顶层字段为准。

抗网络抖动：
  单步执行内置「快速重试」：若因 DNS/连接/超时等瞬断失败，会立即原地重试若干次，
  避免偶发抖动就傻等 30 分钟；仍失败才进入 30 分钟轮询重试。

仅依赖 Python 3 标准库。所有敏感凭据（refresh_token、企业微信 webhook）由技能目录与
push 配置文件在服务器本地保管，本脚本不读取、不打印任何令牌。
"""

from __future__ import annotations

import atexit
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, date, timedelta

# ===================== 路径配置（自动兼容旧扁平部署与新项目结构） =====================
HERE = os.path.dirname(os.path.abspath(__file__))          # .../src
ROOT = os.path.dirname(HERE)                                # 项目根


def _pick(*candidates):
    """返回第一个存在的候选路径；都不存在时返回首个（便于报错定位）。"""
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]


SKILL_DIR = os.environ.get(
    "WBSKILL_DIR",
    _pick(os.path.join(ROOT, "lib"),                          # 新结构：lib/
          os.path.join(HERE, "skills", "totorosir-workbuddy-score"),  # 旧扁平结构
          os.path.join(ROOT, "skills", "totorosir-workbuddy-score")),
)
PUSH_CONFIG = os.environ.get(
    "WBPUSH_CONFIG",
    _pick(os.path.join(ROOT, "config", "config.json"),        # 新结构
          os.path.join(HERE, "config.json"),                  # 旧扁平结构
          os.path.join(ROOT, "config.json")),
)
LOG_DIR = os.environ.get("WBLOG_DIR", os.path.join(ROOT, "logs"))
STATE_FILE = os.path.join(LOG_DIR, "last_run_state.json")
RUN_LOG = os.path.join(LOG_DIR, "run.log")   # 运行日志（看板读取，独立于 cron 重定向）
RUN_LOCK = os.path.join(LOG_DIR, "run.lock")  # 单飞锁文件（cron 与 /run 共用，防并发竞态）
CRON_LOG = os.path.join(LOG_DIR, "cron.log")  # cron / wecom-echo 重定向写入，须跨身份可写

def _tool(name):
    """定位工具脚本：兼容新结构 lib/<name> 与旧结构 <SKILL_DIR>/scripts/<name>。"""
    return _pick(os.path.join(SKILL_DIR, name),
                 os.path.join(SKILL_DIR, "scripts", name))


# ===================== 重试策略 =====================
MAX_RETRIES = int(os.environ.get("WB_MAX_RETRIES", "3"))
RETRY_INTERVAL_SEC = int(os.environ.get("WB_RETRY_INTERVAL_SEC", str(30 * 60)))
STEP_TIMEOUT_SEC = int(os.environ.get("WB_STEP_TIMEOUT_SEC", "300"))
PUSH_CHANNELS = os.environ.get("WB_PUSH_CHANNELS", "wecom,wecom_app")  # 企业微信群+个人微信(自建应用插件,全文无限制)

# 单步内部快速重试（对抗 DNS/连接瞬时抖动），避免偶发抖动就进入 30 分钟轮询
INNER_RETRIES = int(os.environ.get("WB_INNER_RETRIES", "3"))
INNER_RETRY_DELAY_SEC = int(os.environ.get("WB_INNER_DELAY_SEC", "20"))
# 签到业务失败（非网络类）的快速重试间隔：避免整点高峰抖动就傻等 30 分钟
CHECKIN_FAST_RETRY_DELAY_SEC = int(os.environ.get("WB_CHECKIN_FAST_DELAY", "60"))
# 网络类失败关键词：命中才做内部快速重试；业务失败（如 code!=0）不无意义重试
NETWORK_FAIL_HINTS = ("解析", "name resolution", "连接", "connection",
                      "timeout", "timed out", "网络", "HTTP 0", "URL",
                      "urlopen", "refused", "reset by peer", "getaddrinfo")

PYTHON = sys.executable

# 旅行 auto_log 中出现这些关键词，且不是成功/正常状态，才判定为真实失败。
TRAVEL_FAIL_HINTS = ("失败", "错误", "异常", "timeout", "timed out",
                     "connection", "refused", "unauthorized", "拒绝", "HTTP 4", "HTTP 5")

# ===================== 免费 / 折扣模型快照（通知用） =====================
# 来源：WorkBuddy 客户端「模型」下拉菜单（用户截图核对于 FREE_MODEL_SNAPSHOT_DATE）。
# 说明：免费标签多为「限时 / 夜间」性质，可能随活动变动；checkin 接口 JSON 经全字段
#       扫描确认不含任何模型/额度数据，故此处用静态快照。标签变动时告知我更新此列表，
#       或让我另寻实时接口。所有改动只动下面这一个列表即可。
FREE_MODEL_SNAPSHOT_DATE = "2026-10-26"
FREE_MODELS_SNAPSHOT = [
    {"name": "Hy3", "tag": "限时免费", "mult": "0.00x"},
    {"name": "Hy4 preview", "tag": "夜间免费", "mult": "0.29x"},
    {"name": "Deepseek-V4.1-Flash", "tag": "夜间折扣", "mult": "0.11x"},
]


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "[%s] %s" % (ts, msg)
    print(line, flush=True)
    try:
        with open(RUN_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001
        pass


def acquire_run_lock():
    """单飞锁：保证 cron 与看板 /run 触发的 daily_runner 同一时刻仅一个实例在运行。

    采用 fcntl.flock 非阻塞排他锁，锁文件为 RUN_LOCK；锁随进程退出自动释放，
    不存在残留锁导致死锁的风险。root（经 /run）与 ubuntu（cron）跨身份共用同一锁
    文件，故文件权限放宽到 0666。已被其他实例持有时返回 None（调用方应跳过本次运行）。
    """
    try:
        fd = os.open(RUN_LOCK, os.O_RDWR | os.O_CREAT, 0o666)
    except OSError as e:
        log("单飞锁：无法打开锁文件（%s），降级为不加锁运行" % e)
        return None
    try:
        os.chmod(RUN_LOCK, 0o666)
    except OSError:
        pass
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def release_run_lock(fd):
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def _log_skip_due_to_lock():
    """单飞锁命中：向 run.log 追加一行（不实际执行，避免并发竞态）。"""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(RUN_LOG, "a", encoding="utf-8") as fh:
            fh.write("[%s] 单飞锁：已有实例运行中，本次触发已合并跳过（避免并发竞态）\n" % ts)
    except Exception:  # noqa: BLE001
        pass


def extract_json(text):
    """从 buddy_station.py --json 的 stdout 中提取最后一个完整 JSON 对象。"""
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.rfind("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            return None
    return None


def parse_claimed_credit(auto_log):
    """从旅行 auto_log 文本里提取「本次实际领取的积分」。

    travel_claim 成功时会写入形如「✅ 已领取旅行奖励 +6 积分」的日志。
    """
    if not auto_log:
        return None
    for line in auto_log:
        m = re.search(r"已领取旅行奖励\s*\+?\s*(\d+)", str(line))
        if m:
            return int(m.group(1))
    return None


def _run_once(kind):
    """运行单个步骤一次，返回 (data, ok, reason, extra)。

    kind: "checkin" 或 "travel"
    """
    cmd = [PYTHON, _tool("buddy_station.py"),
           "--json", "--no-toast", "--no-push"]
    if kind == "checkin":
        cmd.append("checkin")
    elif kind == "travel":
        cmd.append("--travel-auto")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=STEP_TIMEOUT_SEC,
                              env=dict(os.environ, HOME="/home/ubuntu"))
    except subprocess.TimeoutExpired:
        return None, False, "执行超时（%d 秒）" % STEP_TIMEOUT_SEC, {}
    except Exception as exc:  # noqa: BLE001
        return None, False, "启动失败：%s" % exc, {}

    data = extract_json(proc.stdout)
    if data is None:
        err = (proc.stderr or "").strip().splitlines()
        err = err[-1] if err else "(无 stderr)"
        return None, False, "无法解析输出：%s" % err, {}

    if kind == "checkin":
        ok, reason, extra = judge_checkin(data)
    else:
        ok, reason, extra = judge_travel(data)
    return data, ok, reason, extra


def _status_signed():
    """只读核实今日是否已签（buddy_station --check-only）。任何异常返回 False。"""
    cmd = [PYTHON, _tool("buddy_station.py"),
           "--json", "--no-toast", "--no-push", "--check-only", "checkin"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception:  # noqa: BLE001
        return False
    data = extract_json(proc.stdout)
    return bool(data and data.get("today_checked_in") is True)


def run_step(kind):
    """运行单个步骤：签到失败先只读核实状态，网络抖动原地重试，签到业务失败快速重试。"""
    last = None
    for attempt_i in range(INNER_RETRIES + 1):
        data, ok, reason, extra = _run_once(kind)
        last = (data, ok, reason, extra)
        if ok:
            return last
        reason_s = reason or ""
        # 签到报失败先只读核实：常见于「实际已签但响应异常」，避免空等 30 分钟
        if kind == "checkin" and _status_signed():
            extra = dict(extra or {})
            extra["status_verified"] = True
            log("  [%s] 接口报失败但状态核实今日已签，按成功处理" % kind)
            return (data, True, "首次响应异常，经只读核实今日已签", extra)
        # 网络类失败：原地快速重试
        if any(h in reason_s for h in NETWORK_FAIL_HINTS) and attempt_i < INNER_RETRIES:
            log("  [%s] 网络瞬时失败，%d 秒后快速重试（%d/%d）：%s"
                % (kind, INNER_RETRY_DELAY_SEC, attempt_i + 1, INNER_RETRIES, reason_s))
            time.sleep(INNER_RETRY_DELAY_SEC)
            continue
        # 签到业务失败（如整点高峰抖动）：最多再快速重试 2 次，仍失败才进入 30 分钟轮询
        if kind == "checkin" and attempt_i < 2:
            log("  [%s] 失败，%d 秒后快速重试（%d/2）：%s"
                % (kind, CHECKIN_FAST_RETRY_DELAY_SEC, attempt_i + 1, reason_s))
            time.sleep(CHECKIN_FAST_RETRY_DELAY_SEC)
            continue
        return last
    return last


def calc_current_streak(dates):
    """从当月签到日期集合计算「当前连续登录天数」（与客户端活跃地图同口径）。

    实测确认：接口的 streak_days 是「累计签到天数」（= checkin_dates_total，
    2026-10-26 实测均为 12），不是当前连续；当前连续必须自己按日期算。
    局限：checkin_dates_this_month 只含当月，若连续段跨月则少算，如实按当月计。
    """
    ds = set()
    for s in dates or []:
        try:
            y, m, d = str(s).split("-")
            ds.add(date(int(y), int(m), int(d)))
        except Exception:  # noqa: BLE001
            continue
    streak = 0
    day = date.today()
    if day not in ds:
        day -= timedelta(days=1)
    while day in ds:
        streak += 1
        day -= timedelta(days=1)
    return streak


def judge_checkin(data):
    """判定签到成功/失败，并提取余额、连签等展示信息。

    字段口径（2026-10-26 实测对齐客户端「活跃地图」）：
      - streak_days = 累计签到天数（非当前连续！）
      - 当前连续登录 = 由 checkin_dates_this_month 自行计算
      - streak_schedule 中 type=累计发放 的 remaining = 距下一档累计奖励的天数
    """
    cr = data.get("checkin_result") or {}
    action = cr.get("action")
    today = data.get("today_checked_in")
    total = data.get("total_credits")
    streak = data.get("streak_days")
    cur = calc_current_streak(data.get("checkin_dates_this_month"))
    mile = None
    for t in (data.get("streak_schedule") or []):
        if isinstance(t, dict) and t.get("type") == "累计发放" \
                and t.get("remaining") is not None:
            mile = t
            break
    extra = {"total_credits": total, "streak_days": streak,
             "today_checked_in": today, "action": action,
             "current_streak": cur, "milestone": mile}

    if action == "failed":
        return False, "签到失败：" + (cr.get("msg") or "未知原因"), extra
    if action == "clicked":
        return True, "今日新签到成功", extra
    if action in ("skip_already_signed", "skip_check_only") or today is True:
        return True, "今日已签到（幂等，不重复领取）", extra
    return False, "签到状态未知：action=%s" % action, extra


def judge_travel(data):
    """判定猫猫旅行是否真正失败，并提取领取/派遣展示信息。

    正确字段来自 JSON 顶层 travel：state / state_text / reward_credit / auto_log。
    """
    tr = data.get("travel") or {}
    if not isinstance(tr, dict):
        return False, "未返回旅行结果字段", {}
    if tr.get("available") is False:
        return False, "旅行数据不可取（鉴权/网络/接口异常）", {}

    auto_log = tr.get("auto_log") or []
    claimed = parse_claimed_credit(auto_log)
    fail_lines = [str(ln) for ln in auto_log
                  if any(h in str(ln).lower() for h in TRAVEL_FAIL_HINTS)]
    extra = {
        "state_text": tr.get("state_text") or tr.get("state"),
        "state": tr.get("state"),
        "reward_credit": tr.get("reward_credit"),
        "claimed_credit": claimed,
        "auto_log": auto_log,
    }
    if fail_lines:
        return False, "旅行子操作失败：" + "；".join(fail_lines), extra
    return True, "旅行流程已执行（含自动领取）", extra


def _short(s, n=28):
    s = str(s)
    return s if len(s) <= n else s[:n] + "…"


def fmt_step(kind, attempts):
    """把某项目的多次尝试压缩为一行（成功）或一行失败说明（失败）。"""
    label = "签到" if kind == "checkin" else "旅行"
    a = attempts[-1]
    icon = "✅" if a["ok"] else "❌"
    ex = a.get("extra") or {}
    if not a["ok"]:
        return "%s %s：失败——%s（已重试 %d 次）" % (icon, label, a["reason"],
                                                 max(0, len(attempts) - 1))
    if kind == "checkin":
        bits = []
        if ex.get("current_streak") is not None:
            bits.append("连续 %s 天" % ex["current_streak"])
        if ex.get("streak_days") is not None:
            bits.append("累计 %s 天" % ex["streak_days"])
        return "%s %s：已签｜%s" % (icon, label, "｜".join(bits) or a["reason"])
    parts = []
    st_map = {"traveling": "旅行中", "arrived": "已完成", "idle": "空闲"}
    st = st_map.get(str(ex.get("state") or "")) or ex.get("state_text") or ex.get("state")
    if st:
        parts.append(str(st))
    if ex.get("claimed_credit"):
        parts.append("已领 +%s" % ex["claimed_credit"])
    elif ex.get("reward_credit"):
        parts.append("待领 %s" % ex["reward_credit"])
    else:
        parts.append("待领 0")
    alog = ex.get("auto_log") or []
    dispatch = [str(ln) for ln in alog
                if any(k in str(ln) for k in ("派遣", "派出", "已派", "前往"))]
    if dispatch:
        parts.append(_short(dispatch[-1]))
    return "%s %s：%s" % (icon, label, "｜".join(parts))


def _count_unfinished(tasks):
    """统计未完成任务数：progress.current < progress.target。"""
    n = 0
    for t in tasks or []:
        p = t.get("progress") or {}
        cur = p.get("current", 0) or 0
        tgt = p.get("target", 0) or 0
        if cur < tgt:
            n += 1
    return n


def fmt_activity(data):
    """把「成长计划 + 积分活动」各压缩为一行。"""
    if not isinstance(data, dict):
        return None
    g = data.get("growth") or {}
    act = data.get("activity") or {}
    claim = data.get("claim") or {}
    tasks = g.get("tasks") or []
    prof = g.get("profile") or {}
    buddy = g.get("buddy") or {}
    lines = []
    bits = []
    if prof.get("level") is not None:
        bits.append("Lv%s" % prof.get("level"))
    if buddy.get("name"):
        bits.append("%s %s" % (buddy.get("name"), buddy.get("tier") or ""))
    if data.get("week_progress_total"):
        bits.append("本周 %s/%s 天" % (data.get("week_progress_done"), data.get("week_progress_total")))
    if tasks:
        bits.append("未完成任务 %s 项" % _count_unfinished(tasks))
    if bits:
        lines.append("成长计划：" + "｜".join(bits))
    abits = []
    if act.get("active"):
        s = str(act.get("activity_name") or act.get("theme_name") or "活动")
        if act.get("remaining_days") is not None:
            s += " 剩%s天" % act["remaining_days"]
        if act.get("full_attendance_estimate") is not None:
            s += " 全勤+%s" % act["full_attendance_estimate"]
        abits.append(s)
    else:
        abits.append("无进行中")
    # 只按「真实可领积分」提示；claim_button_text 是服务端静态文案（已签到时仍回
    # 「立即领取」），拿它当判据会产生假阳性（v1.2.7 及之前的老毛病）。
    ccb = claim.get("claimable_credit") or 0
    if ccb > 0:
        detail = []
        ck = claim.get("claimable_checkin_credit") or 0
        tc = claim.get("claimable_task_count") or 0
        if ck:
            detail.append("今日签到未领 +%s" % ck)
        if tc:
            detail.append("%s 项任务奖励 +%s" % (tc, ccb - ck))
        abits.append("⚠️ 可领 +%s（%s）" % (ccb, "、".join(detail)))
    lines.append("活动：" + "｜".join(abits))
    return "\n".join(lines)


def fmt_free_models(snapshot=None):
    """免费/折扣模型一行速览（静态快照，标签变动时更新 FREE_MODELS_SNAPSHOT）。"""
    items = snapshot if snapshot is not None else FREE_MODELS_SNAPSHOT
    if not items:
        return None
    parts = ["%s %s %s" % (m.get("name"), m.get("tag"), m.get("mult")) for m in items]
    return "免费模型：" + "；".join(parts) + "（以客户端为准）"


def fmt_balance():
    """积分余额一行（直连接口；失败返回提示行，不影响整体）。"""
    text, _ = _balance_text_and_info()
    return text


def _balance_text_and_info():
    """返回 (展示行, 结构化信息)。结构化信息供状态文件/看板使用。"""
    try:
        import balance_direct
        data = balance_direct.fetch_balance()
        total = balance_direct._num(data.get("TotalCredits"))
        info = {"balance": total,
                "plan": data.get("SubscriptionPackageName")}
        return "积分余额：%s" % total, info
    except Exception as exc:  # noqa: BLE001
        return "积分余额：获取失败（%s）" % str(exc)[:80], {"balance_error": str(exc)[:120]}


def _bold_labels(block):
    """把每行「名称：」的名称部分加粗（markdown **），供企业微信渲染。"""
    lines = []
    for line in block.split("\n"):
        if "：" in line and not line.startswith("**"):
            head, _, rest = line.partition("：")
            lines.append("**%s**：%s" % (head, rest))
        else:
            lines.append(line)
    return "\n".join(lines)


def build_report(date_str, attempts, run_started, checkin_data=None):
    all_ok = attempts["checkin"][-1]["ok"] and attempts["travel"][-1]["ok"]
    blocks = ["**WorkBuddy 每日播报 %s（%s）**"
              % (date_str, "全部成功" if all_ok else "存在失败，见下")]
    blocks.append(_bold_labels(fmt_step("checkin", attempts["checkin"])))
    blocks.append(_bold_labels(fmt_step("travel", attempts["travel"])))
    blocks.append(_bold_labels(fmt_balance()))
    act = fmt_activity(checkin_data)
    if act:
        blocks.append(_bold_labels(act))
    fm = fmt_free_models()
    if fm:
        blocks.append(_bold_labels(fm))
    return "\n".join(blocks)


def push_report(title, content):
    push_script = _tool("push_notify.py")
    if not os.path.isfile(push_script):
        log("未找到 push_notify.py，跳过推送")
        return False
    if not os.path.isfile(PUSH_CONFIG):
        log("未找到推送配置 %s，跳过推送" % PUSH_CONFIG)
        return False
    cmd = [PYTHON, push_script, "--title", title, "--content", content,
           "--channels", PUSH_CHANNELS, "--push-config", PUSH_CONFIG]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        log("推送结果：%s" % (proc.stdout or proc.stderr).strip())
        return proc.returncode == 0
    except Exception as exc:  # noqa: BLE001
        log("推送异常：%s" % exc)
        return False


def save_state(state):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001
        log("状态文件写入失败：%s" % exc)


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    # 单飞锁：先尝试加锁；已被其他实例（cron 或上一轮 /run）持有则合并跳过
    _lock_fd = acquire_run_lock()
    if _lock_fd is None:
        _log_skip_due_to_lock()
        sys.exit(0)
    atexit.register(release_run_lock, _lock_fd)
    os.makedirs(LOG_DIR, exist_ok=True)
    # 保证运行日志与锁文件跨身份（root 经 /run 与 ubuntu cron）均可写：
    # /run 由 wecom-echo(root) 派生的子进程可能先创建这些文件导致属主为 root，
    # 使 ubuntu 的 cron 任务无法追加日志。统一放宽到 0666 自愈合。
    for _p in (RUN_LOG, RUN_LOCK, CRON_LOG):
        try:
            if not os.path.exists(_p):
                _fd = os.open(_p, os.O_RDWR | os.O_CREAT, 0o666)
                os.close(_fd)
            os.chmod(_p, 0o666)
        except OSError:
            pass
    date_str = datetime.now().strftime("%Y-%m-%d")
    run_started = now_str()
    log("==== 开始当日自动化（%s）====" % date_str)

    # 首跑
    attempts = {"checkin": [], "travel": []}
    last_data = {"checkin": None, "travel": None}
    for kind in ("checkin", "travel"):
        data, ok, reason, extra = run_step(kind)
        last_data[kind] = data
        attempts[kind].append({"ts": now_str(), "ok": ok,
                               "reason": reason, "extra": extra})
        log("%s 首跑：%s —— %s" % (kind, "成功" if ok else "失败", reason))

    # 重试循环：仅对失败项目重试，最多 MAX_RETRIES 次，间隔 RETRY_INTERVAL_SEC
    pending = {k: not attempts[k][-1]["ok"] for k in ("checkin", "travel")}
    retry_count = {"checkin": 0, "travel": 0}
    while any(pending.values()):
        log("等待 %d 秒后进行下一轮重试…" % RETRY_INTERVAL_SEC)
        time.sleep(RETRY_INTERVAL_SEC)
        for kind in ("checkin", "travel"):
            if not pending[kind]:
                continue
            if retry_count[kind] >= MAX_RETRIES:
                pending[kind] = False
                continue
            retry_count[kind] += 1
            data, ok, reason, extra = run_step(kind)
            last_data[kind] = data
            attempts[kind].append({"ts": now_str(), "ok": ok,
                                   "reason": reason, "extra": extra})
            log("%s 重试#%d：%s —— %s" % (kind, retry_count[kind],
                                        "成功" if ok else "失败", reason))
            if ok:
                # 成功即停止该项目后续重试
                pending[kind] = False

    # 用最近一次「签到」返回的完整 JSON 填充积分活动/可领提醒区块
    report = build_report(date_str, attempts, run_started,
                          checkin_data=last_data.get("checkin"))
    log("==== 当日报告 ====\n" + report)

    # 看板所需的结构化摘要：余额、成长计划等级/Buddy、未完成任务数
    _, bal_info = _balance_text_and_info()
    cdata = last_data.get("checkin") or {}
    g = (cdata.get("growth") or {}) if isinstance(cdata, dict) else {}
    ck_extra = attempts["checkin"][-1].get("extra") or {}
    ck_extra.update(bal_info)
    gprof = g.get("profile") or {}
    gbuddy = g.get("buddy") or {}
    gtasks = g.get("tasks") or []
    ck_extra["growth"] = {
        "level": gprof.get("level"),
        "buddy": (gbuddy.get("name") or "") + (
            (" " + gbuddy["tier"]) if gbuddy.get("tier") else ""),
    }
    ck_extra["unfinished_tasks"] = _count_unfinished(gtasks)
    attempts["checkin"][-1]["extra"] = ck_extra

    save_state({"date": date_str, "started": run_started,
                "finished": now_str(), "attempts": attempts})
    push_report("WorkBuddy 每日自动化 %s" % date_str, report)
    log("==== 当日自动化结束 ====")


if __name__ == "__main__":
    main()
