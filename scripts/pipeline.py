#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""预检 —— 只回答一个问题：**这套东西跑得起来吗。**

    python scripts/pipeline.py <项目目录> --stage script    # 出图前：文件齐不齐
    python scripts/pipeline.py <项目目录> --stage image     # 渲染前：图还在不在
    python scripts/pipeline.py <项目目录> --stage render     # 合成前：参数有没有写错
    python scripts/pipeline.py <项目目录> --stage all

**这个文件不判断好不好。**

上一版在这里写了 22 条阻断判定和两张词表（回合/加码/老底…），想用脚本保证
「文案像故事」。实测不成立：拿一段纯粹是清单、主角全程不开口、主持人满口
「先把局面摆一摆」的念白去跑，它给了 ✓ 通过 —— 因为脚本只会数字符、查字符串。
把「第二回合」改成「第二件事」，词表一声没响。

拿规则引擎去判质量，等于把判断权交给一个只会数数的东西：坏的拦不住，
好的被误伤（字数差 19 字报警、气泡 8 字上限、格数必须在 6–9）。
**质量靠写得对，不靠跑得通。**

所以这里只剩两类检查，失败都意味着「跑不完」或「产出是废片」：

    文件 / 函数不存在      → 中途崩，或者那一格静默消失
    念白缺失、气泡出画      → 那格没声音，或者字幕跑到画外
    图几乎空白 / 整片涂黑   → 渲出来是废片

风格、节奏、字数、句式的判断，一律不做，也不打印「建议」。要读，读
`references/example.md` 里那版念白 —— 照着它写，比对着任何一个数字改管用。
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

INK_BLANK = 0.8              # 墨迹 <0.8% = 基本空白
INK_DARK = 30.0              # 墨迹 >30% = 整片涂黑（已出片的样本最高 23.7%）


class Report:
    def __init__(self, title: str):
        self.title = title
        self.pre: list[str] = []
        self.rows: list[tuple[str, str]] = []
        self.fails: list[str] = []

    def ok(self, msg=""):
        self.rows.append(("✓", msg))

    def fail(self, msg):
        self.rows.append(("✗", msg))
        self.fails.append(msg)

    def line(self, text: str):
        self.pre.append(text)

    def dump(self) -> bool:
        print(f"\n══ {self.title} ══", flush=True)
        for p in self.pre:
            print(p)
        for mark, msg in self.rows:
            print(f"  {mark} {msg}" if mark else msg)
        print()
        if self.fails:
            print("✗ 跑不起来 —— 下面这些会让流程中途崩，或者产出一段废片：")
            for f in self.fails:
                print(f"   · {f}")
        else:
            print("✓ 可以跑")
        return not self.fails


