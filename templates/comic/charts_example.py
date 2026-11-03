#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""charts.py 范例 —— 信息图格。

信息图是每期定制的（讲兵力就不一样，讲年表又不一样），所以不做成配置，
而是写代码：Comic 已经给齐了积木，画一张信息图通常 20 行。

放在项目目录下，story.json 里 "chart": "chart_s2" 就会调到这里同名函数。
函数签名固定：fn(c: Comic) -> None，画在 c 上即可。

排版要点
--------
· 信息图是「一眼看完」，不是「读」：每行只放一个大信息，层级最多两级。
· 字要够大：主标题 60~64，狠话 48~52，正文 26~30。少于 26 在手机上看不见。
· 强调色只用一处（红）。到处都是红，等于没有强调。
· 别贴着画布边缘，留 60px —— 竖屏合成时四周要留白。

版面右半边通常是空的，所以**底衬图由脚本自动贴**：`comic_layers` 会在调本函数
之前，先铺一张淡掉的「上一格」到右下角（365×425，opacity 0.28）。
所以这里**不要**自己 c.art()，会叠两层。
某格不想要，story.json 里写 "backdrop": false。

要让画面更有节奏，别加 zoompan（裁剪窗宽是小数，ffmpeg 每帧取整，字会一直抖），
改成拆层逐行淡入 —— 那样 charts 要能按步骤输出多张 png，是进阶做法。
"""

from __future__ import annotations

import sys
from pathlib import Path

# comic_layers.py 载入本文件前，已经把 <skill>/lib 放进了 sys.path，
# 所以这里直接 import 就行 —— 不要用 Path(__file__).parents[1] 去猜 skill 位置，
# 这个文件是要被复制到项目目录里的，猜出来的路径是项目目录的上一级。
from comic_layer import CREAM, GREY, INK, RED, YELLOW, Comic  # noqa: E402

W, H = 1080, 1200


def chart_s2(c: Comic):
    """账面实力：条形的长度就是兵力，刘备那条几乎是一个点 —— 这就是笑点。"""
    c.note((60, 96), "账面实力", color=INK, size=64, anchor="lm", kind="hei")
    c.note((60, 168), "公元208年，曹操南下前的家底", color=GREY, size=30,
           anchor="lm", kind="hei")

    rows = [("曹  操", "二十余万", 200000, INK),
            ("孙  权", "三万", 30000, INK),
            ("刘  备", "两千", 2000, RED)]

    for i, (name, num, val, col) in enumerate(rows):
        y = 300 + i * 250
        c.note((60, y), name, color=INK, size=46, anchor="lm", kind="hei")

        bar = max(14, int(val / 200000 * 560))
        x0 = 250
        c.d.rounded_rectangle(
            [x0 * c.S, (y - 34) * c.S, (x0 + bar) * c.S, (y + 34) * c.S],
            radius=12 * c.S, fill=col)
        c.note((x0 + bar + 20, y), num, color=col, size=46, anchor="lm", kind="hei")

        if val == 2000:
            c.note((250, y + 96), "念出来都不好意思", color=RED, size=34, anchor="lm")

    c.note((60, 1090), "这仗怎么打？", color=RED, size=52, anchor="lm")


def chart_s5(c: Comic):
    """三个回合：问什么 / 怎么答。打完架回头数战果，比一直打更耐看。"""
    c.note((60, 96), "三个回合", color=INK, size=64, anchor="lm", kind="hei")
    c.note((60, 168), "全被打回去", color=RED, size=34, anchor="lm")

    rows = [("①", "张昭", "你吹的牛呢？", "大鹏不跟麻雀聊"),
            ("②", "虞翻", "拿什么挡？", "我跑得了，你们跑不了"),
            ("③", "步骘", "你就是说客", "你们也配？")]

    for i, (no, who, ask, ret) in enumerate(rows):
        y = 300 + i * 280
        c.tag(120, y, no, fill=YELLOW, size=40, padx=26, pady=16)
        c.note((215, y - 40), who, color=GREY, size=30, anchor="lm", kind="hei")
        c.note((215, y + 26), ask, color=INK, size=50, anchor="lm", kind="hei")

        # 右栏留给底衬插图，箭头终点压在 x=800 以内，别爬上去
        c.arrow((646, y), (704, y), color=RED, w=5, head=16, bend=-0.12)
        c.note((718, y), ret, color=RED, size=28, anchor="lm")

        if i < 2:
            c.hline(y + 140, 60, W - 60)

    c.note((60, 1120), "一屋子人，一句都没接住。", color=RED, size=50, anchor="lm")


CHARTS = {"chart_s2": chart_s2, "chart_s5": chart_s5}


if __name__ == "__main__":
    # 想单独看效果（不跑整条流水线）：
    #   PYTHONPATH=<skill>/lib python charts.py
    # 整条流水线里用：python scripts/comic_layers.py <项目> --only charts
    out = Path(__file__).parent / "_preview"
    out.mkdir(exist_ok=True)
    for name, fn in CHARTS.items():
        c = Comic(W, H, bg=CREAM, ss=3)
        fn(c)
        c.save(out / f"{name}.png")
        print(out / f"{name}.png")
