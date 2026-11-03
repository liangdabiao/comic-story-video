#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""comic_finish —— 第 5 步：合成、字幕、竖屏。

三段：
    compose  线稿动画 × 底色 × 气泡 → 平屏片
    subs     写 ASS 字幕（按分镜时长 + 字数比例分配）
    post     平屏 → 1080×1920 竖屏，烧标题与字幕，响度归一到 -16 LUFS

三条必须遵守的技术铁律（都是实测踩出来的）
------------------------------------------
1. **底色不能用 blend=all_mode=multiply。**
   它即使在 format=rgb24 之后内部仍按 YUV 算，浅蓝 (202,226,244) 会被乘成
   (89,255,84) 荧光绿。改用 colorkey 抠白 + overlay，背景精确还原。

2. **信息图不要加 zoompan 缓推。**
   输入 = 输出分辨率时，裁剪窗宽 1080/zoom 是小数，ffmpeg 每帧取整，
   画面每两三帧横竖各跳 1px，细笔画的字会一直在「呼吸」。
   现在改成静止 + 0.35s 淡入。（反面教材两条：先放大再 zoompan 会裁掉右边缘；
   把 zoom 从 1 以下起也会裁。）

3. **字幕必须烧 ASS 本体，写明 PlayResX/PlayResY。**
   用 subtitles=x.srt:force_style=... 时，libass 会用 384×288 的默认坐标系，
   58 号字被放大成几百像素，直接飞到画面外。

用法
----
    python scripts/comic_finish.py <项目目录>              # 三段全跑
    python scripts/comic_finish.py <项目目录> --only compose
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "lib"))
import theme  # noqa: E402

theme.setup_ffmpeg_env()
FF = theme.ffmpeg_path()


def _ffprobe() -> str:
    cand = Path(FF).with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
    return str(cand) if cand.exists() else "ffprobe"


BG_HEX = {"sky": "0xCBE3F5", "cream": "0xFAF2E0", "mint": "0xDEE6E0", "white": "0xFFFFFF"}
VERTICAL = (1080, 1920)


def run(cmd, quiet=True):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print("\n".join(r.stderr.splitlines()[-12:]))
        raise SystemExit("ffmpeg 失败：" + " ".join(str(c) for c in cmd[:6]) + " ...")
    return r


