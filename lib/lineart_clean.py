#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""lineart_clean —— 把生成模型出的图，变成白板引擎能「逐笔描」的纯线稿。

为什么必须有这一道
------------------
whiteboard_animator 内部走 skeleton_paths：先取连通域 → 算骨架 → 按人手顺序逐段描。
它假设输入是「纯白底 + 纯黑线 + 大片空白」。

生成模型给的是「近似」这样：边缘有抗锯齿灰阶、可能有纸纹噪点、偶尔还有浅灰辅助线。
这些灰阶会被骨架化当成笔画，画出来是一团墨，而不是一笔一笔。

所以只做三件事，别多做：
  1. 灰度 → 阈值二值化（硬边，不留灰）
  2. 去掉面积过小的连通域（噪点、孤立灰点）
  3. 输出白底黑线的 RGB PNG

再顺手处理两个生成模型的通病：
  · 右下角「AI 生成」水印（会变成一个连不上的小连通域，先抹掉）
  · 画面四周大片空白（auto_crop 裁掉，否则人物在画布里太小，气泡尾巴要拖很长）

命令行
------
    python lib/lineart_clean.py in.png out.png            # 净化
    python lib/lineart_clean.py in.png --stats            # 只看连通域体检
    python lib/lineart_clean.py in.png out.png --watermark br
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


# ────────────────────────── 连通域 ──────────────────────────
def _label(mask: np.ndarray, min_area: int = 0):
    """4 邻域连通域标记（BFS，不引 scipy）。返回 (大小列表, 过滤后的 mask)。

    一万多像素的线稿图在 1 秒级，够用；引入 scipy 反而是额外的安装负担。
    """
    h, w = mask.shape
    seen = np.zeros((h, w), dtype=bool)
    out = mask.copy()
    sizes = []
    for y0 in range(h):
        row = mask[y0]
        if not row.any():
            continue
        for x0 in np.flatnonzero(row):
            x0 = int(x0)
            if seen[y0, x0]:
                continue
            stack = [(y0, x0)]
            seen[y0, x0] = True
            cells = []
            while stack:
                cy, cx = stack.pop()
                cells.append((cy, cx))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            sizes.append(len(cells))
            if min_area and len(cells) < min_area:
                for cy, cx in cells:
                    out[cy, cx] = False
    return sizes, out


def strip_watermark(a: np.ndarray, corner: str = "br",
                    fw: float = 0.26, fh: float = 0.09) -> np.ndarray:
    """抹掉生成模型的水印块（直接刷白）。

    corner: br / bl / tr / tl；fw/fh 是水印块占画面的宽高比例。
    """
    h, w = a.shape
    y0, y1 = (int(h * (1 - fh)), h) if corner in ("br", "bl") else (0, int(h * fh))
    x0, x1 = (int(w * (1 - fw)), w) if corner in ("br", "tr") else (0, int(w * fw))
    a = a.copy()
    a[y0:y1, x0:x1] = 255
    return a


def auto_crop(a: np.ndarray, pad: int = 12):
    """按墨迹外接框裁掉四周空白。"""
    ys, xs = np.where(a < 128)
    if len(ys) == 0:
        raise RuntimeError("净化后无墨迹：图可能是空白的，或阈值太严")
    h, w = a.shape
    box = (max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad),
           min(w, int(xs.max()) + pad), min(h, int(ys.max()) + pad))
    return a, box


# ────────────────────────── 主函数 ──────────────────────────
def clean(src, dst=None, threshold: int = 175, min_area: int = 20,
          watermark: str | None = None, crop: bool = False):
    """src: 输入路径；dst: 输出路径（None 则返回 PIL.Image）。"""
    a = np.array(Image.open(src).convert("L"))

    # 中值滤波抹掉纸纹与压缩噪点，同时保住线（核必须是 3）
    a = np.array(Image.fromarray(a).filter(ImageFilter.MedianFilter(3)))

    if watermark:
        a = strip_watermark(a, watermark)

    ink = a < threshold
    _, ink = _label(ink, min_area)

    out = np.where(ink, 0, 255).astype(np.uint8)
    if crop:
        out, box = auto_crop(out)
        img = Image.fromarray(out, mode="L").convert("RGB")
    else:
        img = Image.fromarray(out, mode="L").convert("RGB")
        box = None

    if dst:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        img.save(dst)
        return dst if box is None else (dst, box)
    return img if box is None else (img, box)


def stats(path) -> dict:
    """连通域体检 —— 这个数字直接决定「几秒画完」。

    最大连通域占比越高，引擎越会把它当成一整块一次描完。
    实测一张多角色图 78% 墨迹连在一起 → 10 秒的分镜前 3 秒就画完了，
    剩下 7 秒画面不动。解法见 comic_boards.py 的三带切分。
    """
    a = np.array(Image.open(path).convert("L"))
    ink = a < 128
    total = int(ink.sum())
    if total == 0:
        return {"ink": 0, "components": 0, "largest": 0, "largest_share": 0.0}
    sizes, _ = _label(ink, 0)
    big = sorted(sizes, reverse=True)
    ys, xs = np.where(ink)
    return {
        "ink": total,
        "components": len(sizes),
        "largest": big[0],
        "largest_share": round(big[0] / total * 100, 1),
        "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
        "size": [int(a.shape[1]), int(a.shape[0])],
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        raise SystemExit(0)

    src = args[0]
    if "--stats" in args:
        import json
        print(json.dumps(stats(src), ensure_ascii=False, indent=2))
        raise SystemExit(0)

    dst = args[1] if len(args) > 1 and not args[1].startswith("--") else str(
        Path(src).with_name(Path(src).stem + "_clean.png"))
    wm = None
    if "--watermark" in args:
        wm = args[args.index("--watermark") + 1]
    r = clean(src, dst, watermark=wm, crop="--crop" in args)
    print(r)
