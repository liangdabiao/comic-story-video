#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""comic_run —— 一条命令跑完整条片子。

    python scripts/comic_run.py <项目目录>

顺序（有依赖，不能乱）：
    tts     先配音   —— 时长决定后面所有的节奏
    layers  气泡+信息图 —— 只看 story.json，不依赖别的
    boards  线稿净化 + 落版 + plan.json
    render  白板引擎逐笔渲染（最慢，几分钟）
    finish  合成 → 字幕 → 竖屏

跑之前先预检：python scripts/pipeline.py <项目目录> --stage image

单步重跑用对应的 comic_*.py；本脚本是「全跑」的便捷入口。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parent
PY = sys.executable

STEPS = {
    "tts": SKILL / "comic_tts.py",
    "layers": SKILL / "comic_layers.py",
    "boards": SKILL / "comic_boards.py",
    "finish": SKILL / "comic_finish.py",
}


def call(name: str, project: Path, extra=None):
    t0 = time.time()
    print(f"\n══ {name} ══", flush=True)
    cmd = [PY, str(STEPS[name]), str(project)] + (extra or [])
    r = subprocess.run(cmd, cwd=str(project))
    if r.returncode != 0:
        raise SystemExit(f"✗ {name} 失败（rc={r.returncode}），先修好再继续")
    print(f"── {name} ok  {time.time() - t0:.1f}s", flush=True)


def main():
    ap = argparse.ArgumentParser(description="一条命令出片")
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--skip", default="", help="跳过步骤，逗号分隔：tts,layers,boards,render,finish")
    ap.add_argument("--quality", default="high", choices=["low", "medium", "high"])
    ap.add_argument("--no-gate", action="store_true", help="跳过图门禁（不建议）")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}

    # 先过图门禁：缺图 / 空白 / 涂黑会在 boards 那步才炸，白等一轮渲染
    if not args.no_gate and "boards" not in skip and "render" not in skip:
        sys.path.insert(0, str(SKILL))
        import pipeline
        if not pipeline.check_images(project):
            raise SystemExit("✗ 缺图或废图，先补（--no-gate 可跳过）")

    if "tts" not in skip:
        call("tts", project)
    if "layers" not in skip:
        call("layers", project)
    if "boards" not in skip:
        call("boards", project)

    if "render" not in skip:
        t0 = time.time()
        print("\n══ render ══", flush=True)
        r = subprocess.run([
            PY, str(SKILL / "render_explainer.py"), str(project / "plan.json"),
            "--out", str(project / "out" / "lineart.mp4"), "--quality", args.quality,
        ], cwd=str(project))
        if r.returncode != 0:
            raise SystemExit("✗ 渲染失败")
        print(f"── render ok  {time.time() - t0:.1f}s", flush=True)

    if "finish" not in skip:
        call("finish", project)

    print("\n完成 →", project / "out")


if __name__ == "__main__":
    main()
