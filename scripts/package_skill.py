# -*- coding: utf-8 -*-
"""把技能打包成开放平台可直接上传的 zip，并在打包前做一次合规自检。

用法：
    python scripts/package_skill.py                 # 打市场版（skill/market）
    python scripts/package_skill.py --selfuse       # 打自用版（skill）

自检项（任一项不过就退出码非 0，不产出 zip）：
    1. 能切出 YAML frontmatter
    2. 开放平台八项必填齐全：name / display_name / display_name_en /
       description / description_zh / description_en / version / author
    3. name 是 kebab-case（小写字母、数字、连字符）
    4. name == 压缩包顶层目录名
    5. version 是 x.y.z
    6. examples_zh 建议 3 条（决定详情页「试试这样问我」）
    7. zip 内路径统一用 /，剔除 __pycache__ / .pyc / .log
    8. 总体积 <= 3MB
"""

import hashlib
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")

REQUIRED = ["name", "display_name", "display_name_en", "description",
            "description_zh", "description_en", "version", "author"]
LIST_FIELDS = ("examples_zh", "examples_en")
LIMIT = 3 * 1024 * 1024


def parse_frontmatter(text):
    """极简 YAML 头解析：只处理顶层 key: value 与 - 列表项。"""
    if not text.startswith("---"):
        raise SystemExit("SKILL.md 没有以 --- 开头，无法切出 frontmatter")
    parts = text.split("\n")
    end = None
    for i in range(1, len(parts)):
        if parts[i].strip() == "---":
            end = i
            break
    if end is None:
        raise SystemExit("SKILL.md 的 frontmatter 没有闭合的 ---")
    data = {}
    cur = None
    for line in parts[1:end]:
        if not line.strip():
            continue
        if line.lstrip().startswith("- ") and cur:
            data.setdefault(cur, [])
            if isinstance(data[cur], list):
                data[cur].append(line.lstrip()[2:].strip().strip('"').strip("'"))
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val == "":
            data[key] = []
            cur = key
        else:
            data[key] = val.strip('"').strip("'")
            cur = None
    return data


def check(src_dir, name):
    md = os.path.join(src_dir, "SKILL.md")
    if not os.path.isfile(md):
        raise SystemExit("缺 SKILL.md：%s" % md)
    with open(md, "r", encoding="utf-8") as fh:
        fm = parse_frontmatter(fh.read())

    problems = []
    for k in REQUIRED:
        if not fm.get(k):
            problems.append("缺必填字段：%s" % k)
    nm = fm.get("name") or ""
    if nm and not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", nm):
        problems.append("name 不是 kebab-case：%s" % nm)
    if nm and nm != name:
        problems.append("name(%s) 与顶层目录名(%s) 不一致" % (nm, name))
    ver = fm.get("version") or ""
    if ver and not re.match(r"^\d+\.\d+\.\d+$", ver):
        problems.append("version 不是 x.y.z：%s" % ver)
    for k in LIST_FIELDS:
        v = fm.get(k)
        if isinstance(v, list) and v and len(v) != 3:
            problems.append("%s 建议 3 条，当前 %d 条" % (k, len(v)))

    if problems:
        print("自检未通过：")
        for p in problems:
            print("  - " + p)
        raise SystemExit(1)

    print("自检通过：八项必填齐全，name=%s，version=%s，examples_zh=%d 条"
          % (nm, ver, len(fm.get("examples_zh") or [])))
    return fm


def build(src_dir, name, version, extra_skip=()):
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, "%s-v%s.zip" % (name, version))
    skip_parts = {"__pycache__", ".git", ".DS_Store"} | set(extra_skip)
    skip_ext = {".pyc", ".log", ".zip"}
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(src_dir):
            dirs[:] = [d for d in dirs if d not in skip_parts]
            for f in sorted(files):
                p = os.path.join(base, f)
                rel = os.path.relpath(p, src_dir).replace("\\", "/")
                if os.path.splitext(f)[1].lower() in skip_ext:
                    continue
                if any(part in skip_parts for part in rel.split("/")):
                    continue
                z.write(p, "%s/%s" % (name, rel))
                n += 1
    size = os.path.getsize(out)
    if size > LIMIT:
        os.remove(out)
        raise SystemExit("体积 %.1f KB 超过 3MB 上限，已删除产物" % (size / 1024.0))
    return out, n, size


def verify_zip(path, name):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    tops = set(x.split("/")[0] for x in names)
    if tops != {name}:
        raise SystemExit("顶层目录不唯一：%s" % tops)
    if "%s/SKILL.md" % name not in names:
        raise SystemExit("SKILL.md 不在顶层一级，平台会解析失败")
    return names


if __name__ == "__main__":
    selfuse = "--selfuse" in sys.argv
    src = os.path.join(ROOT, "skill") if selfuse else os.path.join(ROOT, "skill", "market")
    folder = "buddy-keeper" if selfuse else "yanning-buddy-keeper-watch"

    fm = check(src, folder)
    # 自用版打包时要排掉 skill/market/，否则会把市场版一并塞进包里
    out, n, size = build(src, folder, fm["version"],
                         extra_skip=("market",) if selfuse else ())
    names = verify_zip(out, folder)

    h = hashlib.sha256(open(out, "rb").read()).hexdigest()
    print("已生成 %s" % out)
    print("文件数 %d  体积 %d 字节 (%.1f KB)  上限 3MB" % (n, size, size / 1024.0))
    print("压缩包内路径：")
    for x in names:
        print("  " + x)
    print("SHA-256 %s" % h)
