#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""comic_layer —— 漫画叙事层：把「一张线稿」变成「一格会讲故事的分镜」。

为什么需要这一层
----------------
生成模型只会画线稿，而且**写不了中文**（一定出乱码方块）。
所以分工是死的：模型只负责「谁、什么表情、什么动作」，
台词气泡、标签、强调圈、手写旁注、箭头、底色 —— 全部由代码叠上去。

三层叠法
--------
    底色层（浅蓝/米黄）  →  线稿层（相乘，白底自动让位）  →  叙事层（气泡/圈/注）

坐标系一律用 1x 逻辑坐标，内部乘 ss 超采样，最后 LANCZOS 缩回。
超采样不是为了清晰，是为了让 6px 的笔触在缩回后仍有「马克笔」的边缘，
直接在小尺寸上画会得到 PPT 折线。

字体
----
气泡字用「排版黑体」（混子哥的气泡是印刷字体，不是手写）；
旁注用打包自带的手写体 assets/fonts/MaShanZheng-Regular.ttf。
跨平台候选表见 _FONT_HEI，可用环境变量 COMIC_FONT_HEI / COMIC_FONT_HAND 覆盖。

用法
----
    from comic_layer import Comic, SKY, CREAM, RED, INK

    c = Comic(1080, 1200, bg=SKY)
    c.art("boards/s1_clean.png", (0, 300, 1080, 900))
    c.bubble(245, 175, 145, 92, "哪来的？", tail_to=(265, 372), at=3.6)
    c.ring(310, 640, 56, 42, color=RED)
    c.note((540, 1150), "一屋子人，骂不过一个。", color=RED, size=62)
    c.save("out/s1.png")
