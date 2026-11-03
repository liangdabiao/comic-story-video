#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""comic_boards —— 第 2 步：净化 → 统一排版 → 产出 plan.json。

**这里不做任何切分。** 早先版本把画面横切成三带、后来又改成在带边界下刀，
都是为了让引擎「按带慢慢画」—— 实测证明这条路走不通：

    引擎的分组会把整幅内容合并成一个语义物体，物体时长上限 1.6 秒。
    10.5 秒的分镜实测 1.5 秒就画满 98%，剩下 9 秒画面完全不动。
    切 box 没用（box 只决定先后），在像素上下刀也没用（合并发生在分组阶段）。

真正管用的是 `render_explainer.py` 里**不传 element_plan**：
引擎退回 `_schedule_components`，按 √面积把 draw_duration 分给每个连通域，
总时长恒等于 draw_duration —— 天然铺满。同一格重测：0→6 秒均匀推进，
7.8 秒画满，剩 2.7 秒留白。曲线见 references/comic-story.md。

所以这一步只负责：净化线稿、抹水印、裁白边、等比落版、写 plan.json，
外加一份墨迹体检（boards_meta.json）。

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
from scipy import ndimage

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "lib"))
from lineart_clean import clean, stats  # noqa: E402

DEFAULT_CANVAS = (1080, 1200)
INNER = (1040, 900)          # 人物在画布上的最大尺寸（顶部留给气泡）
FLOOR_RATIO = 0.983          # 脚底对齐到画布高度的 98.3%


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


def ink_report(dst: Path) -> dict:
    """落版后的墨迹体检：bbox + 最大连通域占比。

    只做记录，不切图。**不要再往这张图上切带或下刀** —— 绘制节奏由
    render_explainer 的 draw_duration 控制（见该文件顶部说明），
    在像素上断开只会留下白缝，对节奏没有任何帮助。
    """
    a = np.array(Image.open(dst).convert("L"))
    ink = a < 128
    ys, xs = np.where(ink)
    if len(ys) == 0:
        return {"ink": None, "largest": 0.0}
    lab, n = ndimage.label(ink, structure=np.ones((3, 3)))
    sizes = ndimage.sum(ink, lab, range(1, n + 1))
    return {
        "ink": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
        "components": int(n),
        "largest": round(float(sizes.max() / max(sizes.sum(), 1)) * 100, 1),
    }


def main():
    ap = argparse.ArgumentParser(description="生成图 → 统一画布 → plan.json")
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
            tip = "连通域过多，多半是噪点" if s["components"] > 400 else "ok"
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
        rep = ink_report(boards / f"{sid}.png")

        # 不写 regions：没有逐句时间戳时，窗口是估的，反而让引擎
        # 按「单物体 1.6 秒上限」提前画完。绘制节奏交给 draw_duration。
        scenes.append({
            "id": sid,
            "image": f"boards/{sid}.png",
            "audio": f"audio/{sid}.mp3",
        })
        meta[sid] = {"fig": size, "top": top, **rep}
        ink_h = (rep["ink"][3] - rep["ink"][1]) if rep["ink"] else 0
        print(f"  {sid}  {sc['src']:<18} → {size[0]}x{size[1]}  top={top}  "
              f"墨高={ink_h}  连通域={rep['components']}  最大块={rep['largest']}%")

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
