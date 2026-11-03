<div align="center">

# 漫画面讲故事 · comic-story-video

**把任何选题做成 60–90 秒竖屏漫画短视频：线稿被一笔笔描出来，台词气泡逐个弹入，配音加大字幕。**

图片在讲故事，不是给旁白配插图。

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![Engine](https://img.shields.io/badge/engine-whiteboard--animator%200.1.1-6E4AFF.svg)](https://pypi.org/project/whiteboard-animator/)

</div>

<p align="center">
  <img src="assets/demo/draw-preview.gif" width="320" alt="绘制过程演示：线稿一笔笔描出，气泡随后弹入">
</p>

<p align="center"><sub>↑ 成片里的 9 秒：白板引擎正在逐笔描线，气泡在旁白说到那一句时才弹出</sub></p>

---

## 它解决什么问题

绝大多数 AI 解说视频长这样：一张插画摆在中间，台词全挤在底部字幕条。
观众的眼睛其实一直在读字，图只是背景板。

这套方法把信息搬回画面里——**图是分镜，台词长在画上**：

| | 普通讲解片 | 本 skill |
|---|---|---|
| 图是什么 | 插图 / 背景板 | **分镜**，画面本身就是信息主体 |
| 台词在哪 | 底部字幕条 | **画面内的气泡**，尾巴指向说话的人 |
| 判断标准 | 旁白讲清楚了没 | **关掉声音，还看得懂在吵什么吗** |
| 旁白字数 | 越多越好（填满时间） | 越少越好：`+14%` 语速约 4.7 字/秒 → 65 秒 ≈ 300 字 |
| 冲突怎么来 | 靠文案叙述 | 靠**人物关系**：指、躲、围、瘫 |

一句话：**图不是配图，图是分镜。**

---

## 效果

实测成片《晏子使楚》：**74 秒 / 1080×1920 / 7 格 / 349 字旁白**。

<p align="center">
  <img src="assets/demo/storyboard.png" width="860" alt="七格分镜总览">
</p>

B站效果： https://www.bilibili.com/video/BV1p64M6wE1w/?vd_source=86926e418c83af75f6850b5546388a79


<p align="center"><sub>7 格里 5 个对话格 + 2 个信息图格，交替推进：狗门 → 底牌 → 开嘲 → 战况 → 绑贼 → 反击 → 收尾</sub></p>

<p align="center">
  <img src="assets/demo/hero.png" width="300" alt="对话格：谁在说什么">
</p>

每一格都同时干三件事：**交代发生了什么**（人物动作）、**给出原话**（气泡 ≤8 字）、
**推进一句吐槽**（底部大字幕，与气泡绝不重复）。

整条片子的完整记录——可直接跑的 `story.json`、五张线稿的最终 prompt、两张信息图的代码、
四个坑的处置、抽帧验收数据——都在 [`references/demo-yianzi.md`](references/demo-yianzi.md)。

---

## 三个核心做法

**1. 生成模型只画线稿，一个字都不让它写。**
它写中文必出乱码方块，没有例外。台词、标签、强调圈、红圈全部由代码叠。

**2. 线稿进引擎逐笔描，气泡在合成时弹。**
白板引擎会把彩色区域二值化成黑块，所以气泡不能进引擎。
拆开反而更好：气泡的出场时机变得完全可控——旁白说到哪句，哪句才弹出来。

**3. 连通域决定绘制节奏。**
一张图里 78%~94% 的墨迹是连在一起的，引擎会把它当一整块、3 秒画完，
剩下 7 秒画面不动。解法是把人物按横向三带切成三个绘制区，
引擎于是按 头 → 身 → 脚 的顺序画，绘制过程自然铺满整段旁白。

```
10 秒分镜的绘制进度（三带切分前 / 后）
前： 0.15s 21% → 0.6s 81% → 1.2s 89% → 2.6s 95%   ← 3 秒就画完了
后： 1s 只出轮廓 → 8s 画完                          ← 铺满旁白
```

---

## 快速开始

### 1) 安装

```bash
git clone https://github.com/liangdabiao/comic-story-video.git
cd comic-story-video

bash scripts/setup.sh                                            # macOS / Linux / Git Bash
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1       # Windows
```

setup 会建 `.venv`、装依赖（含白板引擎与约 83MB 的 CRAFT 模型）、探测 ffmpeg 和字体。

### 2) 自检

```bash
python scripts/self_test.py          # 6 项检查，含一次 2 秒真渲染
```

### 3) 起一个项目

```bash
mkdir my-story && cd my-story
cp ../templates/comic/story.example.json story.json
cp ../templates/comic/charts_example.py charts.py
```

### 4) 出图

```bash
python ../scripts/comic_gen.py . --list      # 打印每格完整 prompt
```

把 prompt 贴给任何图生图模型（ImageGen / 即梦 / Midjourney / SD），
**参考图必须传 `assets/reference/01-style-anchor.png`**，相似度调低。
生成的图按 `s1.png`、`s3.png` 命名放进 `raw/`。

### 5) 一条命令出片

```bash
python ../scripts/comic_run.py .
```

产物：`out/final.mp4`（1080×1920，含配音与烧录字幕）。

> 没有配音也能先看画面：`python ../scripts/comic_run.py . --skip tts`。

---

## 流水线

```
选题
 ├ ① 文案      写旁白 + 气泡台词              references/mixi-script.md
 ├ ② 出图      图生图，锚点图当参考            raw/s1.png
 ├ ③ 净化排版  二值化→抹水印→裁白边→三带切分   comic_boards.py
 ├ ④ 配音      edge-tts 逐格出声              audio/s1.mp3
 ├ ⑤ 叠层      透明气泡 + 信息图               comic_layers.py
 ├ ⑥ 渲染      白板引擎逐笔描（最慢）          render_explainer.py
 └ ⑦ 合成      底色 + 线稿 + 气泡 → 字幕 → 竖屏 comic_finish.py
```

| 脚本 | 作用 |
|---|---|
| `scripts/comic_gen.py` | 打印每格完整 prompt（或调 Agnes 后端批量出图） |
| `scripts/comic_boards.py` | 净化、抹水印、统一画布、三带切分、生成 `plan.json` |
| `scripts/comic_tts.py` | 逐格配音，量真实时长，报字/秒；文案变了自动重配 |
| `scripts/comic_layers.py` | 透明气泡层 + 信息图整图 |
| `scripts/render_explainer.py` | 白板引擎渲染（`--only s3` 单格调试） |
| `scripts/comic_finish.py` | 合成、ASS 字幕、竖屏、响度归一 |
| `scripts/comic_run.py` | 一条命令全跑（`--skip` 跳过某几步） |
| `scripts/verify_media.py` | 校验时长 / 分辨率 / 音轨 |

---

## story.json

唯一配置文件。一格一个对象：

```json
{
  "title": "晏子使楚",
  "voice": "zh-CN-YunjianNeural",
  "rate": "+14%",
  "scenes": [
    {
      "id": "s1",
      "type": "art",
      "src": "g1.png",
      "bg": "sky",
      "narration": "晏子要去楚国出差。楚国给他开的门，一米四。这不是门，这是狗洞。",
      "bubbles": [
        { "cx": 470, "cy": 300, "rx": 175, "ry": 92,
          "text": "这也叫门？", "tail": [392, 700], "tail_w": 62, "at": 6.0 }
      ]
    },
    { "id": "s2", "type": "chart", "bg": "cream", "narration": "..." }
  ]
}
```

- `type: art` 线稿格，走白板引擎；`type: chart` 信息图格，走 `charts.py` 的静帧
- `bubbles[].at` 是相对本格开始的秒数 —— **说到哪句，哪句才弹**
- `bubbles[].tail` 是尾巴尖坐标，指向说话的人；`tail_w` 别小于 50，否则像根针
- 字号不用手调：字太宽会自动缩；缺字形会被预检拦下（防方框）

---

## 两类格子

一条片子只由这两种构成，交替出现，**对话格 : 信息图 ≈ 5 : 2**。

<p align="center">
  <img src="assets/reference/02-dialog-panel.png" width="46%" alt="对话格目标样式">
  <img src="assets/reference/03-timeline-info.jpg" width="46%" alt="信息图格目标样式">
</p>

**对话格**（浅蓝底 `#CBE3F5`）—— 解决「谁在说什么」

- 2–5 个角色，**彼此必须有关系**：指着对方、躲开、围住、瘫坐
- 橙色椭圆气泡，尾巴指向说话的人，**台词 ≤8 字**
- 红色手绘圈全格只压一处（一般是不说话那个人的眼睛）
- 底部不加东西 —— 位置留给大字幕

**信息图格**（米黄底 `#FAF2E0`）—— 解决「几回合、怎么收的」

- 标题 64 + 副题 30，3 行主体，每行一个大信息
- 黄色 `①②③` 标签 + 大字狠话 + 红字回击
- 一眼看完，不是「读」。字号下限 26，右侧留 60px

推荐 7 格节奏：

```
1 对话·冲突先行   2 信息图·底牌   3 对话·对手开炮   4 对话·对手加码
5 信息图·战况     6 对话·主角反击  7 对话·收尾加码
```

---

## 文案：贱萌，不是搞笑

决定观众留不留下来的是那句吐槽，不是画。

三条底层（详见 [`references/mixi-script.md`](references/mixi-script.md)）：

- **降格** —— 舌战群儒 →「一个人怼一屋子」
- **拆穿** —— 「你自比管仲乐毅，怎么越跟越惨？」→「**你吹的牛呢？**」
- **自曝** —— 主角必须有毛病，这本身就是把柄

最狠的一条硬规则：**旁白里的台词和气泡里的台词，绝不能是同一句。**
一个在骂，一个在解说。声音一重复，气泡就白做了。

> 唯一允许的重叠：**气泡给原话，旁白给翻译**，且翻译要比原话长一倍以上。
> 气泡「齐国没人了？」，旁白「翻译一下：就派你这么个矮子？」—— 这是递进。
> 旁白「楚王问：齐国没人了吗？」—— 这是原地重复，必须改。

---

## 出图纪律（成败就在这里）

**必须图生图。** 把 [`assets/reference/01-style-anchor.png`](assets/reference/01-style-anchor.png)
当参考图传进去。文生图每次都会漂：线条变粗、加阴影、加灰阶、脸型换一套。

**参考图相似度必须调低（low / 0.3–0.5）。** 这是最反直觉的一条：
相似度 `high` 时模型会**照抄参考图的姿势**，无视你写的动作。
实测同一句「伸食指水平指向右侧」，`high` 两次都出了「举手指天比 V」，`low` 一次就对。

**prompt 三段结构**，风格前缀逐字照抄（`scripts/comic_gen.py` 里的 `STYLE`）：

```
[风格前缀] + 内容：<谁>+<什么表情>+<什么动作，朝哪>+<在哪> + [尾部约束]
```

尾部两句一个字别省：

> 画面上方留出大片纯空白（留给对话气泡）。
> 绝对不要画任何文字、气泡、标题、对话框、边框、水印。

**体型差必须写成硬指标。** 想让角色显矮，别写「矮个子」——模型会给你一个正常身高的成年人，
梗当场就没了。要写「头顶只到旁边那人胸口」这种**可比较的参照**，末尾再加「体型差非常明显」。

**返工率要有预期**：单角色格基本一次过，多角色格（3 人以上、要指定谁指谁）
实际两三成要重出。重出单格成本极低，别整批重来。

---

## 常见故障

不报错但画面是错的那种，最难查。这些是实测踩出来的：

| 症状 | 真因 | 处置 |
|---|---|---|
| 分镜 3 秒画完，后面不动 | 连通域太大 | 三带切分（默认开）；`comic_boards.py --check` 确认 |
| 背景是荧光绿 | `blend=all_mode=multiply` 在 YUV 空间算 | 改 `colorkey` + `overlay`（脚本已内置） |
| 信息图一直轻微晃动 | `zoompan` 缓推的取整抖动 | 已删 zoompan，改静止 + 0.35s 淡入 |
| 字幕飞出画面 | SRT + `force_style` 交给 libass | 手写 ASS，声明 `PlayResX/Y` |
| 气泡里出方框 | 字体缺字形（`→`『』等） | `missing_glyphs()` 预检；符号改中文词 |
| 改了旁白，声音还是旧的 | 缓存只认「文件在不在」 | 已修：按文案+音色+语速取指纹 |
| 合并报「分拍合计 ≠ 成片时长」 | 分拍缓存是旧音频渲的 | 已修：比对时长，超 0.15s 自动重渲 |
| 模型照抄参考图姿势 | 相似度太高 | 调 low + 加「不要举手」负向词 |
| 所有人一样高 | 「矮个子」是无效描述 | 改「只到旁边那人胸口」+「体型差非常明显」 |
| 图右下角「AI生成」 | 生成模型水印 | `--watermark br` 抹掉（默认开） |
| 气泡压着脸 | 出图没留顶部空白 | prompt 加「上方留大片纯空白」 |
| 配音 403 | edge-tts 被 IP 级封锁 | 升到 ≥7.3；仍 403 换 apiz，见 `references/apiz-tts-fallback.md` |
| 渲染 `ArrayMemoryError` | 内存不足（1080 画布需 ≥3GB） | 关掉别的程序，或临时降宽 |
| 空镜像卡住 | 信息图是静帧 | `pad` 加 1–3 秒；要动就拆层逐行淡入，别加 zoompan |

---

## 验收：抽帧，别靠感觉

```bash
python scripts/verify_media.py --file out/final.mp4 --expect 74.3
ffmpeg -y -ss 3 -i out/final.mp4 -vframes 1 check/03.png
ffmpeg -i out/final.mp4 -af volumedetect -f null -     # mean_volume 应在 -20 ~ -14 dB
```

四件事只有肉眼能发现：

1. **绘制是否铺开** —— 第 1 秒应该只出轮廓，不该已经画完
2. **气泡是否逐个弹出** —— 3 秒前不该有气泡
3. **底色是否正确** —— 浅蓝 / 米黄，不是绿、不是白
4. **字幕是否出画** —— 字号、位置、有没有被裁

**及格线**：关掉声音，每格都看得懂在干什么；每格都有一个人在说话 / 动作 / 躲；
旁白里有一句让人想复述的吐槽；最后一格推翻了前面某句正经话。

**不及格**：图是并排站着的肖像、台词全在字幕条里、旁白在念名词定义、结尾收在总结上。

---

## 项目结构

```
comic-story-video/
├── SKILL.md                   skill 主文档（agent 读这个）
├── README.md
├── scripts/
│   ├── comic_gen.py           出图 prompt / 批量出图
│   ├── comic_boards.py        净化 + 三带切分
│   ├── comic_tts.py           逐格配音
│   ├── comic_layers.py        气泡层 + 信息图
│   ├── comic_finish.py        合成 + 字幕 + 竖屏
│   ├── comic_run.py           一条命令全跑
│   ├── render_explainer.py    白板引擎渲染器
│   ├── self_test.py           环境自检
│   ├── verify_media.py        产物校验
│   └── setup.sh / setup.ps1
├── lib/
│   ├── comic_layer.py         叙事层：气泡 / 标签 / 红圈 / 手写注 / 箭头
│   ├── lineart_clean.py       线稿净化 + 连通域体检
│   ├── theme.py               ffmpeg 定位
│   └── lib_agnes.py           可选：Agnes 图生图后端
├── assets/
│   ├── fonts/                 手写体（马善政楷书，OFL）
│   ├── reference/             风格锚点 + 两类格子范例
│   └── demo/                  README 用的演示截图与 GIF
├── templates/comic/           story.json 与 charts.py 模板
├── references/
│   ├── demo-yianzi.md         完整案例：晏子使楚 74 秒全流程
│   ├── comic-story.md         完整制作手册（唯一真相）
│   ├── mixi-script.md         文案方法：降格 / 拆穿 / 自曝
│   ├── prompt-recipes.md      出图 prompt 库
│   └── apiz-tts-fallback.md   edge-tts 403 替代方案
└── vendor/ATTRIBUTION.md      第三方组件归属
```

---

## 依赖

| 依赖 | 必须？ | 说明 |
|---|---|---|
| Python 3.10+ | 必须 | |
| `whiteboard-animator==0.1.1` | 必须 | 白板引擎（PyPI），自带 83MB CRAFT 模型 |
| `ffmpeg`（含 libx264） | 必须 | 合成、竖屏、字幕 |
| `edge-tts>=7.3` | 建议 | 免费配音；7.2.x 会被 Edge 拒绝（403） |
| `fonttools` | 建议 | 字形预检（防气泡里出方框） |
| 图生图模型 | 必须 | ImageGen / 即梦 / Midjourney / SD 均可 |
| `AGNES_API_KEY` | 可选 | 想让脚本自己批量出图时才需要 |

`ffprobe` 可选，缺了会自动退回 `ffmpeg` 解析时长。
引擎与 CRAFT 模型不随本仓库分发，由 setup 从 PyPI 拉取，归属见 [`vendor/ATTRIBUTION.md`](vendor/ATTRIBUTION.md)。

---

## 已知限制

- **多角色格返工率两三成**：prompt 对「谁指谁」这类空间关系的控制力有限。
- **角色不做统一**：每格可以是不同的人，靠风格锚点保持画风一致。
  要固定同一张脸，得把上一格当参考链式传下去。
- **信息图要写代码**：每期内容不同，不适合做成配置。`Comic` 已给齐积木，一张图通常 20 行。
- **1080 画布需 ≥3GB 可用内存**，否则渲染会 `ArrayMemoryError`。
- **节奏偏慢**：74 秒 7 格，一格 9~13 秒。想更快就把信息图格压到 8 秒。

---

## 装进 agent

```bash
# 作为 skill 装到 agent（推荐放项目级：<项目>/.workbuddy/skills/comic-story-video）
git clone https://github.com/liangdabiao/comic-story-video.git \
  .workbuddy/skills/comic-story-video
bash .workbuddy/skills/comic-story-video/scripts/setup.sh
```

装好后按关键词自动激活（「漫画讲故事」「混子哥风格」「图片讲故事」「漫画分镜视频」），
也可手动作业：

> 用 comic-story-video 做一期：晏子使楚

agent 会读 `SKILL.md`，按流水线走完文案 → 出图 → 排版 → 配音 → 渲染 → 合成。

---

## 致谢与 License

- 绘制引擎：[whiteboard-animator](https://github.com/masihsultani/whiteboard-animator)（MIT），文字检测用 [CRAFT-pytorch](https://github.com/clovaai/CRAFT-pytorch)
- 手写字体：马善政楷书（SIL Open Font License，见 `assets/fonts/OFL-MaShanZheng.txt`）
- 叙事与文案方法参考「混子哥」的漫画解说风格，仅供学习研究

https://linux.do 社区支持感谢

本项目：[MIT](LICENSE) © comic-story-video contributors

