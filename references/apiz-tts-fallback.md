# edge-tts 被封时的替代方案：apiz

> 当 `comic_tts.py` 报 `WSServerHandshakeError 403` 时走这一条。
> 实测：本机 edge-tts 被微软全域封锁，apiz 方案 35 段旁白 0 失败。

---

## 0. 先确认 edge-tts 真的不能用

403 是**按 IP/地区长期封锁**，不是偶发抖动，重试没有意义。

```bash
python -c "
import asyncio, edge_tts
asyncio.run(edge_tts.Communicate('测试一句', 'zh-CN-YunjianNeural').save('/tmp/p.mp3'))
"
```

报错长这样就是被封了：

```
WSServerHandshakeError 403, message='Invalid response status',
url='wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1?...'
```

先升版本（`pip install -U edge-tts`，7.2.x 有已知问题），仍 403 就换 apiz。

---

## 1. apiz 是什么

**[NEX AI](https://apiz.ai/)** —— 面向 AI agent 的模型网关，图像 / 视频 / 语音都有，
提供 CLI、Python SDK、MCP server。本 skill 只用到**语音合成**。

- key 申请：https://apiz.ai/#/api-keys
- 计费：1 积分 = 0.01 元，按量

| | edge-tts | apiz speak |
|---|---|---|
| 成本 | 免费 | 按量（turbo 档很便宜） |
| 音色 | 少量 | 300+，中文几十种 |
| 稳定性 | **经常 403** | 正常 |

---

## 2. 安装与登录

```bash
curl -fsSL https://apiz.ai/cli | sh          # macOS / Linux
scoop install apiz                          # Windows
brew install apiz-ai/tap/apiz               # 或 brew

apiz auth login --api-key sk-xxxxxxxx
apiz account balance                        # 余额不足时所有模型一起挂
```

配置优先级：`--api-key` > `APIZ_API_KEY` 环境变量 > `~/.config/apiz/config.toml`。

> ⚠️ **余额闸门**：余额 < 10 元时**所有**模型都返回 `HTTP 429 余额不足`。
> 排查先跑 `apiz account balance`。

---

## 3. 合成

```bash
apiz voices list --json          # 看全部音色
apiz speak "要合成的文本" \
  --model speech-2.6-turbo \
  --voice "Chinese (Mandarin)_Gentleman" \
  --speed 1.14 \
  --output-file audio/s1.mp3
```

| 参数 | 说明 |
|---|---|
| `--model` | `speech-2.8-hd` / `2.8-turbo` / `2.6-hd` / `2.6-turbo`。默认 2.8-hd，最省用 2.6-turbo |
| `--voice` | 省略则自动挑第一个公共音色 |
| `--speed` | 0.5–2.0，**替代 edge-tts 的 `rate="+14%"`**（1.14 ≈ +14%） |
| `--output-file` | 存成 mp3 |

中文讲解常用：

- `Chinese (Mandarin)_Gentleman` —— 温润男声，讲历史/科普
- `Chinese (Mandarin)_Warm_Bestie` —— 温暖女性，长篇不累

**两个坑：**

1. 用 `apiz speak`，**不要** `apiz generate --model minimax/t2a`。
   后者是异步任务模型，只返回 `task_id`，拿不到音频。
2. 脚本里调用要显式加 `--json`（非 TTY 环境默认才是 json，别赌）。

---

## 4. 接回 comic_tts.py

`comic_tts.py` 只有一个合成函数 `synth()`，换掉它就行。
在 `comic_tts.py` 里把 `synth` 替换成下面这个（或用环境变量分流）：

```python
async def synth(text: str, out: Path, voice: str, rate: str):
    """edge-tts 被封时改用 apiz CLI。rate="+14%" → speed≈1.14"""
    import subprocess
    speed = 1.0 + int(rate.strip("%+")) / 100 if rate.startswith(("+", "-")) else 1.0
    voice_map = {
        "zh-CN-YunjianNeural": "Chinese (Mandarin)_Gentleman",
        "zh-CN-YunxiNeural":   "Chinese (Mandarin)_Gentleman",
        "zh-CN-XiaoxiaoNeural": "Chinese (Mandarin)_Warm_Bestie",
    }
    r = subprocess.run([
        "apiz", "speak", text,
        "--model", "speech-2.6-turbo",
        "--voice", voice_map.get(voice, voice),
        "--speed", f"{speed:.2f}",
        "--output-file", str(out),
    ], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"apiz 失败：{(r.stderr or r.stdout)[-300:]}")
```

其余步骤完全不变：

```bash
python scripts/comic_tts.py <项目>        # 现在走 apiz
python scripts/comic_layers.py <项目>
python scripts/comic_boards.py <项目>
python scripts/render_explainer.py plan.json --out out/lineart.mp4
python scripts/comic_finish.py <项目>
```

**不要改 `story.json` 里的 `rate`** —— 上面那行会自动换算成 `--speed`。
文案一个字都别动，换的只是发声引擎。

---

## 5. 排查速查

| 现象 | 原因 | 处理 |
|---|---|---|
| `WSServerHandshakeError 403` | edge-tts 被封 | 换 apiz（本文档） |
| 所有模型都 `HTTP 429 余额不足` | 余额 < 10 元触发全局闸门 | `apiz account balance` → 充值 |
| `apiz generate` 建了任务但没音频 | 用错子命令 | 必须 `apiz speak --output-file` |
| mp3 是 0 字节 | 合成失败但文件已创建 | `comic_tts.py` 已按 `size < 2KB` 判空重试 |
| `command not found: apiz` | 未装或不在 PATH | 见第 2 节 |
| 音色名写错 | voice_id 拼写不对 | `apiz voices list --json` 查准确 id |
| 语速和原来不一样 | `--speed` 与 `rate` 比例不同 | 1.14 ≈ +14%，1.22 ≈ +22% |
