# -*- coding: utf-8 -*-
"""RLS 改造验收：用三种身份（未登录 publishable key / 用户A / 用户B）实际打接口，
逐条验证「谁能写、谁不能写」。

设计原则：
  · 每个断言都真的发一次 HTTP 请求，不看策略文本猜行为
  · 越权写一律以「数据有没有变」为准，而不是只看状态码
    （PostgREST 对被 RLS 过滤掉的行会返回 200 + 空数组，状态码看不出问题）
"""
import json
import os
import sys
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV = 'xuyanning-d2g5ejg513e3c8e1d'
GW = 'https://%s.api.tcloudbasegateway.com' % ENV
REST = GW + '/v1/rdb/rest'

with open(os.path.join(ROOT, '..', '.key.txt'), 'r', encoding='utf-8') as f:
    KEY = f.read().strip()

PASS, FAIL = 0, 0
FAILS = []


def ok(name, extra=''):
    global PASS
    PASS += 1
    print('  PASS  %-56s %s' % (name, extra))


def bad(name, extra=''):
    global FAIL
    FAIL += 1
    FAILS.append(name + (' | ' + extra if extra else ''))
    print('  FAIL  %-56s %s' % (name, extra))


def check(name, cond, extra=''):
    ok(name, extra) if cond else bad(name, extra)


def call(method, path, token, body=None, prefer=None, timeout=25):
    headers = {'Authorization': 'Bearer ' + token}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    if prefer:
        headers['Prefer'] = prefer
    req = urllib.request.Request(REST + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8', 'replace')
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', 'replace')
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return -1, 'EXC %s: %s' % (type(e).__name__, e)


def signin(dev):
    req = urllib.request.Request(
        GW + '/auth/v1/signin/anonymously', data=b'{}', method='POST',
        headers={'Content-Type': 'application/json', 'x-device-id': dev})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())['access_token']


def whoami(token):
    st, j = call('POST', '/rpc/kb_whoami', token, body={})
    return j if st == 200 else {}


def board_doc(bid, code, owner=None):
    d = {
        'id': bid, 'title': 'RLS 测试看板', 'share_code': code,
        'column_defs': [{'id': 'todo', 'title': '待办'}, {'id': 'done', 'title': '已完成'}],
        'members': [{'id': 'm1', 'name': '徐', 'color': '#2f6feb'}],
        'tags': [{'id': 't1', 'name': '测试', 'color': '#0f9d58'}],
    }
    if owner is not None:
        d['owner_uid'] = owner
    return d


def card_doc(cid, bid, col='todo'):
    return {'id': cid, 'board_id': bid, 'column_id': col, 'title': '测试卡', 'position': 0}


def board_exists(token, bid):
    st, rows = call('GET', '/bk_boards?select=id,owner_uid&id=eq.' + bid, token)
    return bool(rows)


def card_exists(token, cid):
    st, rows = call('GET', '/bk_cards?select=id&id=eq.' + cid, token)
    return bool(rows)


