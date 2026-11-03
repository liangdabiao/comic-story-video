#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""contact_sheet —— 把整片的分镜拼成一张总览图，一次看完。

    python scripts/contact_sheet.py <项目目录>

产物 `_contact.png`：每格缩小成一行一个、标上格号，一眼能看出
「哪格缺人、哪格多得离谱、哪几张画风跑偏」。

为什么要这个
------------
出完图本来要「每张都开一眼」，5 格就是 5 次看图，每次 1.5~2.5k token。
拼成一张之后只花 1 次的量，而且**横向对比**才看得出画风漂移 ——
单张看每一张都「还行」，八张并排就明显了。

它只做一件事：拼图。不下判定、不建议重出。
容错度的边界见 SKILL.md「出图的容错度」：只有缺人/多人这种叙事错误值得回头。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "lib"))

try:
    from comic_layer import font
except Exception:  # noqa: BLE001          字体库没装也能拼，只是标号用默认字体
    font = None


CELL_W = 360                 # 每格缩略宽度，8 格拼成 4×2 正好一屏
PAD = 10
LABEL_H = 30
BG = (246, 243, 236)


def _label(draw, xy, text, size=20):
    try:
        f = font("hei", size) if font else None
    except Exception:  # noqa: BLE001
        f = None
    draw.text(xy, text, fill=(30, 30, 30), font=f)


def build(root: Path, cols: int = 4) -> Path:
    cfg_path = root / "story.json"
    if not cfg_path.exists():
        raise SystemExit(f"没有 {cfg_path}")

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    # 有 boards/ 就看净化后的（那才是进引擎的东西），没有就看 raw/
    # 注意两处命名不同：boards/ 用格号，raw/ 用 story.json 里的 src
    use_boards = any((root / "boards").glob("*.png"))
    src_dir = root / "boards" if use_boards else root / "raw"

    cells = []
    for sc in cfg["scenes"]:
        sid = sc.get("id", "?")
        kind = sc.get("type", "art")
        if kind == "chart":
            p = root / "charts" / f"{sid}.png"
        elif use_boards:
            p = src_dir / f"{sid}.png"
        else:
            p = src_dir / (sc.get("src") or f"{sid}.png")
        cells.append((sid, kind, p if p.exists() else None))

    have = [c for c in cells if c[2]]
    if not have:
        raise SystemExit(f"{src_dir} 里没有可拼的图，先出图或先跑 comic_boards.py")

    # 按原图长宽比排版：每格统一高度，宽度随比例
    row_h = CELL_W
    rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]

    sheet_w = cols * (CELL_W + PAD) + PAD
    sheet_h = len(rows) * (row_h + LABEL_H + PAD) + PAD
    sheet = Image.new("RGB", (sheet_w, sheet_h), BG)
    d = ImageDraw.Draw(sheet)

    for r, row in enumerate(rows):
        y = PAD + r * (row_h + LABEL_H + PAD)
        for c, (sid, kind, p) in enumerate(row):
            x = PAD + c * (CELL_W + PAD)
            if p is None:
                d.rectangle([x, y, x + CELL_W, y + row_h], outline=(200, 80, 60), width=3)
                _label(d, (x + 12, y + 12), f"{sid}  缺图", 22)
            else:
                im = Image.open(p).convert("RGB")
                im.thumbnail((CELL_W, row_h))
                # 居中贴，留白用底色填，不然会看出裁切
                ox = x + (CELL_W - im.width) // 2
                oy = y + (row_h - im.height) // 2
                sheet.paste(im, (ox, oy))

            tag = f"{sid}" + ("  [信息图]" if kind == "chart" else "")
            if p:
                tag += f"  {p.name}"
            _label(d, (x + 4, y + row_h + 4), tag, 19)

    out = root / "_contact.png"
    sheet.save(out)
    missing = [s for s, _, p in cells if p is None]
    print(f"  {out}   {len(cells)} 格拼成 {len(rows)}×{cols}"
          f"（源：{src_dir.name}/）")
    if missing:
        print(f"  缺图：{', '.join(missing)}")
    print("\n  看这一张就够 —— 只需要确认「人在不在、有没有莫名的多一个人」。")
    print("  图上零星文字/符号、手指数量、留白多少、线条干净度都不用管，")
    print("  见 SKILL.md「出图的容错度」。")
    return out


def main():
    ap = argparse.ArgumentParser(description="把整片分镜拼成一张总览图")
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--cols", type=int, default=4, help="每行几格（默认 4）")
    args = ap.parse_args()
    build(Path(args.project).resolve(), args.cols)


if __name__ == "__main__":
    main()
