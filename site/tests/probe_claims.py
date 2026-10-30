# -*- coding: utf-8 -*-
"""打印匿名用户 token 的完整 claim 集，与 publishable key 对比，找区分点。"""
import base64
import json
import urllib.request

ENV = 'xuyanning-d2g5ejg513e3c8e1d'
GW = 'https://%s.api.tcloudbasegateway.com' % ENV

req = urllib.request.Request(
    GW + '/auth/v1/signin/anonymously',
    data=b'{}', method='POST',
    headers={'Content-Type': 'application/json', 'x-device-id': 'claims-dump-001'})
with urllib.request.urlopen(req, timeout=25) as r:
    j = json.loads(r.read().decode())

tok = j['access_token']


def dec(seg):
    seg += '=' * (-len(seg) % 4)
    return json.loads(base64.urlsafe_b64decode(seg))


pl = dec(tok.split('.')[1])
print('--- 匿名用户 token 全部 claim 键 ---')
for k in sorted(pl):
    v = pl[k]
    s = json.dumps(v, ensure_ascii=False)
    if len(s) > 160:
        s = s[:150] + '...'
    print('  %-16s = %s' % (k, s))
