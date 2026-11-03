#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ink_probe —— 量「一格格子到底画了多久」，别靠肉眼判断。

原理：白底黑线稿，画面里非白像素的比例 = 已经画出来的墨迹比例。
按固定间隔抽帧、算这个比例，就得到一条绘制进度曲线。

为什么要这个工具（血泪教训）
--------------------------
早先文档里写着「实测 1 秒只出轮廓、8 秒画完」，那是假的 —— 没人量过。
真去量才发现：10.5 秒的格子 1.5 秒就画满 98%，剩下 9 秒画面完全静止。
一个没被验证的结论在文档里待了很久，后面所有判断都建在它上面。

判定标准（默认）：
    draw_duration = 0.75 × 该格时长
    墨迹到 95% 的时间点 t95 应该落在 draw_duration 的 55%~115% 之间
    太早 → 引擎提前画完了（多半是传了 element_plan）
    太晚 → DRAW_BUDGET 偏高，收尾没留白

用法
----
    python scripts/ink_probe.py <项目目录>                  # 量全部分拍
    python scripts/ink_probe.py <项目目录> --part s3        # 只量一格
    python scripts/ink_probe.py <项目目录> --step 0.25      # 更细的采样
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "lib"))

DRAW_BUDGET = 0.75       # 与 render_explainer.py 保持一致
PROBE_WIDTH = 270        # 抽帧缩到这个宽度再算，够准且快 20 倍


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


def ink_series(video: Path, step: float) -> list[tuple[float, float]]:
    """返回 [(秒, 墨迹百分比)]，按时间升序。"""
    tmp = Path(tempfile.mkdtemp(prefix="inkprobe_"))
    try:
        subprocess.run(
            [ffmpeg(), "-y", "-loglevel", "error", "-i", str(video),
             "-vf", f"fps=1/{step},scale={PROBE_WIDTH}:-1", str(tmp / "%05d.png")],
            check=True,
        )
        frames = sorted(tmp.glob("*.png"))
        out = []
        for i, f in enumerate(frames):
            a = np.array(Image.open(f).convert("L"))
            out.append(((i + 1) * step, float((a < 200).mean() * 100)))
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probe(video: Path, step: float, label: str) -> dict:
    dur = duration(video)
    series = ink_series(video, step)
    if not series:
        print(f"  {label:<6} 抽帧失败")
        return {}

    final = max(v for _, v in series)
    t95 = next((t for t, v in series if v >= final * 0.95), dur)
    budget = dur * DRAW_BUDGET
    ratio = t95 / budget if budget else 0

    if ratio < 0.55:
        flag, note = "⚠ 太早", "引擎提前画完了（多半传了 element_plan）"
    elif ratio > 1.15:
        flag, note = "⚠ 太晚", "画到最后才收尾，气泡没时间弹"
    else:
        flag, note = "✓", "节奏正常"

    print(f"  {label:<6} {dur:>5.1f}s   墨迹 {final:>5.2f}%   "
          f"95% 在 {t95:>4.1f}s（预算 {budget:>4.1f}s，{ratio * 100:>3.0f}%）  {flag} {note}")
    return {"id": label, "dur": dur, "ink": final, "t95": t95, "ok": flag == "✓"}


def main():
    ap = argparse.ArgumentParser(description="抽帧量每格的绘制进度曲线")
    ap.add_argument("project", nargs="?", default=".", help="项目目录")
    ap.add_argument("--part", help="只量这一格（如 s3）")
    ap.add_argument("--step", type=float, default=0.5, help="采样间隔秒数")
    args = ap.parse_args()

    root = Path(args.project).resolve()
    parts = sorted((root / "out" / "lineart_parts").glob("*.mp4"))
    if args.part:
        parts = [p for p in parts if p.stem == args.part]
    if not parts:
        sys.exit(f"{root}/out/lineart_parts 里没有分拍 mp4，先跑渲染")

    print(f"量绘制进度（预算 = 时长 × {DRAW_BUDGET}）")
    results = [probe(p, args.step, p.stem) for p in parts]
    bad = [r for r in results if r and not r["ok"]]
    print()
    if bad:
        print(f"{len(bad)} 格节奏不对：{', '.join(r['id'] for r in bad)}")
        sys.exit(1)
    print("全部正常")


if __name__ == "__main__":
    main()
