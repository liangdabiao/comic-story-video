#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""verify_media —— 产物校验：每个 mp4/mp3 出来都过一遍。

纪律：probe-first → 可解码 → 时长对得上 → 有音轨。
任何一项失败就非零退出，不许静默继续 —— 因为「时长差 3 秒」这种问题
只有在你导出后才发现，那时候已经晚了两小时。

用法：
  python scripts/verify_media.py --file out/final.mp4 --expect 68.8
  python scripts/verify_media.py --manifest manifest.json
  python scripts/verify_media.py --file out/final.mp4 --json

manifest.json: [{"path": "out/final.mp4", "expect": 68.8}, ...]
               expect 可省略（只查可解码）
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

TOL = 0.75  # 时长容差（秒）。重编码 / 关键帧裁剪有固有偏差


def _ff() -> str:
    theme.setup_ffmpeg_env()
    ff = theme.ffmpeg_path()
    if not ff:
        raise SystemExit("找不到 ffmpeg")
    return ff


def _ffprobe() -> str | None:
    cand = Path(_ff()).with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
    return str(cand) if cand.exists() else None


def probe(path: Path) -> dict:
    """返回 {duration, has_audio, width, height}。ffprobe 优先，缺了用 ffmpeg 兜底。"""
    fp = _ffprobe()
    if fp:
        r = subprocess.run([fp, "-v", "error", "-show_entries",
                            "format=duration:stream=codec_type,width,height",
                            "-of", "json", str(path)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode == 0 and r.stdout.strip():
            d = json.loads(r.stdout)
            streams = d.get("streams", [])
            v = next((s for s in streams if s.get("codec_type") == "video"), {})
            return {
                "duration": float(d.get("format", {}).get("duration") or 0),
                "has_audio": any(s.get("codec_type") == "audio" for s in streams),
                "width": v.get("width"),
                "height": v.get("height"),
            }
    # 兜底：解析 ffmpeg -i 的 stderr
    r = subprocess.run([_ff(), "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr)
    if not m:
        raise ValueError("ffmpeg 也读不出时长")
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    vm = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", r.stderr)
    return {
        "duration": h * 3600 + mi * 60 + s,
        "has_audio": "Audio:" in r.stderr,
        "width": int(vm.group(1)) if vm else None,
        "height": int(vm.group(2)) if vm else None,
    }


def decodable(path: Path) -> tuple[bool, str]:
    """真解一遍。文件头对但中间坏掉的情况，只有全文解码才查得出来。"""
    r = subprocess.run([_ff(), "-v", "error", "-i", str(path), "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    err = (r.stderr or "").strip()
    return (r.returncode == 0 and not err), err.splitlines()[-1][:140] if err else ""


def check_one(path: Path, expect: float | None) -> dict:
    out = {"path": str(path), "ok": True, "msg": ""}
    if not path.exists():
        return {**out, "ok": False, "msg": "文件不存在"}

    ok, err = decodable(path)
    if not ok:
        return {**out, "ok": False, "msg": f"无法完整解码：{err}"}

    try:
        info = probe(path)
    except Exception as e:  # noqa: BLE001
        return {**out, "ok": False, "msg": f"探测失败：{e}"}

    d = info["duration"]
    if expect is not None and abs(d - float(expect)) > TOL:
        return {**out, "ok": False, "duration": d, "info": info,
                "msg": f"时长 {d:.2f}s ≠ 期望 {expect:.2f}s（容差 {TOL}s）"}

    if path.suffix.lower() == ".mp4":
        if not info["has_audio"]:
            return {**out, "ok": False, "duration": d, "info": info, "msg": "没有音轨"}
        if not info["width"]:
            return {**out, "ok": False, "duration": d, "info": info, "msg": "没有视频流"}

    return {**out, "duration": round(d, 2), "info": info,
            "msg": f"{d:.2f}s" + (f"  {info['width']}x{info['height']}" if info["width"] else "")}


def main():
    ap = argparse.ArgumentParser(description="产物校验")
    ap.add_argument("--manifest")
    ap.add_argument("--file")
    ap.add_argument("--expect", type=float)
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args()

    items = []
    if args.manifest:
        items += json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if args.file:
        items.append({"path": args.file, "expect": args.expect})
    if not items:
        raise SystemExit("没有待校验的产物（用 --file 或 --manifest）")

    rows = [check_one(Path(it["path"]), it.get("expect")) for it in items]
    failed = [r for r in rows if not r["ok"]]

    if args.json:
        print(json.dumps({"ok": not failed, "rows": rows}, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['path']}  {r['msg']}")
        print(f"verify_media：{len(rows) - len(failed)}/{len(rows)} 通过")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
