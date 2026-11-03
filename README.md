# 漫画面讲故事

把任意选题做成 110–135 秒竖屏漫画短视频：线稿被一笔笔描出来，台词气泡逐个弹入，单口配音 + 大字幕。

产出一条 `out/final.mp4`，1080×1920，可直接发抖音 / 视频号 / 小红书。

![分镜示例](assets/reference/storyboard.png)

示例视频： https://www.bilibili.com/video/BV1wCxm6zE9n/?vd_source=86926e418c83af75f6850b5546388a79

---

## 它和普通讲解片的区别

| | 普通讲解片 | 这套方法 |
|---|---|---|
| 图是什么 | 插图 / 背景板 | **分镜**：人物在指、在躲、在僵住 |
| 台词在哪 | 底部字幕条，声音不念 | **念白念出来，气泡再写一遍**，气泡指着说话的人 |
| 判断标准 | 旁白讲清楚了没 | **只听不看，能讲出整个故事吗** |

一句话：**声音讲事，画面加戏。**

---

## 装环境

需要 Python 3.9+ 和 ffmpeg（含 libx264）。

```bash
bash scripts/setup.sh                                          # macOS / Linux / Git Bash
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1      # Windows
python scripts/self_test.py                                    # 6 项自检，跑一次就够
```

配音默认走 apiz（MiniMax 语音），需要 API key。edge-tts 当兜底。

---

## 跑一条片子

```bash
mkdir -p out/my-story/raw
cp templates/comic/story.example.json out/my-story/story.json

# ① 填 story.json 头三行 + 每格念白（写法见 references/example.md）
python scripts/pipeline.py out/my-story --stage script

# ② 出图：打印 prompt，出完放进 raw/
python scripts/comic_gen.py out/my-story --list
python scripts/contact_sheet.py out/my-story
python scripts/pipeline.py out/my-story --stage image

# ③ 一条命令做完剩下的：配音 + 气泡 + 渲染 + 合成
python scripts/comic_run.py out/my-story
```

产物 `out/my-story/out/final.mp4`。

---

## 目录

```
comic-story-video/
├── SKILL.md                     给 AI 的执行说明（流程 + 十条硬规则）
├── references/
│   ├── example.md               一版合格的八格念白（先看这个）
│   ├── story.md                 怎么把选题变成故事
│   ├── production.md            出图 / 气泡 / 配音 / 渲染 / 合成参数
│   ├── troubleshooting.md       症状 → 真因 → 处置
│   ├── prompt-recipes.md        出图 prompt 模板与反向约束词
│   ├── voice-design.md          音色生成
│   └── apiz-tts-fallback.md     edge-tts 403 时的替代方案
├── scripts/                     全部可执行脚本
├── lib/                         线稿净化、气泡排版、主题
├── templates/comic/             story.json 与 charts.py 模板
└── assets/reference/            风格锚点与范例图
```

---

## 常见问题

**画面两秒就画满了** → `plan.json` 里删掉 `regions`，重跑渲染。不要重出图。

**气泡坐标要对准人** → 默认不用填，自动排版。要指人才写 `tail: [x, y]`。
