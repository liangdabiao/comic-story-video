---
name: comic-story-video
version: 2.1.0
display_name: 漫画面讲故事
display_name_en: Comic Story Video
description_zh: 把选题做成「图片在讲故事」的竖屏短视频——生成式线稿 + 白板引擎逐笔描出 + 代码叠加台词气泡 + 大字幕配音。核心不是画得好看，而是让画面自己承担叙事：角色在吵、在指、在躲，台词长在画面上，关掉声音也能看懂。当用户要做漫画风格解说、历史/知识类短视频、贱萌吐槽向科普，或要求"像混子哥那样讲"、"图片讲故事"、"漫画分镜视频"时使用。
description_en: 'Turns a topic into a vertical "pictures tell the story" short video: generated line art, traced stroke-by-stroke by a whiteboard engine, with speech bubbles, punchlines and burned-in subtitles composited in code. The point is not pretty drawing — it is that the frame itself carries the narrative: characters argue, point, flinch; dialogue lives inside the picture, so it still reads with the sound off. Use for comic-style explainers, history/knowledge shorts, snarky popular-science videos, or when the user asks for "mixige-style", "comic storytelling", or "let the images tell the story".'
description: 把选题做成「图片在讲故事」的竖屏短视频——生成式线稿 + 白板引擎逐笔描出 + 代码叠加台词气泡 + 大字幕配音。核心不是画得好看，而是让画面自己承担叙事：角色在吵、在指、在躲，台词长在画面上，关掉声音也能看懂。触发词：漫画讲故事、混子哥风格、图片讲故事、漫画分镜视频、贱萌科普、历史短视频、comic storytelling、mixige。
---

# 漫画面讲故事

把选题做成 60–90 秒竖屏短视频：**7 格左右分镜，线稿被一笔笔描出来，气泡逐个弹入，配音加大字幕。**

## 它和普通讲解片的区别（先看这条，别跳过）

| | 普通讲解片 | 这套方法 |
|---|---|---|
| 图是什么 | 插图 / 背景板 | **分镜**，画面的信息量是主体 |
| 台词在哪 | 底部字幕条 | **画面内的气泡**，指着说话的人 |
| 判断标准 | 旁白讲清楚了没 | **关掉声音，还看得懂在吵什么吗** |
| 旁白字数 | 越多越好（填满时间） | 越少越好。+14% 语速约 4.7 字/秒 → 65 秒 ≈ 300 字 |

一句话：**图不是配图，图是分镜。**

## 五条不可动摇的原则

1. **生成模型只画线稿，一个字都不让它写。** 它写中文必出乱码方块，没有例外。
   台词、标签、强调圈全部由代码叠。
2. **气泡不能进引擎。** 引擎会把彩色二值化成黑块。线稿进引擎逐笔描，
   气泡在合成时按时间弹 —— 反而更好，节奏可精确控制。
3. **连通域决定节奏。** 一张图 78%~94% 墨迹连在一起，引擎会 3 秒画完。
   靠横向三带切分让绘制铺满旁白（脚本默认已开）。
4. **文案要贱萌，不是搞笑。** 降格、拆穿、自曝，三条底层见 `references/mixi-script.md`。
5. **每格一张图。** 不要试图一张图讲三个回合，那本来就是三个格子。

## 快速开始

```bash
# 1) 装（建 venv、装引擎、检查 ffmpeg）
bash scripts/setup.sh                    # macOS / Linux / Git Bash
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1   # Windows

# 2) 自检（6 项，含一次 2 秒真渲染）
python scripts/self_test.py

# 3) 出片
python scripts/comic_run.py <项目目录>
```

`comic_run.py` 依次跑：配音 → 气泡/信息图 → 净化排版 → 逐笔渲染 → 合成竖屏。
单步重跑用对应的 `comic_*.py`。

## 五段流水线

