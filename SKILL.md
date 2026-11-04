---
name: comic-story-video
version: 3.1.0
display_name: 漫画面讲故事
display_name_en: Comic Story Video
description_zh: 把任意选题做成「图片在讲故事」的竖屏短视频——生成式线稿逐笔描出 + 代码叠台词气泡 + 单口配音 + 大字幕。声音是主线：念白本身必须是一条听得懂的故事。适用于漫画风格解说、历史与知识类短视频、贱萌吐槽向科普，或用户要求「像混子哥那样讲」「图片讲故事」「漫画分镜视频」时。
description_en: Turns any topic into a vertical "pictures tell the story" short video — generated line art traced stroke by stroke, speech bubbles composited in code, single-voice narration with burned-in subtitles. Audio leads: the narration alone must be a followable story. Use for comic-style explainers, history/knowledge shorts, snarky pop-science, or requests like "mixige-style", "comic storytelling", "let the images tell the story".
description: 把任意选题做成「图片在讲故事」的竖屏短视频——生成式线稿逐笔描出 + 代码叠台词气泡 + 单口配音 + 大字幕。声音是主线：念白本身必须是一条听得懂的故事。适用于漫画风格解说、历史与知识类短视频、贱萌吐槽向科普，或用户要求「像混子哥那样讲」「图片讲故事」「漫画分镜视频」时。触发词：漫画讲故事、混子哥风格、图片讲故事、漫画分镜视频、贱萌科普、历史短视频、comic storytelling、mixige。
agent_created: true
---

# 漫画面讲故事

把选题做成 110–135 秒竖屏短视频：线稿被一笔笔描出来，台词气泡逐个弹入，单口配音 + 大字幕。
产物 `<项目>/out/final.mp4`（1080×1920）。

**声音是主线。** 把音轨单独抽出来听，必须是一条讲得通的故事；画面负责加戏，不是理解的前提。

---

## 五步做完

### ① 定故事 → `<项目>/story.json`

**先读 `references/example.md`。** 那里面有一版八格念白，还有三句写完就能用的自检。照着那个形状写，比看下面任何一句规则都管用。

建目录、拷模板：

```bash
mkdir -p <项目>/raw && cp templates/comic/story.example.json <项目>/story.json
```

先填文件头三行，**填不出来就别写格子**：

```json
"story_line": "谁 / 想干什么 / 卡在哪 / 结果，一句话说完",
"question":   "开场砸出来的那个问题",
"answer":     "最后一格给出、能答掉它的答案"
```

`question` 要挑「说不通」的点，不要挑「这是什么」。答案不该是一串时间线。

然后写每格的 `narration`（念白）和 `bubbles[].text`（台词）。念白 440–540 字，标点算字，按 4.0 字/秒反算。

```bash
python scripts/pipeline.py <项目> --stage script     # 只查文件齐不齐，不判文案好坏
```

**① 查的是「跑不跑得起来」**：story.json 能读、每格有念白、art 格有 `src` 和 `prompt`、`charts.py` 里有对应函数、气泡不出画。

**文案写成什么样，脚本一律不管** —— 它只会数数，让它判故事，等于让一把尺子判文章。好坏只有一个办法：把八格念白连着读一遍，用 `references/example.md` 末尾那三句话问自己。

### ② 出图 → `<项目>/raw/<id>.png`

**先把所有 prompt 写完，再一次性出图。** 出一张看一张会把出图拖到一两小时，中途改 prompt 还会让画风漂。

```bash
python scripts/comic_gen.py <项目> --list     # 打印没出过的 prompt，出过的自动跳过
```

按打印出来的 prompt 逐张生成，图存进 `raw/`。必须图生图，参考图用 `assets/reference/01-style-anchor.png`，相似度调 low。

```bash
python scripts/contact_sheet.py <项目>        # 拼成一张总览图，看一次
python scripts/pipeline.py <项目> --stage image
```

**② 的判定**：总览图上只看两件事——**该在的人在不在**、**有没有整片涂黑或空白**。
其余（图上零星文字、身高差半个头、线条脏、尾巴偏几十像素）一律不看，直接往下走。

### ③ 制作 → `final.mp4`

```bash
python scripts/comic_run.py <项目>
```

依次跑：配音 → 气泡层 / 信息图 → 净化落版 → 逐笔渲染 → 合成竖屏 → 烧字幕。
单步重跑用对应的 `comic_*.py`。

### ④ 验收

```bash
python scripts/verify_media.py --file <项目>/out/final.mp4 --expect <秒数>
ffmpeg -y -ss 3 -i <项目>/out/final.mp4 -vframes 1 <项目>/check/03.png
```

