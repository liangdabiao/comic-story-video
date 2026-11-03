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
