#!/usr/bin/env python3
"""Extract Feishu whiteboard assets from HAR and render simplified SVG previews.

[INPUT]: 本地 .har 文件（Chrome DevTools 导出）；仅依赖 Python 3.10+ 标准库
[OUTPUT]: whiteboard-XX.simple.svg / whiteboard-XX.source.* / summary.json /
          index.md，可选 audit-package JSON 与 all-images/
[POS]: feishu-whiteboard-har skill 的唯一执行入口，被 SKILL.md 工作流调用；
       渲染规则全部数据驱动（主题色板 + 形状默认色），禁止按文字内容特判
[PROTOCOL]: 变更时更新此头部，然后检查 SKILL.md；改渲染逻辑先跑 tests/
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import math
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


SVG_NS = "http://www.w3.org/2000/svg"
XHTML_NS = "http://www.w3.org/1999/xhtml"

# ============================================================
# 形状类型: 飞书 compositeShape.shapeType
# ============================================================
SHAPE_ROUND_RECT = 1
SHAPE_ELLIPSE = 2
SHAPE_CYLINDER = 4
SHAPE_NODE = 8           # 流程图"处理"节点
SHAPE_DIAMOND = 10       # 流程图"判断"菱形
SHAPE_FRAME = 11         # 容器框
SHAPE_DASHED_ELLIPSE = 13
SHAPE_CARD = 56          # 主题卡片
SHAPE_MIND_TEXT = 57     # 思维导图文本节点

# ============================================================
# 飞书主题色板: theme.fillColorCode -> 填充色
# 由多份真实 HAR 的源图像素采样交叉验证反推。
# 码值优先于 fillV2: 用户在 UI 换主题色只更新 code，旧 fillV2 残留。
# ============================================================
THEME_FILL = {
    0: "#ffffff",
    1: "#f0f4fc",
    2: "#eae2fe",
    6: "#fee3e2",
    8: "#f5f8ff",
    9: "#856acb",
    10: "#5178c6",
    16: "#dff6e6",
}

# 节点无任何颜色数据时的形状默认填充（飞书流程图模板内置默认，源图采样验证）
SHAPE_DEFAULT_FILL = {
    SHAPE_NODE: "#f0f4fc",
    SHAPE_ELLIPSE: "#eae2fe",
    SHAPE_DIAMOND: "#fef1ce",
    SHAPE_CARD: "#5178c6",
}

# 非矩形形状的文字排版区 = 内接矩形（菱形精确值 1/2，椭圆 1/sqrt(2)）。
# 飞书按内接矩形换行（源图验证: 99px 宽菱形里两行各约 48px），
# 直接用外接矩形会让文字戳出斜边。
SHAPE_TEXT_INSET = {
    SHAPE_DIAMOND: 0.5,
    SHAPE_ELLIPSE: 0.7071,
    SHAPE_DASHED_ELLIPSE: 0.7071,
}


def text_box(info: dict[str, Any]) -> tuple[float, float, float, float]:
    x, y, width, height = base_rect(info)
    factor = SHAPE_TEXT_INSET.get((info.get("compositeShape") or {}).get("shapeType"))
    if not factor:
        return x, y, width, height
    box_w, box_h = width * factor, height * factor
    return x + (width - box_w) / 2, y + (height - box_h) / 2, box_w, box_h

DARK_TEXT = "#1f2430"
STICKY_FILL = "#fff0c2"
MIND_LINE = "#5d82c8"
MIND_TEXT_GAP = 8.0


def rgb(value: int | None, fallback: str = "#ffffff") -> str:
    if value is None:
        return fallback
    return f"#{value & 0xFFFFFF:06x}"


def first_color(style: dict[str, Any] | None, fallback: str | None = None) -> str | None:
    if not style:
        return fallback
    data = style.get("fillStyleList", {}).get("data", [])
    if not data:
        return fallback
    item = data[0]
    if not item.get("active", True):
        return fallback
    return rgb(item.get("color"), fallback or "#ffffff")


def theme_fill(info: dict[str, Any]) -> str | None:
    code = info.get("theme", {}).get("fillColorCode")
    return THEME_FILL.get(code)


def is_dark(color: str) -> bool:
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 140


def border_color(info: dict[str, Any]) -> str:
    data = info.get("borderV2", {}).get("colorFillStyleList", {}).get("data", [])
    if data:
        return rgb(data[0].get("color"), "#222222")
    return "#222222"


def connector_color(info: dict[str, Any]) -> str:
    # 连接线颜色只取 borderV2（缺省深灰）。真实数据里连接线的 fillV2
    # 是无效占位（恒为 #bacefd），源图中的线条颜色始终跟随 border。
    return border_color(info)


def color_marker_key(color: str) -> str:
    return re.sub(r"[^0-9a-fA-F]+", "", color).lower() or "222222"


def arrow_marker_id(color: str, *, start: bool = False) -> str:
    prefix = "arrow-start" if start else "arrow"
    return f"{prefix}-{color_marker_key(color)}"


def line_width(info: dict[str, Any]) -> float:
    return float(info.get("borderV2", {}).get("borderStyleItem", {}).get("lineWidth", 1.5))


def text_color(text_v2: dict[str, Any]) -> str:
    return first_color(text_v2.get("fill"), DARK_TEXT) or DARK_TEXT


def node_text(info: dict[str, Any]) -> str:
    return ((info.get("textV2") or {}).get("text") or "").strip()


def node_id(node: dict[str, Any]) -> str:
    return str(node.get("id") or node.get("token") or "")


def base_rect(info: dict[str, Any]) -> tuple[float, float, float, float]:
    base = info.get("baseV2", {})
    return (
        float(base.get("x", 0)),
        float(base.get("y", 0)),
        float(base.get("width", 0)),
        float(base.get("height", 0)),
    )


def absolute_nodes(nodes: list[dict[str, Any]], offset_x: float = 0, offset_y: float = 0, depth: int = 0) -> list[dict[str, Any]]:
    # 只重建需要改坐标的两层 dict，children 留浅引用；deepcopy 会把整棵子树
    # 复制一遍再递归重复复制，深嵌套大白板上是 O(n^2)。
    flattened: list[dict[str, Any]] = []
    for node in nodes:
        info = node.get("info") or {}
        base = info.get("baseV2") or {}
        x = float(base.get("x", 0)) + offset_x
        y = float(base.get("y", 0)) + offset_y

        copied = {**node, "_depth": depth}
        if isinstance(info.get("baseV2"), dict):
            copied["info"] = {**info, "baseV2": {**info["baseV2"], "x": x, "y": y}}
        flattened.append(copied)

        children = node.get("children") or []
        if children:
            flattened.extend(absolute_nodes(children, x, y, depth + 1))
    return flattened


def block_nodes(block_data: dict[str, Any]) -> list[dict[str, Any]]:
    return absolute_nodes(block_data.get("data", {}).get("nodes") or [])


def effective_shape_fill(info: dict[str, Any], shape_type: int | None) -> str:
    # 三层规则，无内容特判: 主题码 > 显式 fillV2 > 形状默认色
    themed_fill = theme_fill(info)
    if themed_fill:
        return themed_fill
    explicit_fill = first_color(info.get("fillV2"))
    if explicit_fill:
        return explicit_fill
    return SHAPE_DEFAULT_FILL.get(shape_type, "#ffffff")


def forced_text_color(info: dict[str, Any]) -> str | None:
    # 与填充同构的两级规则，无逐形状特判:
    # 主题码生效时文字色全自动对比（显式文字色同样视为残留）；
    # 否则尊重显式文字色，缺失时按底色亮度反白。
    themed_fill = theme_fill(info)
    if themed_fill is not None:
        return "#ffffff" if is_dark(themed_fill) else DARK_TEXT
    text_v2 = info.get("textV2") or {}
    if first_color(text_v2.get("fill")):
        return None
    shape_type = (info.get("compositeShape") or {}).get("shapeType")
    return "#ffffff" if is_dark(effective_shape_fill(info, shape_type)) else None


def bold_style_ids(text_v2: dict[str, Any]) -> set[str]:
    table = text_v2.get("overrideInfo", {}).get("styleOverrideTable", {}).get("data", {}) or {}
    return {
        str(style_id)
        for style_id, style in table.items()
        if str(style.get("fontWeight", "")).lower() == "bold"
    }


def line_font_weight(text_v2: dict[str, Any], offset: int, line: str) -> str:
    if str(text_v2.get("fontWeight", "")).lower() in {"bold", "700"}:
        return "700"
    bold_ids = bold_style_ids(text_v2)
    overrides = text_v2.get("overrideInfo", {}).get("characterStyleOverrides", {}).get("data", [])
    for index in range(offset, min(offset + len(line), len(overrides))):
        if str(overrides[index]) in bold_ids:
            return "700"
    return "inherit"


def svg_attrs(attrs: dict[str, Any]) -> str:
    parts = []
    for key, value in attrs.items():
        if value is None or value is False:
            continue
        if value is True:
            parts.append(key)
        else:
            parts.append(f'{key}="{html.escape(str(value), quote=True)}"')
    return " ".join(parts)


def tag(name: str, attrs: dict[str, Any], content: str = "") -> str:
    attr_text = svg_attrs(attrs)
    if content:
        return f"<{name} {attr_text}>{content}</{name}>"
    return f"<{name} {attr_text}/>"


def response_bytes(entry: dict[str, Any]) -> bytes:
    content = entry.get("response", {}).get("content", {})
    text = content.get("text") or ""
    if content.get("encoding") == "base64":
        return base64.b64decode(text)
    return text.encode()


def response_text(entry: dict[str, Any]) -> str:
    return response_bytes(entry).decode("utf-8", errors="replace")


def load_entries(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        raw = json.loads(text)
        return raw.get("log", {}).get("entries", [])
    except json.JSONDecodeError as exc:
        entries = recover_complete_entries(text)
        print(
            f"warning: HAR is not valid JSON ({exc}); recovered {len(entries)} complete entries",
            file=sys.stderr,
        )
        return entries


def recover_complete_entries(text: str) -> list[dict[str, Any]]:
    entries_key = text.find('"entries"')
    if entries_key < 0:
        return []
    array_start = text.find("[", entries_key)
    if array_start < 0:
        return []

    entries: list[dict[str, Any]] = []
    index = array_start + 1
    end = len(text)
    while index < end:
        while index < end and text[index] in " \r\n\t,":
            index += 1
        if index >= end or text[index] == "]":
            break
        if text[index] != "{":
            index += 1
            continue

        object_start = index
        depth = 0
        in_string = False
        escaped = False
        while index < end:
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            else:
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        index += 1
                        try:
                            entries.append(json.loads(text[object_start:index]))
                        except json.JSONDecodeError:
                            pass
                        break
            index += 1
        else:
            break
    return entries


def whiteboard_blocks(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks = []
    for entry_index, entry in enumerate(entries):
        url = entry.get("request", {}).get("url", "")
        if "/space/api/whiteboard/block" not in url:
            continue
        try:
            parsed = json.loads(response_text(entry))
        except Exception:
            continue
        nodes = parsed.get("data", {}).get("nodes") or []
        if nodes:
            blocks.append({"entry": entry_index, "url": url, "data": parsed})
    return blocks


def image_ext(mime: str, data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    return "jpg" if mime == "image/jpeg" else mime.split("/")[-1]


def whiteboard_images(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    images = []
    for entry_index, entry in enumerate(entries):
        content = entry.get("response", {}).get("content", {})
        mime = (content.get("mimeType") or "").split(";")[0].strip().lower()
        url = entry.get("request", {}).get("url", "")
        if not (mime.startswith("image/") and "cdp-whiteboard" in url):
            continue
        data = response_bytes(entry)
        images.append({"entry": entry_index, "url": url, "mime": mime, "ext": image_ext(mime, data), "bytes": data})
    return images


def related_image_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    images = []
    for entry_index, entry in enumerate(entries):
        content = entry.get("response", {}).get("content", {})
        mime = (content.get("mimeType") or "").split(";")[0].strip().lower()
        url = entry.get("request", {}).get("url", "")
        if not mime.startswith("image/"):
            continue
        if "cdp-whiteboard" in url:
            kind = "whiteboard"
        elif "/space/api/box/stream/download/v2/cover/" in url:
            kind = "doc-cover"
        else:
            continue
        data = response_bytes(entry)
        images.append(
            {
                "entry": entry_index,
                "url": url,
                "mime": mime,
                "ext": image_ext(mime, data),
                "bytes": data,
                "kind": kind,
            }
        )
    return images


def write_related_images(out_dir: Path, entries: list[dict[str, Any]]) -> list[str]:
    target_dir = out_dir / "all-images"
    target_dir.mkdir(parents=True, exist_ok=True)
    names = []
    lines = ["# Extracted Related Images", ""]
    for index, image in enumerate(related_image_entries(entries), start=1):
        name = f"{index:02d}-{image['kind']}-entry-{image['entry']}.source.{image['ext']}"
        (target_dir / name).write_bytes(image["bytes"])
        names.append(f"all-images/{name}")
        lines += [
            f"## {index:02d} {image['kind']}",
            "",
            f"- entry: {image['entry']}",
            f"- source: [{name}]({name})",
            # 去掉 query：飞书图片 URL 携带签名 token，写进输出会泄露访问凭证
            f"- url: `{str(image['url']).split('?')[0][:240]}`",
            "",
        ]
    (target_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")
    return names


def query_value(url: str, key: str) -> str | None:
    values = parse_qs(urlparse(url).query).get(key) or []
    return values[0] if values else None


def block_token(block: dict[str, Any]) -> str | None:
    return query_value(str(block.get("url") or ""), "blockToken")


def image_token(image: dict[str, Any]) -> str | None:
    match = re.search(r"cdp-whiteboard-([^/~?]+)", str(image.get("url") or ""))
    return match.group(1) if match else None


def match_images_to_blocks(blocks: list[dict[str, Any]], images: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    # 图片身份用列表下标，不做整图 bytes 的值比较。
    by_token: dict[str, list[int]] = {}
    for image_index, image in enumerate(images):
        token = image_token(image)
        if token:
            by_token.setdefault(token, []).append(image_index)

    claimed: set[int] = set()
    matches: dict[int, dict[str, Any]] = {}
    for index, block in enumerate(blocks):
        candidates = by_token.get(block_token(block) or "")
        if not candidates:
            continue
        image_index = candidates.pop(0)
        matches[index] = images[image_index]
        claimed.add(image_index)

    unclaimed = [i for i in range(len(images)) if i not in claimed]
    for index, _block in enumerate(blocks):
        if index in matches or not unclaimed:
            continue
        image_index = unclaimed.pop(0)
        matches[index] = images[image_index]
        claimed.add(image_index)
    return matches, [images[i] for i in range(len(images)) if i not in claimed]


def node_bbox(node: dict[str, Any]) -> tuple[float, float, float, float]:
    base = node.get("info", {}).get("baseV2", {})
    x = float(base.get("x", 0))
    y = float(base.get("y", 0))
    return x, y, x + float(base.get("width", 0)), y + float(base.get("height", 0))


def board_bbox(nodes: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    if not nodes:
        return 0, 0, 0, 0
    xs: list[float] = []
    ys: list[float] = []
    for node in nodes:
        x1, y1, x2, y2 = node_bbox(node)
        xs.extend([x1, x2])
        ys.extend([y1, y2])
    return min(xs), min(ys), max(xs), max(ys)


def line_fragments(text_v2: dict[str, Any], text_align: str, justify: str) -> str:
    lines = text_v2.get("text", "").split("\n")
    paragraph_styles = text_v2.get("paragraphStyles", {}).get("data", [])
    counters: dict[int, int] = {}
    fragments: list[str] = []
    offset = 0
    for index, line in enumerate(lines):
        style = paragraph_styles[index] if index < len(paragraph_styles) else {}
        indent = int(style.get("indent", 0))
        list_type = int(style.get("listType", 0))
        marker = ""
        weight = line_font_weight(text_v2, offset, line)
        if list_type == 1:
            marker = "•" if indent == 0 else "◦"
        elif list_type == 2:
            counters[indent] = counters.get(indent, 0) + 1
            marker = f"{counters[indent]}."
        escaped = html.escape(line)
        margin_left = indent * 18
        if marker:
            fragments.append(
                '<div style="display:flex;align-items:flex-start;'
                f'margin-left:{margin_left}px;text-align:left;width:100%;font-weight:{weight};">'
                f'<span style="display:inline-block;width:14px;flex:0 0 14px;">{marker}</span>'
                f'<span style="flex:1 1 auto;">{escaped}</span></div>'
            )
        else:
            fragments.append(
                '<div style="display:flex;align-items:flex-start;'
                f'justify-content:{justify};text-align:{text_align};'
                f'margin-left:{margin_left}px;font-weight:{weight};width:100%;">{escaped}</div>'
            )
        offset += len(line) + 1
    return "".join(fragments)


def visual_units(text: str) -> float:
    # This is only an SVG-side estimate; it keeps mind-map anchors off visible text.
    total = 0.0
    for char in text:
        if char.isspace():
            total += 0.34
        elif char in ".,:;!|'`":
            total += 0.28
        elif char in "mwMW@#%&":
            total += 0.78
        elif ord(char) < 128:
            total += 0.56
        elif char in "，。！？；：、·":
            total += 0.95
        elif char in "（）【】《》〈〉「」『』":
            total += 0.82
        else:
            total += 1.0
    return total


def fitted_font_size(text_v2: dict[str, Any], width: float, height: float, padding: float, line_height: float) -> float:
    original = float(text_v2.get("fontSize", 14))
    text = str(text_v2.get("text") or "")
    if not text or width <= 0 or height <= 0:
        return original
    usable_w = max(width - padding * 2, 1)
    usable_h = max(height - padding * 2, 1)
    lines = text.replace("\r", "").split("\n") or [""]
    min_size = max(6.5, min(original, 9.0))
    size = original
    for _ in range(18):
        capacity = max(1.0, usable_w / max(size, 1))
        wrapped_lines = sum(max(1, math.ceil(visual_units(line) / capacity)) for line in lines)
        if wrapped_lines * size * line_height <= usable_h * 1.04:
            break
        size *= 0.92
    return max(min_size, min(original, size))


def text_div(
    text_v2: dict[str, Any],
    width: float,
    height: float,
    *,
    plain: bool = False,
    forced_color: str | None = None,
    fit: bool = False,
    clip: bool = False,
) -> str:
    font_size = float(text_v2.get("fontSize", 14))
    font_weight = "700" if str(text_v2.get("fontWeight", "")).lower() in {"bold", "700"} else "400"
    h_align = int(text_v2.get("horizontalAlign", 0))
    v_align = int(text_v2.get("verticalAlign", 0))
    color = forced_color or text_color(text_v2)
    h_justify = {0: "flex-start", 1: "center", 2: "flex-end"}.get(h_align, "flex-start")
    v_justify = {0: "flex-start", 1: "center", 2: "flex-end"}.get(v_align, "flex-start")
    text_align = {0: "left", 1: "center", 2: "right"}.get(h_align, "left")
    align_items = {0: "flex-start", 1: "center", 2: "flex-end"}.get(h_align, "flex-start")
    padding = 0 if plain else max(4, min(10, font_size * 0.55))
    line_height = 1.25 if plain else 1.32
    if fit:
        font_size = fitted_font_size(text_v2, width, height, padding, line_height)
        padding = 0 if plain else max(3, min(10, font_size * 0.5))
    style = (
        f"width:{width:.3f}px;height:{height:.3f}px;"
        f"display:flex;flex-direction:column;align-items:{align_items};justify-content:{v_justify};"
        f"text-align:{text_align};font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif;"
        f"font-size:{font_size:.3f}px;font-weight:{font_weight};line-height:{line_height};"
        f"color:{color};box-sizing:border-box;padding:{padding:.3f}px;"
        f"white-space:normal;overflow:{'hidden' if clip else 'visible'};"
    )
    return f'<div xmlns="{XHTML_NS}" style="{style}">{line_fragments(text_v2, text_align, h_justify)}</div>'


def render_text(node: dict[str, Any], *, fit_text: bool = False) -> str:
    info = node["info"]
    text_v2 = info.get("textV2")
    if not text_v2 or not text_v2.get("text"):
        return ""
    x, y, width, height = text_box(info)
    is_inset = (x, y, width, height) != base_rect(info)
    is_mind_leaf = bool(info.get("mindMap")) and info.get("compositeShape", {}).get("shapeType") == SHAPE_MIND_TEXT
    is_standalone_text = "compositeShape" not in info and not info.get("mindMap")
    # 内接矩形排版的形状不裁剪: 文字过长时对称溢出，和飞书行为一致
    clip = not (is_mind_leaf or is_standalone_text or is_inset)
    return tag(
        "foreignObject",
        {
            "x": f"{x:.3f}",
            "y": f"{y:.3f}",
            "width": f"{width:.3f}",
            "height": f"{height:.3f}",
            "overflow": "hidden" if clip else "visible",
        },
        text_div(
            text_v2,
            width,
            height,
            plain=is_standalone_text or is_mind_leaf or is_inset,
            forced_color=forced_text_color(info),
            fit=fit_text and not (is_mind_leaf or is_standalone_text),
            clip=clip,
        ),
    )


def scaled_sizes(items: list[dict[str, Any]], total: float) -> list[float]:
    sizes = [float(item.get("size", 0)) for item in items]
    actual = sum(sizes)
    if not sizes or actual <= 0:
        return [total]
    scale = total / actual
    return [size * scale for size in sizes]


def even_sizes(count: int, total: float) -> list[float]:
    if count <= 0:
        return []
    return [total / count for _ in range(count)]


def table_rows(table: dict[str, Any]) -> list[dict[str, Any]]:
    return table.get("tableRowInfo", {}).get("data", []) or []


def table_column_count(row_data: list[dict[str, Any]]) -> int:
    count = 0
    for row in row_data:
        cells = row.get("data", []) or []
        span_count = 0
        for cell in cells:
            base = cell.get("cellBaseInfo", {}) or {}
            span_count += max(1, int(base.get("colSpan", 1)))
        count = max(count, span_count)
    return count


def render_table(node: dict[str, Any], *, fit_text: bool = False) -> str:
    info = node["info"]
    table = info.get("table") or {}
    meta = table.get("metaInfo", {})
    x, y, width, height = base_rect(info)
    row_data = table_rows(table)
    meta_cols = meta.get("columns", {}).get("data", []) or []
    meta_rows = meta.get("rows", {}).get("data", []) or []
    cols = scaled_sizes(meta_cols, width) if meta_cols else even_sizes(table_column_count(row_data), width)
    rows = scaled_sizes(meta_rows, height) if meta_rows else even_sizes(len(row_data), height)
    if not cols or not rows:
        return ""

    parts: list[str] = [
        tag("rect", {"x": f"{x:.3f}", "y": f"{y:.3f}", "width": f"{width:.3f}", "height": f"{height:.3f}", "fill": "#ffffff", "stroke": "#222222", "stroke-width": 2})
    ]
    cy = y
    for row_index, row_height in enumerate(rows):
        cx = x
        cells = row_data[row_index].get("data", []) if row_index < len(row_data) else []
        for col_index, col_width in enumerate(cols):
            cell = cells[col_index] if col_index < len(cells) else {}
            style = cell.get("styleInfo", {})
            fill = first_color(style.get("fillProps"), "#ffffff") or "#ffffff"
            if row_index == 0 and fill == "#ffffff":
                fill = "#f2f3f5"
            parts.append(
                tag(
                    "rect",
                    {
                        "x": f"{cx:.3f}",
                        "y": f"{cy:.3f}",
                        "width": f"{col_width:.3f}",
                        "height": f"{row_height:.3f}",
                        "fill": fill,
                        "stroke": "#222222",
                        "stroke-width": 1.5,
                    },
                )
            )
            text_props = style.get("textProps") or {}
            if text_props.get("text"):
                parts.append(
                    tag(
                        "foreignObject",
                        {
                            "x": f"{cx + 4:.3f}",
                            "y": f"{cy + 4:.3f}",
                            "width": f"{max(col_width - 8, 1):.3f}",
                            "height": f"{max(row_height - 8, 1):.3f}",
                            "overflow": "hidden",
                        },
                        text_div(text_props, max(col_width - 8, 1), max(row_height - 8, 1), forced_color=DARK_TEXT, fit=fit_text, clip=True),
                    )
                )
            cx += col_width
        cy += row_height
    return "<g>\n" + "\n".join(parts) + "\n</g>"


def render_group(node: dict[str, Any]) -> str:
    info = node["info"]
    if not node.get("children") or not info.get("title"):
        return ""
    x, y, width, height = base_rect(info)
    title = str(info.get("title") or "")
    label_w = max(84, min(width, len(title) * 18 + 28))
    label_h = 34
    parts = [
        tag(
            "rect",
            {
                "x": f"{x:.3f}",
                "y": f"{y:.3f}",
                "width": f"{width:.3f}",
                "height": f"{height:.3f}",
                "fill": "#f6f7f9",
                "stroke": "#bfc5cf",
                "stroke-width": 1.5,
                "rx": 6,
                "ry": 6,
            },
        ),
        tag(
            "rect",
            {
                "x": f"{x:.3f}",
                "y": f"{y - label_h - 6:.3f}",
                "width": f"{label_w:.3f}",
                "height": label_h,
                "fill": "#eef0f4",
                "stroke": "#c8cdd6",
                "stroke-width": 1,
                "rx": 5,
                "ry": 5,
            },
        ),
        tag(
            "text",
            {
                "x": f"{x + 12:.3f}",
                "y": f"{y - 15:.3f}",
                "font-family": "'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif",
                "font-size": 18,
                "font-weight": 700,
                "fill": DARK_TEXT,
            },
            html.escape(title),
        ),
    ]
    return "<g>\n" + "\n".join(parts) + "\n</g>"


def render_sticky_note(node: dict[str, Any]) -> str:
    info = node["info"]
    if "stickyNoteProps" not in info:
        return ""
    x, y, width, height = base_rect(info)
    props = info.get("stickyNoteProps") or {}
    author = props.get("authorInfo", {}) if props.get("showAuthorInfo") else {}
    author_name = author.get("name") or author.get("enName") or ""
    footer_h = 28 if author_name else 0
    text_v2 = info.get("textV2") or {}
    parts = [
        tag(
            "rect",
            {
                "x": f"{x:.3f}",
                "y": f"{y:.3f}",
                "width": f"{width:.3f}",
                "height": f"{height:.3f}",
                "fill": first_color(info.get("fillV2"), STICKY_FILL) or STICKY_FILL,
                "stroke": "none",
                "rx": 2,
                "ry": 2,
                "filter": "url(#sticky-shadow)",
            },
        )
    ]
    if text_v2.get("text"):
        parts.append(
            tag(
                "foreignObject",
                {
                    "x": f"{x + 12:.3f}",
                    "y": f"{y + 10:.3f}",
                    "width": f"{max(width - 24, 1):.3f}",
                    "height": f"{max(height - 20 - footer_h, 1):.3f}",
                    "overflow": "hidden",
                },
                text_div(text_v2, max(width - 24, 1), max(height - 20 - footer_h, 1), plain=True, forced_color=DARK_TEXT, fit=False, clip=True),
            )
        )
    if author_name:
        cy = y + height - 16
        parts.extend(
            [
                tag("circle", {"cx": f"{x + 18:.3f}", "cy": f"{cy:.3f}", "r": 8, "fill": "#4f7fd9"}),
                tag(
                    "text",
                    {
                        "x": f"{x + 32:.3f}",
                        "y": f"{cy + 5:.3f}",
                        "font-family": "'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif",
                        "font-size": 13,
                        "fill": "#5c6472",
                    },
                    html.escape(str(author_name)),
                ),
            ]
        )
    return "<g>\n" + "\n".join(parts) + "\n</g>"


def render_cylinder(common: dict[str, Any], x: float, y: float, width: float, height: float) -> str:
    ry = min(height * 0.18, 18)
    body = tag("path", {**common, "d": f"M{x:.3f},{y + ry:.3f} v{height - 2 * ry:.3f} a{width / 2:.3f},{ry:.3f} 0 0 0 {width:.3f},0 v{-height + 2 * ry:.3f} a{width / 2:.3f},{ry:.3f} 0 0 0 {-width:.3f},0"})
    top = tag("ellipse", {**common, "fill": common.get("fill"), "cx": f"{x + width / 2:.3f}", "cy": f"{y + ry:.3f}", "rx": f"{width / 2:.3f}", "ry": f"{ry:.3f}"})
    bottom = tag("path", {"d": f"M{x:.3f},{y + height - ry:.3f} a{width / 2:.3f},{ry:.3f} 0 0 0 {width:.3f},0", "fill": "none", "stroke": common.get("stroke"), "stroke-width": common.get("stroke-width")})
    return f"<g>{body}{top}{bottom}</g>"


def render_shape(node: dict[str, Any], *, fit_text: bool = False) -> str:
    info = node["info"]
    if "table" in info:
        return render_table(node, fit_text=fit_text)
    if "stickyNoteProps" in info:
        return render_sticky_note(node)
    group = render_group(node)
    if group:
        return group

    x, y, width, height = base_rect(info)
    shape_type = info.get("compositeShape", {}).get("shapeType")
    fill = effective_shape_fill(info, shape_type)
    stroke = border_color(info)
    stroke_width = line_width(info)
    common = {"fill": fill, "stroke": stroke, "stroke-width": stroke_width}
    if shape_type == SHAPE_ROUND_RECT:
        radius = max(4, min(height / 2, width / 2))
        return tag("rect", {**common, "x": f"{x:.3f}", "y": f"{y:.3f}", "width": f"{width:.3f}", "height": f"{height:.3f}", "rx": f"{radius:.3f}", "ry": f"{radius:.3f}"})
    if shape_type == SHAPE_ELLIPSE:
        return tag("ellipse", {**common, "cx": f"{x + width / 2:.3f}", "cy": f"{y + height / 2:.3f}", "rx": f"{width / 2:.3f}", "ry": f"{height / 2:.3f}"})
    if shape_type == SHAPE_CYLINDER:
        return render_cylinder(common, x, y, width, height)
    if shape_type == SHAPE_DIAMOND:
        points = [(x + width / 2, y), (x + width, y + height / 2), (x + width / 2, y + height), (x, y + height / 2)]
        return tag("polygon", {**common, "points": " ".join(f"{px:.3f},{py:.3f}" for px, py in points)})
    if shape_type == SHAPE_DASHED_ELLIPSE:
        return tag(
            "ellipse",
            {
                **common,
                "fill": "none",
                "stroke-dasharray": "2.2 5.2",
                "stroke-linecap": "round",
                "cx": f"{x + width / 2:.3f}",
                "cy": f"{y + height / 2:.3f}",
                "rx": f"{width / 2:.3f}",
                "ry": f"{height / 2:.3f}",
            },
        )
    if shape_type == SHAPE_FRAME:
        return tag("rect", {**common, "x": f"{x:.3f}", "y": f"{y:.3f}", "width": f"{width:.3f}", "height": f"{height:.3f}", "rx": 4, "ry": 4})
    if shape_type == SHAPE_CARD:
        return tag("rect", {**common, "x": f"{x:.3f}", "y": f"{y:.3f}", "width": f"{width:.3f}", "height": f"{height:.3f}", "rx": 8, "ry": 8})
    if shape_type == SHAPE_MIND_TEXT:
        return ""
    if shape_type is None:
        return ""
    return tag("rect", {**common, "x": f"{x:.3f}", "y": f"{y:.3f}", "width": f"{width:.3f}", "height": f"{height:.3f}", "rx": 6, "ry": 6})


def point_along(points: list[tuple[float, float]], t: float) -> tuple[float, float]:
    # 折线弧长参数 t (0..1) 处的坐标
    segments = list(zip(points, points[1:]))
    lengths = [math.dist(p0, p1) for p0, p1 in segments]
    total = sum(lengths)
    if total <= 0:
        return points[0]
    target = max(0.0, min(1.0, t)) * total
    travelled = 0.0
    for (p0, p1), seg in zip(segments, lengths):
        if travelled + seg >= target and seg > 0:
            ratio = (target - travelled) / seg
            return (p0[0] + (p1[0] - p0[0]) * ratio, p0[1] + (p1[1] - p0[1]) * ratio)
        travelled += seg
    return points[-1]


def render_connector_captions(info: dict[str, Any], points: list[tuple[float, float]]) -> list[str]:
    # connectorV2.captions: 挂在连接线上的文字标签，t 为沿线位置
    parts: list[str] = []
    for caption in (info.get("connectorV2", {}).get("captions") or {}).get("data", []):
        style = caption.get("textStyle") or {}
        text = (style.get("text") or "").strip()
        if not text:
            continue
        cx, cy = point_along(points, float(caption.get("t", 0.5)))
        font_size = float(style.get("fontSize", 14))
        lines = text.split("\n")
        width = max(visual_units(line) for line in lines) * font_size + 16
        height = len(lines) * font_size * 1.32 + 8
        left, top = cx - width / 2, cy - height / 2
        parts.append(
            tag("rect", {"x": f"{left:.3f}", "y": f"{top:.3f}", "width": f"{width:.3f}", "height": f"{height:.3f}", "fill": "#ffffff"})
        )
        parts.append(
            tag(
                "foreignObject",
                {"x": f"{left:.3f}", "y": f"{top:.3f}", "width": f"{width:.3f}", "height": f"{height:.3f}", "overflow": "visible"},
                text_div(style, width, height, plain=True),
            )
        )
    return parts


def render_connector(node: dict[str, Any]) -> str:
    info = node["info"]
    base = info.get("baseV2", {})
    conn = info.get("connectorV2", {})
    x = float(base.get("x", 0))
    y = float(base.get("y", 0))
    start = conn.get("startPoint", {})
    end = conn.get("endPoint", {})
    points = [(x + float(start.get("x", 0)), y + float(start.get("y", 0)))]
    for point in conn.get("turningPoints", {}).get("data", []):
        points.append((x + float(point.get("x", 0)), y + float(point.get("y", 0))))
    points.append((x + float(end.get("x", 0)), y + float(end.get("y", 0))))
    advance = info.get("borderV2", {}).get("borderStyleItem", {}).get("advanceSettings", {})
    connect_style = info.get("theme", {}).get("connectStyleCode")
    dashed = connect_style == 3 or bool(advance.get("dashes"))
    color = connector_color(info)
    line = tag(
        "polyline",
        {
            "points": " ".join(f"{px:.3f},{py:.3f}" for px, py in points),
            "fill": "none",
            "stroke": color,
            "stroke-width": line_width(info),
            "stroke-linejoin": "round",
            "stroke-linecap": "round",
            "stroke-dasharray": "2.2 5.2" if dashed else None,
            "marker-end": f"url(#{arrow_marker_id(color)})" if int(advance.get("end", 0)) else None,
            "marker-start": f"url(#{arrow_marker_id(color, start=True)})" if int(advance.get("start", 0)) else None,
        },
    )
    return "\n".join([line, *render_connector_captions(info, points)])


def mind_text_width(info: dict[str, Any]) -> float:
    text_v2 = info.get("textV2") or {}
    text = str(text_v2.get("text") or "")
    if not text:
        return base_rect(info)[2]
    font_size = float(text_v2.get("fontSize", 14))
    lines = text.replace("\r", "").split("\n") or [text]
    return max(visual_units(line) * font_size for line in lines)


def mind_anchor_right(info: dict[str, Any]) -> float:
    x, _y, width, _height = base_rect(info)
    shape_type = (info.get("compositeShape") or {}).get("shapeType")
    if shape_type != SHAPE_MIND_TEXT:
        return x + width
    text_right = mind_text_width(info) + MIND_TEXT_GAP
    return x + min(width, text_right)


def mind_anchor_left(info: dict[str, Any]) -> float:
    x, _y, width, _height = base_rect(info)
    shape_type = (info.get("compositeShape") or {}).get("shapeType")
    if shape_type != SHAPE_MIND_TEXT:
        return x
    # Keep the connector just outside the text box so it does not collide with visible glyphs.
    return x - min(MIND_TEXT_GAP, max(width * 0.25, 0))


def render_mind_connectors(nodes: list[dict[str, Any]]) -> list[str]:
    mind_nodes = {node_id(node): node for node in nodes if (node.get("info") or {}).get("mindMap")}
    paths: list[str] = []
    for node in mind_nodes.values():
        info = node.get("info") or {}
        parent_id = str((info.get("mindMap") or {}).get("parentId") or "")
        parent = mind_nodes.get(parent_id)
        if not parent:
            continue
        parent_info = parent.get("info") or {}
        px, py, pw, ph = base_rect(parent_info)
        x, y, width, height = base_rect(info)
        child_on_left = x + width / 2 < px + pw / 2
        start_x = mind_anchor_left(parent_info) if child_on_left else mind_anchor_right(parent_info)
        start_y = py + ph / 2
        end_x = mind_anchor_right(info) if child_on_left else mind_anchor_left(info)
        end_y = y + height / 2
        curve = max(24, abs(end_x - start_x) * 0.45)
        mid_x = start_x - curve if child_on_left else start_x + curve
        paths.append(
            tag(
                "path",
                {
                    "d": f"M{start_x:.3f},{start_y:.3f} C{mid_x:.3f},{start_y:.3f} {mid_x:.3f},{end_y:.3f} {end_x:.3f},{end_y:.3f}",
                    "fill": "none",
                    "stroke": MIND_LINE,
                    "stroke-width": 3,
                    "stroke-linecap": "round",
                },
            )
        )
    return paths


def connector_marker_defs(nodes: list[dict[str, Any]]) -> str:
    colors = sorted(
        {
            connector_color(node.get("info") or {})
            for node in nodes
            if "connectorV2" in (node.get("info") or {})
        }
    )
    parts: list[str] = []
    for color in colors:
        parts.append(
            f'''  <marker id="{arrow_marker_id(color)}" markerWidth="5.5" markerHeight="5.5" refX="5.1" refY="2.75" orient="auto" markerUnits="strokeWidth">
    <path d="M0,0 L5.5,2.75 L0,5.5 z" fill="{html.escape(color, quote=True)}"/>
  </marker>'''
        )
        parts.append(
            f'''  <marker id="{arrow_marker_id(color, start=True)}" markerWidth="5.5" markerHeight="5.5" refX="0.4" refY="2.75" orient="auto" markerUnits="strokeWidth">
    <path d="M5.5,0 L0,2.75 L5.5,5.5 z" fill="{html.escape(color, quote=True)}"/>
  </marker>'''
        )
    return "\n".join(parts)


def render_svg(block: dict[str, Any], title: str, *, square: bool = True, margin: float = 160, fit_text: bool = False) -> str:
    nodes = block_nodes(block)
    min_x, min_y, max_x, max_y = board_bbox(nodes)
    view_x = min_x - margin
    view_y = min_y - margin
    view_w = max_x - min_x + margin * 2
    view_h = max_y - min_y + margin * 2
    output_w = view_w
    output_h = view_h
    if square:
        side = max(max_x - min_x, max_y - min_y) + margin * 2
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        view_x = center_x - side / 2
        view_y = center_y - side / 2
        view_w = side
        view_h = side
        output_w = 2560
        output_h = 2560
    marker_defs = connector_marker_defs(nodes)
    mind_connectors = render_mind_connectors(nodes)
    connectors: list[str] = []
    container_shapes: list[str] = []
    sized_shapes: list[tuple[float, str]] = []
    texts: list[str] = []
    for node in nodes:
        info = node.get("info", {})
        if "connectorV2" in info:
            connectors.append(render_connector(node))
        else:
            shape = render_shape(node, fit_text=fit_text)
            is_container = (
                "table" in info
                or (bool(node.get("children")) and bool(info.get("title")))
                or info.get("compositeShape", {}).get("shapeType") == SHAPE_FRAME
            )
            if is_container:
                container_shapes.append(shape)
            else:
                _x, _y, width, height = base_rect(info)
                sized_shapes.append((width * height, shape))
            if "stickyNoteProps" not in info:
                texts.append(render_text(node, fit_text=fit_text))
    # 数据无 zIndex 时按面积降序绘制: 大形状垫底，小形状浮上，
    # 避免后出现的大框盖住先画的小节点（稳定排序保留同面积的文档序）
    shapes = [shape for _area, shape in sorted(sized_shapes, key=lambda item: -item[0])]
    body = "\n".join(item for item in container_shapes + mind_connectors + connectors + shapes + texts if item)
    return f'''<svg xmlns="{SVG_NS}" width="{output_w:.0f}" height="{output_h:.0f}" viewBox="{view_x:.3f} {view_y:.3f} {view_w:.3f} {view_h:.3f}" role="img" aria-label="{html.escape(title, quote=True)}">
<defs>
  <filter id="sticky-shadow" x="-12%" y="-12%" width="130%" height="135%">
    <feDropShadow dx="10" dy="18" stdDeviation="11" flood-color="#000000" flood-opacity="0.18"/>
  </filter>
{marker_defs}
</defs>
<rect x="{view_x:.3f}" y="{view_y:.3f}" width="{view_w:.3f}" height="{view_h:.3f}" fill="#ffffff"/>
{body}
</svg>
'''


def block_summary(block: dict[str, Any], index: int) -> dict[str, Any]:
    nodes = block_nodes(block["data"])
    counts: dict[str, int] = {"nodes": len(nodes), "texts": 0, "connectors": 0, "shapes": 0, "mindmap_nodes": 0, "sticky_notes": 0, "tables": 0}
    samples = []
    for node in nodes:
        info = node.get("info", {})
        if "connectorV2" in info:
            counts["connectors"] += 1
        if "compositeShape" in info:
            counts["shapes"] += 1
        if "mindMap" in info:
            counts["mindmap_nodes"] += 1
        if "stickyNoteProps" in info:
            counts["sticky_notes"] += 1
        if "table" in info:
            counts["tables"] += 1
        text = (info.get("textV2") or {}).get("text") or ""
        if text:
            counts["texts"] += 1
            samples.append(re.sub(r"\s+", " ", text.replace("\n", " | ")).strip()[:120])
    min_x, min_y, max_x, max_y = board_bbox(nodes)
    return {
        "index": index,
        "entry": block["entry"],
        "nodes": counts["nodes"],
        "texts": counts["texts"],
        "shapes": counts["shapes"],
        "connectors": counts["connectors"],
        "mindmap_nodes": counts["mindmap_nodes"],
        "sticky_notes": counts["sticky_notes"],
        "tables": counts["tables"],
        "bbox": [round(min_x, 2), round(min_y, 2), round(max_x, 2), round(max_y, 2)],
        "samples": samples[:8],
    }


def audit_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\n", " | ")).strip()


def table_audit_summary(info: dict[str, Any]) -> dict[str, int]:
    table = info.get("table") or {}
    meta = table.get("metaInfo") or {}
    row_data = table_rows(table)
    meta_cols = meta.get("columns", {}).get("data", []) or []
    meta_rows = meta.get("rows", {}).get("data", []) or []
    return {
        "meta_rows": len(meta_rows),
        "meta_cols": len(meta_cols),
        "row_info_rows": len(row_data),
        "row_info_cols": table_column_count(row_data),
    }


def node_audit_slice(node: dict[str, Any]) -> dict[str, Any]:
    info = node.get("info") or {}
    text_v2 = info.get("textV2") or {}
    connector = info.get("connectorV2") or {}
    border = info.get("borderV2") or {}
    return {
        "id": node_id(node),
        "depth": node.get("_depth"),
        "baseV2": info.get("baseV2"),
        "shapeType": (info.get("compositeShape") or {}).get("shapeType"),
        "textV2": {
            "text": text_v2.get("text"),
            "fontSize": text_v2.get("fontSize"),
            "fontWeight": text_v2.get("fontWeight"),
            "horizontalAlign": text_v2.get("horizontalAlign"),
            "verticalAlign": text_v2.get("verticalAlign"),
            "paragraphStyles_count": len((text_v2.get("paragraphStyles") or {}).get("data") or []),
            "overrideInfo_keys": sorted((text_v2.get("overrideInfo") or {}).keys()),
            "fill": text_v2.get("fill"),
        }
        if text_v2
        else None,
        "mindMap": info.get("mindMap"),
        "connectorV2": {
            "startPoint": connector.get("startPoint"),
            "endPoint": connector.get("endPoint"),
            "turningPoints": connector.get("turningPoints"),
            "color": connector_color(info),
            "lineWidth": line_width(info),
            "advanceSettings": (border.get("borderStyleItem") or {}).get("advanceSettings"),
        }
        if connector
        else None,
        "theme": info.get("theme"),
        "fillV2": info.get("fillV2"),
        "has_children": bool(node.get("children")),
        "child_count": len(node.get("children") or []),
        "has_table": "table" in info,
        "table_summary": table_audit_summary(info) if "table" in info else None,
        "has_sticky_note": "stickyNoteProps" in info,
    }


def block_audit_slice(block: dict[str, Any], index: int, summary: dict[str, Any]) -> dict[str, Any]:
    nodes = block_nodes(block["data"])
    mind_nodes = {node_id(node): node for node in nodes if (node.get("info") or {}).get("mindMap")}
    mind_edges: list[dict[str, Any]] = []
    for node in mind_nodes.values():
        info = node.get("info") or {}
        parent_id = str((info.get("mindMap") or {}).get("parentId") or "")
        parent = mind_nodes.get(parent_id)
        if not parent:
            continue
        parent_info = parent.get("info") or {}
        px, py, pw, ph = base_rect(parent_info)
        x, y, width, height = base_rect(info)
        child_on_left = x + width / 2 < px + pw / 2
        mind_edges.append(
            {
                "parent_id": parent_id,
                "child_id": node_id(node),
                "parent_text": audit_text((parent_info.get("textV2") or {}).get("text")),
                "child_text": audit_text((info.get("textV2") or {}).get("text")),
                "parent_box": dict(zip(("x", "y", "width", "height"), (px, py, pw, ph))),
                "child_box": dict(zip(("x", "y", "width", "height"), (x, y, width, height))),
                "child_on_left": child_on_left,
                "anchor_start": mind_anchor_left(parent_info) if child_on_left else mind_anchor_right(parent_info),
                "anchor_end": mind_anchor_right(info) if child_on_left else mind_anchor_left(info),
            }
        )
    return {
        "index": index,
        "entry": block["entry"],
        "url": str(block.get("url") or "").split("?")[0],
        "block_token": block_token(block),
        "summary": summary,
        "nodes_key_fields": [node_audit_slice(node) for node in nodes],
        "mind_edges_with_current_anchor_math": mind_edges,
    }


def endpoint_audit_entries(entries: list[dict[str, Any]]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    counts: dict[str, int] = {}
    relevant: list[dict[str, Any]] = []
    for entry_index, entry in enumerate(entries):
        url = entry.get("request", {}).get("url", "")
        if "/space/api/whiteboard/" not in url and "cdp-whiteboard" not in url:
            continue
        path = url.split("?")[0]
        counts[path] = counts.get(path, 0) + 1
        response = entry.get("response") or {}
        content = response.get("content") or {}
        relevant.append(
            {
                "entry": entry_index,
                "url_path": path,
                "status": response.get("status"),
                "mimeType": content.get("mimeType"),
                "body_size": len(response_bytes(entry)) if "/space/api/whiteboard/" in path else response.get("bodySize"),
            }
        )
    return counts, relevant


def write_audit_package(
    target: Path,
    *,
    har: Path,
    entries: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    images: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    out_dir: Path,
) -> None:
    endpoint_counts, endpoint_entries = endpoint_audit_entries(entries)
    payload = {
        "purpose": "Minimal HAR-derived audit package for reviewing feishu-whiteboard-har without loading the full HAR by default.",
        "full_har_fallback_path": str(har),
        "instruction_for_reviewer": "Use this JSON first. Do not load the full HAR unless this package is insufficient for a specific finding; if you need it, state why.",
        "har_size_bytes": har.stat().st_size if har.exists() else None,
        "entries_count": len(entries),
        "relevant_endpoint_counts": endpoint_counts,
        "relevant_endpoint_entries": endpoint_entries,
        "whiteboard_image_metadata": [
            {
                "entry": image["entry"],
                "url": str(image["url"]).split("?")[0],
                "token": image_token(image),
                "mime": image["mime"],
                "ext": image["ext"],
                "bytes": len(image["bytes"]),
            }
            for image in images
        ],
        "generated_output_dir": str(out_dir),
        "generated_summary": {"blocks": summaries},
        "whiteboard_blocks": [block_audit_slice(block, index, summaries[index]) for index, block in enumerate(blocks)],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def default_out_dir(har: Path) -> Path:
    return Path.cwd() / "output" / "feishu-whiteboard-har" / har.stem


def write_index(out_dir: Path, har: Path, summaries: list[dict[str, Any]], image_count: int, unmatched_images: list[str] | None = None) -> None:
    lines = [
        f"# Feishu Whiteboard HAR: {har.name}",
        "",
        f"- whiteboard blocks: {len(summaries)}",
        f"- cdp-whiteboard images: {image_count}",
        "",
    ]
    for item in summaries:
        n = item["index"] + 1
        lines += [
            f"## Whiteboard {n:02d}",
            "",
            f"- nodes: {item['nodes']}",
            f"- texts: {item['texts']}",
            f"- shapes: {item['shapes']}",
            f"- connectors: {item['connectors']}",
            f"- mindmap nodes: {item['mindmap_nodes']}",
            f"- sticky notes: {item['sticky_notes']}",
            f"- tables: {item['tables']}",
            f"- svg: [whiteboard-{n:02d}.simple.svg](whiteboard-{n:02d}.simple.svg)",
            f"- source image: [{item['source_image']}]({item['source_image']})" if item.get("source_image") else "- source image: not found",
            "",
            "Samples:",
        ]
        lines += [f"- {sample}" for sample in item["samples"]]
        lines.append("")
    if unmatched_images:
        lines += ["## Unmatched Images", ""]
        lines += [f"- [{name}]({name})" for name in unmatched_images]
        lines.append("")
    (out_dir / "index.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Feishu whiteboard PNGs and render simplified SVGs from a HAR.")
    parser.add_argument("har", type=Path, help="Path to .har file")
    parser.add_argument("--out", type=Path, default=None, help="Output directory")
    parser.add_argument("--no-square", action="store_true", help="Keep natural SVG aspect ratio instead of 2560 square")
    parser.add_argument("--fit-text", action="store_true", help="Shrink shape/table text only when it would overflow its box")
    parser.add_argument("--margin", type=float, default=160, help="Canvas margin in whiteboard coordinate units")
    parser.add_argument("--extract-related-images", action="store_true", help="Also extract cdp-whiteboard and doc cover images to all-images/")
    parser.add_argument("--audit-package", type=Path, default=None, help="Write a compact HAR-derived JSON package for model/code review")
    args = parser.parse_args()

    har = args.har.expanduser().resolve()
    out_dir = (args.out or default_out_dir(har)).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = load_entries(har)
    blocks = whiteboard_blocks(entries)
    images = whiteboard_images(entries)
    image_matches, unmatched_images = match_images_to_blocks(blocks, images)

    source_images: dict[int, str] = {}
    for idx, block in enumerate(blocks):
        image = image_matches.get(idx)
        if not image:
            continue
        number = idx + 1
        ext = image["ext"]
        target = out_dir / f"whiteboard-{number:02d}.source.{ext}"
        target.write_bytes(image["bytes"])
        source_images[idx] = target.name

    unmatched_names: list[str] = []
    for idx, image in enumerate(unmatched_images, start=1):
        ext = image["ext"]
        target = out_dir / f"whiteboard-extra-{idx:02d}.source.{ext}"
        target.write_bytes(image["bytes"])
        unmatched_names.append(target.name)
    related_image_names = write_related_images(out_dir, entries) if args.extract_related_images else []

    summaries = []
    for idx, block in enumerate(blocks):
        number = idx + 1
        svg = render_svg(block["data"], f"{har.stem} whiteboard {number:02d}", square=not args.no_square, margin=args.margin, fit_text=args.fit_text)
        (out_dir / f"whiteboard-{number:02d}.simple.svg").write_text(svg, encoding="utf-8")
        summary_item = block_summary(block, idx)
        summary_item["block_token"] = block_token(block)
        summary_item["source_image"] = source_images.get(idx)
        summary_item["source_image_entry"] = image_matches.get(idx, {}).get("entry") if idx in image_matches else None
        summaries.append(summary_item)

    summary = {
        "har": str(har),
        "entries": len(entries),
        "whiteboard_blocks": len(blocks),
        "cdp_whiteboard_images": len(images),
        "blocks": summaries,
        "unmatched_images": unmatched_names,
        "related_images": related_image_names,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_index(out_dir, har, summaries, len(images), unmatched_names)
    if args.audit_package:
        write_audit_package(args.audit_package.expanduser().resolve(), har=har, entries=entries, blocks=blocks, images=images, summaries=summaries, out_dir=out_dir)

    print(json.dumps({"out_dir": str(out_dir), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
