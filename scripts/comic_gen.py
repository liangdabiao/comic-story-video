#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""comic_gen —— 第 2 步：按 story.json 出线稿。

两种用法
--------
1) **让 agent 出图（推荐，画风最稳）**
       python scripts/comic_gen.py <项目目录> --list
   打印每格拼好的完整 prompt。把 assets/reference/01-style-anchor.png 作为参考图
   （图生图 / image reference），一起喂给 ImageGen、即梦、Midjourney、SD 都行。
   出完图按文件名放进 raw/。

2) **自带后端批量出图（需要 AGNES_API_KEY）**
       python scripts/comic_gen.py <项目目录> --backend agnes

三道锁（都是「少花钱」的锁，不是流程洁癖）
------------------------------------------
**锁一 · 文案没过门禁，不给 prompt。**
出图是全链路最贵的一步（每张 5–10 credits）。先跑 `pipeline.py --stage script`，
文案字数/气泡坐标/charts 函数有结构性问题就停下来 —— 那意味着你一定会改文案，
而改文案之后图就白出了。急用可以 `--no-gate`，但那是给自己找返工。

**锁二 · 出过的图不再打印。**
raw/ 里已经有这张图、且 prompt 指纹没变 → 直接标「已出图」跳过。
实测反例：《陈白沙》10 张里 4 张是重复出图，白花 20–40 credits。

**锁三 · 角色描述只写一次。**
story.json 顶层写 `"characters": {"laozi": "头饰+胡须+衣服+体型 四件事"}`，
prompt 里用 `{laozi}` 占位。每条 prompt 省掉 300 字重复描述，
改一次角色设定八格全变 —— 而以前要改八处，漏一处就是「两个人长得像」。

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
sys.path.insert(0, str(SKILL_ROOT / "lib"))
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import story_util as SU  # noqa: E402

STYLE_ANCHOR = SKILL_ROOT / "assets" / "reference" / "01-style-anchor.png"
# 兼容旧引用：这两个名字以前在本文件里
STYLE = SU.STYLE
NO_TEXT = SU.NO_TEXT
ROOM_TOP = SU.ROOM_TOP
full_prompt = SU.full_prompt


def _load_ledger(raw: Path) -> dict:
    p = raw / ".gen.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"prompts": {}, "at": {}}


def _save_ledger(raw: Path, led: dict):
    raw.mkdir(exist_ok=True)
    (raw / ".gen.json").write_text(json.dumps(led, ensure_ascii=False, indent=2),
                                   encoding="utf-8")


def cmd_list(cfg, root: Path, gate: bool, show_done: bool):
    arts = [s for s in cfg["scenes"] if s.get("type", "art") == "art"]
    raw = root / "raw"
    led = _load_ledger(raw)

    if gate:
        import pipeline
        if not pipeline.check_script(root):
            raise SystemExit(
                "\n✗ 文案没过门禁，不出图。出图是最贵的一步，文案还会改，"
                "现在出的图大概率作废。\n"
                "  改完重跑：python scripts/pipeline.py <项目目录> --stage script\n"
                "  （确定要硬出，加 --no-gate）")

    todo, done = [], []
    for sc in arts:
        h = SU.prompt_hash(sc, cfg)
        exists = (raw / (sc.get("src") or f"{sc['id']}.png")).exists()
        (done if (exists and led["prompts"].get(sc["id"]) == h and not show_done) else todo).append(sc)

    print(f"共 {len(arts)} 格要出图"
          f"（已出 {len(done)} 格，本次要出 {len(todo)} 格）。\n"
          f"参考图（必须作为 image reference 传入）：\n  {STYLE_ANCHOR}\n")
    if done:
        print("已出图、prompt 未变，跳过（要重出加 --show-done 或删掉 raw/ 里那张）：")
        print("  " + "  ".join(f"{sc['id']}({sc.get('src')})" for sc in done) + "\n")

    for sc in todo:
        print("─" * 72)
        print(f"【{sc['id']}】 → 存成 {root / 'raw' / sc.get('src', sc['id'] + '.png')}")
        print("input_fidelity / image_weight: low   "
              "（调高会照抄参考图的姿势，反而害事）")
        print("─" * 72)
        print(full_prompt(sc, cfg))
        print()
        led["prompts"][sc["id"]] = SU.prompt_hash(sc, cfg)

    _save_ledger(raw, led)
    if todo:
        print("出完图后：把文件放进 raw/，文件名和 story.json 的 src 对上，"
              "然后跑 scripts/pipeline.py <项目目录> --stage image")


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
    led = _load_ledger(raw)
    ratio = cfg.get("ratio", "1:1")
    size = cfg.get("gen_size", "2K")

    ok = 0
    for sc in cfg["scenes"]:
        if sc.get("type", "art") != "art":
            continue
        out = raw / (sc.get("src") or f"{sc['id']}.png")
        if out.exists() and not force:
            print(f"  skip {sc['id']}（{out.name} 已存在，--force 可覆盖）")
            continue
        print(f"  {sc['id']} 生成中…", flush=True)
        generate_image(full_prompt(sc, cfg), out,
                       size=size, ratio=ratio, image_ref=STYLE_ANCHOR)
        led["prompts"][sc["id"]] = SU.prompt_hash(sc, cfg)
        _save_ledger(raw, led)
        ok += 1
        print(f"  ✓ {out}")
    print(f"\n完成 {ok} 张 → {raw}")


def main():
    ap = argparse.ArgumentParser(description="出线稿（打印 prompt 或调后端）")
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--list", action="store_true", help="只打印 prompt")
    ap.add_argument("--backend", default="none", choices=["none", "agnes"])
    ap.add_argument("--force", action="store_true", help="agnes 后端：覆盖已有图")
    ap.add_argument("--no-gate", action="store_true", help="跳过文案门禁（不建议）")
    ap.add_argument("--show-done", action="store_true", help="出过的也重新打印")
    args = ap.parse_args()

    root = Path(args.project).resolve()
    cfg = json.loads((root / "story.json").read_text(encoding="utf-8"))

    if args.list or args.backend == "none":
        cmd_list(cfg, root, not args.no_gate, args.show_done)
    else:
        cmd_agnes(cfg, root, args.force)


if __name__ == "__main__":
    main()
