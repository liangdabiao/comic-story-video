#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""pipeline —— 两道门禁 + 一道复核。每一步都是「机器判」，不靠肉眼、不靠记文档。

    python scripts/pipeline.py <项目目录> --stage script    # 出图之前（会拦）
    python scripts/pipeline.py <项目目录> --stage image     # 净化/配音之前（会拦）
    python scripts/pipeline.py <项目目录> --stage render    # 合成之前（只复核，不拦）
    python scripts/pipeline.py <项目目录> --stage all       # 全查

**前两道不通过就非零退出**，是门禁：没过就别往下走。
第三道只输出信息、永远通过 —— 因为渲染节奏是参数问题，不是图的问题。

为什么要这个文件
----------------
上一版把「先定稿文案再出图」「出图前量连通域」都写进了 SKILL.md 的散文里。
结果实测一条片子：文案改 3 版、出图 10 张只用 6 张、返工两轮、墙钟 46 分钟。
不是文档没写，是**写了也没人拦得住** —— 顺序错了不报错，一路静默通过。

所以判定必须变成代码：能量出来的就给数字和阈值，量不出来的不该写成硬指标。

每一关只拦「会导致返工的结构性问题」，「风格建议」一律只警告不阻断 ——
一条动不动就红的门禁，等于没有门禁。

阈值全部来自实测，没量过的写「仅记录」，不设判定
----------------------------------------------
· 字/秒 4.0（标点算字）：546 字符 / 134.3 秒 = 4.07，取 4.0 偏保守
· 「最大块 > 90% 就重出」**已废除**。量了 6 个已经出片成功的项目，91~96% 的
  五格里有三格节奏正常（惠州 s7 95.0% → 57% 正常、惠州 s4 91.1% → 57% 正常、
  佛印 s8 92.4% → 67% 正常）。单人图的轮廓天然就是一块，这个数判不出来。
  → 只打印数字，**不提示、不判定、不引导去查任何东西**
· 「中灰 > 8% 就重出」**已废除**：通过的 6 张里有 3 张在 8.4~11.3%，
  照这条会白重出三张。同样只记录
· 连通域个数不作质量指标：已通过的图在 252~2222 之间，全属正常
· 「面积 t95 < 55% 就是画太快」**已废除**：34 格已出片的片子 t95 在 37%~76%
  乱跳（大色块填充会让面积提前到 95%，笔其实还在走），照这条会重出一堆
  没问题的图。现在的指标是「活跃占比」，而且**只复核、不阻断**

**别往这里加判定 —— 加一条就多一次返工**
--------------------------------------
这个文件存在的目的是「拦住真会返工的错」，不是「把所有不完美都标红」。
加新判定前先回答：**这条不满足，观众会看不懂故事吗？**

会（可以阻断）：缺图、空白、整片涂黑、缺念白、气泡出画、charts 函数不存在。
不会（只记录，不许阻断）：图上有零星文字/符号、尾巴偏几十像素、身高略飘、
顶部留白少、线条有脏点、灰阶没除干净、气泡字数偏多、念白少了几十字。

上一版把「图上有文字」「气泡尾巴没落在头顶正中央」都写成了重出条件，
实测 5 张完美图里最后一张为了纸牌上的日文白重出一次，气泡坐标反复挪到
看图 token 比出图还贵。**判定越严，浪费越多**，而且严的那几条几乎都不是
用户要求的 —— 是自己加的标准。
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

# ── 阈值（均有实测依据，见文件头）──
TARGET_SEC = (110, 135)      # 成片目标区间
TARGET_CHARS = (int(TARGET_SEC[0] * SU.CHAR_PER_SEC),
                int(TARGET_SEC[1] * SU.CHAR_PER_SEC))   # 440~540
HARD_MAX_CHARS = 570         # 超过就是 140 秒，必超时
SCENE_RANGE = (6, 9)         # 格数跟着故事走，不迁就固定 8 格
BUBBLE_MAX_CHARS = 8
INK_BLANK = 0.8              # 墨迹 <0.8% = 基本空白
INK_DARK = 30.0              # 墨迹 >30% = 整片涂黑（已通过的样本最高 23.7%）
# 「最大块占比」不设阈值。实测单人图天然就是一块（91~96% 的一堆全部正常出片），
# 量它只能得到噪音。数字照打，不出判定、不提示行动 —— 见文件头。

