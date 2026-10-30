# -*- coding: utf-8 -*-
"""静态校验 index.html：内联脚本语法 / CSS 花括号 / 标签配平 / 关键配置一致性。"""
import re, subprocess, sys, tempfile, os, json, base64

P = 'index.html'
src = open(P, encoding='utf-8').read()
fails = []

print('文件大小:', len(src.encode('utf-8')), 'B, 行数:', src.count('\n') + 1)

# ---------- 1. 内联脚本语法 ----------
scripts = re.findall(r'<script>(.*?)</script>', src, re.S)
print('\n[1] 内联 <script> 块:', len(scripts), '个')
for i, s in enumerate(scripts):
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(s); tmp = f.name
    r = subprocess.run(['node', '--check', tmp], capture_output=True, text=True)
    ok = r.returncode == 0
    print('  块%d (%d 行): %s' % (i + 1, s.count('\n') + 1, 'PASS' if ok else 'FAIL'))
    if not ok:
        print('    ', r.stderr.strip()[:500])
        fails.append('script%d 语法错误' % (i + 1))
    os.unlink(tmp)

# ---------- 2. CSS 花括号 ----------
css = '\n'.join(re.findall(r'<style>(.*?)</style>', src, re.S))
core = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
bal = core.count('{') - core.count('}')
print('\n[2] CSS 花括号: { =%d, } =%d, 差值 =%d  -> %s' % (core.count('{'), core.count('}'), bal, 'PASS' if bal == 0 else 'FAIL'))
if bal:
    fails.append('CSS 花括号不配平')

# ---------- 3. HTML 标签配平 ----------
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
body = src[src.index('<body'):]
body = re.sub(r'<script>.*?</script>', '', body, flags=re.S)
body = re.sub(r'<style>.*?</style>', '', body, flags=re.S)
body = re.sub(r'<!--.*?-->', '', body, flags=re.S)
# 切片起点就是 <body，尾部的 </body></html> 没有对应的开标签，先摘掉
body = re.sub(r'</body>\s*</html>\s*$', '</body>', body, flags=re.S)
stack, bad = [], []
for m in re.finditer(r'<(/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*?)(/?)>', body):
    close, tag, attrs, selfc = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
    if tag in VOID or selfc == '/':
        continue
    if close:
        if stack and stack[-1] == tag:
            stack.pop()
        else:
            bad.append('多余闭合 </%s> @%d' % (tag, m.start()))
    else:
        stack.append(tag)
print('\n[3] HTML 标签配平: 未闭合 =%s, 错配 =%s -> %s'
      % (stack or '无', bad or '无', 'PASS' if not stack and not bad else 'FAIL'))
if stack or bad:
    fails.append('HTML 标签不配平')

# ---------- 4. 关键配置 ----------
print('\n[4] 关键配置')
env = re.search(r"^\s*env: '([^']+)'", src, re.M).group(1)
rest = re.search(r"^\s*rest: '([^']+)'", src, re.M).group(1)
key = re.search(r"^\s*key: '([^']+)'", src, re.M).group(1)
pl = json.loads(base64.urlsafe_b64decode(key.split('.')[1] + '=' * (-len(key.split('.')[1]) % 4)))
checks = [
    ('env 出现在 rest 里', env in rest),
    ('key 的 iss 含 env', env in (pl.get('iss') or '')),
    ('key 的 aud == env', pl.get('aud') == env),
    ('key 的 role == anon', pl.get('role') == 'anon'),
    ('key 未过期', pl.get('exp', 0) > 1900000000),
]
for name, ok in checks:
    print('  %s %s' % ('PASS' if ok else 'FAIL', name))
    if not ok: fails.append(name)

# ---------- 5. 五个标签与面板一一对应 ----------
tabs = re.findall(r'<button data-tab="([^"]+)"', src)
panels = re.findall(r'<section class="panel[^"]*" id="([^"]+)"', src)
print('\n[5] 标签: %s' % tabs)
print('    面板: %s' % panels)
ok = tabs == panels
print('  %s 标签与面板一一对应且顺序一致' % ('PASS' if ok else 'FAIL'))
if not ok: fails.append('标签/面板不对应')

print('\n==== %s ====' % ('全部通过' if not fails else '失败: ' + '; '.join(fails)))
sys.exit(1 if fails else 0)
