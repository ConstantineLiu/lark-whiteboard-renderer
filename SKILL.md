---
name: feishu-whiteboard-har
description: Extract Feishu/Lark whiteboard mind-map assets from HAR captures and render simplified SVG previews. Use when the user provides a .har file from Feishu docs/wiki/whiteboard and asks how many mind maps/whiteboards it contains, wants cdp-whiteboard images extracted, or wants whiteboard/block JSON converted to SVG for Markdown or visual review.
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

If the user asks for every image from the captured page, not only whiteboard assets, add:

```bash
--extract-related-images
```

This writes `cdp-whiteboard` images and Feishu doc cover images under `$OUT_DIR/all-images/`.

Use this default when the user gives no output preference:

```bash
OUT_DIR="$PWD/output/feishu-whiteboard-har/$(basename "$HAR" .har)"
```

3. Report only the counts and output paths:

- `whiteboard_blocks`
- `cdp_whiteboard_images`
- `index.md`
- generated `whiteboard-XX.simple.svg`
- extracted `whiteboard-XX.source.png`

## Review Package

When asking another model or reviewer to audit this skill against a large HAR, do not give it the full HAR by default. Generate a compact script-derived package:

```bash
python3 "$CODEX_HOME/skills/feishu-whiteboard-har/scripts/process_har.py" "$HAR" --out "$OUT_DIR" --audit-package "$OUT_DIR/audit-package.json"
```

The audit package is produced by `process_har.py`, not selected by the model. It includes relevant endpoint counts, `whiteboard/block` node key fields, `cdp-whiteboard` image metadata, table/mind-map/connector summaries, current mind-map anchor math, generated output paths, and the full HAR path as fallback only. Ask reviewers to load the full HAR only when the package is insufficient for a specific finding.

## HAR Capture

When the user needs help creating a HAR, point them to `references/har-capture-tutorial.md`. The short version is: open the Feishu page in Chrome, open DevTools Network, refresh, wait until the whiteboard is mostly loaded, export the HAR, and give that HAR file to the agent.

## Visual Check

If the user asks to compare quality or correctness, render quick thumbnails:

```bash
qlmanage -t -s 1600 -o "$OUT_DIR/preview" "$OUT_DIR"/*.simple.svg
```

Then inspect the preview PNGs visually. The SVG renderer is approximate: it preserves nodes, text, basic shapes, colors, and connectors, but it is not Feishu's native renderer.

## PNG-Guided Refinement

Use this when the user says the SVG is visually wrong or asks to refine against the PNG reference.

1. Use `whiteboard-XX.source.png` as the visual ground truth.
2. Render the matching `whiteboard-XX.simple.svg` to a PNG preview at 2560x2560 when possible. Prefer system Chrome if available; `qlmanage` is acceptable for quick checks but can distort long SVGs.
3. Crop the same region from source PNG and SVG preview, then inspect side by side.
4. Patch only `scripts/process_har.py`; do not hand-edit generated SVG unless the user explicitly asks for one-off manual edits.
5. Re-run `process_har.py` on the HAR after each renderer change.

Tune in this order:

- viewBox and output size first, because scale errors make every local comparison misleading
- connector arrows and dash patterns next
- text overflow, line height, font size, and list markers next
- colors and border widths last

Keep the final response concrete: say which renderer parameters changed and point to the updated SVG and source PNG.

## Notes

- The script reads local HAR files only. It does not call Feishu or leave backend traces.
- If a HAR is truncated or otherwise invalid JSON, the script falls back to scanning and recovering complete `log.entries` objects before the broken tail. Treat recovered output as best-effort and mention the warning.
- Extracted whiteboard image extensions are chosen from image magic bytes first, then response MIME type, because Feishu responses can report a PNG MIME while serving JPEG bytes.
- Prefer source PNG when exact visual fidelity matters.
- Prefer SVG when editable/vector structure matters.
- The renderer now expands nested `children`, applies parent-relative coordinates, and approximates Feishu tables, sticky notes, mind-map connectors, common flowchart shapes, and ordinary connectors.
- `whiteboard-XX.source.*` files are matched to blocks by `blockToken` and `cdp-whiteboard-<token>` when possible; unmatched images are written as `whiteboard-extra-XX.source.*`.
- Ordinary connectors preserve their `fillV2`/border color, width, dash state, and arrow direction. Arrow markers are generated per connector color.
- Text uses Feishu's original `textV2.fontSize` by default. Use `--fit-text` only when a preview has text overflow and preserving every original font size matters less than keeping text inside its own box.
- Preserve `textV2.horizontalAlign` and `textV2.verticalAlign` as separate axes. For mind-map nodes, connector paths should use the node box's vertical center, support both left and right child branches, and use text-only horizontal anchors based on the visible text edge plus a small gap instead of raw box edges.
- Table rendering uses Feishu `table.metaInfo` row/column sizes first and falls back to `tableRowInfo` row/cell counts when metadata is incomplete.
- SVG output uses a default 160-unit canvas margin; use `--margin N` to make the whiteboard looser or tighter.
- Keep answers concise; the script already writes `summary.json` and `index.md`.
