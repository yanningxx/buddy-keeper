# -*- coding: utf-8 -*-
"""模拟浏览器对 gateway 的 CORS 预检（OPTIONS）与实际跨域请求。"""
import urllib.request, urllib.error
import os
ROOT = os.path.dirname(os.path.abspath(__file__))
KEYP = os.path.join(ROOT, '..', '.key.txt')
HTMLP = os.path.join(ROOT, '..', 'index.html')
KEY = open(KEYP).read().strip()
ORIGIN = 'https://xuyanning-d2g5ejg513e3c8e1d-1414642200.tcloudbaseapp.com'
BASE = 'https://xuyanning-d2g5ejg513e3c8e1d.api.tcloudbasegateway.com/v1/rdb/rest'

def show(label, method, path, headers, body=None):
    r = urllib.request.Request(BASE + path, data=body, method=method)
    for k, v in headers.items():
        r.add_header(k, v)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            s, hs = resp.status, resp.headers
    except urllib.error.HTTPError as e:
        s, hs = e.code, e.headers
    print('\n%s  %s %s -> %d' % (label, method, path.split('?')[0], s))
    for k in ('access-control-allow-origin', 'access-control-allow-methods',
              'access-control-allow-headers', 'access-control-max-age',
              'access-control-expose-headers'):
        print('   %-30s = %s' % (k, hs.get(k)))

common = {'Origin': ORIGIN, 'Access-Control-Request-Method': 'PATCH',
          'Access-Control-Request-Headers': 'authorization,content-type,prefer'}

show('[预检 PATCH]', 'OPTIONS', '/bk_cards?id=eq.xx', common)
show('[预检 DELETE]', 'OPTIONS', '/bk_cards?id=eq.xx',
     {'Origin': ORIGIN, 'Access-Control-Request-Method': 'DELETE',
      'Access-Control-Request-Headers': 'authorization,prefer'})
show('[预检 POST]', 'OPTIONS', '/bk_boards',
     {'Origin': ORIGIN, 'Access-Control-Request-Method': 'POST',
      'Access-Control-Request-Headers': 'authorization,content-type,prefer'})
show('[实际 GET]', 'GET', '/bk_boards?select=count',
     {'Origin': ORIGIN, 'Authorization': 'Bearer ' + KEY})
