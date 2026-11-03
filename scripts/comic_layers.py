#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""comic_layers —— 第 3 步：画气泡层，渲染信息图格。

为什么气泡必须单独成层
----------------------
白板引擎会把输入图二值化成黑线。橙色气泡是实心色块，进引擎只会被涂成一块黑。
所以气泡不能进引擎，只能在合成阶段按时间弹上去。

这反而是好事：气泡的出场时机变得完全可控 —— 旁白说到哪句，哪句才弹出来。
一次全弹出来，观众会先读完再看画，节奏就散了。

产物
----
    bubbles/s1_0.png   透明气泡，合成时 overlay
    charts/s2.png      信息图格整图（不进引擎，合成时静止 + 淡入）

用法
----
    python scripts/comic_layers.py <项目目录>
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "lib"))
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from comic_layer import BG, Comic, missing_glyphs  # noqa: E402
import story_util as SU  # noqa: E402

DEFAULT_CANVAS = (1080, 1200)


def _ink_bbox(path: Path):
    a = np.array(Image.open(path).convert("L"))
    ys, xs = np.where(a < 128)
    if len(ys) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def _audio_dur(root: Path, sid: str) -> float:
    """读本格音频时长；没有音频就返回 0（气泡时刻退回均分）。"""
    p = root / "audio" / f"{sid}.mp3"
    if not p.exists():
        p = root / "audio" / f"{sid}.wav"
    if not p.exists():
        return 0.0
    try:
        from comic_tts import duration
        return duration(p)
    except Exception:  # noqa: BLE001
        return 0.0


def build_bubbles(cfg, root: Path, canvas):
    out_dir = root / "bubbles"
    out_dir.mkdir(exist_ok=True)
    W, H = canvas
    total = 0
    fatal = []

    for sc in cfg["scenes"]:
        bubbles = sc.get("bubbles") or []
        if not bubbles:
            continue

        board = root / "boards" / f"{sc['id']}.png"
        dur = _audio_dur(root, sc["id"])

        for i, b in enumerate(bubbles):
            # `at` 不写（或写 "auto"）就按念白反推 —— 字幕本来是按分句+字数
            # 铺的，气泡用同一把尺子量，就不用掐着音频听了。
            at = b.get("at")
            auto = at in (None, "", "auto")
            if auto:
                at = SU.bubble_at(sc, b.get("text", ""), dur, i, len(bubbles))
            else:
                at = float(at)

            # 坐标同样可以不写：缺任意一个就整颗按字数自动排版（`story_util.auto_bubble`）。
            # 填准坐标要看图量头顶，一颗来回三四次就比出图还贵，而差几十像素看不见。
            box = SU.bubble_box(b, canvas, i, len(bubbles))
            boxed = all(isinstance(b.get(k), (int, float))
                        for k in ("cx", "cy", "rx", "ry"))
            tail = b.get("tail") or (box["cx"], box["cy"] + box["ry"] + 60)

            c = Comic(W, H, bg=None, ss=3)
            c.bubble(box["cx"], box["cy"], box["rx"], box["ry"], b["text"],
                     tail_to=tuple(tail),
                     tail_w=b.get("tail_w", 52),
                     size=b.get("size", 42),
                     seed=abs(hash(sc["id"] + str(i))) % 999)
            c.save(out_dir / f"{sc['id']}_{i}.png")
            total += 1

            # 只拦「必然出片即废」的两种：气泡出画、缺字形。
            #
            # 「气泡压到头」「尾巴悬空」以前也判，但那个判定拿的是**全图最高点**：
            # 一格里有两个人时，尾巴指向矮的那个（实测 s6：右边络腮胡头顶 y≈439，
            # 而全图最高点在左边那位身上），就会被误判成「悬空」。
            # 结果是为了让这个检查闭嘴，反复看图挪坐标 —— 烧的 token 比重出图还多，
            # 而差 30~50px 在成片里根本看不出来。宁可少报，不要误报。
            if boxed:
                if box["cx"] - box["rx"] < 0 or box["cx"] + box["rx"] > W:
                    fatal.append(f"{sc['id']}_{i}「{b['text']}」气泡左右出画"
                                 f"（cx±rx = {box['cx'] - box['rx']}~{box['cx'] + box['rx']}，画布 0~{W}）")
                if box["cy"] + box["ry"] > H - 20:
                    fatal.append(f"{sc['id']}_{i}「{b['text']}」气泡下沿出画")

            bad = missing_glyphs(b["text"])
            if bad:
                fatal.append(f"{sc['id']}_{i}「{b['text']}」缺字形：{bad}（渲染出来是方框）")

            flag = " (auto)" if auto else ""
            pos = "" if boxed else "  [坐标自动]"
            print(f"  bubbles/{sc['id']}_{i}.png  t={at:.1f}s{flag}{pos}  「{b['text']}」")

    print(f"气泡 {total} 个")
    if fatal:
        print("\n✗ 气泡阻断（这些必然出片即废）：")
        for p in fatal:
            print("   · " + p)
    return len(fatal)


BACKDROP_BOX = (655, 715, 365, 425)   # 右下角，右/下各留 60
BACKDROP_OPACITY = 0.28