def main():
    print('=' * 78)
    print('准备身份')
    print('=' * 78)
    tok_a = signin('rls-test-user-a')
    tok_b = signin('rls-test-user-b')
    ua = whoami(tok_a)
    ub = whoami(tok_b)
    uk = whoami(KEY)
    print('  未登录(key) : uid=%-24r kb_uid=%-8r anon=%s' % (uk.get('uid'), uk.get('kb_uid'), uk.get('anon')))
    print('  用户A       : uid=%-24r kb_uid=%r' % (ua.get('uid'), ua.get('kb_uid')))
    print('  用户B       : uid=%-24r kb_uid=%r' % (ub.get('uid'), ub.get('kb_uid')))
    A, B = ua.get('kb_uid'), ub.get('kb_uid')

    print('\n' + '=' * 78)
    print('0. 身份解析前提')
    print('=' * 78)
    check('publishable key 的 uid 是字面量 anon', uk.get('uid') == 'anon', repr(uk.get('uid')))
    check('publishable key 的 kb_uid 归一为 NULL', uk.get('kb_uid') is None, repr(uk.get('kb_uid')))
    check('用户A 有真实 uid 且 kb_uid 同值', bool(A) and A == ua.get('uid'), repr(A))
    check('A、B 是两个不同身份', A != B, '%r vs %r' % (A, B))
    if not A or A == B or uk.get('kb_uid') is not None:
        print('\n前提不成立，后续断言无意义，终止。')
        return 1

    ba, ca = 'rlsA' + os.urandom(4).hex(), 'RLSA' + os.urandom(3).hex().upper()
    bb, cb = 'rlsB' + os.urandom(4).hex(), 'RLSB' + os.urandom(3).hex().upper()
    cid_a, cid_b = 'rlsCA' + os.urandom(3).hex(), 'rlsCB' + os.urandom(3).hex()

    print('\n' + '=' * 78)
    print('1. 未登录（publishable key）：只能读，不能写')
    print('=' * 78)
    st, rows = call('GET', '/bk_boards?select=id&limit=3', KEY)
    check('可以读看板', st == 200 and isinstance(rows, list), 'status=%s n=%s' % (st, len(rows or [])))

    st, r = call('POST', '/bk_boards', KEY, board_doc(ba + 'x', 'NOAUTH1', owner='anon'),
                 prefer='return=representation')
    check('拿 key 冒充 owner=anon 建板被拒', st in (401, 403), 'status=%s %s' % (st, str(r)[:110]))
    check('越权建板后库里没有这行', not board_exists(KEY, ba + 'x'))

    st, r = call('POST', '/bk_boards', KEY, board_doc(ba + 'y', 'NOAUTH2', owner=A),
                 prefer='return=representation')
    check('拿 key 伪造他人 owner 建板被拒', st in (401, 403), 'status=%s' % st)

    st, r = call('PATCH', '/bk_boards?share_code=eq.4ZX99GZL', KEY,
                 {'title': '被未登录篡改'}, prefer='return=representation')
    check('未登录改演示看板 → 0 行受影响', st == 200 and r == [], 'status=%s rows=%s' % (st, r))

    st, r = call('DELETE', '/bk_boards?share_code=eq.4ZX99GZL', KEY, prefer='return=minimal')
    st2, rows = call('GET', '/bk_boards?select=share_code&share_code=eq.4ZX99GZL', KEY)
    check('未登录删演示看板 → 看板仍在', bool(rows), 'delete_status=%s' % st)

    print('\n' + '=' * 78)
    print('2. 用户A：能写自己的，写不了别人的')
    print('=' * 78)
    st, r = call('POST', '/bk_boards', tok_a, board_doc(ba, ca, owner=A), prefer='return=representation')
    check('A 用自己的 uid 建板成功', st == 201 and r and r[0]['id'] == ba, 'status=%s' % st)

    st, r = call('POST', '/bk_boards', tok_a, board_doc(ba + 'z', 'SPOOF1', owner=B),
                 prefer='return=representation')
    check('A 把 owner 伪造成 B → 被拒', st in (401, 403), 'status=%s %s' % (st, str(r)[:110]))
    check('伪造失败后库里没有这行', not board_exists(tok_a, ba + 'z'))

    st, r = call('POST', '/bk_boards', tok_a, board_doc(ba + 'w', 'NOOWNER'), prefer='return=representation')
    check('A 建板但不写 owner → 被拒', st in (400, 401, 403), 'status=%s' % st)

    st, r = call('PATCH', '/bk_boards?id=eq.' + ba, tok_a, {'title': 'A 改自己的'},
                 prefer='return=representation')
    check('A 改自己的看板成功', st == 200 and len(r or []) == 1 and r[0]['title'] == 'A 改自己的',
          'status=%s' % st)

    st, r = call('PATCH', '/bk_boards?id=eq.' + ba, tok_a, {'owner_uid': B},
                 prefer='return=representation')
    st2, rows = call('GET', '/bk_boards?select=owner_uid&id=eq.' + ba, tok_a)
    check('A 不能把 owner 转让给 B', rows and rows[0]['owner_uid'] == A,
          'patch_status=%s owner_now=%r' % (st, (rows or [{}])[0].get('owner_uid')))

    st, r = call('POST', '/bk_cards', tok_a, card_doc(cid_a, ba), prefer='return=representation')
    check('A 在自己的看板建卡成功', st == 201 and r and r[0]['id'] == cid_a, 'status=%s' % st)

    st, r = call('PATCH', '/bk_cards?id=eq.' + cid_a, tok_a,
                 {'title': 'A 改自己的卡', 'column_id': 'done'}, prefer='return=representation')
    check('A 改自己的卡成功', st == 200 and len(r or []) == 1, 'status=%s' % st)

    print('\n' + '=' * 78)
    print('3. 用户B：能读A的看板（分享语义），但改不了')
    print('=' * 78)
    st, rows = call('GET', '/bk_boards?select=id,title,owner_uid&share_code=eq.' + ca, tok_b)
    check('B 能按分享码读到 A 的看板', st == 200 and len(rows or []) == 1, 'status=%s' % st)
    check('B 读到的 owner_uid 是 A', rows and rows[0]['owner_uid'] == A, repr((rows or [{}])[0].get('owner_uid')))

    st, rows = call('GET', '/bk_cards?select=id&board_id=eq.' + ba, tok_b)
    check('B 能读到 A 看板里的卡', st == 200 and len(rows or []) == 1, 'n=%s' % len(rows or []))

    st, r = call('PATCH', '/bk_boards?id=eq.' + ba, tok_b, {'title': 'B 篡改'}, prefer='return=representation')
    st2, rows = call('GET', '/bk_boards?select=title&id=eq.' + ba, tok_b)
    check('B 改 A 的看板 → 0 行受影响', st == 200 and r == [], 'status=%s rows=%s' % (st, r))
    check('B 篡改后标题仍是 A 写的', rows and rows[0]['title'] == 'A 改自己的', repr((rows or [{}])[0].get('title')))

    st, r = call('PATCH', '/bk_cards?id=eq.' + cid_a, tok_b, {'title': 'B 篡改卡'},
                 prefer='return=representation')
    st2, rows = call('GET', '/bk_cards?select=title&id=eq.' + cid_a, tok_b)
    check('B 改 A 的卡 → 0 行受影响', st == 200 and r == [], 'status=%s rows=%s' % (st, r))
    check('B 篡改后卡片标题仍是 A 写的', rows and rows[0]['title'] == 'A 改自己的卡', repr((rows or [{}])[0].get('title')))

    st, r = call('POST', '/bk_cards', tok_b, card_doc(cid_b, ba), prefer='return=representation')
    check('B 往 A 的看板塞卡 → 被拒', st in (401, 403), 'status=%s %s' % (st, str(r)[:110]))
    check('被拒后 A 的看板里没有这张卡', not card_exists(tok_b, cid_b))

    st, r = call('DELETE', '/bk_cards?id=eq.' + cid_a, tok_b, prefer='return=minimal')
    check('B 删 A 的卡 → 卡仍在', card_exists(tok_b, cid_a), 'delete_status=%s' % st)

    st, r = call('DELETE', '/bk_boards?id=eq.' + ba, tok_b, prefer='return=minimal')
    check('B 删 A 的看板 → 看板仍在', board_exists(tok_b, ba), 'delete_status=%s' % st)

    print('\n' + '=' * 78)
    print('4. 演示看板（owner 为空）：任何人都只读')
    print('=' * 78)
    st, rows = call('GET', '/bk_boards?select=owner_uid&share_code=eq.4ZX99GZL', tok_a)
    check('演示看板 owner_uid 为空', bool(rows) and rows[0]['owner_uid'] is None, repr((rows or [{}])[0].get('owner_uid')))
    st, r = call('PATCH', '/bk_boards?share_code=eq.4ZX99GZL', tok_a, {'title': 'A 想改演示'},
                 prefer='return=representation')
    check('登录用户也改不了演示看板', st == 200 and r == [], 'status=%s rows=%s' % (st, r))

    print('\n' + '=' * 78)
    print('5. 收尾：A 清理自己的数据')
    print('=' * 78)
    st, r = call('DELETE', '/bk_cards?board_id=eq.' + ba, tok_a, prefer='return=minimal')
    check('A 能删自己看板下的卡', st in (200, 204), 'status=%s' % st)
    st, r = call('DELETE', '/bk_boards?id=eq.' + ba, tok_a, prefer='return=minimal')
    check('A 能删自己的看板', st in (200, 204), 'status=%s' % st)
    check('清理后 A 的看板不存在', not board_exists(tok_a, ba))
    check('清理后 A 的卡不存在', not card_exists(tok_a, cid_a))

    print('\n' + '=' * 78)
    print('结果：%d 通过 / %d 失败' % (PASS, FAIL))
    if FAILS:
        print('\n失败项：')
        for f in FAILS:
            print('  -', f)
    print('=' * 78)
    return 0 if FAIL == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
