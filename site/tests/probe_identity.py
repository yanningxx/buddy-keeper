# -*- coding: utf-8 -*-
"""验证匿名身份稳定性：
1. 同一 x-device-id 多次登录是否返回同一 sub
2. refresh_token 能否换新 access_token（grant_type=refresh_token）
3. 不带 x-device-id 时行为如何
"""
import json
import os
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV = 'xuyanning-d2g5ejg513e3c8e1d'
GW = 'https://%s.api.tcloudbasegateway.com' % ENV


def call(method, url, headers=None, body=None, timeout=25, form=None):
    h = dict(headers or {})
    data = None
    if form is not None:
        data = form.encode('utf-8')
        h.setdefault('Content-Type', 'application/x-www-form-urlencoded')
    elif body is not None:
        data = json.dumps(body).encode('utf-8')
        h.setdefault('Content-Type', 'application/json')
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:
        return -1, 'EXC %s: %s' % (type(e).__name__, e)


DEV = 'stable-device-probe-001'
print('--- 同一 device-id 连登 3 次 ---')
subs = []
for i in range(3):
    st, raw = call('POST', GW + '/auth/v1/signin/anonymously',
                   headers={'x-device-id': DEV}, body={})
    j = json.loads(raw) if st == 200 else {}
    subs.append(j.get('sub'))
    print('  #%d status=%s sub=%s exp_in=%s' % (i + 1, st, j.get('sub'), j.get('expires_in')))
print('  sub 全相同 =', len(set(subs)) == 1)

print('\n--- 换一个 device-id ---')
st, raw = call('POST', GW + '/auth/v1/signin/anonymously',
               headers={'x-device-id': 'stable-device-probe-002'}, body={})
j2 = json.loads(raw) if st == 200 else {}
print('  status=%s sub=%s 与上面不同 =' % (st, j2.get('sub')), j2.get('sub') not in subs)

print('\n--- 不带 x-device-id ---')
st, raw = call('POST', GW + '/auth/v1/signin/anonymously', body={})
print('  status=%s body=%s' % (st, raw[:300]))

print('\n--- refresh_token 换新 token ---')
st, raw = call('POST', GW + '/auth/v1/signin/anonymously',
               headers={'x-device-id': DEV}, body={})
j = json.loads(raw)
rt = j.get('refresh_token')
print('  refresh_token len =', len(rt or ''))
for grant in ('refresh_token',):
    for keyname in ('refresh_token', 'token'):
        st, raw2 = call('POST', GW + '/auth/v1/token',
                        body={'grant_type': grant, keyname: rt})
        print('  grant_type=%s field=%s -> %s %s' % (grant, keyname, st, raw2[:220]))

st, raw2 = call('POST', GW + '/auth/v1/token',
                form='grant_type=refresh_token&refresh_token=%s' % rt)
print('  form 编码 ->', st, raw2[:220])
