#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""self_test —— 装完先跑这个，确认环境能出片。

    python scripts/self_test.py            # 五项全跑（含一次 2 秒渲染）
    python scripts/self_test.py --quick    # 跳过渲染，只查依赖与字体

任何一项失败，先修它，别急着做片子 —— 后面每一步都会卡在同一个地方。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "lib"))

OK, FAIL = "✓", "✗"
results: list[tuple[str, bool, str]] = []


def check(name: str, fn):
    try:
        detail = fn()
        results.append((name, True, detail or ""))
        print(f"  {OK} {name}  {detail or ''}")
    except Exception as e:  # noqa: BLE001
        results.append((name, False, f"{type(e).__name__}: {e}"))
        print(f"  {FAIL} {name}  {type(e).__name__}: {e}")


def t_fonts():
    from comic_layer import missing_glyphs, resolve_font
    hei, hand = resolve_font("hei"), resolve_font("hand")
    bad = missing_glyphs("哪来的？就他？你吹的牛呢？打。①②③④")
    if bad:
        raise RuntimeError(f"字体缺字形：{bad}")
    return f"hei={Path(hei).name} hand={Path(hand).name}"


def t_layer():
    from comic_layer import Comic
    tmp = Path(tempfile.gettempdir()) / "comic_selftest.png"
    c = Comic(360, 420, bg=None, ss=3)
    c.bubble(150, 90, 110, 62, "能写中文吗", tail_to=(160, 200), seed=1)
    c.ring(200, 320, 46, 34)
    c.save(tmp)
    if tmp.stat().st_size < 800:
        raise RuntimeError("产出异常小")
    return f"{tmp.name} {tmp.stat().st_size // 1024}KB"


def t_ffmpeg():
    import theme
    theme.setup_ffmpeg_env()
    ff = theme.ffmpeg_path()
    if not ff:
        raise RuntimeError("找不到 ffmpeg")
    r = subprocess.run([ff, "-version"], capture_output=True, text=True, errors="replace")
    ver = r.stdout.splitlines()[0][:38] if r.stdout else "?"
    probe = Path(ff).with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
    return f"{ver}{'  (+ffprobe)' if probe.exists() else '  (无 ffprobe，已内置兜底)'}"


def t_tts():
    import edge_tts
    return f"edge-tts {getattr(edge_tts, '__version__', '?')}"


def t_engine():
    from whiteboard_animator import WhiteboardAnimator  # noqa: F401
    import whiteboard_animator
    pkg = Path(whiteboard_animator.__file__).parent
    model = pkg / "models" / "craft.onnx"
    if not model.exists():
        raise RuntimeError("CRAFT 模型缺失（请装 whiteboard-animator==0.1.1）")
    return f"引擎就绪，CRAFT {model.stat().st_size / 1e6:.0f}MB"


