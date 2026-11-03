# apiz / MiniMax 配音（不只是 403 的备胎）

> `comic_tts.py` 已内置两个引擎，改 `story.json` 就能切。**MiniMax 语气比 edge 活**
> —— 混子哥那种贱萌吐槽，edge 的播音腔撑不住，所以即使 edge 没被封，也建议用它。
> 本文档同时是 403 的应急方案。

---

## 0. 现在怎么切（推荐路径）

`story.json` 里加一段，什么都不用改：

```json
"tts": {
  "engine": "apiz",
  "model": "speech-2.8-hd",
  "voice": "Chinese (Mandarin)_Unrestrained_Young_Man",
  "speed": 1.30,
  "post_speed": 1.15
}
```

命令行临时覆盖：

```bash
python scripts/comic_tts.py <项目> --engine apiz --voice "..." --speed 1.3 --post-speed 1.15
```

指纹里带了 engine / voice / speed / post_speed，**换引擎或换音色会自动整批重配**，
不会出现「文案改了声音还是旧的」。

### 混子哥向的音色短名单（`apiz voices list --json` 查全量）

| voice_id | 听感 | 适合 |
|---|---|---|
| `Chinese (Mandarin)_Unrestrained_Young_Man` | 不羁青年，有痞气、欠 | **吐槽向首选** |
| `Chinese (Mandarin)_Stubborn_Friend` | 嘴硬竹马 | 抬杠、反问多的稿子 |
| `male-qn-badao` | 霸道青年 | 情绪更冲 |
| `Chinese (Mandarin)_Gentleman` | 温润男声 | 正经科普，不够贱 |
| `Chinese (Mandarin)_Humorous_Elder` | 搞笑大爷 | 老年主角 |

### 两个必须知道的坑

1. **`--speed` 在 1.3 以上就饱和了。** 实测同一句话：1.0 → 6.34s、
   1.3 → 5.94s、1.8 → 5.72s。再往上调没有意义。
2. **MiniMax 的基准语速比 edge 慢一档**（4.0～4.4 字/秒 vs 4.7）。
   光靠 `speed` 压不到短视频的密度，所以有了 `post_speed`：
   合成后用 `ffmpeg -filter:a atempo` 再加速一遍，**不变调**。
   实测 `speed 1.30 + post_speed 1.15` ≈ 4.8 字/秒，正好落在混子哥的节奏上。

`post_speed` 只影响节奏，不影响音色；但**不要再叠加第三次加速**，
2 倍以上 atempo 会出金属味，宁可回去砍文案。

---

## 1. 先确认 edge-tts 真的不能用（只在报 403 时才需要看）

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

## 2. apiz 是什么

**[NEX AI](https://apiz.ai/)** —— 面向 AI agent 的模型网关，图像 / 视频 / 语音都有，
提供 CLI、Python SDK、MCP server。本 skill 只用到**语音合成**。

- key 申请：https://apiz.ai/#/api-keys
- 计费：1 积分 = 0.01 元，按量

| | edge-tts | apiz speak |
|---|---|---|
| 成本 | 免费 | 按量（turbo 档很便宜） |
| 音色 | 少量 | 300+，中文几十种 |
| 语气 | 播音腔，平 | **有起伏，能演** |
| 稳定性 | **经常 403** | 正常 |

---

## 3. 安装与登录

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

## 4. 手工合成（排查用）

```bash
apiz voices list --json          # 看全部音色
apiz speak "要合成的文本" \
  --model speech-2.8-hd \
  --voice "Chinese (Mandarin)_Unrestrained_Young_Man" \
  --speed 1.30 \
  --output-file audio/s1.mp3
```

| 参数 | 说明 |
|---|---|
| `--model` | `speech-2.8-hd` / `2.8-turbo` / `2.6-hd` / `2.6-turbo`。hd 更像人，turbo 更便宜 |
| `--voice` | 省略则自动挑第一个公共音色 |
| `--speed` | 0.5–2.0，**但 1.3 以上饱和**（见上） |
| `--output-file` | 存成 mp3 |

**两个坑：**

1. 用 `apiz speak`，**不要** `apiz generate --model minimax/t2a`。
   后者是异步任务模型，只返回 `task_id`，拿不到音频。
2. 脚本里调用要显式加 `--json`（非 TTY 环境默认才是 json，别赌）。

---

## 5. 排查速查

| 现象 | 原因 | 处理 |
|---|---|---|
| `WSServerHandshakeError 403` | edge-tts 被封 | 换 apiz（本文档第 0 节） |
| 所有模型都 `HTTP 429 余额不足` | 余额 < 10 元触发全局闸门 | `apiz account balance` → 充值 |
| `HTTP 400 Server disconnected` | 单次抖动，偶发 | 直接重跑；连续失败再查网络 |
| `apiz generate` 建了任务但没音频 | 用错子命令 | 必须 `apiz speak --output-file` |
| mp3 是 0 字节 | 合成失败但文件已创建 | `comic_tts.py` 已按 `size < 2KB` 判空重试 |
| `command not found: apiz` | 未装或不在 PATH | 见第 3 节 |
| 速度调了没变化 | `--speed` 已饱和 | 用 `post_speed`（atempo） |
| 音色名写错 | voice_id 拼写不对 | `apiz voices list --json` 查准确 id |
| 语速和原来不一样 | `--speed` 与 `rate` 比例不同 | 1.14 ≈ +14%，1.22 ≈ +22% |

