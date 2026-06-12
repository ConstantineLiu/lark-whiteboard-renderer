---
name: feishu-whiteboard-har
description: Extract Feishu/Lark whiteboard and mind-map assets from Chrome HAR captures and render simplified SVG previews, fully offline. Use whenever the user provides a .har file from a Feishu/Lark doc, wiki, or whiteboard page, mentions 飞书白板/思维导图/抓包 together with extraction or rendering, asks how many whiteboards or mind maps a capture contains, wants cdp-whiteboard source images pulled out, wants whiteboard/block JSON converted to editable SVG for Markdown or visual review, or asks to refine/compare SVG output against the original whiteboard image. Also use when the user asks how to capture a HAR of a Feishu page in the first place.
---

# Feishu Whiteboard HAR

## Workflow

1. Locate the HAR the user names. Prefer exact filename search:

```bash
rg --files -g '*.har' -g '*.HAR' /path/to/search | rg '<name fragment>'
```

2. Run the bundled script. Do not manually inspect large HAR contents unless the script fails.

```bash
python3 "$CODEX_HOME/skills/feishu-whiteboard-har/scripts/process_har.py" "$HAR" --out "$OUT_DIR"
```

Use this default when the user gives no output preference:

```bash
OUT_DIR="$PWD/output/feishu-whiteboard-har/$(basename "$HAR" .har)"
```

If the user asks for every image from the captured page (not only whiteboard assets), add `--extract-related-images`; images land under `$OUT_DIR/all-images/`.

3. Report only the counts and output paths:

- `whiteboard_blocks` / `cdp_whiteboard_images`
- `index.md`
- generated `whiteboard-XX.simple.svg`
- extracted `whiteboard-XX.source.png`

Keep answers concise; the script already writes `summary.json` and `index.md`.

## Options

- `--margin N` — canvas margin in whiteboard units (default 160)
- `--no-square` — keep natural aspect ratio instead of 2560 square
- `--fit-text` — shrink overflowing text only; use when keeping text inside boxes matters more than original font sizes
- `--audit-package PATH` — compact HAR-derived JSON for model/code review

## Review Package

When asking another model or reviewer to audit this skill against a large HAR, do not give it the full HAR by default:

```bash
python3 "$CODEX_HOME/skills/feishu-whiteboard-har/scripts/process_har.py" "$HAR" --out "$OUT_DIR" --audit-package "$OUT_DIR/audit-package.json"
```

The package contains endpoint counts, node key fields, image metadata, and generated paths; the full HAR path is included as fallback only. Ask reviewers to load the full HAR only when the package is insufficient for a specific finding.

## HAR Capture

When the user needs help creating a HAR, point them to `references/har-capture-tutorial.md`. Short version: open the Feishu page in Chrome, DevTools → Network, refresh, wait for the whiteboard to load, Export HAR (the full log, not a single request).

## PNG-Guided Refinement

Use this when the user says the SVG is visually wrong or asks to refine against the PNG reference.

1. Read `references/renderer-notes.md` first — it documents the color-resolution rules, z-order, anchors, and known limitations.
2. Run the regression tests before touching anything: `python3 -m unittest discover tests`.
3. Use `whiteboard-XX.source.png` as visual ground truth. Render the matching SVG to PNG (prefer headless Chrome at 2560×2560; `qlmanage` distorts long SVGs), crop the same region from both, inspect side by side.
4. Patch only `scripts/process_har.py`. Rendering must stay data-driven: derive colors from palette/sampling, never from node text content.
5. After each change: re-run the script, re-run tests (`tests/regen_golden.sh` only for intended output changes, then eyeball the diff), and re-compare visually.

Tune in this order: viewBox/output size → connectors and arrows → text overflow/line height/markers → colors and border widths.

Keep the final response concrete: say which renderer parameters changed and point to the updated SVG and source PNG.

## Notes

- The script reads local HAR files only; no Feishu calls, no backend traces.
- Truncated/invalid HAR: the script recovers complete `log.entries` before the broken tail and prints a warning — mention it and treat output as best-effort.
- Markdown outputs strip URL query strings: Feishu image URLs embed signed access tokens.
- Prefer source PNG when exact fidelity matters; prefer SVG when editable vector structure matters.
- SVG text uses `foreignObject` — GitHub and some Markdown viewers strip it, leaving shapes without text. View locally in a browser or QuickLook.
