# -*- coding: utf-8 -*-
"""创建一块带真实内容的演示看板，返回分享码。"""
import json, urllib.request, urllib.error, random, string, sys
import os
ROOT = os.path.dirname(os.path.abspath(__file__))
KEYP = os.path.join(ROOT, '..', '.key.txt')
HTMLP = os.path.join(ROOT, '..', 'index.html')

KEY = open(KEYP).read().strip()
REST = 'https://xuyanning-d2g5ejg513e3c8e1d.api.tcloudbasegateway.com/v1/rdb/rest'

def api(m, p, body=None, prefer=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    r = urllib.request.Request(REST + p, data=data, method=m)
    r.add_header('Authorization', 'Bearer ' + KEY)
    r.add_header('Content-Type', 'application/json')
    if prefer: r.add_header('Prefer', prefer)
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:400]

def uid(n):
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))

P = ['#2f6feb', '#0f9d58', '#c77700', '#d13438', '#7c3aed', '#0891b2']

# 复用已有演示板
code = None
s, b = api('GET', '/bk_boards?select=id,share_code,title&order=created_at.asc')
for row in (json.loads(b) if s == 200 else []):
    if row['title'] == 'WorkBuddy 值守看板（演示）':
        code = row['share_code']; BID = row['id']
        break

if not code:
    BID = uid(12); code = uid(8).upper()
    board = {
        'id': BID, 'title': 'WorkBuddy 值守看板（演示）', 'share_code': code,
        'column_defs': [{'id': 'todo', 'title': '待办'},
                        {'id': 'doing', 'title': '进行中'},
                        {'id': 'done', 'title': '已完成'},
                        {'id': 'blocked', 'title': '被阻塞'}],
        'members': [{'id': 'm1', 'name': '徐', 'color': P[0]},
                    {'id': 'm2', 'name': 'Codex', 'color': P[1]},
                    {'id': 'm3', 'name': 'QA', 'color': P[4]}],
        'tags': [{'id': 't1', 'name': '值守', 'color': P[0]},
                 {'id': 't2', 'name': '缺陷', 'color': P[3]},
                 {'id': 't3', 'name': '文档', 'color': P[2]},
                 {'id': 't4', 'name': '发布', 'color': P[1]}],
    }
    print('建板 ->', api('POST', '/bk_boards', board, 'return=minimal'))

    cards = [
        ('todo', '给 /run 接口加令牌校验', '现在任何能访问到端口的人都能触发值守，需要 header token。', ['t2'], ['m1'], '2026-11-05', 0),
        ('todo', '把播报原文接进飞书', '值守跑完自动推一条卡片消息。', ['t1'], ['m2'], '2026-11-08', 1),
        ('todo', '补一份判据对照表', '旧判据 vs 新判据，逐条列反例。', ['t3'], ['m3'], None, 2),
        ('doing', '看板拖拽跨列落库', 'position 批量 PATCH，20 秒轮询跳过自身写入。', ['t1', 't2'], ['m1', 'm2'], '2026-11-02', 0),
        ('doing', '静态托管上线', '已上传到 tcloudbaseapp.com/board/。', ['t4'], ['m1'], None, 1),
        ('done', '修掉「有积分可领」误报', '判据从按钮文案改为 today_checked_in。', ['t2'], ['m1'], None, 0),
        ('done', 'CloudBase 建表 + RLS', 'bk_boards / bk_cards 两张表，anon 可读写。', ['t4'], ['m2'], None, 1),
        ('blocked', '匿名登录策略依赖平台', 'anonymous 开关由平台侧控制，页面无法自助修复。', ['t2'], ['m1'], '2026-10-30', 0),
    ]
    payload = [{'id': uid(12), 'board_id': BID, 'column_id': c, 'title': t, 'description': d,
                'tag_ids': tg, 'member_ids': m, 'due_date': due, 'position': float(pos)}
               for c, t, d, tg, m, due, pos in cards]
    print('灌卡片 ->', api('POST', '/bk_cards', payload, 'return=minimal'))

print(code)
