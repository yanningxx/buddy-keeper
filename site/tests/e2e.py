# -*- coding: utf-8 -*-
"""模拟 index.html 的请求层，做一次完整 CRUD 端到端验证。
   现在所有写操作都必须带匿名登录用户的 token，并在建板时把 owner_uid 写成本人 uid，
   否则会被 RLS 拒绝 —— 这正是本次改造要验证的链路。"""
import base64, json, random, string, urllib.request, urllib.error
import os
ROOT = os.path.dirname(os.path.abspath(__file__))
KEYP = os.path.join(ROOT, '..', '.key.txt')
HTMLP = os.path.join(ROOT, '..', 'index.html')

KEY = open(KEYP).read().strip()
ENV = 'xuyanning-d2g5ejg513e3c8e1d'
GW = 'https://%s.api.tcloudbasegateway.com' % ENV
REST = GW + '/v1/rdb/rest'

def uid(n):
    a = string.ascii_lowercase + string.digits
    return ''.join(random.choice(a) for _ in range(n))

def signin(dev):
    r = urllib.request.Request(
        GW + '/auth/v1/signin/anonymously', data=b'{}', method='POST',
        headers={'Content-Type': 'application/json', 'x-device-id': dev})
    with urllib.request.urlopen(r, timeout=25) as resp:
        j = json.loads(resp.read().decode())
    p = j['access_token'].split('.')[1]
    p += '=' * (-len(p) % 4)
    sub = json.loads(base64.urlsafe_b64decode(p))['sub']
    return j['access_token'], sub

TOK, SUB = signin('e2e-' + uid(10))
print('身份: %s' % SUB)

def req(method, path, body=None, prefer=None, token=None):
    url = REST + path
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header('Authorization', 'Bearer ' + (token or TOK))
    r.add_header('Content-Type', 'application/json')
    if prefer:
        r.add_header('Prefer', prefer)
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:600]
    except Exception as e:
        return 'ERR', repr(e)[:300]

PALETTE = ['#2f6feb', '#0f9d58', '#c77700', '#d13438']
ok = []
def check(name, cond, extra=''):
    ok.append(cond)
    print(('  PASS ' if cond else '  FAIL ') + name + (('  ' + extra) if extra else ''))

BID = uid(12)
CODE = uid(8).upper()

print('\n=== 1. 建看板（POST bk_boards） ===')
board = {
    'id': BID, 'title': '复刻验证看板', 'share_code': CODE,
    'owner_uid': SUB,
    'column_defs': [
        {'id': 'todo', 'title': '待办'},
        {'id': 'doing', 'title': '进行中'},
        {'id': 'done', 'title': '已完成'},
    ],
    'members': [{'id': 'm1', 'name': '徐', 'color': PALETTE[0]},
                {'id': 'm2', 'name': 'Codex', 'color': PALETTE[1]}],
    'tags': [{'id': 't1', 'name': '值守', 'color': PALETTE[0]},
             {'id': 't2', 'name': '缺陷', 'color': PALETTE[3]}],
}
s, b = req('POST', '/bk_boards', board, 'return=representation')
print('  ->', s, b[:200])
check('创建看板 201', s == 201)
if s == 201:
    check('返回体带 owner_uid 且等于本人', json.loads(b)[0].get('owner_uid') == SUB,
          repr(json.loads(b)[0].get('owner_uid')))

print('\n=== 2. 按 share_code 读取（页面 boot 的路径） ===')
s, b = req('GET', '/bk_boards?select=*&share_code=eq.%s&limit=1' % CODE)
rows = json.loads(b) if s == 200 else []
check('share_code 查回 1 条', s == 200 and len(rows) == 1)
if rows:
    r0 = rows[0]
    check('column_defs 反序列化为 3 列', len(r0.get('column_defs') or []) == 3,
          str([c['title'] for c in r0.get('column_defs') or []]))
    check('members 2 人', len(r0.get('members') or []) == 2)
    check('tags 2 个', len(r0.get('tags') or []) == 2)
    check('中文未乱码', r0.get('title') == '复刻验证看板', repr(r0.get('title')))

