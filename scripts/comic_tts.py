#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""comic_tts —— 第 4 步：按分镜批量配音。

一条片子 7 格，每格一段旁白，各自一个 mp3。时长直接决定整条片子的节奏，
所以这一步必须先把真实时长量出来，后面的画面和字幕都按它对齐。

两个引擎
--------
edge（默认，免费）和 apiz / MiniMax（付费，语气更活）。切换用 story.json：

    "tts": {"engine": "apiz", "model": "speech-2.8-hd",
            "voice": "Chinese (Mandarin)_Unrestrained_Young_Man", "speed": 1.14}

命令行 --engine / --voice / --model / --speed 优先级更高。
**改了引擎或音色，`.sig` 指纹会变，全部自动重配** —— 否则声音还是旧的。

两个坑
------
1. **edge-tts 7.2.8 会被 Edge 拒绝（403）**，7.3.1 起才正常。先看版本号。
   如果是 IP/地区级封锁，任何版本都 403 —— 那时换 apiz，见
   references/apiz-tts-fallback.md。
2. ffprobe 不一定在 PATH 里（很多机器只装了 ffmpeg）。这里走 theme.ffmpeg_path()
   自动补路径，缺 ffprobe 时退回解析 ffmpeg stderr。

用法
----
    python scripts/comic_tts.py <项目目录>
    python scripts/comic_tts.py <项目目录> --voice zh-CN-YunxiNeural --rate +10%
    python scripts/comic_tts.py <项目目录> --engine apiz --voice "Chinese (Mandarin)_Humorous_Elder"
    python scripts/comic_tts.py <项目目录> --force          # 全部重配
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "lib"))
import theme  # noqa: E402

_ff = theme.ffmpeg_path()
if _ff:
    os.environ["PATH"] = str(Path(_ff).parent) + os.pathsep + os.environ.get("PATH", "")

DEFAULT_VOICE = "zh-CN-YunjianNeural"
DEFAULT_RATE = "+14%"
DEFAULT_ENGINE = "edge"
DEFAULT_APIZ_MODEL = "speech-2.8-hd"
MIN_BYTES = 2000


def _ffprobe() -> str:
    cand = Path(_ff).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    return str(cand) if cand.exists() else "ffprobe"