抽两帧（第 3 秒、该格总长 × 0.75）对比：**画面在动吗、底色对不对、字幕有没有出画**。
再把音轨抽出来闭眼听一遍：能说出「谁想要什么、发生了哪几件事、最后怎么收」就算过。

### ⑤ 交付

`<项目>/out/final.mp4`。需要平屏版时用 `out/story_flat.mp4`。

---

## 十条硬规则

前三条管故事，违反就是「听完不知道在说什么」。后七条管制作，违反就是画面或声音错了。

**1. 先填 `story_line` / `question` / `answer`，填不出来不写格子。**
缺这三行，八格写完才发现散，是最贵的一种返工。这三行是写给你自己看的，不是给脚本看的 —— 脚本只会检查你有没有填。

**2. 骨架按「主角和阻力是什么关系」选，不要给所有选题套同一张格子表。**

| 主角 vs 阻力 | 骨架 |
|---|---|
| 一个具体对手，一来一回 | 出招 → 化解 → 加码 → 化解 → 最狠一招 → 化解 |
| 自己那条路走不通了 | 老本行快死了 → 试了几样都不成 → 意外冒出一件 → 押上去 → 成了 → 才明白卖的是什么 |
| 一个说不通的现象，倒着查 | 反常的事 → 找到那个人 → 他当时的难处 → 他怎么解的 |
| 爬到了顶，被不起眼的东西掀翻 | 巅峰 → 一道裂缝 → 谁都没当真 → 押错 → 塌 |

格数跟着故事走，5–9 格都行。

**3. 并列的事不要编号成回合。**
把「第一回合」换成「第一次」，故事不损失，那就不是回合，是贴上去的标签——删掉。
同理，不要用「加码」「到顶」「摊牌」「老底」这类解说员行话，观众听到的是暗号。

**4. 念白必须是一条听得懂的完整故事，台词要念出来。**
「他回了一句」「批了俩字」「一句话把他点醒」——听众只知道有人说了话，不知道说了什么。
气泡重复念白不算错，字幕本来就是声音的重复。

**5. 生成模型只画线稿，字由代码叠。**
prompt 里写「不要画任何文字」，这是预防，不是出图验收标准。

**6. 气泡不进引擎。** 引擎会把彩色二值化成黑块。气泡在合成时按时间弹，节奏更可控。

**7. 不传 `element_plan`。**
传了每个物体按 1.6 秒上限画完即停，整格两秒就画满。不传时按 √面积分预算，总时长恒等。

**8. 必须图生图，参考图相似度调 low（0.3–0.5）。**
相似度 high 时模型会照抄参考图的姿势，无视你写的动作。

**9. 角色写进 `characters`，prompt 里用 `{名字}` 引用；任意两人至少三项不同。**
头饰、胡须、衣服、体型各写清。主角用异类头饰（软布巾 / 无冠），方冠冕冠头盔留给对手和兵。

**10. 底色用 `colorkey` + `overlay`；字幕烧 ASS 本体并声明 `PlayResX/Y`。**
用 `blend=all_mode=multiply` 底色会变荧光绿；SRT 交给 libass 会落到 384×288 坐标系，字飞出画面。

---

## 遇到问题查哪份

| 情况 | 读 |
|---|---|
| 不知道念白该长什么样，想要一个能照着写的样本 | `references/example.md` |
| 不知道怎么把选题变成故事、每格该放什么、结尾怎么收 | `references/story.md` |
| 写 prompt、定角色、气泡排版、TTS、渲染与合成参数 | `references/production.md` |
| 出图走命令行（apiz flare / AGNES）怎么接、报错查哪 | `references/imagegen-backends.md` |
| 画面 / 声音 / 时长出错了 | `references/troubleshooting.md` |
| 写 prompt 的具体模板和反向约束词 | `references/prompt-recipes.md` |
| 配音音节 / 音色 | `references/voice-design.md` |
| edge-tts 报 403 | `references/apiz-tts-fallback.md` |

## 目录

```
<项目>/
├── story.json      唯一配置：标题、三行故事、每格念白/气泡/prompt
├── charts.py       信息图格的绘图函数（有 chart 格才需要）
├── raw/            生成模型出的原图 ← 你放进来
├── boards/ bubbles/ charts/ audio/ out/    ← 脚本产出
└── subs.ass
```

## 第一次用

```bash
bash scripts/setup.sh                                          # macOS / Linux / Git Bash
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1      # Windows
python scripts/self_test.py                                    # 6 项自检，跑一次就够
```