# 听众听不出信息的句式 —— 出现即说明台词被抽走了
DEAD_PHRASES = [
    "回了一句", "说了一句", "说了句", "提了一句", "答了一句", "撂下一句",
    "批了俩字", "批了两个字", "一句话把", "一句话就", "张嘴就来",
    "答得挺客气", "意味深长",
]

# 解说员黑话：从体育直播 / 赌桌 / 财报电话会借来的词。
# **只警告不阻断** —— 题材本身是比赛、辩论、对赌时（晏子使楚、舌战群儒），
# 这些词是真的，不是比喻。脚本判不了题材，所以不下结论，只提醒你别无意识照抄。
JARGON = [
    "第一回合", "第二回合", "第三回合", "回合", "加码", "到顶",
    "摊牌", "底牌", "老底", "摆平", "判词", "翻盘", "这局",
    "记分牌", "报分", "零比", "押注",
]

# 骨架必备的三行：一句话故事 / 开场的问题 / 结尾的答案
# 缺失 = 故事还没成形就动笔，八格写完才发现散，是最贵的那种返工
STORY_KEYS = [
    ("story_line", "一句话故事（谁 / 想干什么 / 卡在哪 / 结果）"),
    ("question",   "开场要砸出来的那个问题"),
    ("answer",     "最后一格给出、能答掉上面那个问题的答案"),
]


class Report:
    def __init__(self, title: str):
        self.title = title
        self.pre: list[str] = []      # 标题之后、判定之前先铺的表
        self.rows: list[tuple[str, str]] = []
        self.fails: list[str] = []
        self.warns: list[str] = []

    def ok(self, msg=""):
        self.rows.append(("✓", msg))

    def warn(self, msg):
        self.rows.append(("⚠", msg))
        self.warns.append(msg)

    def fail(self, msg):
        self.rows.append(("✗", msg))
        self.fails.append(msg)

    def line(self, text: str):
        """整行原样输出（每格一行的表格用）。"""
        self.pre.append(text)

    def dump(self) -> bool:
        print(f"\n══ {self.title} ══", flush=True)
        for p in self.pre:
            print(p)
        for mark, msg in self.rows:
            if mark:
                print(f"  {mark} {msg}")
            else:
                print(msg)
        n_ok = sum(1 for m, _ in self.rows if m == "✓")
        print(f"\n  {n_ok} 项通过 / {len(self.warns)} 项警告 / {len(self.fails)} 项阻断")
        if self.fails:
            print("\n✗ 不通过 —— 先把下面这些改掉，别往下走：")
            for f in self.fails:
                print(f"   · {f}")
        elif self.warns:
            print("\n✓ 通过（有警告，自己判断要不要处理）")
        else:
            print("\n✓ 全部通过")
        return not self.fails