# ────────────────────────── ① 文件与字段 ──────────────────────────
def check_script(root: Path) -> bool:
    r = Report("① 文件与字段（出图之前）")
    sp = root / "story.json"
    if not sp.exists():
        r.fail(f"没有 {sp}")
        return r.dump()
    try:
        cfg = json.loads(sp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        r.fail(f"story.json 不是合法 JSON：{e}")
        return r.dump()

    scenes = cfg.get("scenes") or []
    if not scenes:
        r.fail("scenes 是空的")
        return r.dump()

    # 填了就打印出来，方便一眼扫过；没填不报错 —— 它是不是好故事，脚本判不了
    r.line("")
    for key in ("story_line", "question", "answer"):
        val = (cfg.get(key) or "").strip()
        r.line(f"  {key:<11}{val if val else '（未填）'}")

    total_chars, total_est, any_real = 0, 0.0, False
    for sc in scenes:
        sid = sc.get("id", "?")
        kind = sc.get("type", "art")
        narr = sc.get("narration") or ""
        n = SU.narration_chars(narr)
        est = SU.est_seconds(narr)
        total_chars += n
        dur = _scene_dur(root, sid, est)
        if dur != est:
            any_real = True
        total_est += dur

        if not narr.strip():
            r.fail(f"{sid}: 没有 narration —— 这一格没有声音，成片里就是一段静音")

        bubbles = sc.get("bubbles") or []
        r.line(f"  {sid:<3} {kind:<5} {n:>3}字 {dur:>5.1f}s  泡{len(bubbles)}")

        W, H = tuple(cfg.get("canvas", (1080, 1200)))
        for i, b in enumerate(bubbles):
            txt = b.get("text") or ""
            tag = f"{sid} 气泡{i}「{txt}」"
            if not txt.strip():
                r.fail(f"{tag}: 空台词，会渲染成一个空气泡")
            boxed = all(isinstance(b.get(k), (int, float))
                        for k in ("cx", "cy", "rx", "ry"))
            if boxed:
                cx, cy, rx, ry = (float(b[k]) for k in ("cx", "cy", "rx", "ry"))
                if cx - rx < 0 or cx + rx > W:
                    r.fail(f"{tag}: 左右出画（{cx - rx:.0f}~{cx + rx:.0f}，画布 0~{W}）")
                if cy - ry < 0:
                    r.fail(f"{tag}: 顶出画（上沿 {cy - ry:.0f}）")
                if cy + ry > H:
                    r.fail(f"{tag}: 底出画（下沿 {cy + ry:.0f} > {H}）")
            at = b.get("at")
            if at not in (None, "", "auto") and float(at) > dur + 0.8:
                r.fail(f"{tag}: at={at}s 超出本格时长 {dur:.1f}s —— 这颗气泡永远不会出现")
            try:
                from comic_layer import missing_glyphs
                bad = missing_glyphs(txt)
                if bad:
                    r.fail(f"{tag}: 字体缺字形 {bad}，会渲染成方框")
            except Exception:  # noqa: BLE001
                pass

        if kind == "art":
            if not sc.get("src"):
                r.fail(f"{sid}: art 格缺 src —— 不知道用哪张图")
            p = sc.get("prompt") or ""
            if not p.strip():
                r.fail(f"{sid}: art 格缺 prompt —— comic_gen --list 会跳过这一格")
            unk = SU.unknown_placeholders(p, cfg)
            if unk:
                r.fail(f"{sid}: prompt 里的角色 {unk} 没在 characters 里定义，会原样印出花括号")
        elif kind == "chart":
            name = sc.get("chart") or sid
            charts = root / "charts.py"
            if not charts.exists():
                r.fail(f"{sid}: 是信息图格，但项目里没有 charts.py")
            else:
                reg = _chart_registry(charts)
                if reg is None:
                    r.fail(f"{sid}: charts.py 载入失败，信息图会静默跳过")
                elif name not in reg:
                    r.fail(f"{sid}: charts.py 里没有 CHARTS['{name}'] —— 这格会静默消失")
        else:
            r.fail(f"{sid}: type={kind} 不认识（只能是 art / chart）")

    src = "音频实测" if any_real else "按字数估"
    r.line(f"\n  合计 {total_chars} 字 → 约 {total_est:.0f} 秒（{src}，未计格间停顿）")
    return r.dump()


def _scene_dur(root: Path, sid: str, est: float) -> float:
    """本格实际时长：有音频就用音频的，没有才按字数估。

    配音之后再跑预检很常见，这时拿估算的秒数去卡 `at` 会误报。
    """
    for ext in ("mp3", "wav"):
        p = root / "audio" / f"{sid}.{ext}"
        if p.exists():
            try:
                from comic_tts import duration
                d = duration(p)
                if d > 0:
                    return round(d, 1)
            except Exception:  # noqa: BLE001
                pass
    return est


_CHART_CACHE: dict[str, dict | None] = {}


def _chart_registry(charts_py: Path):
    """载入项目的 charts.py，返回 CHARTS 字典（同一次运行只载一次）。"""
    key = str(charts_py)
    if key in _CHART_CACHE:
        return _CHART_CACHE[key]
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location("_proj_charts_probe", charts_py)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(charts_py.parent))
        spec.loader.exec_module(mod)          # noqa: F401
        reg = getattr(mod, "CHARTS", {}) or {}
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ charts.py 载入失败：{e}")
        reg = None
    _CHART_CACHE[key] = reg
    return reg


# ────────────────────────── ② 图在不在 ──────────────────────────
def _measure(p: Path) -> dict:
    import numpy as np
    from PIL import Image
    a = np.array(Image.open(p).convert("L"))
    ink = a < 128
    tot = int(ink.sum())
    h, w = a.shape
    d = {"w": w, "h": h, "ink_pct": round(tot / a.size * 100, 1),
         "gray_pct": round(float(((a >= 60) & (a <= 200)).mean() * 100), 1),
         "largest": 0.0}
    if tot == 0:
        return d
    try:
        from scipy import ndimage
        lab, n = ndimage.label(ink, structure=np.ones((3, 3)))
        sizes = ndimage.sum(ink, lab, range(1, n + 1))
        d["largest"] = round(float(sizes.max() / max(sizes.sum(), 1)) * 100, 1)
    except ImportError:
        from lineart_clean import stats
        d["largest"] = stats(p)["largest_share"]
    return d