| 步 | 命令 | 干什么 | 产物 |
|---|---|---|---|
| ① 文案 | 手写 | 按 `references/mixi-script.md` 写旁白 + 气泡台词 | `story.json` |
| ② 出图 | 交给图生图模型 | 锚点图 + 每格 prompt（`comic_gen.py --list` 打印） | `raw/s1.png` |
| ③ 净化排版 | `comic_boards.py` | 二值化去噪 → 抹水印 → 裁白边 → 统一画布 → 三带切分 | `boards/` + `plan.json` |
| ④ 配音 | `comic_tts.py` | edge-tts 逐格出声，时长决定节奏 | `audio/s1.mp3` |
| ⑤ 叠层 | `comic_layers.py` | 透明气泡层 + 信息图整图 | `bubbles/` `charts/` |
| ⑥ 渲染 | `render_explainer.py` | 白板引擎把线稿一笔笔描出来 | `out/lineart_parts/` |
| ⑦ 合成 | `comic_finish.py` | 底色 + 线稿 + 气泡 → 字幕 → 竖屏 | `out/final.mp4` |

**完整手册（含所有踩坑、参数、配方）：`references/comic-story.md`**
**出图 prompt 库：`references/prompt-recipes.md`**

## 项目目录

```
<项目目录>/
├── story.json      唯一配置：标题、画布、每格文案/气泡/prompt
├── charts.py       信息图格的绘图函数（有 chart 格才需要）
├── raw/            生成模型出的原图 ← 你放进来
├── boards/  bubbles/  charts/  audio/  out/     ← 脚本产出
└── subs.ass
```

从模板起步：

```bash
cp templates/comic/story.example.json <项目目录>/story.json
cp templates/comic/charts_example.py <项目目录>/charts.py
```

## 两类格子

一条片子只由这两种构成，交替出现，**对话格 : 信息图 ≈ 5 : 2**。

**对话格**（浅蓝底 `#CBE3F5`）—— 解决「谁在说什么」

- 2–5 个角色，**彼此必须有关系**：指着对方、躲开、围住、瘫坐
- 橙色椭圆气泡，尾巴指向说话的人，**台词 ≤8 字**
- 红色手绘圈，全格只压一处（一般是不说话那个人的眼睛）
- 底色浅蓝，底部不加东西 —— 位置留给大字幕

**信息图格**（米黄底 `#FAF2E0`）—— 解决「几回合、怎么收的」

- 标题 64 + 副题 30，3 行主体，每行一个大信息
- 黄色 `①②③` 标签 + 大字狠话 + 红字回击
- 一眼看完，不是「读」。字号下限 26，右侧留 60px

推荐 7 格节奏：

```
1 对话·冲突先行   2 信息图·底牌   3 对话·对手开炮   4 对话·对手加码
5 信息图·战况     6 对话·主角反击  7 对话·收尾加码
```

## 出图纪律（成败就在这里）

**必须图生图。** 把 [`assets/reference/01-style-anchor.png`](assets/reference/01-style-anchor.png)
当参考图传给模型。文生图每次都会漂：线条变粗、加阴影、加灰阶、脸型换一套。

**参考图相似度必须调低（low / 0.3–0.5）。** 这是最反直觉的一条：
相似度 `high` 时模型会**照抄参考图的姿势**，无视你写的动作。
实测同一句「伸食指水平指向右侧」，`high` 两次都出了「举手指天比 V」，`low` 一次就对。

**prompt 三段结构**，风格前缀逐字照抄（`scripts/comic_gen.py` 的 `STYLE`）：

```
[风格前缀] + 内容：<谁>+<什么表情>+<什么动作，朝哪>+<在哪> + [尾部约束]
```

尾部两句一个字别省：

> 画面上方留出大片纯空白（留给对话气泡）。
> 绝对不要画任何文字、气泡、标题、对话框、边框、水印。

**返工率要有预期**：单角色格基本一次过，多角色格（3 人以上、要指定谁指谁）
实际两三成要重出。重出单格成本极低，别整批重来。

