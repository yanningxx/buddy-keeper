"""给 BuddyKeeper 绑定自定义域名并启用 HTTPS（一次性原子操作）。

背景（2026-10-28 实测的服务器现状）：
  - Ubuntu 24.04.4 LTS
  - 未安装 nginx、未安装 certbot
  - 80 端口由 systemd 服务 wecom-echo.service 的 python3 进程直接占用
    （/opt/buddy-keeper/src/wecom_echo_server.py，Unit 的 User=root）

因此绑定域名不是「装个 Nginx」那么简单：必须先把 wecom-echo 从 80 挪到
127.0.0.1:8080，Nginx 才能接管 80/443。这个切换必须一次性做完，中途失败
会导致看板完全不可访问，所以脚本内置回滚。

为什么端口用环境变量而不是改源码：deploy.py 每次部署都会重新上传
src/wecom_echo_server.py，直接改服务器上的文件会在下次部署时被覆盖回 80。
所以源码改成读 BK_ECHO_HOST / BK_ECHO_PORT（默认 0.0.0.0:80，行为不变），
再由 systemd unit 注入这两个变量。

用法：
    python scripts/bind_domain.py --check     # 只校验 DNS 与连通性，不改任何东西
    python scripts/bind_domain.py             # 完整执行（需要域名已备案、DNS 已生效）
"""
import base64
import json
import os
import re
import socket
import sys

import paramiko

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRED = os.path.join(ROOT, "config", "deploy.local.json")
SITE_INDEX = os.path.join(ROOT, "site", "index.html")
SRC_SERVER = os.path.join(ROOT, "src", "wecom_echo_server.py")

REMOTE_ROOT = "/opt/buddy-keeper"
WEB_ROOT = "/var/www/buddy-keeper"
UNIT_PATH = "/etc/systemd/system/wecom-echo.service"
SERVICE = "wecom-echo"
ECHO_PORT = 8080

