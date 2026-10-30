# -*- coding: utf-8 -*-
"""穷举注册端点的参数组合，看是否存在「无需邮箱验证」的账号创建路径。"""
import json
import random
import string
import urllib.request
import urllib.error

ENV = 'xuyanning-d2g5ejg513e3c8e1d'
GW = 'https://%s.api.tcloudbasegateway.com' % ENV
SUF = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
DEV = 'signup-probe-' + SUF


def call(path, body, method='POST'):
    req = urllib.request.Request(
        GW + path, data=json.dumps(body).encode(), method=method,
        headers={'Content-Type': 'application/json', 'x-device-id': DEV})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')
    except Exception as e:
        return -1, 'EXC %s: %s' % (type(e).__name__, e)


CASES = [
    ('/auth/v1/signup', {'username': 'probe_' + SUF, 'password': 'Probe!23456'}),
    ('/auth/v1/signup', {'username': 'probe_' + SUF, 'password': 'Probe!23456', 'verification_code': ''}),
    ('/auth/v1/signup', {'email': 'p%s@example.com' % SUF, 'password': 'Probe!23456', 'username': 'probe_' + SUF}),
    ('/auth/v1/signup', {'phone': '13800000000', 'password': 'Probe!23456'}),
    ('/auth/v1/signup', {'phone': '13800000000', 'password': 'Probe!23456', 'verification_code': '000000'}),
    ('/auth/v1/signin/username', {'username': 'probe_' + SUF, 'password': 'Probe!23456'}),
    ('/auth/v1/auth/username', {'username': 'probe_' + SUF, 'password': 'Probe!23456'}),
    ('/auth/v1/signin', {'username': 'probe_' + SUF, 'password': 'Probe!23456'}),
    ('/auth/v1/signin', {'email': 'p%s@example.com' % SUF, 'password': 'Probe!23456'}),
    ('/auth/v1/user', {'username': 'probe_' + SUF, 'password': 'Probe!23456'}),
    ('/auth/v1/users', {'username': 'probe_' + SUF, 'password': 'Probe!23456'}),
    ('/auth/v1/verification', {'phone': '13800000000'}),
    ('/auth/v1/verification/code', {'phone': '13800000000'}),
    ('/auth/v1/signup/verification', {'phone': '13800000000'}),
]

for path, body in CASES:
    st, raw = call(path, body)
    short = raw[:230].replace('\n', ' ')
    print('%-34s %-3s %s' % (path, st, short))
    print('   payload:', json.dumps(body, ensure_ascii=False))