**角色要开「身份证」，任意两人至少三项不同。** 多角色格最容易出的错不是动作画错，
是**主角和配角长得像同一个人**——观众会把配角认成主角，整段叙事直接崩。
实测：晏子写成「戴矮冠、留短须」，模型给了门卫同款的竖条纹方冠 + 同款大胡子，
出图看上去毫无异常，但成片里就是不折不扣的「两个楚王」。
所以每个角色都写清 **头饰 + 胡须 + 衣服 + 体型** 四件事，并且：
主角用**异类**头饰（软布巾 / 无冠 / 儒巾），方冠冕冠头盔全留给对手和兵；
主角跨格固定同一组合，每格都重写一遍，别写「还是那个人」。
结尾再复述一次对比：「帽子样式和胡须绝对不能一样」。详见 `references/prompt-recipes.md` §2.0。

**体型差必须写成硬指标。** 想让某个角色显矮，别写「矮个子」——模型会给你一个
正常身高的成年人，梗当场就没了。要写「头顶只到旁边那个人胸口」这种**可比较的
参照**，末尾再加一句「两个人的体型差非常明显」。同一个角色在不同格之间身高会飘，
出现这种情况就重出那一格，别指望统一。

## 技术铁律（违反会静默出错，不报错但画面是错的）

| # | 铁律 | 错法 → 症状 |
|---|---|---|
| 1 | 底色用 `colorkey` + `overlay`，**不用** `blend=all_mode=multiply` | multiply 内部按 YUV 算 → 浅蓝 `(202,226,244)` 变成荧光绿 `(89,255,84)` |
| 2 | 信息图**静止 + 淡入**，不加 `zoompan` | 缓推的裁剪窗宽是小数，ffmpeg 每帧取整 → 每两三帧跳 1px，字边一直「呼吸」 |
| 3 | 字幕烧 **ASS 本体**，写明 `PlayResX/Y` | SRT + `force_style` → libass 落 384×288 坐标系，58 号字变几百像素飞出画面 |
| 4 | 气泡尾巴 `tail_w ≥ 50`，气泡压低贴着人 | 尾巴又细又长 → 像帽子尖插了根针 |
| 5 | 出图后必须二值化去噪再进引擎 | 灰阶边缘被骨架化当笔画 → 画出来是墨团 |

## 故障自检

| 症状 | 真因 | 处置 |
|---|---|---|
| 分镜 3 秒画完，后面不动 | 连通域太大 | 三带切分（默认开）；`comic_boards.py --check` 确认 |
| 改了旁白，声音还是旧的 | 缓存只认「文件在不在」 | 已修：`comic_tts.py` 按文案+音色+语速取指纹，自动重配 |
| 换了图（重出某格）但画面没变 | 分拍缓存只比时长 | 已修：`render_explainer.py` 写 `.stamp` 指纹（图内容+音频+画质），变了自动重渲 |
| 主角和配角像同一个人 | 主角戴了配角同款、只是矮一点的冠 | 主角换**异类**头饰（软布巾/无冠）+ 去掉胡须；见 `prompt-recipes.md` §2.0 |
| 合并时报「分拍合计 ≠ 成片时长」 | 分拍缓存是旧音频渲的 | 已修：`render_explainer.py` 比对缓存时长，超 0.15s 自动重渲 |
| 背景荧光绿 | blend 在 YUV 空间算 | 铁律 1 |
| 信息图一直轻微晃动、字边毛刺 | `zoompan` 缓推的取整抖动 | 铁律 2：删 zoompan，改静止 + 0.35s 淡入 |
| 字幕飞出画面 | SRT 交给 libass | 铁律 3 |
| 气泡里出方框 | 字体缺字形（`→`『』等） | `comic_layer.missing_glyphs()` 预检；符号改中文词 |
| 模型照抄参考图姿势 | 相似度太高 | 调 low + 加「不要举手」负向词 |
| 模型给所有人同一身高 | 「矮个子」是无效描述 | 改写成「只到旁边那人胸口」+「体型差非常明显」 |
| 图右下角「AI生成」 | 生成模型水印 | `comic_boards.py --watermark br`（默认开） |
| 气泡压着脸 | 出图没留顶部空白 | prompt 加「上方留大片纯空白」 |
| 配音 403 | edge-tts 被 IP 级封锁 | 升到 ≥7.3；仍 403 换 apiz，见 `references/apiz-tts-fallback.md` |
| 渲染 `ArrayMemoryError` | 内存不足（1080 画布需 ≥3GB 可用） | 关掉别的程序或临时降宽 |
| 空镜像卡住 | 信息图是静帧 | `pad` 加 1–3 秒；加 zoompan 会更糟（见铁律 2），要动就拆层逐行淡入 |
| 时长对不上 | concat 混入坏分片 | 删 `out/segs` 重跑 |

