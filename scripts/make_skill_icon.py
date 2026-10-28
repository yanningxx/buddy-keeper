# -*- coding: utf-8 -*-
"""生成技能市场头像：512x512 PNG，无第三方依赖。

用法：
    python scripts/make_skill_icon.py

输出：
    assets/skill-icon-512.png

设计意图：
    深色圆角底 + 暖黄表盘（指针停在 9:00）+ 右下角绿色对勾。
    不加文字，避免中文字体在不同机器上缺失导致字形不一致；
    指针停在 9:00 直接对应「每天 09:00 值守」，对勾对应「签到已完成」。
"""

import os
import struct
import zlib

SIZE = 512
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "assets", "skill-icon-512.png")


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else (hi if v > hi else v)


def cov(sdf, aa=1.0):
    """有符号距离 → 覆盖率（1px 抗锯齿）"""
    return clamp(0.5 - sdf / aa)


def mix(c1, c2, t):
    t = clamp(t)
    return (c1[0] + (c2[0] - c1[0]) * t,
            c1[1] + (c2[1] - c1[1]) * t,
            c1[2] + (c2[2] - c1[2]) * t)


def over(dst, src, a):
    """src 以 alpha a 叠到 dst 上"""
    if a <= 0.0:
        return dst
    if a >= 1.0:
        return src
    return (dst[0] + (src[0] - dst[0]) * a,
            dst[1] + (src[1] - dst[1]) * a,
            dst[2] + (src[2] - dst[2]) * a)


# ---------- 距离场 ----------

def sdf_round_rect(px, py, cx, cy, hw, hh, r):
    qx = abs(px - cx) - (hw - r)
    qy = abs(py - cy) - (hh - r)
    ax = qx if qx > 0.0 else 0.0
    ay = qy if qy > 0.0 else 0.0
    return (ax * ax + ay * ay) ** 0.5 + min(max(qx, qy), 0.0) - r


def sdf_circle(px, py, cx, cy, r):
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5 - r


def sdf_ring(px, py, cx, cy, r, w):
    return abs(((px - cx) ** 2 + (py - cy) ** 2) ** 0.5 - r) - w * 0.5


def sdf_capsule(px, py, ax, ay, bx, by, r):
    """线段 (ax,ay)-(bx,by) 加粗 r 的胶囊"""
    dx = bx - ax
    dy = by - ay
    ll = dx * dx + dy * dy
    if ll == 0.0:
        t = 0.0
    else:
        t = ((px - ax) * dx + (py - ay) * dy) / ll
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    qx = px - (ax + dx * t)
    qy = py - (ay + dy * t)
    return (qx * qx + qy * qy) ** 0.5 - r


# ---------- 绘制 ----------

def render():
    # 颜色
    bg_a = (0x26, 0x2F, 0x42)
    bg_b = (0x0D, 0x10, 0x17)
    gold = (0xFF, 0xC5, 0x3D)
    hand = (0xFF, 0xF1, 0xCC)
    badge = (0x21, 0xC0, 0x8A)
    sep = (0x10, 0x13, 0x19)
    white = (0xFF, 0xFF, 0xFF)

    # 几何
    cx, cy = 250.0, 250.0
    ring_r, ring_w = 158.0, 34.0
    badge_cx, badge_cy, badge_r = 398.0, 398.0, 84.0
    sep_w = 16.0

    rows = []
    for y in range(SIZE):
        py = y + 0.5
        row = bytearray()
        row.append(0)  # filter type 0
        for x in range(SIZE):
            px = x + 0.5

            # 1. 圆角底 + 斜向渐变
            a_bg = cov(sdf_round_rect(px, py, 256.0, 256.0, 256.0, 256.0, 116.0))
            if a_bg <= 0.0:
                row += b"\x00\x00\x00\x00"
                continue
            t = clamp(((px - 40.0) + (py - 40.0)) / 860.0)
            col = mix(bg_a, bg_b, t)

            # 2. 外圈表盘
            col = over(col, gold, cov(sdf_ring(px, py, cx, cy, ring_r, ring_w)))

            # 3. 指针（9:00 —— 时针指左、分针指上）
            a = cov(sdf_capsule(px, py, cx, cy, cx, cy - 104.0, 13.0))
            a = max(a, cov(sdf_capsule(px, py, cx, cy, cx - 76.0, cy, 15.0)))
            col = over(col, hand, a)
            col = over(col, gold, cov(sdf_circle(px, py, cx, cy, 15.0)))

            # 4. 对勾徽标（先画一圈底色做分隔，避免和表盘糊在一起）
            col = over(col, sep, cov(sdf_circle(px, py, badge_cx, badge_cy,
                                                badge_r + sep_w)))
            col = over(col, badge, cov(sdf_circle(px, py, badge_cx, badge_cy, badge_r)))
            a = cov(sdf_capsule(px, py, 368.0, 398.0, 390.0, 422.0, 11.0))
            a = max(a, cov(sdf_capsule(px, py, 390.0, 422.0, 430.0, 366.0, 11.0)))
            col = over(col, white, a)

            row += bytes((int(col[0] + 0.5), int(col[1] + 0.5),
                          int(col[2] + 0.5), int(a_bg * 255.0 + 0.5)))
        rows.append(bytes(row))
    return b"".join(rows)


def write_png(path, raw, size):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8bit RGBA
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


if __name__ == "__main__":
    raw = render()
    n = write_png(OUT, raw, SIZE)
    print("已生成 %s" % OUT)
    print("尺寸 %dx%d  体积 %d 字节 (%.1f KB)" % (SIZE, SIZE, n, n / 1024.0))
    print("平台要求：512x512、<=500KB、JPG/PNG -> %s"
          % ("通过" if n <= 500 * 1024 else "超标"))
