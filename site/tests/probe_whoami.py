# -*- coding: utf-8 -*-
"""实测 auth.uid() / auth.role() 在三种凭证下的取值：
   A. publishable key（未登录访客）
   B. 匿名用户 token（/auth/v1/signin/anonymously）
   C. 无 Authorization
走 PostgREST RPC: POST /v1/rdb/rest/rpc/kb_whoami
"""
import json
import os
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV = 'xuyanning-d2g5ejg513e3c8e1d'
GW = 'https://%s.api.tcloudbasegateway.com' % ENV
REST = GW + '/v1/rdb/rest'

with open(os.path.join(ROOT, '..', '.key.txt'), 'r', encoding='utf-8') as f:
    KEY = f.read().strip()


def post(url, headers, body=b'{}', method='POST'):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:
        return -1, 'EXC %s: %s' % (type(e).__name__, e)


# 取匿名 token
st, raw = post(GW + '/auth/v1/signin/anonymously',
               {'Content-Type': 'application/json', 'x-device-id': 'whoami-probe-001'})
anon = json.loads(raw)['access_token'] if st == 200 else None
print('匿名 token 取得:', st, '| len', len(anon or ''))

CASES = [
    ('A. publishable key', {'Authorization': 'Bearer ' + KEY}),
    ('B. 匿名用户 token', {'Authorization': 'Bearer ' + (anon or '')}),
    ('C. 无 Authorization', {}),
]

for name, hdr in CASES:
    h = {'Content-Type': 'application/json'}
    h.update(hdr)
    st, raw = post(REST + '/rpc/kb_whoami', h)
    print('\n=== %s ===' % name)
    print('status:', st)
    try:
        j = json.loads(raw)
        print(json.dumps(j, indent=2, ensure_ascii=False))
    except Exception:
        print(raw[:500])
