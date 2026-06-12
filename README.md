# Feishu Whiteboard HAR

从飞书/Lark 页面的 HAR 抓包文件中提取白板/思维导图，渲染为可编辑的 SVG 预览 — 全程离线，不调用飞书接口。

[English](#english)

## 功能

1. 解析 Chrome 导出的 HAR 文件（来自飞书文档/知识库/白板页面）
2. 提取所有 `/space/api/whiteboard/block` 响应和 `cdp-whiteboard` 源图
3. 将每个白板 block 渲染为 `.simple.svg`，支持节点、连接线、表格、思维导图分支、便签和常见流程图形状
4. 输出 `summary.json` 和 `index.md` 供快速查阅

## 环境要求

- Python 3.10+
- 无第三方依赖，仅使用标准库

## 使用方法

```bash
python3 scripts/process_har.py <HAR文件路径> --out <输出目录>
```

### 参数说明

| 参数 | 说明 |
|---|---|
| `--out DIR` | 输出目录（默认：`./output`） |
| `--extract-related-images` | 同时提取飞书文档封面图等页面图片 |
| `--audit-package PATH` | 输出精简 JSON 审核包，供模型或 reviewer 审查 |
| `--margin N` | SVG 画布边距，单位 px（默认：160） |
| `--fit-text` | 缩小文字以适应节点框（有损） |
| `--no-square` | 不强制输出正方形比例的 SVG |

### 输出文件

```
output/
  summary.json                  # 白板数量、节点数、bbox、样本文本
  index.md                      # 可读索引
  whiteboard-01.simple.svg      # 渲染的 SVG 预览
  whiteboard-01.source.png      # 从 HAR 中提取的飞书原图
  ...
```

## 如何抓取 HAR

1. 用 Chrome 打开飞书白板页面
2. 打开开发者工具（`Cmd+Option+I`）→ 切到 **Network** 面板
3. 清空已有请求，然后刷新页面
4. 等白板加载完成（内容较多时可以拖动/缩放一次，触发懒加载）
5. 点击 **Export HAR…**（不要右键单个请求导出，要导出完整 Network 记录）
6. 保存 `.har` 文件，传给脚本处理

## Agent 集成

本项目可作为 coding agent 的 skill 使用。将本目录放到 agent 的 skills 目录下，然后对 agent 说：

```
用 lark-whiteboard-renderer 处理这个 HAR：/path/to/file.har，生成 SVG 给我看。
```

详见 `SKILL.md`。

## 已知限制

- SVG 是对飞书原生渲染的近似还原，不是飞书官方渲染器
- 字体精确宽度受本机 SVG 渲染器和安装字体影响
- 左侧思维导图分支、缺失表格 metadata、connector 起点箭头已有代码支持，但仍需更多真实 HAR 样本回归测试

## 隐私提醒

HAR 文件可能包含页面 URL、请求头、响应体和认证 cookie。只将 HAR 分享给有权查看对应飞书页面的人或工具。

## License

MIT

---

<details>
<summary><h2>English</h2></summary>

Extract whiteboard / mind-map assets from a Feishu (Lark) HAR capture and render simplified SVG previews — entirely offline, no Feishu API calls.

### What It Does

1. Parses a Chrome HAR file exported from a Feishu doc / wiki / whiteboard page
2. Extracts every `/space/api/whiteboard/block` response and `cdp-whiteboard` source image
3. Renders each whiteboard block as an editable `.simple.svg` with nodes, connectors, tables, mind-map branches, sticky notes, and common flowchart shapes
4. Outputs a `summary.json` and `index.md` for quick review

### Requirements

- Python 3.10+
- No third-party dependencies — stdlib only

### Usage

```bash
python3 scripts/process_har.py <path-to-har> --out <output-dir>
```

#### Options

| Flag | Description |
|---|---|
| `--out DIR` | Output directory (default: `./output`) |
| `--extract-related-images` | Also extract Feishu doc cover images and other page images |
| `--audit-package PATH` | Write a compact JSON package for model / reviewer audit |
| `--margin N` | SVG canvas margin in px (default: 160) |
| `--fit-text` | Shrink text to fit inside node boxes (lossy) |
| `--no-square` | Don't force square aspect ratio on output SVG |

#### Output

```
output/
  summary.json                  # counts, bbox, sample text
  index.md                      # human-readable index
  whiteboard-01.simple.svg      # rendered SVG preview
  whiteboard-01.source.png      # original image from HAR
  ...
```

### How to Capture a HAR

1. Open the Feishu page in Chrome
2. Open DevTools (`Cmd+Option+I`) → **Network** tab
3. Clear existing requests, then refresh the page
4. Wait until the whiteboard finishes loading (scroll / zoom if content is lazy-loaded)
5. Click **Export HAR…** (do NOT right-click a single request — export the full network log)
6. Save the `.har` file and pass it to the script

### Agent Integration

This project can be used as a skill for coding agents. Drop it into your agent's skills directory and invoke with:

```
Use lark-whiteboard-renderer to extract whiteboards from this HAR and render SVG previews.
```

See `SKILL.md` for the full agent workflow spec.

### Known Limitations

- SVG output is an approximation — not Feishu's native renderer
- Font metrics depend on your local SVG viewer and installed fonts
- Left-side mind-map branches, missing table metadata, and connector start-arrows are supported but need more real-world HAR samples for regression

### Privacy

HAR files may contain page URLs, request headers, response bodies, and authentication cookies. Only share them with people or tools authorized to view the original Feishu page.

</details>
