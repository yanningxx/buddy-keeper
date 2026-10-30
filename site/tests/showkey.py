# -*- coding: utf-8 -*-
"""从发布页里取出发布密钥，方便新克隆的仓库补回 site/.key.txt。

用法（在 site/ 目录下）：
    python tests/showkey.py > .key.txt

密钥本来就写在页面的 CFG.key 里，是公开值；单独落到文件只是省掉每个脚本重复解析 HTML。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "..", "index.html")

with open(HTML, encoding="utf-8") as f:
    html = f.read()

m = re.search(r"key:\s*'([A-Za-z0-9._\-]+)'", html)
if not m:
    print("在 %s 里没找到 CFG.key，页面结构可能变了" % os.path.normpath(HTML), file=sys.stderr)
    sys.exit(1)

key = m.group(1)
if len(key) < 100:
    print("取到的 key 只有 %d 字符，不像正常值，已中止" % len(key), file=sys.stderr)
    sys.exit(1)

print(key)
