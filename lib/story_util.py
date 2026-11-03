#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""story_util —— story.json 的共用读数工具。

被 comic_gen / comic_layers / pipeline 共用。放这里是为了避免互相 import
形成环：pipeline 要拿 prompt 指纹来判「图是不是按旧 prompt 出的」，
comic_gen 要拿同一份指纹来上锁，两边必须算得一模一样。

三个容易被写歪的地方
--------------------
1. **字/秒 = 4.0，而且标点算字。** 实测《陈白沙》546 个字符（含标点）/ 134.3 秒
   = 4.07。只数汉字是 463 个 / 134.3 = 3.45 —— 拿 3.45 反算会把 130 秒的片子
   写成 150 秒。所以 `narration_chars` 数的是 `len(text.strip())`，标点全算。
2. **角色描述抽成常量。** 每格 prompt 里重复抄 300 字角色设定，改一次要改八处，
   而且出图时每次都在重传同一段。用 `{名字}` 占位，出图前统一展开。
3. **prompt 指纹必须包含展开后的全文。** 只哈希 `scene["prompt"]` 的话，
   改了 characters 里的描述，指纹不变，图就永远是旧的。
"""

from __future__ import annotations

import hashlib
import re

# ── 风格前缀：实测有效的原文，逐字照抄。改了要重新调阈值 ──
STYLE = (
    "白底黑白线稿的简笔漫画，手绘马克笔风格。纯白背景，只有黑色线条和少量纯黑填色"
    "（眉毛、胡须、眼珠、头发、冠帽），绝对不要灰度、不要阴影、不要排线、"
    "不要纸张纹理、不要彩色。线条干净肯定、带轻微不规则的手绘感。漫画夸张比例，头大身小。"
)

NO_TEXT = "绝对不要画任何文字、气泡、标题、对话框、边框、水印。"
ROOM_TOP = "画面上方留出大片纯空白（留给对话气泡）。"

CHAR_PER_SEC = 4.0          # 反算用，偏保守（实测 4.07）
_PUNCT = re.compile(r"[\s，。、？！；：""''（）—…·「」《》,.!?;:()~～]")


def expand(text: str, cfg: dict) -> str:
    """把 prompt 里的 `{角色名}` 换成顶层 characters 里的描述。

    不认识的占位符原样留着 —— 那是写错了名字，pipeline 会报出来，
    比静默替换成空串安全（空串会出一张没有人的图，还看不出来）。
    """
    chars = cfg.get("characters") or {}
    if not text or not chars:
        return text

    def rep(m):
        k = m.group(1).strip()
        return chars.get(k, m.group(0))

    return re.sub(r"\{([^{}]+)\}", rep, text)


def unknown_placeholders(text: str, cfg: dict) -> list[str]:
    chars = cfg.get("characters") or {}
    return [k.strip() for k in re.findall(r"\{([^{}]+)\}", text or "")
            if k.strip() not in chars]


def full_prompt(scene: dict, cfg: dict) -> str:
    body = expand(scene.get("prompt") or "", cfg)
    parts = [cfg.get("style") or STYLE, "内容：" + body]
    if scene.get("room_top", True):
        parts.append(ROOM_TOP)
    parts.append(NO_TEXT)
    return "\n".join(parts)


def prompt_hash(scene: dict, cfg: dict) -> str:
    """出图用的是「展开后」的全文，指纹也必须按全文算。"""
    return hashlib.md5(full_prompt(scene, cfg).encode("utf-8")).hexdigest()[:12]


def narration_chars(text: str) -> int:
    """念白字数 = 所有字符（标点算）。见文件头第 1 条的实测依据。"""
    return len((text or "").strip())


def pure_chars(text: str) -> int:
    """去掉标点的字数，只用来报「纯字数」，不参与时长换算。"""
    return len(_PUNCT.sub("", text or ""))


def est_seconds(text: str) -> float:
    return round(narration_chars(text) / CHAR_PER_SEC, 1)


def sentences(text: str) -> list[str]:
    """按句末标点切句 —— 与 comic_finish 分配字幕的切法保持一致。"""
    return [x for x in re.split(r"(?<=[。？！；!?;])", text or "") if x.strip()]


def bubble_at(scene: dict, text: str, dur: float, index: int, count: int) -> float:
    """由念白反推气泡的出场时刻，不用听着音频掐。

    字幕是按「分句 + 字数比例」铺的（见 comic_finish.subs），所以气泡时刻
    照同一个刻度算：先做字符级对齐，找出这句台词落在念白的哪个位置。

    为什么不用「找含台词的那一句」这种粗粒度做法 —— 一句可能有二十几个字，
    台词往往在句尾（「…纸条写：买把青菜回来。」），取句首会早四秒。
    实测《陈白沙》七颗气泡，句子级有三颗偏 4~7 秒，字符级压到 1.5 秒内。

    台词和念白完全对不上（改写过、只留了意思）时退回均分 —— 观感差一点，
    但不会弹到格尾去，所以不报警。
    """
    n = scene.get("narration") or ""
    if not n.strip() or dur <= 0:
        return round(max(0.2, dur * 0.25), 1)

    import difflib
    sm = difflib.SequenceMatcher(None, text or "", n)
    blocks = [b for b in sm.get_matching_blocks() if b.size >= 2]

    if blocks:
        # 取最长的那段匹配的**开头** —— 台词一开始念，气泡就该弹。
        # 用中点会晚一秒左右（台词往往有 5~8 个字），实测七颗气泡会齐刷刷晚 1.2 秒。
        main = max(blocks, key=lambda b: b.size)
        at = dur * main.b / len(n) - 0.15
        return round(min(max(0.2, at), dur - 0.4), 1)

    return round(min(max(0.3, dur * (index + 1) / (count + 1)), dur - 0.4), 1)


# ────────────────────────── 气泡自动排版 ──────────────────────────
# 为什么要这个：坐标（cx/cy/rx/ry）以前是必填的，而填准它得看 `boards/` 量头顶，
# 或者更糟——出片后看着不顺眼再挪。每看一次图 1.5~2.5k token，
# 一颗气泡来回三四次就比出图贵了。而差 30~50px 在竖屏成片里看不出来。
#
# 实测参数（《陈白沙》《晏子》的成片值）：7 字 rx≈145、8 字 rx≈205、ry≈92。
# 黑体全角字宽 ≈ 字号，气泡内切宽 = 2*rx*0.82，反推 rx ≈ 25.6×每行字数。
BUBBLE_SIZE = 42
_BUBBLE_LINE_MAX = 8          # 一行最多 8 字，超过就折两行（实测成片是单行 7~8 字）


def auto_bubble(text: str, canvas: tuple[int, int], index: int, count: int,
                tail: tuple[float, float] | None = None) -> dict:
    """不给坐标时按字数排一个「够用」的气泡，返回 cx/cy/rx/ry。

    目标是「不难看」，不是「精确」。气泡会自动缩字号（见 `Comic.bubble`），
    所以 rx 估小了也只是字变小，不会溢出。

    给了 `tail` 就跟着尾巴走：气泡中心对齐尾巴的 x，往上放。
    这是最省事的手写方式 —— 只想让气泡指着某个人时，只写 `tail` 一个坐标就够了。
    """
    W, H = canvas
    n = max(1, len(text or ""))
    lines = 1 if n <= _BUBBLE_LINE_MAX else 2
    per_line = n if lines == 1 else (n + 1) // 2
    per_line = min(per_line, _BUBBLE_LINE_MAX)

    rx = min(W * 0.45, max(110.0, per_line * 23 + 30))
    ry = 88 + (66 if lines > 1 else 0)

    if tail:
        # 气泡跟着尾巴走，但不许贴边（留 24px）
        cx = min(max(float(tail[0]), rx + 24), W - rx - 24)
        # 尾巴在肩膀以上时气泡放上面，否则放下面
        cy = float(tail[1]) - ry - 56
        if cy - ry < 16:
            cy = min(float(tail[1]) + ry + 56, H - ry - 16)
    else:
        cx = W / 2
        # 多颗时从上往下依次排开，互相不压：第一颗在 y≈120，每颗让出 2*ry+18
        cy = min(120 + index * (2 * ry + 18), H * 0.45)

    return {"cx": round(cx, 1), "cy": round(cy, 1), "rx": round(rx, 1), "ry": round(ry, 1)}


def bubble_box(b: dict, canvas: tuple[int, int], index: int, count: int) -> dict:
    """取气泡坐标：四个都填了就用填的，缺任意一个就整颗自动排版。

    不允许「填了两个、剩下两个靠猜」——混着来会排出一个更怪的形状。
    """
    need = ("cx", "cy", "rx", "ry")
    if all(isinstance(b.get(k), (int, float)) for k in need):
        return {k: float(b[k]) for k in need}
    return auto_bubble(b.get("text", ""), canvas, index, count,
                       tail=tuple(b["tail"]) if b.get("tail") else None)