def dur(p: Path) -> float:
    r = subprocess.run([_ffprobe(), "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(p)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise SystemExit(f"读不出时长：{p}")


# ────────────────────────── compose ──────────────────────────
def seg_art(sc, root: Path, canvas, seg_dir: Path):
    sid = sc["id"]
    src = root / "out" / "lineart_parts" / f"{sid}.mp4"
    if not src.exists():
        raise SystemExit(
            f"缺 {src}\n先跑渲染：\n"
            f"  python scripts/render_explainer.py {root / 'plan.json'} "
            f"--out {root / 'out' / 'lineart.mp4'}"
        )
    d = dur(src)
    W, H = canvas
    bg = BG_HEX.get(sc.get("bg", "sky"), BG_HEX["sky"])
    fade = sc.get("bubble_fade", 0.28)

    args = [FF, "-y", "-i", str(src),
            "-f", "lavfi", "-i", f"color=c={bg}:s={W}x{H}:r=30:d={d}"]
    # 铁律 1：colorkey + overlay，不是 blend=multiply
    fc = ("[0:v]format=rgba,colorkey=0xFFFFFF:0.12:0.04[la];"
          "[1:v][la]overlay=0:0:shortest=1,format=yuv420p[bg]")
    last, idx = "bg", 2

    for i, b in enumerate(sc.get("bubbles") or []):
        args += ["-loop", "1", "-i", str(root / "bubbles" / f"{sid}_{i}.png")]
        at = float(b.get("at", 0))
        fc += (f";[{idx}:v]format=rgba,fade=t=in:st={at}:d={fade}:alpha=1[bb{i}]")
        fc += f";[{last}][bb{i}]overlay=0:0:enable='gte(t,{at})'[v{i}]"
        last, idx = f"v{i}", idx + 1

    args += ["-filter_complex", fc, "-map", f"[{last}]", "-map", "0:a",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
             "-t", f"{d:.3f}", str(seg_dir / f"{sid}.mp4")]
    run(args)
    return d


def seg_chart(sc, root: Path, canvas, seg_dir: Path):
    sid = sc["id"]
    img = root / "charts" / f"{sid}.png"
    audio = root / "audio" / f"{sid}.mp3"
    if not img.exists():
        raise SystemExit(f"缺 {img}（先跑 comic_layers.py）")
    ad = dur(audio)
    d = ad + sc.get("pad", 0.8)
    W, H = canvas

    # 信息图是给人读的，读的时候画面不该动 —— 原来挂的 zoompan 缓推已经删掉。
    # 那个抖动的成因：输入=输出分辨率时，裁剪窗宽 1080/zoom 是小数
    # （1079.6、1079.2…），ffmpeg 每帧取整，等于每两三帧横竖各跳 1px；
    # 再叠上 yuv420p 每帧色度抽样错位，细笔画的字边就一直在「呼吸」。
    # 真要动，正解是让信息图逐行淡入（见 references/production.md 第六节），
    # 而不是给一整张静态图加缓推。
    vf = "fade=t=in:st=0:d=0.35,format=yuv420p"

    run([FF, "-y", "-loop", "1", "-framerate", "30", "-i", str(img), "-i", str(audio),
         "-vf", vf, "-af", f"apad=pad_dur={d - ad:.3f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
         "-t", f"{d:.3f}", str(seg_dir / f"{sid}.mp4")])
    return d


def compose(cfg, root: Path):
    canvas = tuple(cfg.get("canvas", (1080, 1200)))
    seg_dir = root / "out" / "segs"
    seg_dir.mkdir(parents=True, exist_ok=True)
    total = 0.0
    for sc in cfg["scenes"]:
        d = seg_art(sc, root, canvas, seg_dir) if sc.get("type") == "art" \
            else seg_chart(sc, root, canvas, seg_dir)
        total += d
        print(f"  {sc['id']}  {sc.get('type', 'art'):5s}  {d:6.2f}s")

    lst = root / "out" / "segs.txt"
    lst.write_text("".join(
        f"file '{(seg_dir / (sc['id'] + '.mp4')).as_posix()}'\n" for sc in cfg["scenes"]),
        encoding="utf-8")
    flat = root / "out" / "story_flat.mp4"
    run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(flat)])
    got = dur(flat)
    print(f"平屏成片 {got:.2f}s（各段合计 {total:.2f}s）→ out/story_flat.mp4")
    if abs(got - total) > 0.75:
        print("⚠️  时长对不上，可能混入了坏分片：删掉 out/segs 重跑")


# ────────────────────────── subs ──────────────────────────
def _ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    return f"{h}:{m:02d}:{sec % 60:05.2f}"


def _split(t: str):
    return [x.strip() for x in re.split(r"(?<=[。？！；])", t) if x.strip()]


