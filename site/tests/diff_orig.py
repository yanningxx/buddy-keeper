# -*- coding: utf-8 -*-
"""对比原站与复刻版四个原面板的文本内容，列出所有漂移。"""
import re, urllib.request, difflib, sys
import os
ROOT = os.path.dirname(os.path.abspath(__file__))
KEYP = os.path.join(ROOT, '..', '.key.txt')
HTMLP = os.path.join(ROOT, '..', 'index.html')

ORIG = 'https://buddy-keeper.app.workbuddy.host/?sharecode=37JOHWXES6'
ORIG_LOCAL = os.path.join(ROOT, 'original.html')
MINE = open(HTMLP, encoding='utf-8').read()

# 基线优先用仓库里的快照：线上原站随时可能被新版本覆盖，一旦覆盖，对比就成了「自己比自己」，
# 悄悄变成永远通过。快照不存在时才退回线上抓取，并明确打印来源。
if os.path.isfile(ORIG_LOCAL):
    orig = open(ORIG_LOCAL, encoding='utf-8').read()
    print('[基线] 使用仓库内快照 tests/original.html（%d B）' % len(orig.encode('utf-8')))
else:
    req = urllib.request.Request(ORIG, headers={'User-Agent': 'Mozilla/5.0'})
    orig = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', 'replace')
    print('[基线] 快照缺失，改为线上抓取 %s' % ORIG)

def panels(html):
    out = {}
    for m in re.finditer(r'<section class="panel[^"]*" id="([^"]+)">(.*?)</section>', html, re.S):
        out[m.group(1)] = m.group(2)
    return out

def norm(s):
    s = re.sub(r'<script.*?</script>', '', s, flags=re.S)
    s = re.sub(r'<[^>]+>', '\n', s)
    s = re.sub(r'&nbsp;', ' ', s)
    lines = [re.sub(r'\s+', ' ', x).strip() for x in s.split('\n')]
    return [x for x in lines if x]

po, pm = panels(orig), panels(MINE)
print('原站面板:', list(po))
print('复刻面板:', list(pm))

for k in ['board', 'lab', 'replay', 'notes']:
    a, b = norm(po.get(k, '')), norm(pm.get(k, ''))
    if a == b:
        print('\n[%s] 文本完全一致（%d 行）' % (k, len(a)))
        continue
    print('\n[%s] 存在差异：原来 %d 行，现在 %d 行' % (k, len(a), len(b)))
    for line in difflib.unified_diff(a, b, 'original', 'replica', lineterm='', n=0):
        if line.startswith(('---', '+++', '@@')):
            continue
        print('   ' + line)

# 标题与页脚
to = re.search(r'<title>(.*?)</title>', orig, re.S).group(1)
tm = re.search(r'<title>(.*?)</title>', MINE, re.S).group(1)
print('\n[title] 原: %s\n        新: %s' % (to, tm))

def footer(h):
    m = re.search(r'<footer[^>]*>(.*?)</footer>', h, re.S)
    return norm(m.group(1)) if m else []
fo, fm = footer(orig), footer(MINE)
print('[footer] 一致:', fo == fm)
if fo != fm:
    print('   原:', fo)
    print('   新:', fm)

def header(h):
    m = re.search(r'<header[^>]*>(.*?)</header>', h, re.S)
    return norm(m.group(1)) if m else []
ho, hm = header(orig), header(MINE)
print('[header] 一致:', ho == hm)
if ho != hm:
    print('   原:', ho)
    print('   新:', hm)

# CSS 变量
def vars_of(h):
    return dict(re.findall(r'(--[a-z]+)\s*:\s*([^;]+);', h))
vo, vm = vars_of(orig), vars_of(MINE)
common = {k: (vo[k], vm[k]) for k in vo if k in vm and vo[k].strip() != vm[k].strip()}
print('\n[CSS 变量] 原站 %d 个，取值不同: %s' % (len(vo), common or '无'))
print('[CSS 变量] 原站有而复刻缺失:', sorted(set(vo) - set(vm)) or '无')
