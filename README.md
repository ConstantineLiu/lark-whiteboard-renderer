# Feishu Whiteboard HAR

Extract whiteboard / mind-map assets from a Feishu (Lark) HAR capture and render simplified SVG previews — entirely offline, no Feishu API calls.

[中文说明](#中文说明)

## What It Does

1. Parses a Chrome HAR file exported from a Feishu doc / wiki / whiteboard page
2. Extracts every `/space/api/whiteboard/block` response and `cdp-whiteboard` source image
3. Renders each whiteboard block as an editable `.simple.svg` with nodes, connectors, tables, mind-map branches, sticky notes, and common flowchart shapes
4. Outputs a `summary.json` and `index.md` for quick review

## Requirements

- Python 3.10+
- No third-party dependencies — stdlib only

## Usage

```bash
python3 scripts/process_har.py <path-to-har> --out <output-dir>
```

### Options

| Flag | Description |
|---|---|
| `--out DIR` | Output directory (default: `./output`) |
| `--extract-related-images` | Also extract Feishu doc cover images and other page images |
| `--audit-package PATH` | Write a compact JSON package for model / reviewer audit |
| `--margin N` | SVG canvas margin in px (default: 160) |
| `--fit-text` | Shrink text to fit inside node boxes (lossy) |
| `--no-square` | Don't force square aspect ratio on output SVG |

### Output

```
output/
  summary.json                  # counts, bbox, sample text
  index.md                      # human-readable index
  whiteboard-01.simple.svg      # rendered SVG preview
  whiteboard-01.source.png      # original image from HAR
  ...
```

## How to Capture a HAR

1. Open the Feishu page in Chrome
2. Open DevTools (`Cmd+Option+I`) → **Network** tab
3. Clear existing requests, then refresh the page
4. Wait until the whiteboard finishes loading (scroll / zoom if content is lazy-loaded)
5. Click **Export HAR…** (do NOT right-click a single request — export the full network log)
6. Save the `.har` file and pass it to the script

## Codex / Agent Integration

This project is also an [OpenAI Codex skill](https://openai.com/index/codex/). Drop it into your Codex skills directory and invoke with:

```
Use $feishu-whiteboard-har to extract whiteboards from this HAR and render SVG previews.
```

See `SKILL.md` for the full agent workflow spec.

## Known Limitations

- SVG output is an approximation — not Feishu's native renderer
- Font metrics depend on your local SVG viewer and installed fonts
- Left-side mind-map branches, missing table metadata, and connector start-arrows are supported but need more real-world HAR samples for regression

## Privacy

HAR files may contain page URLs, request headers, response bodies, and authentication cookies. Only share them with people or tools authorized to view the original Feishu page.

## License

MIT

---

## 中文说明

从飞书/Lark 页面的 HAR 抓包文件中提取白板/思维导图，渲染为 SVG 预览 — 全程离线，不调用飞书接口。

### 快速开始

```bash
# 1. 在 Chrome 打开飞书白板页面
# 2. DevTools → Network → 刷新页面 → 等加载完 → Export HAR
# 3. 运行脚本
python3 scripts/process_har.py your-file.har --out output/
```

脚本会输出：
- `whiteboard-XX.simple.svg` — SVG 预览
- `whiteboard-XX.source.png` — HAR 中提取的飞书原图
- `summary.json` / `index.md` — 摘要和索引

### 作为 Codex Skill 使用

把本目录放到 `~/.codex/skills/` 下，然后对 agent 说：

```
用 feishu-whiteboard-har 处理这个 HAR：/path/to/file.har，生成 SVG 给我看。
```

详见 `SKILL.md`。
