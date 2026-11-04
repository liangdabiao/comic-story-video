# 生图后端：apiz flare 与 AGNES

两条实测跑通的命令行出图路线。共同点：都是**图生图**——先把 `assets/reference/01-style-anchor.png`
喂进去当参考图（相似度 low），prompt 用 `comic_gen.py --list` 打印的全文，一张别手抄节选。

## 路线一：apiz / gpt-image-2.5-flare（按量计费的便宜档）

实测 `quality=low + size=1K` 每张 **19 积分**（≈0.19 元），1024×1024。
低分辨率够用：净化落版会做二值化，1K 线稿出来没有损失。

**大坑：CLI 的 `--image-url` 不能用。** 它会映射成 `image_url` 参数，flare 的接口直接
拒收（HTTP 400「不支持的参数」）。参考图要走参数包：

1. 先把锚点图传 CDN 拿 URL：`apiz upload assets/reference/01-style-anchor.png`
2. 生成时参考图塞进 `--params`（CLI 会正确嵌套到请求的 `params` 字段）：

```
apiz generate "<完整prompt>" --model apiz/gpt-image-2.5-flare --aspect-ratio 1:1 \
  --params '{"reference_image_urls":["<锚点URL>"],"quality":"low","size":"1K"}' \
  --wait --json
```

**已验证合法的 params 键**（`ratio`、`image` 系列名字全部非法）：

| 键 | 取值 |
|---|---|
| `reference_image_urls` | URL 数组，最多 16 张 |
| `quality` | low / medium / high / xhigh / max |
| `size` | 1K / 2K / 4K（也可 `width` + `height` 自定义） |
| `aspect_ratio` | 1:1、9:16 等十种比例 |

**免费探测参数名**：params 里塞一个必然非法的键（如 `"zzz":1`），校验失败不会建任务、
不扣费，报错一次只报一个未知参数名——逐轮剔除就能摸清 schema，不用猜。

结果在返回 JSON 的 `result.images[0].url`，下载存进 `raw/<src>`。余额看 `apiz account balance`。

## 路线二：AGNES（免费）

`comic_gen.py --backend agnes` 走 `lib/lib_agnes.py` 直连，出图 **0 元**，2048×2048。
key 用环境变量传（`AGNES_API_KEY`），**不要写进任何文件**。

**大坑：key 分站点，报 401 不一定是 key 坏。**

| base URL | 说明 |
|---|---|
| `api.agnes-ai.cn` | 国内站，lib 默认值 |
| `apihub.agnes-ai.com` | **国际站**，key 从国际站申请就必须指到这里 |
| `api.agnes-ai.com` | 错误网关，别用（报 Resource not found / Login expired） |

站点错了的典型症状：`HTTP 401 无效的令牌`。先验站点再怀疑 key：
`GET {base}/v1/models` 能列出模型（agnes-image-2.1-flash 等）就是有效。

**下载坑（Windows）**：生成成功但产物图（域名 `platform-outputs.agnes-ai.space`）下载报
`WinError 10061 连接拒绝`——是系统代理拒绝了陌生域，curl 反而能下。解法是跑脚本时
加环境变量 `NO_PROXY="*" no_proxy="*"`，不用改库代码。

画风提示：AGNES 出的图带淡彩/灰色调，不是纯黑白线稿；门禁中灰实测 2–17% 都能过，
净化+二值化之后观感正常。上游偶发 503「Service busy」，客户端自带指数退避重试。

## 共同纪律

- **先过门禁再出图**：`pipeline.py <项目> --stage script` 不绿不出图——出图是全链路
  最贵（apiz）或最慢（AGNES）的一步，缺字段会让这格白出。
- **出图前写完全部 prompt**：一张一张看会把节奏拖垮，中途改 prompt 画风会漂。
- **出完只看总览图**：`contact_sheet.py` 拼一张，只判「该在的人在不在、有没有整片涂黑
  或空白」，其余零星瑕疵一律放行。
- **重跑不花钱**：`raw/.gen.json` 记了 prompt 指纹，没改文案的格再跑 `--list` 会自动跳过。