def duration(p: Path) -> float:
    try:
        r = subprocess.run(
            [_ffprobe(), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(p)],
            capture_output=True, text=True)
        v = float(r.stdout.strip())
        if v > 0:
            return v
    except (FileNotFoundError, ValueError):
        pass
    # 兜底：从 ffmpeg 的 stderr 里抠 Duration
    r = subprocess.run([_ff, "-i", str(p)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr)
    if not m:
        raise RuntimeError(f"读不出时长：{p}")
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + s


def rate_to_speed(rate: str) -> float:
    """edge-tts 的 "+14%" → apiz 的 1.14。"""
    m = re.match(r"\s*([+-]?\d+(?:\.\d+)?)\s*%?\s*$", str(rate))
    return 1.0 + float(m.group(1)) / 100 if m else 1.0


async def synth_edge(text: str, out: Path, voice: str, rate: str):
    import edge_tts
    try:
        await edge_tts.Communicate(text, voice=voice, rate=rate).save(str(out))
    except TypeError:  # 老版本签名是位置参数
        await edge_tts.Communicate(text, voice, rate=rate).save(str(out))


def synth_apiz(text: str, out: Path, voice: str, speed: float,
               model: str = DEFAULT_APIZ_MODEL):
    """apiz speak → MiniMax。语气比 edge 活，代价是按量计费。

    必须用 `speak`，不要 `generate --model minimax/t2a` —— 后者是异步任务，
    只回 task_id，拿不到音频。
    """
    cmd = ["apiz", "speak", text, "--model", model, "--voice", voice,
           "--speed", f"{speed:.2f}", "--output-file", str(out), "--json"]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 or not out.exists():
        tail = (r.stderr or r.stdout or "").strip()[-300:]
        if "429" in tail:
            raise RuntimeError("apiz 余额闸门：apiz account balance 看余额（<10 元全局 429）")
        raise RuntimeError(f"apiz 失败：{tail}")


async def synth(text: str, out: Path, voice: str, rate: str,
                engine: str = DEFAULT_ENGINE, model: str = DEFAULT_APIZ_MODEL):
    if engine == "apiz":
        synth_apiz(text, out, voice, rate_to_speed(rate), model)
        return
    await synth_edge(text, out, voice, rate)


def post_speed(path: Path, factor: float):
    """合成后再加速一次（atempo，不变调）。

    MiniMax 的 --speed 在 1.3 以上基本饱和：实测同一句话
    1.0 → 6.34s、1.3 → 5.94s、1.8 → 5.72s，再调也没用。
    它的基准语速又比 edge 慢一档（4.0 字/秒 vs 4.7），
    所以要压到短视频的节奏，只能出音之后再 atempo 一遍。
    """
    if abs(factor - 1.0) < 0.01:
        return
    tmp = path.with_name(path.stem + "_sp.mp3")
    r = subprocess.run([_ff, "-y", "-i", str(path), "-filter:a", f"atempo={factor:.3f}",
                        "-b:a", "128k", str(tmp)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not tmp.exists():
        raise RuntimeError(f"atempo 失败：{r.stderr[-200:]}")
    tmp.replace(path)


def _sig(text: str, voice: str, rate: str, engine: str = DEFAULT_ENGINE,
         model: str = "", post: float = 1.0) -> str:
    """这段配音的指纹：文案 / 引擎 / 音色 / 语速任一变，就必须重配。

    只判断「文件在不在」会静默出错 —— 改完旁白重跑，声音还是旧的，
    字幕却按新文案生成，声画对不上，而且全程不报错。
    """
    raw = f"{text}\n{engine}\n{voice}\n{rate}\n{model}\n{post}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()[:16]


async def main_async(args):
    root = Path(args.project).resolve()
    cfg = json.loads((root / "story.json").read_text(encoding="utf-8"))
    tts = cfg.get("tts") or {}

    engine = args.engine or tts.get("engine") or DEFAULT_ENGINE
    voice = args.voice or tts.get("voice") or cfg.get("voice") or DEFAULT_VOICE
    rate = args.rate or tts.get("rate") or cfg.get("rate") or DEFAULT_RATE
    model = args.model or tts.get("model") or DEFAULT_APIZ_MODEL
    # tts.speed 是 apiz 的原生单位（1.30 = +30%），优先级高于 rate。
    # MiniMax 的基准语速比 edge 慢一档，同一句话要多给 15%~20% 才等长。
    if args.speed:
        rate = f"{(float(args.speed) - 1) * 100:+.0f}%"
    elif tts.get("speed"):
        rate = f"{(float(tts['speed']) - 1) * 100:+.0f}%"
    post = float(args.post_speed or tts.get("post_speed") or 1.0)

    if engine == "apiz":
        r = subprocess.run(["apiz", "--version"], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit("找不到 apiz CLI：见 references/apiz-tts-fallback.md")
        print(f"apiz / MiniMax  model={model}  voice={voice}  "
              f"speed={rate_to_speed(rate):.2f}（rate {rate}）")
    else:
        try:
            import edge_tts
            ver = getattr(edge_tts, "__version__", "?")
            print(f"edge-tts {ver}  voice={voice}  rate={rate}")
        except ImportError:
            raise SystemExit("未安装 edge-tts：pip install -U edge-tts")

    aud = root / "audio"
    aud.mkdir(exist_ok=True)

    total, chars, failed = 0.0, 0, []
    stale = 0
    for sc in cfg["scenes"]:
        out = aud / f"{sc['id']}.mp3"
        sig_file = aud / f"{sc['id']}.sig"
        want = _sig(sc["narration"], voice, rate, engine, model, post)
        have = sig_file.read_text(encoding="utf-8").strip() if sig_file.exists() else ""
        need = (args.force or not out.exists()
                or out.stat().st_size < MIN_BYTES or have != want)
        if need:
            if have and have != want:
                stale += 1
                print(f"  ↻ {sc['id']} 文案/引擎/音色变了，重配")
            try:
                await synth(sc["narration"], out, voice, rate, engine, model)
                post_speed(out, post)
            except Exception as e:  # noqa: BLE001
                msg = f"{type(e).__name__}: {e}"
                failed.append((sc["id"], msg))
                print(f"  ✗ {sc['id']}  {msg[:110]}")
                if "403" in msg or "Handshake" in msg:
                    print("    → edge-tts 被拒。重试无用："
                          "① 先升级 pip install -U edge-tts；"
                          "② 仍 403 就是 IP 级封锁，换 apiz（--engine apiz）")
                continue
            sig_file.write_text(want, encoding="utf-8")

        if out.stat().st_size < MIN_BYTES:
            failed.append((sc["id"], "产物 <2KB，可能是 0 字节分片"))
            continue

        d = duration(out)
        total += d
        chars += len(sc["narration"])
        print(f"  {sc['id']}  {d:5.2f}s  {len(sc['narration']):3d}字  {sc['narration'][:24]}")

    if failed:
        raise SystemExit(f"{len(failed)} 格配音失败，先修好再往下走")

    print(f"\n总时长 {total:.1f}s ／ {chars} 字 ／ {chars / total:.1f} 字每秒")
    if total > 0 and chars / total < 4.0:
        print("⚠️  语速偏慢（<4 字/秒）。短视频节奏建议 +12%~+18%，改 story.json 的 rate")
    elif total > 0 and chars / total > 6.0:
        print("⚠️  语速偏快（>6 字/秒），观众跟不上字幕")


def main():
    ap = argparse.ArgumentParser(description="按分镜批量配音")
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--voice")
    ap.add_argument("--rate")
    ap.add_argument("--engine", choices=["edge", "apiz"])
    ap.add_argument("--model", help="apiz 模型：speech-2.8-hd / 2.8-turbo / 2.6-turbo")
    ap.add_argument("--speed", type=float, help="apiz 语速倍数，1.14 ≈ +14%")
    ap.add_argument("--post-speed", type=float, help="合成后 atempo 再加速，1.15 最常见")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