"""

from __future__ import annotations

import math
import os
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

# ────────────────────────── 调色 ──────────────────────────
INK = (26, 26, 28)
PAPER = (255, 255, 255)
RED = (200, 44, 38)
SKY = (203, 227, 245)        # 浅蓝底：讲「人」的场次（对话格）
CREAM = (250, 242, 224)      # 米黄底：讲「背景/知识」的场次（信息图格）
MINT = (222, 236, 224)       # 浅绿底：讲「另一方阵营」
ORANGE = (240, 160, 72)      # 气泡橙
YELLOW = (247, 203, 70)      # 标签黄
GREY = (140, 140, 142)       # 时间轴灰 / 次要文字

BG = {"sky": SKY, "cream": CREAM, "mint": MINT, "white": PAPER}

SKILL_ROOT = Path(__file__).resolve().parent.parent
HAND_FONT = SKILL_ROOT / "assets" / "fonts" / "MaShanZheng-Regular.ttf"

# 黑体候选：粗体优先（气泡要压得住画面），其次常规
_FONT_HEI = [
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]

_font_cache: dict = {}


def _first_existing(paths, env_key=None):
    if env_key and os.environ.get(env_key):
        return os.environ[env_key]
    for p in paths:
        if Path(p).exists():
            return str(p)
    raise FileNotFoundError(
        "找不到中文字体。请装一款 CJK 字体，或用环境变量 "
        f"{env_key or 'COMIC_FONT_HEI'} 指定路径。\n候选：\n  " + "\n  ".join(map(str, paths))
    )


def resolve_font(kind: str = "hei") -> str:
    """kind: 'hei' 排版黑体 / 'hand' 手写体。"""
    if kind == "hand":
        return _first_existing([HAND_FONT], "COMIC_FONT_HAND")
    return _first_existing(_FONT_HEI, "COMIC_FONT_HEI")


def font(kind: str, size: int):
    key = (kind, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(resolve_font(kind), max(6, int(size)), index=0)
    return _font_cache[key]


def missing_glyphs(text: str, kind: str = "hei") -> str:
    """预检缺字形（豆腐块）。PIL 对缺字会照常出墨画成方框，抽帧查不出来。

    需要 fonttools：pip install fonttools
    """
    try:
        from fontTools.ttLib import TTCollection, TTFont
    except ImportError:
        return ""  # 没装就不检查，不阻断出片
    path = resolve_font(kind)
    try:
        cmap = set(TTCollection(path).fonts[0].getBestCmap())
    except Exception:
        cmap = set(TTFont(path).getBestCmap())
    return "".join(sorted({ch for ch in text
                           if ord(ch) >= 32 and ord(ch) not in cmap}))


# ────────────────────────── 几何小工具 ──────────────────────────
def _ellipse_pts(cx, cy, rx, ry, n=84, amp=0.0, seed=0):
    """带低频抖动的椭圆。amp 是「手画的松」，1~3px 刚好，超过 6px 就成烂番茄。"""
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, math.tau) for _ in range(3)]
    pts = []
    for i in range(n + 1):
        a = math.tau * i / n
        k = 1.0 + (amp / max(rx, 1)) * (0.62 * math.sin(2 * a + ph[0])
                                        + 0.38 * math.sin(3 * a + ph[1]))
        pts.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a)))
    return pts


class Comic:
    def __init__(self, w, h, bg=SKY, ss=3):
        self.S = ss
        self.W, self.H = w, h
        self.transparent = bg is None
        mode = "RGBA" if self.transparent else "RGB"
        self.img = Image.new(mode, (w * ss, h * ss), (0, 0, 0, 0) if self.transparent else bg)
        self.d = ImageDraw.Draw(self.img)

    def _c(self, color):
        """透明画布上画 RGB 色必须补 alpha，否则 PIL 当成 (r,g,b,0) 画成全透明。"""
        if self.transparent and len(color) == 3:
            return color + (255,)
        return color

    def _p(self, pts):
        s = self.S
        return [(x * s, y * s) for x, y in pts]

    # ────────────────── 贴线稿 ──────────────────
    def art(self, path, box, keep_top=None, fit="width", paper=PAPER):
        """把白底线稿铺进 box（x, y, w, h）。

        用相乘而不是 paste：白底自动让出底色，黑线原样压上去，接缝不会有一圈白边。
        fit="width"  按宽铺满，纵向居中裁（人物格用）
        fit="contain" 整幅装进框，绝不裁（信息图每格插图长宽比差太大）
        """
        src = Image.open(path).convert("RGB")
        if keep_top is not None:
            src = src.crop((0, keep_top, src.width, src.height))

        tw, th = int(box[2] * self.S), int(box[3] * self.S)

        if fit == "contain":
            k = min(tw / src.width, th / src.height)
            src = src.resize((max(1, int(src.width * k)), max(1, int(src.height * k))),
                             Image.LANCZOS)
        else:
            nw = tw
            nh = max(1, int(src.height * tw / src.width))
            src = src.resize((nw, nh), Image.LANCZOS)
            if nh > th:
                top = (nh - th) // 2
                src = src.crop((0, top, nw, top + th))

        layer = Image.new("RGB", self.img.size, paper)
        layer.paste(src, (int(box[0] * self.S) + (tw - src.width) // 2,
                          int(box[1] * self.S) + (th - src.height) // 2))
        self.img = ImageChops.multiply(self.img, layer)
        self.d = ImageDraw.Draw(self.img)

    # ────────────────── 对话气泡 ──────────────────
    def bubble(self, cx, cy, rx, ry, text, tail_to=None, fill=ORANGE,
               fg=INK, size=42, seed=1, tail_w=52, min_size=18):
        """椭圆气泡 + 尖尾巴 + 居中台词。

        两个经验值：
        · 先画尾巴再画气泡，同色叠加，接缝看不见。
        · 尾巴根部必须够宽（≥50）。尾巴又细又长，看着像帽子尖上插了根针。
        · 字太宽会自动缩字号，不手动调。
        """
        if tail_to is not None:
            tx, ty = tail_to
            ux, uy = tx - cx, ty - cy
            n = math.hypot(ux, uy) or 1
            ux, uy = ux / n, uy / n
            k = 1.0 / math.sqrt((ux / rx) ** 2 + (uy / ry) ** 2)
            ex, ey = cx + ux * k, cy + uy * k
            px, py = -uy, ux
            base = [(ex + px * tail_w * 0.55 - ux * 3, ey + py * tail_w * 0.55 - uy * 3),
                    (tx, ty),
                    (ex - px * tail_w * 0.55 - ux * 3, ey - py * tail_w * 0.55 - uy * 3)]
            self.d.polygon(self._p(base), fill=self._c(fill))

        self.d.polygon(self._p(_ellipse_pts(cx, cy, rx, ry, amp=1.4, seed=seed)),
                       fill=self._c(fill))

        # 自动缩放：文字宽度不超过气泡内切宽的 82%
        lines = text.split("\n")
        limit = rx * 2 * 0.82
        while size > min_size:
            f = font("hei", int(size * self.S))
            widest = max(self.d.textlength(ln, font=f) for ln in lines) / self.S
            if widest <= limit:
                break
            size -= 2

        f = font("hei", int(size * self.S))
        lh = size * 1.2
        y0 = cy - lh * (len(lines) - 1) / 2
        for i, ln in enumerate(lines):
            self.d.text((cx * self.S, (y0 + i * lh) * self.S), ln,
                        font=font("hei", int(size * self.S)),
                        fill=self._c(fg), anchor="mm")
        return self

    # ────────────────── 标签（圆角色块） ──────────────────
    def tag(self, cx, cy, text, fill=YELLOW, fg=INK, size=30, padx=22, pady=12):
        f = font("hei", int(size * self.S))
        tw = self.d.textlength(text, font=f) / self.S
        w, h = tw + padx * 2, size + pady * 2
        r = h * 0.32
        x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        self.d.rounded_rectangle([x0 * self.S, y0 * self.S, x1 * self.S, y1 * self.S],
                                 radius=r * self.S, fill=self._c(fill))
        self.d.text((cx * self.S, cy * self.S), text, font=f,
                    fill=self._c(fg), anchor="mm")
        return self

    # ────────────────── 手绘强调圈 ──────────────────
    def ring(self, cx, cy, rx, ry=None, color=RED, w=5, seed=3, turns=1.12):
        """绕 1.1 圈的手绘圈 —— 一定要超出起点一点，否则像个死环。"""
        ry = rx if ry is None else ry
        pts = _ellipse_pts(cx, cy, rx, ry, n=int(90 * turns), amp=3.2, seed=seed)
        self.d.line(self._p(pts), fill=self._c(color), width=int(w * self.S), joint="curve")
        return self

    # ────────────────── 写字 ──────────────────
    def note(self, xy, text, color=INK, size=34, rot=0.0, anchor="mm", kind="hand"):
        """kind='hand' 手写批注 / kind='hei' 排版文字（信息图里黑体更清楚）。

        注意：旋转走「单独图层 + alpha_composite」，直接对整张图 rotate 会把画面转掉。
        """
        f = font(kind, int(size * self.S))
        if rot:
            layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            d.text((xy[0] * self.S, xy[1] * self.S), text,
                   font=f, fill=self._c(color), anchor=anchor)
            layer = layer.rotate(rot, center=(xy[0] * self.S, xy[1] * self.S),
                                 resample=Image.BICUBIC)
            base = self.img.convert("RGBA")
            self.img = Image.alpha_composite(base, layer)
            self.img = self.img.convert("RGB") if not self.transparent else self.img
            self.d = ImageDraw.Draw(self.img)
        else:
            self.d.text((xy[0] * self.S, xy[1] * self.S), text,
                        font=f, fill=self._c(color), anchor=anchor)
        return self

    # ────────────────── 箭头 ──────────────────
    def arrow(self, p0, p1, color=INK, w=4, head=14, bend=0.0):
        """二次贝塞尔箭头。bend 正负决定弯向哪边（法向 = (-dy, dx)）。"""
        (x0, y0), (x1, y1) = p0, p1
        dx, dy = x1 - x0, y1 - y0
        n = math.hypot(dx, dy) or 1
        cx, cy = (x0 + x1) / 2 - dy / n * bend * n, (y0 + y1) / 2 + dx / n * bend * n
        pts = []
        for i in range(25):
            t = i / 24
            u = 1 - t
            pts.append((u * u * x0 + 2 * u * t * cx + t * t * x1,
                        u * u * y0 + 2 * u * t * cy + t * t * y1))
        self.d.line(self._p(pts), fill=self._c(color), width=int(w * self.S), joint="curve")
        ang = math.atan2(y1 - pts[-3][1], x1 - pts[-3][0])
        for s in (+1, -1):
            a = ang + s * 0.42
            self.d.line(self._p([(x1, y1), (x1 - head * math.cos(a), y1 - head * math.sin(a))]),
                        fill=self._c(color), width=int(w * self.S), joint="curve")
        return self

    # ────────────────── 分隔线 ──────────────────
    def vline(self, x, y0, y1, color=GREY, w=3):
        self.d.line(self._p([(x, y0), (x, y1)]), fill=self._c(color), width=int(w * self.S))
        return self

    def hline(self, y, x0, x1, color=(212, 204, 186), w=2):
        self.d.line(self._p([(x0, y), (x1, y)]), fill=self._c(color), width=int(w * self.S))
        return self

    # ────────────────── 输出 ──────────────────
    def result(self):
        return self.img.resize((self.W, self.H), Image.LANCZOS)

    def save(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.result().save(path)
        return path


if __name__ == "__main__":
    # 冒烟测试：三层齐活，确认字体和透明层都能用
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "comic_smoke.png"

    print("hei  ->", resolve_font("hei"))
    print("hand ->", resolve_font("hand"))
    bad = missing_glyphs("哪来的？就他？你吹的牛呢？打。①②③")
    print("缺字形:", bad or "无")

    c = Comic(720, 800, bg=SKY)
    c.bubble(230, 150, 150, 92, "你算老几？", tail_to=(240, 330), seed=1)
    c.bubble(480, 120, 130, 88, "拿什么挡？", tail_to=(470, 320), seed=2)
    c.ring(360, 520, 70, 52)
    c.note((360, 700), "一屋子人，骂不过一个。", color=RED, size=42)
    c.save(out)
    print("saved", out)