def t_render():
    """真渲 2 秒：一张小线稿，确认「逐笔描」这条路通。"""
    from PIL import Image, ImageDraw
    tmp = Path(tempfile.mkdtemp(prefix="comic_render_"))
    img = Image.new("RGB", (480, 480), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.ellipse([140, 100, 340, 300], outline=(0, 0, 0), width=7)
    d.line([(140, 380), (340, 380)], fill=(0, 0, 0), width=7)
    img.save(tmp / "b.png")

    import theme
    theme.setup_ffmpeg_env()
    ff = theme.ffmpeg_path()
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", "2", str(tmp / "a.mp3")], capture_output=True, check=True)

    plan = {"idea": "selftest", "canvas": [480, 480], "gap": 0.1,
            "scenes": [{"id": "s1", "image": "b.png", "audio": "a.mp3"}]}
    (tmp / "plan.json").write_text(json.dumps(plan), encoding="utf-8")

    r = subprocess.run([sys.executable, str(SKILL_ROOT / "scripts" / "render_explainer.py"),
                        str(tmp / "plan.json"), "--out", str(tmp / "o.mp4"),
                        "--quality", "low"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1][:160])
    out = tmp / "o.mp4"
    if not out.exists() or out.stat().st_size < 10_000:
        raise RuntimeError("成片异常小")
    return f"{out.stat().st_size // 1024}KB  {tmp}"


def t_gate():
    """门禁代码本身能跑通 —— 用一个最小项目正反各测一次。

    这是必须的自检项：门禁判错了比没有门禁更糟（会拦掉好图，白花钱重出）。
    同时验证「节奏关永远放行」—— 它曾经因为 t95 偏低而要人重出图，实测那些图都正常。
    """
    import shutil
    from PIL import Image, ImageDraw
    tmp = Path(tempfile.mkdtemp(prefix="comic_gate_"))
    try:
        (tmp / "raw").mkdir()
        (tmp / "audio").mkdir()
        # 一张干净的图 + 一张几乎空白的图
        img = Image.new("RGB", (600, 600), (255, 255, 255))
        d = ImageDraw.Draw(img)
        d.ellipse([150, 200, 350, 460], outline=(0, 0, 0), width=5)
        d.line([(150, 520), (350, 520)], fill=(0, 0, 0), width=5)
        img.save(tmp / "raw" / "ok.png")
        Image.new("RGB", (600, 600), (255, 255, 255)).save(tmp / "raw" / "blank.png")

        cfg = {
            "title": "gate", "canvas": [1080, 1200],
            "characters": {"hero": "灰袍老者"},
            "scenes": [
                {"id": "s1", "type": "art", "src": "ok.png", "bg": "sky",
                 "narration": "各位，今儿说个人。" * 8,
                 "prompt": "{hero} 站在画面中间，双手拢在袖中，" * 2,
                 "bubbles": [{"cx": 540, "cy": 160, "rx": 140, "ry": 80, "text": "走着瞧"}]},
                {"id": "s2", "type": "art", "src": "blank.png", "bg": "sky",
                 "narration": "第二件事。" * 8,
                 "prompt": "{hero} 站在画面右侧，背着手，" * 2},
            ],
        }
        (tmp / "story.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

        r = subprocess.run([sys.executable, str(SKILL_ROOT / "scripts" / "pipeline.py"),
                            str(tmp), "--stage", "image"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = r.stdout + r.stderr
        if r.returncode == 0:
            raise RuntimeError("空白图没被拦住（门禁失效）")
        if "几乎空白" not in out:
            raise RuntimeError(f"没报出空白，输出：{out[-200:]}")
        if "✓" not in out:
            raise RuntimeError("干净图也被拦了")

        # 气泡时刻自动反推 + 坐标自动排版
        sys.path.insert(0, str(SKILL_ROOT / "lib"))
        import story_util as SU
        at = SU.bubble_at(cfg["scenes"][0], "走着瞧", 10.0, 0, 1)
        if not (0 < at < 10):
            raise RuntimeError(f"bubble_at 算出 {at}")

        # 什么都不填也必须能排出来，且不许出画
        box = SU.bubble_box({"text": "小屏能装游戏吗"}, (1080, 1200), 0, 1)
        if box["cx"] - box["rx"] < 0 or box["cx"] + box["rx"] > 1080:
            raise RuntimeError(f"自动排版出画：{box}")
        if box["cy"] - box["ry"] < 0:
            raise RuntimeError(f"自动排版顶出画：{box}")
        # 给了 tail 就要跟着 tail 走
        box2 = SU.bubble_box({"text": "小屏能装游戏吗", "tail": [900, 500]},
                             (1080, 1200), 0, 1)
        if abs(box2["cx"] - 900) > 200:
            raise RuntimeError(f"tail 没起作用：{box2}")

        # 节奏关必须永远放行 —— 哪怕 plan.json 里写了 regions（真问题）。
        # 上一版会因为「t95 < 55%」判「画太快」，逼人去重出图，
        # 而实测那些图全都正常播完。这条断言就是防它被改回去。
        (tmp / "plan.json").write_text(json.dumps({
            "scenes": [{"id": "s1", "regions": [{
                "label": "all",
                "box": {"ymin": 0, "xmin": 0, "ymax": 1000, "xmax": 1000},
                "start": 0.0, "end": 1.5}]}]}, ensure_ascii=False), encoding="utf-8")
        r2 = subprocess.run([sys.executable, str(SKILL_ROOT / "scripts" / "pipeline.py"),
                             str(tmp), "--stage", "render"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r2.returncode != 0:
            raise RuntimeError("节奏关拦人了 —— 它必须永远放行，只输出信息")
        if "不要重出图" not in (r2.stdout + r2.stderr):
            raise RuntimeError(f"没给出正确处置：{(r2.stdout + r2.stderr)[-200:]}")

        return (f"空图被拦、好图通过、气泡自动 at={at}s、"
                f"坐标自动 {box['rx']:.0f}×{box['ry']:.0f}、节奏关不拦人")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="跳过实际渲染")
    args = ap.parse_args()

    print(f"skill root: {SKILL_ROOT}\n")
    check("字体", t_fonts)
    check("叙事层 comic_layer", t_layer)
    check("ffmpeg", t_ffmpeg)
    check("edge-tts", t_tts)
    check("白板引擎", t_engine)
    check("门禁 pipeline（含节奏关不拦人）", t_gate)
    if not args.quick:
        check("实际渲染 2 秒", t_render)

    bad = [n for n, ok, _ in results if not ok]
    print()
    if bad:
        print(f"✗ {len(bad)} 项未通过：{', '.join(bad)}")
        print("  修好再往下走 —— 后面每一步会卡在同一个地方。")
        return 1
    print(f"✓ 全部通过（{len(results)} 项）。可以开始做片子了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
