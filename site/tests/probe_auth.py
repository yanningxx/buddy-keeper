# -*- coding: utf-8 -*-
"""探测 CloudBase 认证端点：匿名登录 / 用户名密码 / token 刷新 / user/me，并验证角色提升。"""
import json
import os
import random
import string
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV = 'xuyanning-d2g5ejg513e3c8e1d'
GW = 'https://%s.api.tcloudbasegateway.com' % ENV
REST = GW + '/v1/rdb/rest'

with open(os.path.join(ROOT, '..', '.key.txt'), 'r', encoding='utf-8') as f:
    KEY = f.read().strip()


def call(method, url, headers=None, body=None, timeout=25):
    h = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        h.setdefault('Content-Type', 'application/json')
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8', 'replace')
            return r.status, dict(r.headers), raw
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode('utf-8', 'replace')
    except Exception as e:
        return -1, {}, 'EXC %s: %s' % (type(e).__name__, e)


def jwt_role(tok):
    try:
        import base64
        p = tok.split('.')[1]
        p += '=' * (-len(p) % 4)
        d = json.loads(base64.urlsafe_b64decode(p))
        return {k: d.get(k) for k in ('sub', 'role', 'iss', 'aud', 'exp', 'email', 'user_id', 'uid', 'type', 'anonymous', 'provider')}
    except Exception as e:
        return {'decode_error': str(e)}


def show(tag, st, hdr, raw):
    print('\n=== %s ===' % tag)
    print('status :', st)
    for k in ('content-type', 'www-authenticate', 'x-request-id'):
        if k in hdr:
            print('%-14s: %s' % (k, hdr[k]))
    print('body   :', raw[:600])


dev = ''.join(random.choices(string.ascii_lowercase + string.digits, k=13))
print('device-id:', dev)

# ---------- 1. 匿名登录 ----------
st, hdr, raw = call('POST', GW + '/auth/v1/signin/anonymously',
                    headers={'x-device-id': dev}, body={})
show('1. POST /auth/v1/signin/anonymously', st, hdr, raw)
anon_tok = None
if st == 200:
    try:
        j = json.loads(raw)
        anon_tok = j.get('access_token')
        print('token_type:', j.get('token_type'), '| len(access_token):', len(anon_tok or ''))
        print('claims    :', json.dumps(jwt_role(anon_tok), ensure_ascii=False))
        print('full keys :', list(j.keys()))
    except Exception as e:
        print('parse fail:', e)

# ---------- 2. 用 anon token 打数据面 ----------
if anon_tok:
    st, hdr, raw = call('GET', REST + '/bk_boards?select=count',
                        headers={'Authorization': 'Bearer ' + anon_tok})
    show('2. GET /bk_boards?select=count  (anon user token)', st, hdr, raw)

    st, hdr, raw = call('GET', GW + '/auth/v1/user/me',
                        headers={'Authorization': 'Bearer ' + anon_tok})
    show('3. GET /auth/v1/user/me  (anon token)', st, hdr, raw)

# ---------- 4. 用 publishable key 对照 ----------
st, hdr, raw = call('GET', REST + '/bk_boards?select=count',
                    headers={'Authorization': 'Bearer ' + KEY})
show('4. GET /bk_boards?select=count  (publishable key)', st, hdr, raw)

# ---------- 5. token 刷新端点探测 ----------
if anon_tok:
    st, hdr, raw = call('POST', GW + '/auth/v1/token',
                        headers={'Authorization': 'Bearer ' + anon_tok}, body={})
    show('5. POST /auth/v1/token  (refresh)', st, hdr, raw)

# ---------- 6. 用户名密码登录（先探错误码，确认端点存在） ----------
st, hdr, raw = call('POST', GW + '/auth/v1/signin',
                    headers={'x-device-id': dev},
                    body={'username': 'probe@example.com', 'password': 'x'})
show('6. POST /auth/v1/signin  (username/password, 故意错误)', st, hdr, raw)

# ---------- 7. 注册端点是否可用 ----------
st, hdr, raw = call('POST', GW + '/auth/v1/signup',
                    headers={'x-device-id': dev},
                    body={'email': 'probe_%s@example.com' % dev, 'password': 'Probe!23456'})
show('7. POST /auth/v1/signup', st, hdr, raw)
