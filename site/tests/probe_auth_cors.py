# -*- coding: utf-8 -*-
"""检查认证端点的 CORS 预检：自定义头 x-device-id 是否被放行。
   浏览器里 fetch 带自定义头会先发 OPTIONS，allow-headers 不含它就直接失败。"""
import json
import urllib.request
import urllib.error

ENV = 'xuyanning-d2g5ejg513e3c8e1d'
GW = 'https://%s.api.tcloudbasegateway.com' % ENV

ORIGINS = [
    'http://localhost:5173',
    'https://xuyanning-d2g5ejg513e3c8e1d-1414642200.tcloudbaseapp.com',
    'https://buddy-keeper.app.workbuddy.host',
]

PATHS = ['/auth/v1/signin/anonymously', '/auth/v1/token', '/v1/rdb/rest/bk_boards']


def preflight(path, origin, req_headers):
    r = urllib.request.Request(GW + path, method='OPTIONS')
    r.add_header('Origin', origin)
    r.add_header('Access-Control-Request-Method', 'POST' if '/auth/' in path else 'GET')
    r.add_header('Access-Control-Request-Headers', req_headers)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)
    except Exception as e:
        return -1, {'exc': repr(e)}


for path in PATHS:
    for origin in ORIGINS:
        st, h = preflight(path, origin, 'content-type,x-device-id')
        acao = h.get('access-control-allow-origin', '-')
        ach = h.get('access-control-allow-headers', '-')
        acm = h.get('access-control-allow-methods', '-')
        print('\n%s' % path)
        print('  origin: %s' % origin)
        print('  status: %s' % st)
        print('  allow-origin : %s' % acao)
        print('  allow-methods: %s' % acm)
        print('  allow-headers: %s' % ach)
        has = 'x-device-id' in ach.lower()
        if st in (200, 204):
            print('  -> %s' % ('放行 x-device-id' if has else '*** 不放行 x-device-id ***'))
        else:
            print('  -> 预检被拒（%s）' % st)