NGINX_SITE = """server {{
    listen 80;
    listen [::]:80;
    server_name {domain};

    root {web_root};
    index index.html;

    location / {{
        try_files $uri $uri/ /index.html;
    }}

    # 看板后端：/status 与 /run 反代到本机 8080（wecom-echo 的原路径不变）
    location = /status {{
        proxy_pass http://127.0.0.1:{echo_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location = /run {{
        proxy_pass http://127.0.0.1:{echo_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""


class Step:
    """记录已完成的步骤，失败时按逆序回滚。"""

    def __init__(self, ssh, password, user):
        self.ssh = ssh
        self.password = password
        self.user = user
        self.done = []

    def sudo(self, cmd, timeout=600):
        b64 = base64.b64encode(cmd.encode("utf-8")).decode("ascii")
        full = ("echo '%s' | sudo -S bash -c \"echo %s | base64 -d | bash\""
                % (self.password, b64))
        _, out, err = self.ssh.exec_command(full, timeout=timeout)
        o = out.read().decode("utf-8", "replace")
        e = err.read().decode("utf-8", "replace")
        # sudo 的密码提示走 stderr，不算错误
        e = "\n".join(x for x in e.splitlines() if "password for" not in x)
        return o, e

    def user(self, cmd, timeout=120):
        _, out, err = self.ssh.exec_command(cmd, timeout=timeout)
        return (out.read().decode("utf-8", "replace"),
                err.read().decode("utf-8", "replace"))


def load_cred():
    if not os.path.isfile(CRED):
        print("[错误] 缺少 %s，无法连接服务器。" % CRED)
        sys.exit(1)
    with open(CRED, "r", encoding="utf-8") as f:
        return json.load(f)


def connect(cred):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("[连接] %s@%s" % (cred["user"], cred["host"]), flush=True)
    ssh.connect(cred["host"], username=cred["user"], password=cred["pass"],
                timeout=25, look_for_keys=False, allow_agent=False)
    return ssh


def check_dns(domain, expect_ip):
    """域名 A 记录必须指向这台服务器的公网 IP，否则签证书必然失败。"""
    try:
        got = socket.gethostbyname(domain)
    except OSError as exc:
        print("[DNS] %s 解析失败：%s" % (domain, exc))
        return False
    print("[DNS] %s -> %s（期望 %s）" % (domain, got, expect_ip))
    return got == expect_ip


def install_packages(st, log):
    print("[1/9] 安装 nginx / certbot ...", flush=True)
    o, e = st.sudo(
        "export DEBIAN_FRONTEND=noninteractive && "
        "apt-get update -qq && "
        "apt-get install -y -qq nginx certbot python3-certbot-nginx", timeout=900)
    log.append(("install", o[-800:], e[-800:]))
    # 装完 nginx 会自动尝试启动，但 80 此时仍被 wecom-echo 占着，启动会失败；
    # 这里先停掉，等端口腾出来再由我们统一启动。
    st.sudo("systemctl stop nginx || true")
    o2, _ = st.sudo("nginx -v 2>&1; certbot --version 2>&1")
    print("     " + o2.strip().replace("\n", " | "), flush=True)
    st.done.append("install")
    return "nginx" in o2 and "certbot" in o2


def upload_backend(st, ssh, log):
    """上传支持 BK_ECHO_HOST/BK_ECHO_PORT 的新版后端。

    这一步不可省：服务器上现存的是硬编码 `HTTPServer(("0.0.0.0", 80))` 的旧代码，
    只在 systemd unit 里加环境变量它根本不会读，切换端口必然失败。
    """
    print("[2/9] 上传支持环境变量端口的新版后端 ...", flush=True)
    tmp = "/tmp/bk_echo_server_new.py"
    sftp = ssh.open_sftp()
    sftp.put(SRC_SERVER, tmp)
    sftp.close()
    o, e = st.sudo(
        "cp %s %s/src/wecom_echo_server.py && "
        "chown %s:%s %s/src/wecom_echo_server.py && "
        "grep -c 'BK_ECHO_PORT' %s/src/wecom_echo_server.py"
        % (tmp, REMOTE_ROOT, st.user, st.user, REMOTE_ROOT, REMOTE_ROOT))
    st.sudo("rm -f " + tmp)
    log.append(("upload_backend", o, e))
    hits = o.strip().splitlines()[-1] if o.strip() else "0"
    ok = hits.isdigit() and int(hits) >= 1
    print("     文件内 BK_ECHO_PORT 引用数：%s" % hits, flush=True)
    if ok:
        st.done.append("upload_backend")
    return ok


def deploy_static(st, ssh, log):
    print("[3/9] 生成站点目录 /var/www/buddy-keeper ...", flush=True)
    st.sudo("mkdir -p %s && chown -R www-data:www-data %s" % (WEB_ROOT, WEB_ROOT))
    tmp = "/tmp/bk_index_upload.html"
    sftp = ssh.open_sftp()
    sftp.put(SITE_INDEX, tmp)
    sftp.close()
    o, e = st.sudo("cp %s %s/index.html && chown www-data:www-data %s/index.html && "
                   "ls -l %s" % (tmp, WEB_ROOT, WEB_ROOT, WEB_ROOT))
    st.sudo("rm -f " + tmp)
    log.append(("static", o, e))
    st.done.append("static")
    return "index.html" in o


def write_nginx_site(st, domain, log):
    print("[4/9] 写入 Nginx 站点配置 ...", flush=True)
    conf = NGINX_SITE.format(domain=domain, web_root=WEB_ROOT, echo_port=ECHO_PORT)
    tmp = "/tmp/bk_nginx_site.conf"
    b64 = base64.b64encode(conf.encode("utf-8")).decode("ascii")
    st.sudo("echo %s | base64 -d > %s" % (b64, tmp))
    o, e = st.sudo(
        "rm -f /etc/nginx/sites-enabled/default && "
        "mv %s /etc/nginx/sites-available/buddy-keeper && "
        "ln -sfn /etc/nginx/sites-available/buddy-keeper /etc/nginx/sites-enabled/buddy-keeper"
        % tmp)
    log.append(("nginx_conf", o, e))
    st.done.append("nginx_conf")
    return True


def repoint_service(st, log):
    """把 wecom-echo 从 0.0.0.0:80 改到 127.0.0.1:8080（用 unit 环境变量，不改源码）。"""
    print("[5/9] 将 wecom-echo 端口改为 127.0.0.1:%d ..." % ECHO_PORT, flush=True)
    st.sudo("cp %s %s.bak-before-domain" % (UNIT_PATH, UNIT_PATH))
    o, _ = st.sudo("cat " + UNIT_PATH)
    unit = o
    if "BK_ECHO_PORT" not in unit:
        unit = unit.replace(
            "[Service]\n",
            "[Service]\nEnvironment=BK_ECHO_HOST=127.0.0.1\n"
            "Environment=BK_ECHO_PORT=%d\n" % ECHO_PORT)
    b64 = base64.b64encode(unit.encode("utf-8")).decode("ascii")
    st.sudo("echo %s | base64 -d > %s" % (b64, UNIT_PATH))
    st.done.append("unit")
    o2, e2 = st.sudo(
        "systemctl daemon-reload; systemctl restart %s; sleep 3; "
        "echo ACT=$(systemctl is-active %s); "
        "echo P8080=$(ss -lnt | grep -c ':8080' || true); "
        "echo P80=$(ss -lnt | grep -c ':80 ' || true)"
        % (SERVICE, SERVICE))
    log.append(("restart_echo", o2, e2))
    m = dict(re.findall(r"(ACT|P8080|P80)=(\S+)", o2))
    active = m.get("ACT") == "active"
    has_8080 = (m.get("P8080") or "0").isdigit() and int(m.get("P8080") or 0) >= 1
    print("     service=%s  8080监听=%s  80占用残留=%s"
          % (m.get("ACT"), has_8080, m.get("P80")), flush=True)
    return active and has_8080


def start_nginx(st, log):
    print("[6/9] 启动 Nginx ...", flush=True)
    o, e = st.sudo("nginx -t")
    log.append(("nginx_test", o, e))
    if "syntax is ok" not in (o + e).lower() and "test is successful" not in (o + e).lower():
        print("     nginx -t 失败：\n" + (o + e)[:600], flush=True)
        return False
    o2, e2 = st.sudo("systemctl enable nginx >/dev/null 2>&1; systemctl start nginx; "
                     "sleep 2; systemctl is-active nginx")
    log.append(("nginx_start", o2, e2))
    ok = "active" in o2
    print("     nginx: %s" % ("active" if ok else o2.strip()[:120]), flush=True)
    if ok:
        st.done.append("nginx_start")
    return ok


def verify_http(st, domain):
    print("[7/9] 验证 HTTP 与后端反代 ...", flush=True)
    o, _ = st.sudo(
        "curl -s -o /dev/null -w '%%{http_code}' -H 'Host: %s' http://127.0.0.1/ ; echo; "
        "curl -s -o /dev/null -w '%%{http_code}' -H 'Host: %s' 'http://127.0.0.1/status?token=x' ; echo"
        % (domain, domain))
    codes = [x.strip() for x in o.splitlines() if x.strip()]
    print("     首页=%s  /status=%s" % (codes[0] if codes else "?", codes[1] if len(codes) > 1 else "?"), flush=True)
    return bool(codes) and codes[0] == "200"


def run_certbot(st, domain, email, log):
    print("[8/9] 申请 Let's Encrypt 证书（会自动改写 Nginx 配置加 443）...", flush=True)
    o, e = st.sudo(
        "certbot --nginx -d %s --non-interactive --agree-tos -m %s --redirect "
        "--keep-until-expiring" % (domain, email), timeout=600)
    log.append(("certbot", o[-1500:], e[-1500:]))
    ok = any(k in o for k in ("Congratulations", "Successfully received certificate",
                              "not yet due for renewal", "already"))
    print("     certbot: %s" % ("OK" if ok else "FAILED"), flush=True)
    if not ok:
        print((o + e)[-800:], flush=True)
    return ok


def verify_https(st, domain):
    print("[9/9] 验证 HTTPS ...", flush=True)
    o, _ = st.sudo(
        "curl -s -o /dev/null -w '%%{http_code}' --resolve %s:443:127.0.0.1 https://%s/ ; echo; "
        "certbot certificates 2>/dev/null | grep -E 'Certificate Name|Expiry' | head -4"
        % (domain, domain), timeout=120)
    print("     " + o.strip().replace("\n", " | "), flush=True)
    return "200" in o.split("\n")[0]


def rollback(st, log):
    print("\n[回滚] 正在恢复到切换前的状态 ...", flush=True)
    st.sudo("systemctl stop nginx || true; systemctl disable nginx >/dev/null 2>&1 || true")
    st.sudo("if [ -f %s.bak-before-domain ]; then cp %s.bak-before-domain %s; fi"
            % (UNIT_PATH, UNIT_PATH, UNIT_PATH))
    st.sudo("systemctl daemon-reload && systemctl restart %s" % SERVICE)
    o, _ = st.sudo("sleep 2; systemctl is-active %s; curl -s -o /dev/null -w '%%{http_code}' http://127.0.0.1/status?token=x"
                   % SERVICE)
    print("[回滚] " + o.strip().replace("\n", " | "), flush=True)
    print("[回滚] 服务已退回监听 80 端口，看板应可正常访问。", flush=True)


def main():
    check_only = "--check" in sys.argv

    domain = ""
    for i, a in enumerate(sys.argv):
        if a == "--domain" and i + 1 < len(sys.argv):
            domain = sys.argv[i + 1]
    if not domain:
        domain = input("请输入已备案的域名（例如 buddy.example.com）：").strip()
    if not domain or "." not in domain:
        print("[错误] 域名格式不对。")
        return 1

    cred = load_cred()
    expect_ip = cred["host"]

    print("\n=== 前置检查 ===")
    if not check_dns(domain, expect_ip):
        print("\n[中止] DNS 尚未指向本服务器。等解析生效后再执行；未生效就签证书必然失败。")
        print("       如果你还没做解析，先去 DNS 服务商加一条 A 记录：%s -> %s" % (domain, expect_ip))
        return 2
    if not os.path.isfile(SITE_INDEX):
        print("[错误] 缺少 %s" % SITE_INDEX)
        return 1

    email = ""
    for i, a in enumerate(sys.argv):
        if a == "--email" and i + 1 < len(sys.argv):
            email = sys.argv[i + 1]
    if not check_only and not email:
        email = input("请输入证书到期通知邮箱：").strip()
        if "@" not in email:
            print("[错误] 邮箱格式不对。")
            return 1

    if check_only:
        print("\n[检查通过] DNS 已指向 %s，可以执行正式绑定了。" % expect_ip)
        return 0

    ssh = connect(cred)
    st = Step(ssh, cred["pass"], cred["user"])
    log = []
    try:
        if not install_packages(st, log):
            raise RuntimeError("nginx/certbot 安装失败")
        if not upload_backend(st, ssh, log):
            raise RuntimeError("后端源码上传失败（新版未落盘，端口切换不会生效）")
        if not deploy_static(st, ssh, log):
            raise RuntimeError("静态文件部署失败")
        write_nginx_site(st, domain, log)
        if not repoint_service(st, log):
            raise RuntimeError("wecom-echo 改端口后未能启动")
        if not start_nginx(st, log):
            raise RuntimeError("Nginx 启动失败")
        if not verify_http(st, domain):
            raise RuntimeError("HTTP 访问异常")
        if not run_certbot(st, domain, email, log):
            raise RuntimeError("证书申请失败（常见原因：备案未通过、80 端口被防火墙拦截、域名解析未生效）")
        verify_https(st, domain)
        print("\n=== 完成 ===")
        print("站点地址： https://%s/" % domain)
        print("看板后端： https://%s/status?token=...  （已反代到 127.0.0.1:%d）" % (domain, ECHO_PORT))
    except Exception as exc:  # noqa: BLE001
        print("\n[失败] %s" % exc)
        for name, o, e in log[-3:]:
            tail = (o + e).strip()[-500:]
            if tail:
                print("  --- %s ---\n%s" % (name, tail))
        rollback(st, log)
        ssh.close()
        return 1

    ssh.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
