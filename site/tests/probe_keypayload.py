# -*- coding: utf-8 -*-
"""解码 publishable key 的 payload，确认它是否自带 sub（决定未登录访客是否共用一个身份）。"""
import base64
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(ROOT, '..', '.key.txt'), 'r', encoding='utf-8') as f:
    KEY = f.read().strip()

parts = KEY.split('.')
print('segments:', len(parts), '| lens:', [len(p) for p in parts])


def dec(seg):
    seg += '=' * (-len(seg) % 4)
    return json.loads(base64.urlsafe_b64decode(seg))


hdr = dec(parts[0])
pl = dec(parts[1])
print('\n--- header ---')
print(json.dumps(hdr, indent=2, ensure_ascii=False)[:800])
print('\n--- payload ---')
trimmed = {}
for k, v in pl.items():
    if isinstance(v, str) and len(v) > 120:
        v = v[:100] + '...(len=%d)' % len(pl[k])
    trimmed[k] = v
print(json.dumps(trimmed, indent=2, ensure_ascii=False))
print('\nhas sub =', 'sub' in pl, '| sub =', pl.get('sub'))
