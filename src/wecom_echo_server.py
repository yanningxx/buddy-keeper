#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""企业微信「接收消息服务器URL」验证应答器 + 通用通知转发端点。

部署于服务器 80 端口：
- GET /wecom_callback  应答 echostr 验证（SHA1 签名 + AES 解密），验证通过后企业微信才允许配置可信IP。
- POST /notify         通用通知入口：{"token": ..., "title": ..., "content": ...}，
  token 鉴权后经 push_notify.push_send 推送 wecom_app（个人微信自建应用全文）。
服务常驻无害。
"""
import base64
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# /notify 依赖服务器上的 push_notify（wecom_app 渠道实现）
HERE = os.path.dirname(os.path.abspath(__file__))          # .../src
ROOT = os.path.dirname(HERE)                                # 项目根


def _pick(*cands):
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]


# 依赖模块查找：仅用项目内 lib/（旧扁平结构 /opt/workbuddy-automation 已于 2026-10-28 移除）
_LIB = os.path.join(ROOT, "lib")
if os.path.isdir(_LIB):
    sys.path.insert(0, _LIB)

MAIN_CONFIG = _pick(os.path.join(ROOT, "config", "config.json"),
                    os.path.join(HERE, "config.json"))

# 看板 HTML（由本服务同源托管，避免跨域/混合内容拦截）
APP_HTML = _pick(os.path.join(ROOT, "app", "index.html"),
                 os.path.join(HERE, "..", "app", "index.html"),
                 "/opt/buddy-keeper/app/index.html")

try:
    from Crypto.Cipher import AES  # pycryptodome (pip)
except ImportError:  # Ubuntu 24.04 的 apt 包导入名为 Cryptodome
    from Cryptodome.Cipher import AES

CONF_PATH = _pick(os.path.join(ROOT, "config", "wecom_echo_conf.json"),
                 os.path.join(HERE, "wecom_echo_conf.json"))
with open(CONF_PATH, "r", encoding="utf-8") as fh:
    _conf = json.load(fh)
TOKEN = _conf["token"]
AESKEY = base64.b64decode(_conf["encoding_aes_key"] + "=")
NOTIFY_TOKEN = _conf.get("notify_token", "")


def verify_sig(timestamp, nonce, encrypt):
    items = sorted([TOKEN, timestamp, nonce, encrypt])
    return hashlib.sha1("".join(items).encode("utf-8")).hexdigest()


def decrypt_echo(encrypt_b64):
    cipher = AES.new(AESKEY, AES.MODE_CBC, AESKEY[:16])
    plain = cipher.decrypt(base64.b64decode(encrypt_b64))
    pad = plain[-1]
    plain = plain[:-pad]
    msg_len = int.from_bytes(plain[16:20], "big")
    return plain[20:20 + msg_len].decode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/status":
            self._handle_status(u)
            return
        if u.path in ("/", "/app", "/app/", "/index.html"):
            self._handle_dashboard()
            return
        if u.path != "/wecom_callback":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        q = parse_qs(u.query)
        try:
            msg_sign = q["msg_signature"][0]
            ts = q.get("timestamp", [""])[0]
            nonce = q["nonce"][0]
            echo = q["echostr"][0]
            if verify_sig(ts, nonce, echo) != msg_sign:
                self.send_response(403)
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(decrypt_echo(echo).encode("utf-8"))
        except Exception:  # noqa: BLE001
            self.send_response(400)
            self.end_headers()

    def _handle_run(self):
        """POST /run 触发一次完整流程（异步，立即返回；看板免令牌访问）。"""
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            data = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except Exception:  # noqa: BLE001
            self._reply(400, '{"ok":false,"detail":"bad json"}', cors=True)
            return
        runner = os.path.join(ROOT, "src", "daily_runner.py")
        if not os.path.isfile(runner):
            self._reply(500, '{"ok":false,"detail":"runner missing"}', cors=True)
            return
        # 单飞锁（建议性检查）：若已有实例在跑，合并本次触发并返回友好提示，
        # 避免无谓派生进程；真正的排他保证仍由 daily_runner 内部的锁负责。
        _lock_path = os.path.join(ROOT, "logs", "run.lock")
        _busy = False
        _lfd = None
        try:
            _lfd = os.open(_lock_path, os.O_RDWR | os.O_CREAT, 0o666)
            try:
                os.chmod(_lock_path, 0o666)
            except OSError:
                pass
            fcntl.flock(_lfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(_lfd, fcntl.LOCK_UN)  # 当前无运行实例，释放交给子进程持有
        except OSError:
            _busy = True
        finally:
            if _lfd is not None:
                os.close(_lfd)
        if _busy:
            self._reply(200,
                        '{"ok":true,"detail":"已有运行在进行中，本次触发已合并（单飞锁）"}',
                        cors=True)
            return
        try:
            env = dict(os.environ)
            env["WB_MAX_RETRIES"] = "0"
            env["HOME"] = "/home/ubuntu"   # 保证子进程按部署用户解析凭据路径
            _cron_log = os.path.join(ROOT, "logs", "cron.log")
            try:
                os.chmod(_cron_log, 0o666)  # 保底：确保 ubuntu 的 cron 也能写该文件
            except OSError:
                pass
            with open(_cron_log, "a", encoding="utf-8") as logf:
                subprocess.Popen([sys.executable, runner], cwd=ROOT, env=env,
                                 stdout=logf, stderr=subprocess.STDOUT,
                                 start_new_session=True)
            self._reply(200, '{"ok":true,"detail":"已触发，约 10 秒后可刷新查看"}', cors=True)
        except Exception as exc:  # noqa: BLE001
            self._reply(500, json.dumps({"ok": False, "detail": str(exc)[:200]},
                                        ensure_ascii=False), cors=True)

    def _send_notify(self, body):
        """POST /notify：token 鉴权 -> push_send(wecom_app)。"""
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:  # noqa: BLE001
            self._reply(400, '{"ok":false,"detail":"bad json"}')
            return
        if not NOTIFY_TOKEN or data.get("token") != NOTIFY_TOKEN:
            self._reply(403, '{"ok":false,"detail":"bad token"}')
            return
        title = str(data.get("title") or "WorkBuddy 通知")[:64]
        content = str(data.get("content") or "")[:8000]
        if not content.strip():
            self._reply(400, '{"ok":false,"detail":"empty content"}')
            return
        try:
            import push_notify  # noqa: PLC0415
            cfg = push_notify.load_push_config(MAIN_CONFIG)
            results = push_notify.push_send(title, content, content_type="txt",
                                            channels=["wecom_app"], config=cfg)
            ok = any(r.get("status") == "ok" for r in results)
            detail = "; ".join("%s:%s" % (r.get("channel"), r.get("detail", "")) for r in results)
            self._reply(200 if ok else 502,
                        json.dumps({"ok": ok, "detail": detail}, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            self._reply(500, json.dumps({"ok": False, "detail": str(exc)[:200]},
                                        ensure_ascii=False))

    def _reply(self, code, text, cors=False):
        raw = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _handle_dashboard(self):
        """GET / 或 /app：同源托管看板 HTML。"""
        try:
            with open(APP_HTML, "r", encoding="utf-8") as fh:
                html = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html.encode("utf-8"))))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            self.send_response(500)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(("dashboard missing: %s" % exc).encode("utf-8"))

    def do_OPTIONS(self):
        self._reply(204, "")

    def _handle_status(self, u):
        """GET /status 返回最近一次运行状态（看板免令牌访问）。"""
        state_path = os.path.join(ROOT, "logs", "last_run_state.json")
        log_path = _pick(os.path.join(ROOT, "logs", "run.log"),
                        os.path.join(ROOT, "logs", "cron.log"))
        payload = {"ok": True, "state": None, "log_tail": []}
        try:
            if os.path.isfile(state_path):
                with open(state_path, "r", encoding="utf-8") as fh:
                    payload["state"] = json.load(fh)
            if os.path.isfile(log_path):
                with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
                    payload["log_tail"] = fh.read().splitlines()[-40:]
        except Exception as exc:  # noqa: BLE001
            payload["ok"] = False
            payload["detail"] = str(exc)[:200]
        self._reply(200, json.dumps(payload, ensure_ascii=False), cors=True)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/run":
            self._handle_run()
            return
        if path != "/notify":
            self._reply(404, '{"ok":false,"detail":"not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length <= 0 or length > 65536:
            self._reply(400, '{"ok":false,"detail":"bad length"}')
            return
        self._send_notify(self.rfile.read(length))

    def log_message(self, *args):  # 静默访问日志
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 80), Handler).serve_forever()
