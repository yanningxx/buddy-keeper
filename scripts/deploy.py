#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deploy.py — 一键部署 BuddyKeeper 到服务器。

行为：
1. 按项目结构上传 src/ lib/ scripts/ config 模板到 /opt/buddy-keeper
2. 创建/修正运行时目录与权限（logs 属 ubuntu）
3. 远端语法编译校验 + 一次 --test 余额链路自检（不推送）
用法：
  python scripts/deploy.py                 # 完整部署
  python scripts/deploy.py --no-verify     # 跳过自检

凭据（**源码内不含任何默认凭据**，入公开仓库不会泄露）：
  1. 环境变量 BK_HOST / BK_USER / BK_PASS
  2. 本地文件 config/deploy.local.json（已在 .gitignore，不入库）：
     {"host": "...", "user": "...", "pass": "..."}
  两者都没有时脚本直接报错退出。
"""

import argparse
import json
import os
import sys

try:
    import paramiko
except ImportError:
    print("缺少 paramiko：pip install paramiko", file=sys.stderr)
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_local_cred():
    """读取本地未入库的凭据文件；不存在或损坏都返回空字典。"""
    p = os.path.join(ROOT, "config", "deploy.local.json")
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


_CRED = _load_local_cred()
HOST = os.environ.get("BK_HOST") or _CRED.get("host") or ""
USER = os.environ.get("BK_USER") or _CRED.get("user") or ""
PASS = os.environ.get("BK_PASS") or _CRED.get("pass") or ""
REMOTE = os.environ.get("BK_REMOTE", "/opt/buddy-keeper")
PY = "/usr/bin/python3"

# 本地相对路径 -> 远端相对路径
FILES = {
    "src/daily_runner.py": "src/daily_runner.py",
    "src/balance_direct.py": "src/balance_direct.py",
    "src/wecom_echo_server.py": "src/wecom_echo_server.py",
    "app/index.html": "app/index.html",
    "lib/buddy_station.py": "lib/buddy_station.py",
    "lib/push_notify.py": "lib/push_notify.py",
    "lib/rt_auth.py": "lib/rt_auth.py",
    "lib/web_auth.py": "lib/web_auth.py",
    "scripts/setup_cron.sh": "scripts/setup_cron.sh",
    "README.md": "README.md",
    "CHANGELOG.md": "CHANGELOG.md",
    "VERSION": "VERSION",
    "docs/ARCHITECTURE.md": "docs/ARCHITECTURE.md",
    "docs/OPERATIONS.md": "docs/OPERATIONS.md",
}


def run(ssh, cmd, timeout=180):
    _, out, err = ssh.exec_command(cmd, timeout=timeout)
    return (out.read().decode(errors="replace"),
            err.read().decode(errors="replace"))


def connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("[deploy] 连接 %s@%s" % (USER, HOST), flush=True)
    ssh.connect(HOST, username=USER, password=PASS, timeout=25,
                look_for_keys=False, allow_agent=False)
    return ssh


def ensure_dirs(ssh):
    """建目录。首次部署 /opt/<name> 需要 root，普通用户写不了 /opt。"""
    dirs = ["", "src", "lib", "config", "scripts", "docs", "logs"]
    inner = " && ".join(
        ("mkdir -p %s/%s" % (REMOTE, d)) if d else ("mkdir -p " + REMOTE)
        for d in dirs
    )
    inner += " && chown -R %s:%s %s" % (USER, USER, REMOTE)
    # 用 sudo 执行（/opt 一般仅 root 可写）
    out, err = run(ssh, "echo %s | sudo -S bash -c %s"
                   % ("'" + PASS + "'", "'" + inner + "'"))
    if err.strip() and "password for" not in err:
        print("[deploy][warn] " + err.strip()[:200], flush=True)
    print("[deploy] 目录就绪（%s）" % REMOTE, flush=True)


def upload(ssh):
    sftp = ssh.open_sftp()
    for local_rel, remote_rel in FILES.items():
        local = os.path.join(ROOT, local_rel)
        if not os.path.isfile(local):
            print("  ! 跳过（本地缺失）: " + local_rel, flush=True)
            continue
        remote = REMOTE + "/" + remote_rel
        sftp.put(local, remote)
        print("  upload %s" % remote_rel, flush=True)
    example = os.path.join(ROOT, "config", "config.json.example")
    if os.path.isfile(example):
        sftp.put(example, REMOTE + "/config/config.json.example")
    sftp.close()


def link_legacy(ssh):
    """旧扁平结构 /opt/workbuddy-automation 已于 2026-10-28 移除，此函数保留为空操作。

    保留函数名以兼容外部调用；不再创建任何旧路径软链。
    """
    print("[deploy] 跳过兼容层：/opt/workbuddy-automation 已废弃", flush=True)


def fix_perms(ssh):
    run(ssh, "chmod -R u+rwX %s && chown -R %s:%s %s"
        % (REMOTE, USER, USER, REMOTE))
    # 密钥文件保持 600
    run(ssh, "chmod 600 %s/config/*.json %s/config/*.txt 2>/dev/null; true" % (REMOTE, REMOTE))
    print("[deploy] 权限已修正", flush=True)


def verify(ssh):
    print("[deploy] 语法校验", flush=True)
    out, err = run(ssh, "%s -m py_compile %s/src/daily_runner.py %s/src/balance_direct.py "
                        "%s/src/wecom_echo_server.py %s/lib/buddy_station.py "
                        "%s/lib/push_notify.py && echo COMPILE_OK"
                   % (PY, REMOTE, REMOTE, REMOTE, REMOTE, REMOTE))
    print((out + err).strip(), flush=True)

    print("[deploy] 余额链路自检（不推送）", flush=True)
    out, err = run(ssh, "cd %s && %s src/balance_direct.py --test 2>&1" % (REMOTE, PY))
    print((out + err).strip(), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    missing = [n for n, v in (("BK_HOST", HOST), ("BK_USER", USER), ("BK_PASS", PASS)) if not v]
    if missing:
        print("[deploy] 缺少部署凭据：%s 未设置。\n"
              "  方式一：设置环境变量 %s\n"
              "  方式二：创建 config/deploy.local.json：\n"
              '    {"host": "<IP>", "user": "<用户>", "pass": "<密码>"}\n'
              "（源码内不保存任何凭据，避免公开仓库泄露）"
              % ("/".join(missing), "/".join(missing)), file=sys.stderr)
        return 1

    ssh = connect()
    try:
        ensure_dirs(ssh)
        upload(ssh)
        link_legacy(ssh)
        fix_perms(ssh)
        if not args.no_verify:
            verify(ssh)
    finally:
        ssh.close()
    print("[deploy] 完成。检查定时任务：sudo cat /etc/cron.d/buddy-keeper", flush=True)


if __name__ == "__main__":
    main()
