#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""comic_gen —— 第 1 步：按 story.json 出线稿。

两种用法
--------
1) **让 agent 出图（推荐，画风最稳）**
       python scripts/comic_gen.py <项目目录> --list
   打印每格拼好的完整 prompt。把 assets/reference/01-style-anchor.png 作为参考图
   （图生图 / image reference），一起喂给 ImageGen、即梦、Midjourney、SD 都行。
   出完图按文件名放进 raw/。

2) **自带后端批量出图（需要 AGNES_API_KEY）**
       python scripts/comic_gen.py <项目目录> --backend agnes
   自动拿风格锚点当参考图，出到 raw/<id>.png。

为什么必须图生图
----------------
文生图每次都会漂：线条变粗、加阴影、加灰阶、脸型换一套。
把同一张风格锚点图当参考，画风才稳定 —— 而角色可以整批换掉，
这正是「每条视频角色都不同」需要的性质。

风格前缀是这一整套里最重要的一段文字，别改（改了就要重新调阈值）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
STYLE_ANCHOR = SKILL_ROOT / "assets" / "reference" / "01-style-anchor.png"

# ── 风格前缀：实测有效的原文，逐字照抄 ──
STYLE = (
    "白底黑白线稿的简笔漫画，手绘马克笔风格。纯白背景，只有黑色线条和少量纯黑填色"
    "（眉毛、胡须、眼珠、头发、冠帽），绝对不要灰度、不要阴影、不要排线、"
    "不要纸张纹理、不要彩色。线条干净肯定、带轻微不规则的手绘感。漫画夸张比例，头大身小。"
)

# ── 尾部约束：这几句是防翻车的关键，别省 ──
NO_TEXT = "绝对不要画任何文字、气泡、标题、对话框、边框、水印。"
ROOM_TOP = "画面上方留出大片纯空白（留给对话气泡）。"


def full_prompt(scene: dict, cfg: dict) -> str:
    body = scene.get("prompt") or ""
    parts = [cfg.get("style") or STYLE, "内容：" + body]
    if scene.get("room_top", True):
        parts.append(ROOM_TOP)
    parts.append(NO_TEXT)
    return "\n".join(parts)


def cmd_list(cfg, root: Path):
    arts = [s for s in cfg["scenes"] if s.get("type", "art") == "art"]
    print(f"共 {len(arts)} 格要出图。参考图（必须作为 image reference 传入）：\n"
          f"  {STYLE_ANCHOR}\n")
    for sc in arts:
        print("─" * 72)
        print(f"【{sc['id']}】 → 存成 {root / 'raw' / sc['src']}")
        print(f"input_fidelity / image_weight: low   "
              f"（调高会照抄参考图的姿势，反而害事）")
        print("─" * 72)
        print(full_prompt(sc, cfg))
        print()
    print("出完图后：把文件放进 raw/，文件名和 story.json 的 src 对上，"
          "然后跑 scripts/comic_boards.py")


def cmd_agnes(cfg, root: Path, force: bool):
    sys.path.insert(0, str(SKILL_ROOT / "lib"))
    try:
        from lib_agnes import generate_image
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"载入 agnes 客户端失败：{e}")

    if not STYLE_ANCHOR.exists():
        raise SystemExit(f"缺风格锚点：{STYLE_ANCHOR}")

    raw = root / "raw"
    raw.mkdir(exist_ok=True)
    ratio = cfg.get("ratio", "1:1")
    size = cfg.get("gen_size", "2K")

    ok = 0
    for sc in cfg["scenes"]:
        if sc.get("type", "art") != "art":
            continue
        out = raw / sc["src"]
        if out.exists() and not force:
            print(f"  skip {sc['id']}（{out.name} 已存在，--force 可覆盖）")
            continue
        print(f"  {sc['id']} 生成中…", flush=True)
        generate_image(full_prompt(sc, cfg), out,
                       size=size, ratio=ratio, image_ref=STYLE_ANCHOR)
        ok += 1
        print(f"  ✓ {out}")
    print(f"\n完成 {ok} 张 → {raw}")


def main():
    ap = argparse.ArgumentParser(description="出线稿（打印 prompt 或调后端）")
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--list", action="store_true", help="只打印 prompt")
    ap.add_argument("--backend", default="none", choices=["none", "agnes"])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    root = Path(args.project).resolve()
    cfg = json.loads((root / "story.json").read_text(encoding="utf-8"))

    if args.list or args.backend == "none":
        cmd_list(cfg, root)
    else:
        cmd_agnes(cfg, root, args.force)


if __name__ == "__main__":
    main()