def _pick_backdrop(cfg, sc, root: Path):
    """给信息图挑一张底衬。

    优先：本格之前、离得最近的那个线稿格 —— 「上一回合」的语义最准。
    兜底：前面没有线稿格（第一格就是信息图），就在现成的格子里固定随机一张。
    随机必须用格的 id 当种子，否则每次渲染都换图，分拍缓存全废、画面还会跳。
    """
    scenes = cfg["scenes"]
    idx = next((i for i, s in enumerate(scenes) if s.get("id") == sc.get("id")), 0)
    for prev in reversed(scenes[:idx]):
        if prev.get("type", "art") != "art":
            continue
        p = root / "boards" / f"{prev['id']}.png"
        if p.exists():
            return p
    # 兜底随机只能在「分镜里的线稿格」里挑。
    # 不能 glob boards/*.png —— 那里还躺着 storyboard.png（七格拼图），
    # 抽到它会把一整排小格糊到右下角。
    pool = [root / "boards" / f"{s['id']}.png"
            for s in scenes if s.get("type", "art") == "art"]
    pool = [p for p in pool if p.exists()]
    return random.Random(sc["id"]).choice(pool) if pool else None


def _paint_backdrop(c: Comic, cfg, sc, root: Path):
    """信息图右半边基本是空的，贴一张淡掉的别格当底衬，画面立刻不空。

    铁律：**先贴图，再画字。** art() 走 multiply，顺序反了字会被压暗一遍。
    所以这里在 fn(c) 之前调，charts.py 里不要再自己 art()（会叠两层）。

    crop 是必须的：整格 1080×1200 塞进 365×425 的框，人物只剩两三百像素，
    糊成一团线。按墨迹包围盒裁掉「上方给气泡留的白」，对比度才保得住。

    opacity 0.24 是实测值：0.22 只见一团灰影，0.45 以上开始跟标题抢视线。

    某格不想要，story.json 里写 "backdrop": false。
    """
    if sc.get("backdrop") is False:
        return None
    img = _pick_backdrop(cfg, sc, root)
    if img is None:
        return None
    bb = _ink_bbox(img)
    if bb is None:
        return None
    w, h = Image.open(img).size
    pad = 20
    crop = (max(0, bb[0] - pad), max(0, bb[1] - pad),
            min(w, bb[2] + pad), min(h, bb[3] + pad))
    c.art(img, BACKDROP_BOX, fit="contain", opacity=BACKDROP_OPACITY, crop=crop)
    return img


def build_charts(cfg, root: Path, canvas):
    """信息图格由项目自己的 charts.py 画。

    charts.py 里定义 CHARTS = {"s2": fn, ...}，fn(comic) 在给定 Comic 上作画。
    信息图是每期定制的，不适合做成通用配置 —— 代码才是对的工具，
    Comic 已经提供了气泡/标签/圈/箭头/手写注这些积木。

    底衬图是**自动**贴的（上一格优先、兜底随机），charts.py 里不用写。
    """
    chart_scenes = [sc for sc in cfg["scenes"] if sc.get("type") == "chart"]
    if not chart_scenes:
        return

    charts_py = root / "charts.py"
    if not charts_py.exists():
        print(f"⚠️  有 {len(chart_scenes)} 个信息图格，但没找到 {charts_py}")
        print("   参考 templates/comic/charts_example.py 写一个，或用 "
              '"type": "art" 全部改成线稿格')
        return

    sys.path.insert(0, str(root))
    import importlib.util
    spec = importlib.util.spec_from_file_location("proj_charts", charts_py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    registry = getattr(mod, "CHARTS", {})
    out_dir = root / "charts"
    out_dir.mkdir(exist_ok=True)
    W, H = canvas

    for sc in chart_scenes:
        sid = sc["id"]
        fn = registry.get(sc.get("chart") or sid)
        if fn is None:
            print(f"⚠️  {sid}: charts.py 里没有 CHARTS['{sc.get('chart') or sid}']")
            continue
        c = Comic(W, H, bg=BG.get(sc.get("bg", "cream"), BG["cream"]), ss=3)
        # 先贴底衬、再画字，顺序不能反
        used = _paint_backdrop(c, cfg, sc, root)
        if used:
            print(f"     底衬 ← boards/{used.name}")
        fn(c)
        c.save(out_dir / f"{sid}.png")
        print(f"  charts/{sid}.png")


def main():
    ap = argparse.ArgumentParser(description="气泡层 + 信息图格")
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--only", choices=["bubbles", "charts"])
    args = ap.parse_args()

    root = Path(args.project).resolve()
    cfg = json.loads((root / "story.json").read_text(encoding="utf-8"))
    canvas = tuple(cfg.get("canvas", DEFAULT_CANVAS))

    fatal = 0
    if args.only != "charts":
        fatal = build_bubbles(cfg, root, canvas)
    if args.only != "bubbles":
        build_charts(cfg, root, canvas)
    if fatal:
        raise SystemExit(f"\n✗ {fatal} 个气泡无法出片，改完再跑")


if __name__ == "__main__":
    main()
