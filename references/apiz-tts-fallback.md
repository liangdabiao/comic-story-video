# apiz / MiniMax 配音接入

> **音色怎么定：先看 [`voice-design.md`](voice-design.md)。** 那份是首选方案
> ——单口相声腔，用自然语言生成自定义音色，附已验证的描述原文。本文档只解决
> 「怎么把 apiz 接上」「edge 403 怎么办」。
>
> `comic_tts.py` 已内置两个引擎，改 `story.json` 就能切。edge 的播音腔撑不住
> 单口相声，所以即使 edge 没被封也走 apiz。

---

## 0. 现在怎么切（推荐路径）

`story.json` 里加一段：

```json
"tts": {
  "engine": "apiz",
  "model": "speech-2.8-hd",
  "voice": "xiangsheng01",
  "speed": 1.0
}
```

`voice` 用 `voice-design` 生成的**自定义音色**（单口相声腔），生成方法见
[`voice-design.md`](voice-design.md)。**不要从下面的公共音色里挑**，理由在那一节。

命令行临时覆盖：

```bash
python scripts/comic_tts.py <项目> --engine apiz --voice xiangsheng01 --speed 1.0
```

指纹里带了 engine / voice / speed / post_speed，**换引擎或换音色会自动整批重配**，
不会出现「文案改了声音还是旧的」。

### 公共音色：为什么不推荐

公共池 **303 个**，`tags` 字段全是坏的（`Mature_Woman` 标「中文,男,中年」）。
而且全是通用朗读，没有一个是给曲艺调的。

上一版选了 `Unrestrained_Young_Man`（松、痞、懒），听感是脱口秀冷面——
**跟相声的「脆、亮、冲」正好相反**，方向错了。要临时凑合，这几个还能用：

| voice_id | 听感 |
|---|---|
| `Chinese (Mandarin)_Humorous_Elder` | 老年幽默，最接近单口 |
| `Chinese (Mandarin)_Radio_Host` | 口条利落 |
| `Chinese (Mandarin)_Unrestrained_Young_Man` | 不羁青年，松、痞（**已弃用**）|

### 两个必须知道的坑

1. **`--speed` 在 1.3 以上就饱和了。** 实测同一句话：1.0 → 6.34s、
   1.3 → 5.94s、1.8 → 5.72s。别指望用它把「慢」拉成「相声」。
2. **`post_speed` 不要当默认。** 它是等比压时间，会把气口一起缩短：
   0.3 秒压到 0.2 秒就跨过「0.15 以下算卡顿」的感知线，气口没了，听感从
   「有顿挫」变成「匀速念稿」。新方案 `speed` 固定 1.0、不配 `post_speed`，
   节奏交给文本。时长实在超了才用 —— 而且该回头砍文案，不是加系数。

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
apiz voices list --json          # 看全部音色（含 user_voices 里的自定义音色）
apiz speak "要合成的文本" \
  --model speech-2.8-hd \
  --voice xiangsheng01 \
  --speed 1.0 \
  --output-file audio/s1.mp3
```

| 参数 | 说明 |
|---|---|
| `--model` | `speech-2.8-hd` / `2.8-turbo` / `2.6-hd` / `2.6-turbo`。hd 更像人，turbo 更便宜 |
| `--voice` | 省略则自动挑第一个公共音色 —— **别省**，一定要显式指定 |
| `--speed` | 0.5–2.0，**但 1.3 以上饱和**（见上） |
| `--output-file` | 存成 mp3 |

**两个坑：**

1. `speak` 只有 model / voice / speed / output 四个参数，**没有 emotion**。
   要情绪得走 `generate --model minimax/t2a --params`，再 `apiz tasks get <id>`
   取 `result.audio_url`。详见 `voice-design.md` §5。
   （本文档上一版写着「t2a 只回 task_id，拿不到音频」——**那条是错的**，
   `tasks get` 能取到结果。别再按它走。）
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
| 速度调了没变化 | `--speed` 1.3 以上饱和 | 节奏靠文本，别靠系数；`post_speed` 会丢气口，慎用 |
| 音色听着像播报 | 用了公共音色 | 用 `voice-design` 生成，见 `voice-design.md` |
| 自定义音色消失 | 168 小时未使用被回收 | 重跑 voice-design |
| 音色名写错 | voice_id 拼写不对 | `apiz voices list --json` 查准确 id |
| 语速和原来不一样 | `--speed` 与 `rate` 比例不同 | 1.14 ≈ +14%，1.22 ≈ +22% |

