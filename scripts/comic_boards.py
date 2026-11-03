#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""comic_boards —— 第 2 步：把生成图净化、统一排版、切成三带，产出 plan.json。

这一步解决的是全流程最硬的一个约束：

    引擎按「连通域」调度绘制。一张多角色图里 78%~94% 的墨迹是连在一块的，
    引擎把它当一个整体一次描完 —— 10 秒的分镜前 3 秒就画完了，剩下 7 秒画面不动。

解法是把人物按**横向三带**切成三个 region：
    上带 = 头脸      中带 = 身子和手势      下带 = 衣摆
引擎于是按 头 → 身 → 脚 的顺序画，绘制过程自然铺满整段旁白。

（注意：三带只是「时间分配」手段，不改变连通域。真正要分开讲某两块，
必须在出图时就留 8~15px 白缝 —— 见 references/comic-story.md。）

用法
----
    python scripts/comic_boards.py <项目目录>
    python scripts/comic_boards.py <项目目录> --check     # 只体检 raw/ 里的图
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "lib"))
from lineart_clean import clean, stats  # noqa: E402

DEFAULT_CANVAS = (1080, 1200)
INNER = (1040, 900)          # 人物在画布上的最大尺寸（顶部留给气泡）
FLOOR_RATIO = 0.983          # 脚底对齐到画布高度的 98.3%
BANDS = (0.0, 0.40, 0.74, 1.0)   # 三带分界（相对墨迹高度）
BAND_OVERLAP = 0.02          # 相邻带重叠，防「横跨边界」的元素未被完整包含


def make_board(src: Path, dst: Path, canvas, inner, floor_ratio,
               threshold=175, min_area=20, watermark="br"):
    """净化 → 抹水印 → 裁白边 → 等比放进 inner 框 → 脚底对齐落版。"""
    tmp = dst.with_name("_tmp_" + dst.stem + ".png")
    clean(src, tmp, threshold=threshold, min_area=min_area, watermark=watermark)

    a = np.array(Image.open(tmp).convert("L"))
    h, w = a.shape

    ys, xs = np.where(a < 128)
    if len(ys) == 0:
        raise RuntimeError(f"{src.name} 净化后无墨迹（阈值 {threshold} 太严，或图是空白的）")
    pad = 12
    box = (max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad),
           min(w, int(xs.max()) + pad), min(h, int(ys.max()) + pad))
    fig = Image.fromarray(a, mode="L").crop(box)

    # 等比缩放：可以放大（thumbnail 只会缩不会放，别用）
    k = min(inner[0] / fig.width, inner[1] / fig.height)
    fig = fig.resize((max(1, int(fig.width * k)), max(1, int(fig.height * k))), Image.LANCZOS)

    W, H = canvas
    out = Image.new("L", (W, H), 255)
    top = int(H * floor_ratio) - fig.height
    out.paste(fig, ((W - fig.width) // 2, top))
    out.convert("RGB").save(dst)
    tmp.unlink(missing_ok=True)
    return fig.size, top


def make_bands(dst: Path, canvas, bands=BANDS, overlap=BAND_OVERLAP):
    """把人物按高度切成 N 带，返回归一化 0-1000 的 box 列表 [ymin, xmin, ymax, xmax]。"""
    a = np.array(Image.open(dst).convert("L"))
    W, H = canvas
    ys, xs = np.where(a < 128)
    ymin, ymax = int(ys.min()), int(ys.max())
    xmin, xmax = int(xs.min()), int(xs.max())
    hgt = max(1, ymax - ymin)
    ov = hgt * overlap

    boxes = []
    for i in range(len(bands) - 1):
        y0 = ymin + hgt * bands[i] - (ov if i > 0 else 0)
        y1 = ymin + hgt * bands[i + 1] + (ov if i < len(bands) - 2 else 0)
        boxes.append([
            round(max(0, y0) / H * 1000), round(xmin / W * 1000),
            round(min(H, y1) / H * 1000), round(xmax / W * 1000),
        ])
    return boxes, (xmin, ymin, xmax, ymax)


BAND_LABELS = ("top", "mid", "low")
BAND_LINES = ("先画头脸", "再画身子和手势", "最后落下衣摆")


def main():
    ap = argparse.ArgumentParser(description="生成图 → 统一画布 → 三带 → plan.json")
    ap.add_argument("project", nargs="?", default=".", help="项目目录（含 story.json 和 raw/）")
    ap.add_argument("--check", action="store_true", help="只输出 raw/ 的连通域体检，不生成")
    ap.add_argument("--threshold", type=int, default=175)
    ap.add_argument("--min-area", type=int, default=20)
    ap.add_argument("--watermark", default="br",
                    help="水印位置 br/bl/tr/tl，none 表示不处理")
    args = ap.parse_args()

    root = Path(args.project).resolve()
    cfg = json.loads((root / "story.json").read_text(encoding="utf-8"))
    raw = root / "raw"
    boards = root / "boards"
    boards.mkdir(exist_ok=True)

    canvas = tuple(cfg.get("canvas", DEFAULT_CANVAS))
    inner = tuple(cfg.get("inner", INNER))
    floor = cfg.get("floor_ratio", FLOOR_RATIO)
    wm = None if args.watermark in ("none", "None", "") else args.watermark

    if args.check:
        print(f"{'图':<24}{'墨迹%':>8}{'连通域':>8}{'最大占比':>10}  提示")
        for sc in cfg["scenes"]:
            if sc.get("type") != "art":
                continue
            p = raw / sc["src"]
            if not p.exists():
                print(f"{sc['src']:<24}{'缺失':>8}")
                continue
            s = stats(p)
            tip = "连通域过多，多半是噪点" if s["components"] > 400 else (
                "最大块 >70%，必须靠三带切分" if s["largest_share"] > 70 else "ok")
            print(f"{sc['src']:<24}{s['ink'] / (s['size'][0] * s['size'][1]) * 100:>7.1f}%"
                  f"{s['components']:>8}{s['largest_share']:>9.1f}%  {tip}")
        return

    scenes, meta = [], {}
    for sc in cfg["scenes"]:
        if sc.get("type") != "art":
            continue
        sid, src = sc["id"], raw / sc["src"]
        if not src.exists():
            raise SystemExit(f"缺图：{src}\n把生成好的线稿放进 raw/，文件名写进 story.json 的 src")

        size, top = make_board(src, boards / f"{sid}.png", canvas, inner, floor,
                               args.threshold, args.min_area, wm)
        boxes, ink = make_bands(boards / f"{sid}.png", canvas)

        scenes.append({
            "id": sid,
            "image": f"boards/{sid}.png",
            "audio": f"audio/{sid}.mp3",
            "regions": [
                {"label": BAND_LABELS[i], "box": boxes[i],
                 "annotation": BAND_LINES[i], "reveal_order": i + 1}
                for i in range(len(boxes))
            ],
        })
        meta[sid] = {"fig": size, "top": top, "ink": ink, "bands": boxes}
        print(f"  {sid}  {sc['src']:<18} → {size[0]}x{size[1]}  top={top}  "
              f"墨高={ink[3] - ink[1]}")

    plan = {
        "idea": cfg.get("title", "") + " · 漫画面讲故事",
        "canvas": list(canvas),
        "gap": cfg.get("gap", 0.15),
        "scenes": scenes,
    }
    (root / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    (root / "boards_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print(f"plan.json：{len(scenes)} 个线稿格（信息图格不进引擎，合成时单独处理）")


if __name__ == "__main__":
    main()