def check_images(root: Path) -> bool:
    r = Report("② 图（渲染之前）")
    sp = root / "story.json"
    cfg = json.loads(sp.read_text(encoding="utf-8"))
    raw = root / "raw"
    arts = [s for s in cfg["scenes"] if s.get("type", "art") == "art"]
    if not arts:
        r.line("  没有 art 格（全片都是信息图）")
        return r.dump()

    gen = {}
    gj = raw / ".gen.json"
    if gj.exists():
        try:
            gen = json.loads(gj.read_text(encoding="utf-8")).get("prompts", {})
        except json.JSONDecodeError:
            pass

    stale = []
    r.line(f"\n  {'格':<4}{'文件':<14}{'尺寸':>10}{'墨%':>7}{'最大块':>8}{'中灰':>7}")
    for sc in arts:
        sid, src = sc["id"], (sc.get("src") or f"{sc['id']}.png").replace("\\", "/")
        if src.startswith("raw/"):
            src = src[4:]
        p = raw / src
        if not p.exists():
            r.fail(f"{sid}: 缺图 raw/{src} —— 这一格渲不出来")
            r.line(f"  {sid:<4}{src:<14}{'—':>10}")
            continue

        m = _measure(p)
        if sid in gen and gen[sid] != SU.prompt_hash(sc, cfg):
            stale.append(sid)

        bad = None
        if m["ink_pct"] < INK_BLANK:
            bad = "几乎空白"
        elif m["ink_pct"] > INK_DARK:
            bad = "整片涂黑"

        r.line(f"  {sid:<4}{src:<14}{m['w']}x{m['h']:<6}{m['ink_pct']:>7.1f}"
               f"{m['largest']:>7.1f}%{m['gray_pct']:>6.1f}%"
               f"{'   ✗ ' + bad if bad else '   ✓'}")
        if bad:
            r.fail(f"{sid}: {bad} —— 渲出来是废片，需要重出这一张")

    if stale:
        r.line(f"\n  {', '.join(stale)} 的 prompt 在出图后改过，raw/ 里还是旧图")
        r.line("  要么按新 prompt 重出，要么把 prompt 改回去")
    return r.dump()


# ────────────────────────── ③ 渲染参数（永远放行） ──────────────────────────
def check_render(root: Path) -> bool:
    """只查「参数写错了」这一类事实问题。**永远放行。**

    渲染节奏是参数问题，修法在 plan.json，永远不在图。
    上一版拿「面积 t95 < 55%」判「画太快」，实测 34 格已出片的片子里
    t95 在 37%~76% 之间乱跳、全部正常，那条判定只会逼人去重出好图。
    """
    r = Report("③ 渲染参数（不拦，只报事实）")
    import io
    from contextlib import redirect_stdout
    import ink_probe

    cued = ink_probe.cued_scenes(root / "plan.json")
    if cued:
        r.line(f"  plan.json 里这几格带 start/end 的 regions：{', '.join(cued)}")
        r.line("  这会让引擎按窗口卡时间，几秒画完就静止。")
        r.line("  处置：删掉这几格的 regions，重跑渲染（几十秒）。**不要重出图。**")
    else:
        r.ok("plan.json 没有手写 regions")

    parts = sorted((root / "out" / "lineart_parts").glob("*.mp4"))
    if parts:
        r.line("")
        for p in parts:
            buf = io.StringIO()
            try:
                with redirect_stdout(buf):
                    ink_probe.probe(p, 0.25, p.stem)
                r.line(buf.getvalue().rstrip("\n"))
            except Exception as e:  # noqa: BLE001
                r.line(f"  {p.stem:<6} 量不了（{e}）")
    r.dump()
    return True          # 有意不看 dump 的结果：这道不阻断


# ────────────────────────── 入口 ──────────────────────────
def main():
    ap = argparse.ArgumentParser(description="预检：只查跑不跑得起来，不判好不好")
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--stage", default="all",
                    choices=["script", "image", "render", "all"])
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    root = Path(args.project).resolve()
    stages = ["script", "image", "render"] if args.stage == "all" else [args.stage]
    results = {}
    for s in stages:
        fn = {"script": check_script, "image": check_images, "render": check_render}[s]
        try:
            results[s] = fn(root)
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"\n══ {s} ══\n  ✗ 检查本身崩了：{type(e).__name__}: {e}")
            results[s] = False

    if not all(results.values()):
        bad = [k for k, v in results.items() if not v]
        sys.exit(f"\n跑不起来：{', '.join(bad)}")


if __name__ == "__main__":
    main()