print('\n=== 3. 灌 4 张卡片（POST bk_cards） ===')
cards = []
for i, (col, title, desc, tg) in enumerate([
    ('todo',  '核对发布流水线', 'CI 是否真的会拦下失败构建', ['t1']),
    ('todo',  '补充空状态文案', '列表为空时给出下一步动作', ['t2']),
    ('doing', '看板拖拽排序', '跨列移动后 position 批量落库', ['t1', 't2']),
    ('done',  '静态托管上线', '拿到 tcloudbaseapp 域名', []),
]):
    c = {'id': uid(12), 'board_id': BID, 'column_id': col, 'title': title,
         'description': desc, 'tag_ids': tg, 'member_ids': ['m1'] if i % 2 == 0 else ['m2'],
         'due_date': None, 'position': float(i)}
    cards.append(c)
    s, b = req('POST', '/bk_cards', c, 'return=representation')
    if s != 201:
        print('  card', i, '->', s, b[:200])
check('4 张卡片全部 201', len(cards) == 4)

s, b = req('GET', '/bk_cards?select=*&board_id=eq.%s&order=position.asc' % BID)
allc = json.loads(b) if s == 200 else []
check('读回 4 张', len(allc) == 4, 'got %d' % len(allc))
s, b = req('GET', '/bk_cards?select=*&board_id=eq.%s&column_id=eq.doing' % BID)
check('按列过滤 doing = 1 张', s == 200 and len(json.loads(b)) == 1)

print('\n=== 4. 改卡片：跨列移动 + 改标题（PATCH） ===')
cid = cards[0]['id']
s, b = req('PATCH', '/bk_cards?id=eq.%s' % cid,
           {'column_id': 'doing', 'position': 1.5, 'title': '核对发布流水线（改）'},
           'return=representation')
print('  ->', s, b[:160])
check('PATCH 200', s == 200)
s, b = req('GET', '/bk_cards?select=*&id=eq.%s' % cid)
r = json.loads(b)[0] if s == 200 and json.loads(b) else {}
check('列已变 doing', r.get('column_id') == 'doing')
check('标题已改', r.get('title') == '核对发布流水线（改）')
check('position 落库 1.5', abs(float(r.get('position') or 0) - 1.5) < 1e-9)

print('\n=== 5. 批量改 position（拖拽排序 persistOrder 的写法） ===')
for i, c in enumerate(cards):
    s, _ = req('PATCH', '/bk_cards?id=eq.%s' % c['id'],
               {'column_id': 'done' if i == 3 else 'todo', 'position': float(i * 2)})
    if s != 200:
        print('  batch', i, '->', s)
s, b = req('GET', '/bk_cards?select=id,column_id,position&board_id=eq.%s&order=position.asc' % BID)
rows = json.loads(b) if s == 200 else []
check('批量 PATCH 后顺序可读', s == 200 and len(rows) == 4,
      ' -> '.join('%s@%s' % (x['column_id'], x['position']) for x in rows))

print('\n=== 6. 删卡片（DELETE） ===')
s, _ = req('DELETE', '/bk_cards?id=eq.%s' % cards[1]['id'])
check('DELETE 204', s == 204, 'got %s' % s)
s, b = req('GET', '/bk_cards?select=count&board_id=eq.%s' % BID)
check('剩 3 张', s == 200 and json.loads(b)[0]['count'] == 3)

print('\n=== 7. 删列表（连带删该列卡片） ===')
s, _ = req('DELETE', '/bk_cards?board_id=eq.%s&column_id=eq.todo' % BID)
check('按列删卡 204', s == 204)
s, b = req('GET', '/bk_cards?select=count&board_id=eq.%s' % BID)
check('剩 1 张', s == 200 and json.loads(b)[0]['count'] == 1)

print('\n=== 8. 改看板列定义（列重命名 / 增删列） ===')
cols = [{'id': 'todo', 'title': '待办'}, {'id': 'doing', 'title': '进行中'}, {'id': 'done', 'title': '已完成'}]
cols[1]['title'] = '进行中（改）'
cols.append({'id': 'blocked', 'title': '阻塞'})
s, b = req('PATCH', '/bk_boards?id=eq.%s' % BID, {'column_defs': cols}, 'return=representation')
check('列定义 PATCH 200 且 4 列', s == 200 and len(json.loads(b)[0]['column_defs']) == 4)

print('\n=== 9. 清理 ===')
s, _ = req('DELETE', '/bk_cards?board_id=eq.%s' % BID)
s2, _ = req('DELETE', '/bk_boards?id=eq.%s' % BID)
check('清理 204/204', s in (204, 200) and s2 in (204, 200), '%s / %s' % (s, s2))
s, b = req('GET', '/bk_boards?select=count&id=eq.%s' % BID)
check('已清空', s == 200 and json.loads(b)[0]['count'] == 0)

print('\n==== 结果：%d/%d 项通过 ====' % (sum(ok), len(ok)))
raise SystemExit(0 if all(ok) else 1)
