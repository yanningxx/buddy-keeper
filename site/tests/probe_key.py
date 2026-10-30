import base64, json, urllib.request, urllib.error, sys
import os
ROOT = os.path.dirname(os.path.abspath(__file__))
KEYP = os.path.join(ROOT, '..', '.key.txt')
HTMLP = os.path.join(ROOT, '..', 'index.html')

KEY = open(KEYP).read().strip()
ENV = 'xuyanning-d2g5ejg513e3c8e1d'
REST = 'https://%s.api.tcloudbasegateway.com/v1/rdb/rest' % ENV

p = KEY.split('.')
print('key len =', len(KEY), 'seg =', [len(x) for x in p])
payload = json.loads(base64.urlsafe_b64decode(p[1] + '=' * (-len(p[1]) % 4)))
print('iss =', payload.get('iss'))
print('aud =', payload.get('aud'))
print('sub =', payload.get('sub'), '| role =', payload.get('role'))
print('iss contains env:', ENV in (payload.get('iss') or ''))

def req(method, path, body=None, prefer=None):
    url = REST + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header('Authorization', 'Bearer ' + KEY)
    r.add_header('Content-Type', 'application/json')
    if prefer:
        r.add_header('Prefer', prefer)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            raw = resp.read().decode()
            return resp.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]
    except Exception as e:
        return 'ERR', repr(e)[:300]

s, b = req('GET', '/bk_boards?select=*&limit=2')
print('\n[1] GET bk_boards ->', s, b[:300])

s, b = req('GET', '/bk_cards?select=*&limit=2')
print('[2] GET bk_cards  ->', s, b[:300])
