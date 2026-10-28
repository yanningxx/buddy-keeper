#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""balance_direct.py — 余额获取（服务器自给自足，全自动续会话）。

链路（2026-10-27 实测定案，全程只需服务器长效 rt 令牌，不依赖 Windows 客户端）：
1. rt_auth.read_rt() 读长效 refresh token（/home/ubuntu/.workbuddy/checkin-rt.json）
2. rt_auth.refresh_token() 换 accessToken
3. POST /v2/plugin/device/auth/code
   头必须同时带 `Authorization: Bearer <accessToken>` 与 `X-Refresh-Token: <rt>`
   （缺后者返回 code 10034「refresh token is empty」）→ 得 deviceCode（5 分钟有效）
4. GET /console/client-login?code=<deviceCode>&target=/  → 下发网站会话 cookie(session)
5. POST /billing/meter/get-user-resource-summary，头带该 cookie + 客户端 UA
   （网关按 UA 绑定会话，标准浏览器 UA 会 401）
6. 解析 TotalCredits

会话 cookie 每次现取现用，不存在过期问题；rt 失效时自动推失败通知。

用法：
  python balance_direct.py --notify-url http://127.0.0.1/notify   生产
  python balance_direct.py --test                                 只打印
"""

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))          # .../src
ROOT = os.path.dirname(HERE)                                # 项目根

# 依赖模块查找：仅用项目内 lib/（旧扁平结构 /opt/workbuddy-automation 已于 2026-10-28 移除）
_LIB = os.path.join(ROOT, "lib")
if os.path.isdir(_LIB):
    sys.path.insert(0, _LIB)

BALANCE_API = "https://www.workbuddy.cn/billing/meter/get-user-resource-summary"
DEVICE_CODE_API = "https://www.workbuddy.cn/v2/plugin/device/auth/code"
CLIENT_LOGIN = "https://www.workbuddy.cn/console/client-login"
CLIENT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) WorkBuddy/5.9.2 Chrome/138.0.7204.251 "
             "Electron/37.10.3 Safari/537.36")

def _pick(*cands):
    """返回首个存在的路径；都不存在返回第一个（便于报错定位）。"""
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]


TOKEN_PATH = _pick(os.path.join(ROOT, "config", "notify_token.txt"),
                   os.path.join(HERE, "notify_token.txt"))
LEGACY_COOKIE = _pick(os.path.join(ROOT, "config", "wb_session_cookie.txt"),
                      os.path.join(HERE, "wb_session_cookie.txt"))
LOG_PATH = os.path.join(ROOT, "logs", "balance_direct.log")


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line)


def _num(v):
    try:
        f = float(v)
        return ("%.2f" % f).rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(v)


def _mint_session_cookie():
    """申请 deviceCode 并换网站会话 cookie，返回 Cookie 头字符串。"""
    import rt_auth
    from curl_cffi import requests

    rt = rt_auth.read_rt()
    if not rt:
        raise RuntimeError("无长效 rt 令牌")
    at = (rt_auth.refresh_token(rt).get("data") or {}).get("accessToken") or ""
    if not at:
        raise RuntimeError("refresh_token 未返回 accessToken")

    r = requests.post(DEVICE_CODE_API, json={},
                      headers={"Authorization": "Bearer " + at,
                               "X-Refresh-Token": rt,
                               "User-Agent": CLIENT_UA,
                               "Content-Type": "application/json"},
                      impersonate="chrome", timeout=20)
    if r.status_code != 200:
        raise RuntimeError("device/auth/code HTTP %d: %s" % (r.status_code, r.text[:120]))
    dc = ((r.json() or {}).get("data") or {}).get("deviceCode")
    if not dc:
        raise RuntimeError("deviceCode 为空: " + r.text[:120])

    s = requests.Session(impersonate="chrome")
    r2 = s.get(CLIENT_LOGIN, params={"code": dc, "target": "/"},
               headers={"User-Agent": CLIENT_UA, "Accept": "*/*"}, timeout=20)
    if r2.status_code != 200:
        raise RuntimeError("client-login HTTP %d" % r2.status_code)
    ck = {c.name: c.value for c in s.cookies.jar}
    if not ck.get("session"):
        raise RuntimeError("client-login 未下发 session cookie")
    return "; ".join("%s=%s" % (k, v) for k, v in ck.items())


def fetch_balance():
    """取余额 data；优先现取新会话（自愈），失败时回退旧 cookie 文件。"""
    from curl_cffi import requests

    errors = []
    for attempt in ("mint", "legacy"):
        try:
            if attempt == "mint":
                cookie = _mint_session_cookie()
            else:
                if not os.path.isfile(LEGACY_COOKIE):
                    raise RuntimeError("无旧 cookie 文件")
                cookie = open(LEGACY_COOKIE, "r", encoding="utf-8").read().strip()
            r = requests.post(BALANCE_API, data="{}",
                              headers={"Content-Type": "application/json",
                                       "Cookie": cookie, "User-Agent": CLIENT_UA},
                              impersonate="chrome", timeout=20)
            if r.status_code != 200:
                raise RuntimeError("余额接口 HTTP %d" % r.status_code)
            body = r.json()
            if body.get("code") != 0:
                raise RuntimeError("业务错误 code=%s msg=%s"
                                   % (body.get("code"), body.get("msg")))
            if attempt == "mint":
                try:
                    with open(LEGACY_COOKIE, "w", encoding="utf-8") as f:
                        f.write(cookie)
                    os.chmod(LEGACY_COOKIE, 0o600)
                except OSError:
                    pass
            return body["data"]
        except Exception as exc:  # noqa: BLE001
            errors.append("%s: %s" % (attempt, str(exc)[:100]))
    raise RuntimeError("；".join(errors))


def build_report(data):
    return "积分余额：%s" % _num(data.get("TotalCredits"))


def push_notify(notify_url, title, content):
    with open(TOKEN_PATH, "r", encoding="utf-8") as f:
        token = f.read().strip()
    body = json.dumps({"token": token, "title": title, "content": content}).encode("utf-8")
    req = urllib.request.Request(notify_url, data=body,
                                 headers={"Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=25)
    return r.status, r.read().decode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notify-url", default="http://127.0.0.1/notify")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    try:
        data = fetch_balance()
    except ImportError:
        log("FAIL 缺少 curl_cffi")
        sys.exit(6)
    except Exception as exc:  # noqa: BLE001
        log("FAIL %s" % exc)
        if not args.test:
            try:
                push_notify(args.notify_url, "WorkBuddy 余额推送失败", str(exc)[:300])
            except Exception as exc2:  # noqa: BLE001
                log("失败通知推送也失败: %s" % exc2)
        sys.exit(4)

    report = build_report(data)
    log("HIT " + report)
    if args.test:
        return
    try:
        code, resp = push_notify(args.notify_url, "WorkBuddy 积分余额", report)
        log("推送完成 HTTP %d %s" % (code, resp[:160]))
    except Exception as exc:  # noqa: BLE001
        log("推送失败: %s" % exc)
        sys.exit(5)


if __name__ == "__main__":
    main()