def _wrap(text: str, limit: int) -> str:
    """按标点优先折行，兜底硬切，用 ASS 的 \\N 硬换行。

    中文没有词间空格，libass 会整句当一个词 —— WrapStyle: 0 的自动折行
    对中文不生效，句子一长就直接横向溢出画布，两边字被裁掉。
    实测：55 字在 58 号字下 x 从 0 到 1079，左右全被切。
    """
    if limit <= 0 or len(text) <= limit:
        return text
    lines, buf = [], ""
    for ch in text:
        buf += ch
        if len(buf) >= limit:
            cut = max((buf.rfind(p) for p in "，。：；、！？"), default=-1)
            if cut >= limit // 2:          # 断在标点后，读起来不断气
                lines.append(buf[:cut + 1])
                buf = buf[cut + 1:]
            else:
                lines.append(buf)
                buf = ""
    if buf:
        lines.append(buf)
    return "\\N".join(lines)


ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: {VW}
PlayResY: {VH}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{FONT},{SUB_SIZE},&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,1,0,0,0,100,100,0,0,1,7,0,2,70,70,{SUB_MV},1
Style: Title,{FONT},{TITLE_SIZE},&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,1,0,0,0,100,100,2,0,1,7,0,8,0,0,86,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def subs(cfg, root: Path):
    VW, VH = VERTICAL
    font = cfg.get("sub_font", "Microsoft YaHei")
    sub_size = cfg.get("sub_size", 58)
    margin = 70
    head = ASS_HEAD.format(VW=VW, VH=VH, FONT=font,
                           SUB_SIZE=sub_size,
                           SUB_MV=cfg.get("sub_margin_v", 150),
                           TITLE_SIZE=cfg.get("title_size", 64))
    # 一行装多少字：可用宽 / 单字宽。汉字实际宽约 0.78×字号（标点更窄），
    # 系数取 0.78 是量过 22 字实测版面后回来的经验值。
    wrap_limit = max(8, int((VW - 2 * margin) / (sub_size * 0.78)))

    lines, cursor = [], 0.0
    for sc in cfg["scenes"]:
        d = dur(root / "out" / "segs" / f"{sc['id']}.mp4")
        sents = _split(sc["narration"])
        total_chars = sum(len(s) for s in sents) or 1
        span = d * 0.96          # 尾巴留一点静音，字幕不顶到最后一个字
        t = cursor
        for s in sents:
            seg = span * len(s) / total_chars
            lines.append(f"Dialogue: 0,{_ts(t)},{_ts(min(t + seg - 0.04, cursor + d))},"
                         f"Sub,,0,0,0,,{_wrap(s, wrap_limit)}")
            t += seg
        cursor += d

    title = cfg.get("title", "")
    if title:
        lines.insert(0, f"Dialogue: 0,{_ts(0)},{_ts(cursor)},Title,,0,0,0,,{title}")

    out = root / "subs.ass"
    out.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"subs.ass：{len(lines)} 条 / 总长 {cursor:.1f}s")


# ────────────────────────── post ──────────────────────────
def _filter_path(p: Path) -> str:
    """把路径塞进 ffmpeg 滤镜参数里。

    滤镜语法里 `:` 和 `\\` 是分隔符，Windows 盘符必须转义成 `C\\:/...`，
    整体再用单引号包住 —— 否则 ffmpeg 会把 `C:` 当成选项分隔，报
    "Unable to open subs.ass"。用绝对路径，保证 cwd 变了也能找到。
    """
    s = str(Path(p).resolve()).replace("\\", "/")
    s = s.replace(":", "\\:").replace("'", "'\\''")
    return f"'{s}'"


def post(cfg, root: Path):
    flat = root / "out" / "story_flat.mp4"
    W, H = tuple(cfg.get("canvas", (1080, 1200)))
    VW, VH = VERTICAL
    top = cfg.get("pad_top", round((VH - H) * 0.45))
    name = cfg.get("output", "final.mp4")
    dst = root / "out" / name
    ass = _filter_path(root / "subs.ass")

    vf = f"pad={VW}:{VH}:0:{top}:color=white,subtitles={ass}"
    run([FF, "-y", "-i", str(flat), "-vf", vf,
         "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "160k",
         "-movflags", "+faststart", str(dst)], quiet=False)
    print(f"{dst.name}  {dur(dst):.1f}s  {dst.stat().st_size / 1048576:.1f} MB")


def main():
    ap = argparse.ArgumentParser(description="合成 + 字幕 + 竖屏")
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--only", choices=["compose", "subs", "post"])
    args = ap.parse_args()

    root = Path(args.project).resolve()
    cfg = json.loads((root / "story.json").read_text(encoding="utf-8"))
    steps = [args.only] if args.only else ["compose", "subs", "post"]
    for s in steps:
        print(f"\n── {s} ──")
        {"compose": compose, "subs": subs, "post": post}[s](cfg, root)


if __name__ == "__main__":
    main()