# ────────────────────────── ① 文案 ──────────────────────────
def check_script(root: Path) -> bool:
    r = Report("① 文案（出图之前必须过）")
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

    # 骨架三行 —— 零成本、零误报，拦的是「八格写完才发现散」这种最贵的返工
    r.line("")
    for key, what in STORY_KEYS:
        val = (cfg.get(key) or "").strip()
        if not val:
            r.fail(f"story.json 缺 `{key}` —— {what}。"
                   f"先填这一行再写格子（见 SKILL.md「十条硬规则」第 1 条）")
        elif len(val) < 8:
            r.fail(f"`{key}` 只有 {len(val)} 个字，等于没填：{val!r}")
        else:
            r.line(f"  {key:<11}{val}")

    lo, hi = SCENE_RANGE
    if not (lo <= len(scenes) <= hi):
        r.warn(f"{len(scenes)} 格，推荐 6–9 格（格数跟着故事走，别为凑数拆格子）")

    total_chars, total_est, any_real = 0, 0.0, False
    all_narr = ""
    for sc in scenes:
        sid = sc.get("id", "?")
        kind = sc.get("type", "art")
        narr = sc.get("narration") or ""
        n = SU.narration_chars(narr)
        est = SU.est_seconds(narr)
        total_chars += n
        all_narr += narr

        if not narr.strip():
            r.fail(f"{sid}: 没有 narration（这格没声音，节奏直接塌）")
        elif n < 10:
            r.warn(f"{sid}: 念白只有 {n} 字，撑不起一格")

        bubbles = sc.get("bubbles") or []
        dur = _scene_dur(root, sid, est)
        if dur != est:
            any_real = True
        total_est += dur
        r.line(f"  {sid:<3} {kind:<5} {n:>3}字 {dur:>5.1f}s  泡{len(bubbles)}"
               f"{'' if abs(dur - est) < 0.4 else '  (实测)'}")

        # 气泡：字数、越界、缺字形、at
        W, H = tuple(cfg.get("canvas", (1080, 1200)))
        for i, b in enumerate(bubbles):
            txt = b.get("text") or ""
            tag = f"{sid} 气泡{i}「{txt}」"
            if not txt.strip():
                r.fail(f"{tag}: 空台词")
            if len(txt) > BUBBLE_MAX_CHARS:
                r.warn(f"{tag}: {len(txt)} 字，超过 {BUBBLE_MAX_CHARS} 字上限，观众读不完")
            # 坐标可以不写 —— 缺任意一个就整颗自动排版，所以这里只对「填了」的做体检
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
            if at in (None, "", "auto"):
                pass          # 不写是推荐做法：comic_layers 会按念白反推
            elif float(at) > dur + 0.8:
                # 有音频就用实测时长判，别拿字数估的秒数去卡 —— 估算偏低时
                # 会误报「超时长」，那种假警报比不报还坏
                r.fail(f"{tag}: at={at}s 超出本格时长 {dur:.1f}s（改了文案没重算 at）")
            try:
                from comic_layer import missing_glyphs
                bad = missing_glyphs(txt)
                if bad:
                    r.fail(f"{tag}: 字体缺字形 {bad}")
            except Exception:  # noqa: BLE001
                pass

        # 分格类型
        if kind == "art":
            if not sc.get("src"):
                r.fail(f"{sid}: art 格缺 src")
            p = sc.get("prompt") or ""
            if not p.strip():
                r.fail(f"{sid}: art 格缺 prompt")
            elif len(p) < 40:
                r.warn(f"{sid}: prompt 只有 {len(p)} 字，细节多半不够")
            unk = SU.unknown_placeholders(p, cfg)
            if unk:
                r.fail(f"{sid}: prompt 里的角色 {unk} 没在 characters 里定义")
        elif kind == "chart":
            name = sc.get("chart") or sid
            charts = root / "charts.py"
            if not charts.exists():
                r.fail(f"{sid}: 是信息图格，但项目里没有 charts.py")
            else:
                fn = _chart_registry(charts)
                if fn is None:
                    r.fail(f"{sid}: charts.py 载入失败，信息图会静默跳过")
                elif name not in fn:
                    r.fail(f"{sid}: charts.py 里没有 CHARTS['{name}']（这格会静默消失）")
        else:
            r.fail(f"{sid}: type={kind} 不认识（只能是 art / chart）")

    # 全片
    src = "音频实测" if any_real else "按字数估"
    r.line(f"\n  合计 {total_chars} 字 → {total_est:.0f} 秒（{src}，未计格间停顿）"
           f"  目标 {TARGET_SEC[0]}–{TARGET_SEC[1]}s = {TARGET_CHARS[0]}–{TARGET_CHARS[1]} 字")
    if total_chars > HARD_MAX_CHARS:
        r.fail(f"总字数 {total_chars} > {HARD_MAX_CHARS}，成片必然超过 140 秒。"
               f"现在砍字，别等出完图再砍")
    elif total_est > TARGET_SEC[1]:
        r.warn(f"{total_est:.0f}s，超出 {TARGET_SEC[1]}s"
               f"（成片还要加格间停顿，只会更长）")
    elif total_est < TARGET_SEC[0]:
        r.warn(f"{total_est:.0f}s，不到 {TARGET_SEC[0]}s")

    hits = [(p, all_narr.find(p)) for p in DEAD_PHRASES if p in all_narr]
    for p, off in hits:
        r.warn(f"念白里有「{p}」@ 第 {off} 字 —— 听众只会知道有人说了话，不知道说了什么。"
               f"把原话写进去")

    # 解说员黑话：只提醒，不阻断。题材真是比赛/辩论时，这些词是合法的
    jar = [p for p in JARGON if p in all_narr]
    if jar:
        r.warn(f"念白里有解说员行话 {jar} —— 观众听到的是暗号，不是人话。"
               f"改成人话（「第二回合」→「第二年，他又试了一样」）；"
               f"**除非这题材本身就是比赛/辩论**，那就忽略这条")

    if scenes[-1].get("bg") != "cream":
        r.warn("最后一格 bg 不是 cream —— 建议总结格换米黄，视觉上「落定」")
    if scenes[-1].get("type") == "art" and len(scenes[-1].get("bubbles") or []) > 1:
        r.warn("总结格有多个气泡 —— 一句（最好两个字）比一整段好，它是句号不是对话")

    return r.dump()


