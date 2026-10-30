# -*- coding: utf-8 -*-
"""只读体检：看板 / 卡片数量、owner 归属、孤儿卡片、演示看板是否被误改。"""
import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = open(os.path.join(ROOT, ".key.txt")).read().strip()
REST = "https://xuyanning-d2g5ejg513e3c8e1d.api.tcloudbasegateway.com/v1/rdb/rest"
AUTH = "https://xuyanning-d2g5ejg513e3c8e1d.api.tcloudbasegateway.com/auth/v1"
DEMO = "4ZX99GZL"


def get(path, tok=None):
    h = {"apikey": KEY, "Content-Type": "application/json",
         "Authorization": "Bearer " + (tok or KEY)}
    r = urllib.request.Request(REST + path, headers=h, method="GET")
    with urllib.request.urlopen(r, timeout=30) as resp:
        return resp.status, json.loads(resp.read() or b"null")


def signin():
    body = json.dumps({}).encode()
    h = {"apikey": KEY, "Content-Type": "application/json",
         "x-device-id": "healthcheck-%d" % os.getpid()}
    r = urllib.request.Request(AUTH + "/signin/anonymously", data=body, headers=h, method="POST")
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read())["access_token"]


tok = signin()
s, boards = get("/bk_boards?select=id,title,share_code,owner_uid,updated_at&order=updated_at", tok)
print("看板 %d 块" % len(boards))
for b in boards:
    owner = b.get("owner_uid")
    tag = "演示(无 owner)" if not owner else owner[:12] + "…"
    print("  %-9s %-28s %s  upd=%s" % (b["share_code"], b["title"][:26], tag, b["updated_at"]))

s, cards = get("/bk_cards?select=id,board_id,title", tok)
print("卡片 %d 张" % len(cards))
ids = {b["id"] for b in boards}
orph = [c for c in cards if c["board_id"] not in ids]
print("孤儿卡片 %d 张" % len(orph))

demo = [b for b in boards if b["share_code"] == DEMO]
print("演示看板存在: %s" % ("是" if demo else "否"))
if demo:
    print("演示看板 owner 为空: %s" % (demo[0].get("owner_uid") is None))
