#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ink_probe —— 想知道「这格到底画了多久」时跑一下，**不是门禁，没有判定线**。

先说这个工具被推翻过两次，别再改回去
------------------------------------

**第一次：面积 t95 < 55% 就是「画太快」。**
量 6 个项目 34 格已出片、已人工验收的片子，面积 t95 落在 37%~76% 之间乱跳，
全部正常。原因是引擎画大色块时先描轮廓、再一次性填满 —— 填充那一帧墨迹面积
突然跳一大块，「面积」提前到 95%，**笔其实还在走**。拿面积当进度，等于拿
「涂了多少」当「画了多久」。

**第二次：换成「活跃占比」（墨迹还在长的帧占比）。**
健康 34 格是 31%~77%，而人为构造的「1.5 秒画完」病态样本是 28% ——
**和健康下限重叠，分不开**。

所以这个工具现在**不设阈值、不下判决、不返回非零**。它只输出数字，
你自己看。任何在这里加判定线的改动，都会制造一次白花钱的重出图。

真正有用的检查：plan.json 有没有 regions
----------------------------------------
引擎有两条调度路径（详见 `references/comic-story.md` §4）：

    plan.json 的 scene 带 `regions`（有 start/end）
        → `_schedule_semantic_objects`，每个物体 clip 到 0.3~1.6 秒，
          十几秒的格子能在两秒内画完，剩下全程静止。
    plan.json 干净
        → `_schedule_components`，按 √面积 把 draw_duration 分完，
          总时长恒等于预算。实测 s1 调度 12.38s / 预算 12.34s，一秒不丢。

`render_explainer.py` 只在「有逐句 TTS 真实时间戳」时才传 plan，
按字数估的窗口一律不传。所以正常情况下不会出问题 —— 这条静态检查
就是用来抓「有人手写了 regions」的。

用法
----
    python scripts/ink_probe.py <项目目录>               # 全部格
    python scripts/ink_probe.py <项目目录> --part s3     # 只量一格

看到「活跃」很低时，正确处置只有一条：**查 plan.json，删掉 regions 重渲染**。
渲染重跑一格几十秒、零成本；重出一张图要 5-10 credits 外加一轮看图。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "lib"))

DRAW_BUDGET = 0.75       # 与 render_explainer.py 保持一致，只用于算参考值
PROBE_WIDTH = 240        # 抽帧缩到这个宽度再算，够准且快
INK_EPS = 0.005          # 墨迹面积变化超过这个百分点才算「在画」


def ffmpeg() -> str:
    try:
        sys.path.insert(0, str(SKILL_ROOT / "lib"))
        import theme
        theme.setup_ffmpeg_env()
        return theme.ffmpeg_path()
    except Exception:  # noqa: BLE001
        return "ffmpeg"


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def ink_series(video: Path, step: float) -> list[float]:
    """返回逐帧墨迹百分比，按时间升序。"""
    tmp = Path(tempfile.mkdtemp(prefix="inkprobe_"))
    try:
        subprocess.run(
            [ffmpeg(), "-y", "-loglevel", "error", "-i", str(video),
             "-vf", f"fps=1/{step},scale={PROBE_WIDTH}:-1", str(tmp / "%05d.png")],
            check=True,
        )
        return [
            float((np.array(Image.open(f).convert("L")) < 200).mean() * 100)
            for f in sorted(tmp.glob("*.png"))
        ]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cued_scenes(plan_path: Path) -> list[str]:
    """plan.json 里带 start/end 的 regions 的格号 —— 这是唯一会真出问题的情况。"""
    if not plan_path.exists():
        return []
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    bad = []
    for sc in plan.get("scenes") or []:
        regions = sc.get("regions") or []
        if any(r.get("start") is not None and r.get("end") is not None for r in regions):
            bad.append(sc.get("id", "?"))
    return bad


def probe(video: Path, step: float, label: str) -> dict:
    dur = duration(video)
    ink = ink_series(video, step)
    if len(ink) < 4:
        print(f"  {label:<6} 抽帧太少，跳过")
        return {}

    grows = [abs(ink[i] - ink[i - 1]) > INK_EPS for i in range(1, len(ink))]
    active = sum(grows) / len(grows) * 100

    run = longest = 0
    for g in grows:
        run = 0 if g else run + 1
        longest = max(longest, run)

    final = max(ink)
    budget = dur * DRAW_BUDGET
    t95 = next((i * step for i, v in enumerate(ink) if v >= final * 0.95), dur)

    print(f"  {label:<6} {dur:>5.1f}s  末值墨 {final:>5.2f}%  "
          f"活跃 {active:>3.0f}%  最长静止 {longest * step:>4.2f}s  "
          f"面积95% 在 {t95:>4.1f}s / 预算 {budget:>4.1f}s")
    return {"id": label, "dur": dur, "active": active, "t95": t95}


def main():
    ap = argparse.ArgumentParser(description="量每格画面怎么动的（诊断用，不判定）")
    ap.add_argument("project", nargs="?", default=".", help="项目目录")
    ap.add_argument("--part", help="只量这一格（如 s3）")
    ap.add_argument("--step", type=float, default=0.25, help="采样间隔秒数")
    args = ap.parse_args()

    root = Path(args.project).resolve()

    # ① 静态检查：这是唯一确定性的问题，一眼就能查
    cued = cued_scenes(root / "plan.json")
    if cued:
        print(f"⚠ plan.json 里这几格带 start/end 的 regions：{', '.join(cued)}")
        print("  会激活 element_plan，引擎按窗口卡时间，几秒画完就静止。")
        print("  处置：删掉这几格的 regions，重跑渲染（几十秒，零成本）。")
        print("  **不要重出图** —— 图没问题。\n")
    else:
        print("plan.json 干净（没有 regions）→ 引擎按面积铺满预算，不会提前画完。\n")

    parts = sorted((root / "out" / "lineart_parts").glob("*.mp4"))
    if args.part:
        parts = [p for p in parts if p.stem == args.part]
    if not parts:
        print(f"{root}/out/lineart_parts 里没有分拍 mp4，先跑渲染")
        return

    print("下面的数字只是描述，没有判定线：")
    for p in parts:
        probe(p, args.step, p.stem)

    print("\n怎么读这些数：")
    print("  · 已有 34 格出片成功的片子，活跃占比在 31%~77%、面积 t95 在 37%~76%。")
    print("    人为构造的「1.5 秒画完」样本是活跃 28% —— 和健康下限重叠。")
    print("    所以**低不等于坏**，没有阈值能分开，别拿它当验收标准。")
    print("  · 真觉得某格画得快，先看上面第一行的静态检查结果，再看成片。")
    print("    成片抽帧看着「一直在画」就够，不用管这里的数字。")


if __name__ == "__main__":
    main()