def _scene_dur(root: Path, sid: str, est: float) -> float:
    """本格实际时长：有音频就用音频的，没有才用字数估。

    为什么要分两种：文案关在配音之前跑，那时还没有音频；但配音之后再跑一次
    门禁（很常见），拿字数估的秒数去卡 `at` 会误报。
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
        print(f"  ⚠ charts.py 载入失败：{e}")
        reg = None
    _CHART_CACHE[key] = reg
    return reg


# ────────────────────────── ② 图 ──────────────────────────
def _measure(p: Path) -> dict:
    import numpy as np
    from PIL import Image
    a = np.array(Image.open(p).convert("L"))
    ink = a < 128
    tot = int(ink.sum())
    h, w = a.shape
    d = {"w": w, "h": h, "ink_pct": round(tot / a.size * 100, 1),
         "black_pct": round(float((a < 60).mean() * 100), 1),
         "gray_pct": round(float(((a >= 60) & (a <= 200)).mean() * 100), 1),
         "largest": 0.0, "components": 0}
    if tot == 0:
        return d
    try:
        from scipy import ndimage
        lab, n = ndimage.label(ink, structure=np.ones((3, 3)))
        sizes = ndimage.sum(ink, lab, range(1, n + 1))
        d["components"] = int(n)
        d["largest"] = round(float(sizes.max() / max(sizes.sum(), 1)) * 100, 1)
    except ImportError:
        from lineart_clean import stats
        s = stats(p)
        d["components"] = s["components"]
        d["largest"] = s["largest_share"]
    return d


def check_images(root: Path) -> bool:
    r = Report("② 图（净化 / 配音之前必须过）")
    sp = root / "story.json"
    cfg = json.loads(sp.read_text(encoding="utf-8"))
    raw = root / "raw"
    arts = [s for s in cfg["scenes"] if s.get("type", "art") == "art"]
    if not arts:
        r.warn("没有 art 格（全片都是信息图？）")
        return r.dump()

    gen = {}
    gj = raw / ".gen.json"
    if gj.exists():
        try:
            gen = json.loads(gj.read_text(encoding="utf-8")).get("prompts", {})
        except json.JSONDecodeError:
            pass

    stale_prompt = []
    r.line(f"\n  {'格':<4}{'文件':<12}{'尺寸':>10}{'墨%':>7}{'最大块':>8}{'中灰':>7}   判定")
    for sc in arts:
        sid, src = sc["id"], sc.get("src") or f"{sc['id']}.png"
        p = raw / src
        if not p.exists():
            r.fail(f"{sid}: 缺图 raw/{src}")
            r.line(f"  {sid:<4}{src:<12}{'—':>10}")
            continue

        m = _measure(p)
        h = SU.prompt_hash(sc, cfg)
        if sid in gen and gen[sid] != h:
            stale_prompt.append(sid)

        # 只拦「图本身不可用」两类。最大块、中灰一律不进判定 ——
        # 单人图天然就是一块，进判定只会让人去重出没问题的图。
        verdict, bad = "ok", False
        if m["ink_pct"] < INK_BLANK:
            verdict, bad = "几乎空白，重出", True
        elif m["ink_pct"] > INK_DARK:
            verdict, bad = "整片涂黑，重出（prompt 补「不要涂成黑色块」）", True

        r.line(f"  {sid:<4}{src:<12}{m['w']}x{m['h']:<6}{m['ink_pct']:>7.1f}"
               f"{m['largest']:>7.1f}%{m['gray_pct']:>6.1f}%   "
               f"{'✗ ' + verdict if bad else '✓'}")
        if bad:
            r.fail(f"{sid}: {verdict}")

    if stale_prompt:
        r.warn(f"这几格的 prompt 在出图之后改过，raw/ 里还是旧图：{', '.join(stale_prompt)}"
               f" —— 要么按新 prompt 重出，要么把 prompt 改回去")

    # 曾经这里会打印「最大块 >90% 的格」并引导去查节奏。删了。
    # 实测单人图天然就是一块（34 格里 91~96% 的一堆，全部正常出片），
    # 打印出来只会让人以为「这一格可疑」，然后去重出一张没问题的图。
    r.line("\n  注：中灰、最大块、连通域个数都只记录不判定。实测通过的图里"
           "中灰到 11.3%、最大块到 96%、连通域到 2222，都正常出片了。")
    return r.dump()


# ────────────────────────── ③ 节奏（复核，不阻断） ──────────────────────────
def check_render(root: Path) -> bool:
    """量画面活跃度。**这一关永远通过** —— 它只输出信息，不产生返工。

    为什么不再阻断：上一版拿「面积 t95 < 55%」判「画太快」，实测 34 格
    已出片的片子里 t95 在 37%~76% 之间乱跳，全部正常 —— 这条判定会让
    agent 去重出一张完全没问题的图。渲染节奏是**参数问题**，修法在
    plan.json 和 render_explainer，永远不在图。
    """
    r = Report("③ 节奏（复核，不阻断）")
    sys.path.insert(0, str(SKILL_ROOT / "scripts"))
    import io
    from contextlib import redirect_stdout
    import ink_probe

    # 唯一确定性的问题：plan.json 里手写了 regions（带 start/end）。
    # 这个不用量视频，读文件就知道，而且处置明确（删 regions 重渲染）。
    cued = ink_probe.cued_scenes(root / "plan.json")
    if cued:
        r.warn(f"plan.json 里这几格带 start/end 的 regions：{', '.join(cued)}")
        r.line("     这会激活 element_plan，引擎按窗口卡时间，几秒画完就静止。")
        r.line("     处置：删掉这几格的 regions，重跑渲染（几十秒，零成本）。")
        r.line("     **不要重出图** —— 图没问题。")
    else:
        r.ok("plan.json 干净（没有 regions），引擎按面积铺满预算")

    parts = sorted((root / "out" / "lineart_parts").glob("*.mp4"))
    if not parts:
        r.line("\n  还没有 out/lineart_parts/*.mp4，跳过实测")
        r.dump()
        return True

    r.line("")
    for p in parts:
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):      # ink_probe 自己会打印，先收起来
                ink_probe.probe(p, 0.25, p.stem)
            r.line(buf.getvalue().rstrip("\n"))
        except Exception as e:  # noqa: BLE001
            r.line(f"  {p.stem:<6} 量不了（{e}）")

    r.line("\n  注：这些数字没有判定线。34 格已出片的片子活跃 31%~77%、"
           "面积95% 在 37%~76%；人为造的「1.5 秒画完」样本活跃 28%，"
           "和健康下限重叠 —— 分不开，所以不判。")
    r.dump()
    return True          # 有意不看 dump 的结果：这道不阻断


# ────────────────────────── 入口 ──────────────────────────
def main():
    ap = argparse.ArgumentParser(description="两道门禁（文案/图）+ 一道复核（节奏，不拦）")
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
        sys.exit(f"\n门禁未通过：{', '.join(bad)}")
    print(f"\n{len(stages)} 道门禁全部通过 → 可以往下走")


if __name__ == "__main__":
    main()