## 实测基准（照着这个校准预期）

拿「晏子使楚」跑通的一条，7 格：

| 指标 | 实测值 |
|---|---|
| 成片 | 74 秒 / 1080×1920 / 6 MB |
| 旁白 | 349 字，4.8 字每秒（`+14%` 语速） |
| 每格时长 | 对话格 9.6–13 秒，信息图格 8.8–10 秒 |
| 出图 | 5 张，返工 4 次（狗门那张出了 3 版） |
| 单步耗时 | 配音 15s / 叠层 5s / 排版 5s / 渲染 20s / 合成 35s |

返工全集中在多人格：**狗门那格三次才把「门比人矮」画对**，楚王那次
把手画成了比 V。这不是运气问题，是 prompt 对体型差和手指的控制力有限，
所以第 3 节那两条硬约束（体型差写参照、手指别指定具体手势）不是建议，是必需。

## 验收：抽帧，别靠感觉

```bash
python scripts/verify_media.py --file out/final.mp4 --expect <秒数>
ffmpeg -y -ss 3 -i out/final.mp4 -vframes 1 check/03.png
ffmpeg -i out/final.mp4 -af volumedetect -f null -     # mean_volume 应在 -20~-14 dB
```

四件事只有肉眼能发现：

1. **绘制是否铺开** —— 第 1 秒应该只出轮廓，不该已经画完
2. **气泡是否逐个弹出** —— 3 秒前不该有气泡
3. **底色是否正确** —— 浅蓝/米黄，不是绿、不是白
4. **字幕是否出画** —— 字号、位置、有没有被裁

## 质量线：什么算及格

- 关掉声音，每格都看得懂在干什么 → **及格**
- 每格都有一个人在说话 / 在动作 / 在躲 → 及格
- 旁白里有一句让人想复述的吐槽 → 及格
- 最后一格推翻了前面某句正经话 → 及格

反过来，出现下面任何一条就是不及格：图是并排站着的肖像、
台词全在字幕条里、旁白在念名词定义、结尾收在总结上。

**最容易犯、也最难自查的一条：气泡和旁白说了同一件事。**
检验办法：把同一格的旁白按句号切开，逐句和气泡对读。只要有一句
读出来跟气泡是同一句话（哪怕换了几个字），就改 —— 观众会先读完
画面再听，声音就白配了。

唯一允许的重叠：**气泡是原话，旁白是翻译**，而且翻译那句要比
气泡长一倍以上。比如气泡「齐国没人了？」，旁白「翻译一下：
就派你这么个矮子？」—— 这是递进。而旁白如果是「楚王问：齐国
没人了吗？」，那就是原地重复。

## 参考文件

| 文件 | 内容 |
|---|---|
| `references/demo-yianzi.md` | **完整案例**：《晏子使楚》74 秒全流程——可直接跑的 story.json、五张线稿的最终 prompt、两张信息图代码、四个坑的处置、抽帧验收记录 |
| `references/comic-story.md` | **完整制作手册**：两类格子配方、连通域原理、三条铁律、踩坑实录、换选题 12 步 |
| `references/mixi-script.md` | 文案方法：降格 / 拆穿 / 自曝，十条硬规则，三组改写示范 |
| `references/prompt-recipes.md` | 出图 prompt 库：六类模板、反向词表、失败模式对照 |
| `references/apiz-tts-fallback.md` | edge-tts 403 时的替代配音方案 |
| `assets/reference/` | 风格锚点图 + 两类格子范例 + 成片分镜总览 |
| `lib/comic_layer.py` | 叙事层：气泡 / 标签 / 红圈 / 手写注 / 箭头 |
| `lib/lineart_clean.py` | 线稿净化 + 连通域体检（`--stats`） |
| `templates/comic/` | `story.json` 与 `charts.py` 模板 |
