#!/usr/bin/env python3
"""生成合成 HAR fixture，覆盖真实样本测不到的渲染路径。

真实 zhipu 样本里没有思维导图、表格、便签，这个 fixture 专门补盲区，
同时锁定文本特判（agent/输出结果）的现有行为。
确定性输出：同样的代码永远生成同样的字节。
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ============================================================
# 假图片：只需 magic bytes 正确，无需是合法图片
# ============================================================
FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"FAKE-PNG-PAYLOAD"
FAKE_JPG = b"\xff\xd8\xff\xe0" + b"FAKE-JPG-PAYLOAD"


def fill(color: int) -> dict:
    return {"fillStyleList": {"data": [{"fillType": 0, "color": color, "active": True, "opacity": 100}]}}


def border(color: int, width: float = 1.5, **advance) -> dict:
    item: dict = {"lineWidth": width}
    if advance:
        item["advanceSettings"] = advance
    return {"colorFillStyleList": {"data": [{"color": color}]}, "borderStyleItem": item}


def text(content: str, size: int = 14, **extra) -> dict:
    return {"text": content, "fontSize": size, "horizontalAlign": 1, "verticalAlign": 1, **extra}


def base(x: float, y: float, w: float, h: float) -> dict:
    return {"x": x, "y": y, "width": w, "height": h}


# ============================================================
# Block 1：基础形状 + 特判锁定 + 嵌套分组 + 便签 + 连接线
# ============================================================
BLOCK1_NODES = [
    {"id": "n-rect", "info": {"baseV2": base(0, 0, 200, 80), "compositeShape": {"shapeType": 1},
     "textV2": text("圆角矩形"), "fillV2": fill(0xEEF2FF), "borderV2": border(0x222222)}},
    {"id": "n-ellipse", "info": {"baseV2": base(260, 0, 160, 90), "compositeShape": {"shapeType": 2},
     "textV2": text("椭圆"), "fillV2": fill(0xFFE7E7)}},
    {"id": "n-diamond", "info": {"baseV2": base(480, 0, 140, 100), "compositeShape": {"shapeType": 10},
     "textV2": text("菱形判断"), "fillV2": fill(0xFFF6D6)}},
    {"id": "n-cylinder", "info": {"baseV2": base(680, 0, 120, 130), "compositeShape": {"shapeType": 4},
     "textV2": text("数据库"), "fillV2": fill(0xE3F2E9)}},
    {"id": "n-dashed-ellipse", "info": {"baseV2": base(860, 0, 150, 90), "compositeShape": {"shapeType": 13},
     "textV2": text("虚线椭圆"), "borderV2": border(0x888888)}},
    {"id": "n-card56", "info": {"baseV2": base(0, 180, 220, 70), "compositeShape": {"shapeType": 56},
     "textV2": text("主题卡片56")}},
    # ---- 反过拟合锁定：含 agent / "输出结果" 文字的节点必须走通用规则
    #      （无颜色数据 -> 形状默认色），渲染禁止看文字内容 ----
    {"id": "n-agent", "info": {"baseV2": base(280, 180, 220, 70), "compositeShape": {"shapeType": 8},
     "textV2": text("Agent 调度器"),
     "theme": {"fillColorCode": -1}}},
    {"id": "n-output", "info": {"baseV2": base(560, 180, 220, 70), "compositeShape": {"shapeType": 8},
     "textV2": text("输出结果"),
     "theme": {"fillColorCode": -1}}},
    # ---- 主题色板：深紫码自动反白字，浅绿码自动深字 ----
    {"id": "n-theme9", "info": {"baseV2": base(840, 180, 200, 70), "compositeShape": {"shapeType": 8},
     "textV2": text("主题深紫9"), "theme": {"fillColorCode": 9}}},
    {"id": "n-theme16", "info": {"baseV2": base(1080, 180, 200, 70), "compositeShape": {"shapeType": 8},
     "textV2": text("主题浅绿16"), "theme": {"fillColorCode": 16}}},
    # ---- 优先级锁定：主题码(6 粉)必须压过残留的显式 fillV2(绿) ----
    {"id": "n-conflict", "info": {"baseV2": base(1320, 180, 200, 70), "compositeShape": {"shapeType": 2},
     "textV2": text("码优先"), "fillV2": fill(0xDFF5E5), "theme": {"fillColorCode": 6}}},
    # ---- z-order 锁定：后出现的大框不得盖住先出现的小框（面积降序）----
    {"id": "n-small-inner", "info": {"baseV2": base(40, 920, 140, 60), "compositeShape": {"shapeType": 8},
     "textV2": text("小框在上"), "theme": {"fillColorCode": 9}}},
    {"id": "n-big-cover", "info": {"baseV2": base(0, 880, 400, 200), "compositeShape": {"shapeType": 8},
     "textV2": {"text": "大框在底", "fontSize": 14, "horizontalAlign": 0, "verticalAlign": 0},
     "theme": {"fillColorCode": 0}}},
    # ---- 列表 + 加粗 override 文本 ----
    {"id": "n-list", "info": {"baseV2": base(0, 320, 280, 140), "compositeShape": {"shapeType": 1},
     "fillV2": fill(0xFFFFFF), "borderV2": border(0x222222),
     "textV2": {"text": "第一点\n子项缩进\n编号项", "fontSize": 14, "horizontalAlign": 0, "verticalAlign": 0,
                "paragraphStyles": {"data": [{"indent": 0, "listType": 1}, {"indent": 1, "listType": 1}, {"indent": 0, "listType": 2}]},
                "overrideInfo": {"styleOverrideTable": {"data": {"5": {"fontWeight": "bold"}}},
                                 "characterStyleOverrides": {"data": ["5", "5", "5", "0", "0", "0", "0", "0", "0", "0", "0"]}}}}},
    # ---- 独立文本（无 compositeShape）----
    {"id": "n-text", "info": {"baseV2": base(340, 320, 300, 40),
     "textV2": {"text": "独立说明文字", "fontSize": 16, "horizontalAlign": 0, "verticalAlign": 0,
                "fill": fill(0x5C6472)}}},
    # ---- 便签（带作者）----
    {"id": "n-sticky", "info": {"baseV2": base(700, 320, 220, 160),
     "stickyNoteProps": {"showAuthorInfo": True, "authorInfo": {"name": "测试员"}},
     "textV2": text("便签内容\n第二行", 13), "fillV2": fill(0xFFF0C2)}},
    # ---- 三层嵌套分组：分组 → 子矩形 → 孙椭圆（验证坐标叠加）----
    {"id": "n-group", "info": {"baseV2": base(0, 560, 500, 300), "title": "嵌套分组"},
     "children": [
         {"id": "n-child", "info": {"baseV2": base(40, 40, 240, 200), "compositeShape": {"shapeType": 1},
          "textV2": text("子节点"), "fillV2": fill(0xE8F0FE), "borderV2": border(0x4477CC)},
          "children": [
              {"id": "n-grandchild", "info": {"baseV2": base(30, 90, 120, 70), "compositeShape": {"shapeType": 2},
               "textV2": text("孙节点"), "fillV2": fill(0xFFFFFF), "borderV2": border(0x4477CC)}},
          ]},
     ]},
    # ---- 虚线 connector，双向箭头 + 拐点 + 自定义颜色 ----
    {"id": "n-conn-dashed", "info": {"baseV2": base(600, 560, 0, 0),
     "connectorV2": {"startPoint": {"x": 0, "y": 0}, "endPoint": {"x": 260, "y": 140},
                     "turningPoints": {"data": [{"x": 130, "y": 0}, {"x": 130, "y": 140}]}},
     "fillV2": fill(0xE74C3C),
     "borderV2": border(0xE74C3C, 2.5, start=1, end=1, dashes=[4, 4])}},
    # ---- 普通 connector，无箭头，颜色取 borderV2，带沿线 caption ----
    {"id": "n-conn-plain", "info": {"baseV2": base(600, 760, 0, 0),
     "connectorV2": {"startPoint": {"x": 0, "y": 0}, "endPoint": {"x": 300, "y": 0},
                     "turningPoints": {"data": []},
                     "captions": {"data": [{"t": 0.5, "textStyle": {"text": "线上标签", "fontSize": 13,
                                                                    "horizontalAlign": 1, "verticalAlign": 1}}]}},
     "borderV2": border(0x2C3E50, 1.5)}},
]

# ============================================================
# Block 2：思维导图（左右分支）+ 表格（有/无 metaInfo）
# ============================================================


def table_cell(content: str, fill_color: int | None = None, col_span: int = 1) -> dict:
    style: dict = {"textProps": {"text": content, "fontSize": 13, "horizontalAlign": 0, "verticalAlign": 0}}
    if fill_color is not None:
        style["fillProps"] = fill(fill_color)
    return {"cellBaseInfo": {"colSpan": col_span}, "styleInfo": style}


BLOCK2_NODES = [
    # ---- 思维导图：根 + 右子 + 左子（shapeType 57 文本节点）----
    {"id": "mm-root", "info": {"baseV2": base(500, 0, 180, 60), "compositeShape": {"shapeType": 8},
     "textV2": text("中心主题"), "fillV2": fill(0x517FD6), "mindMap": {"parentId": ""}}},
    {"id": "mm-right", "info": {"baseV2": base(780, -60, 140, 40), "compositeShape": {"shapeType": 57},
     "textV2": {"text": "右分支", "fontSize": 14, "horizontalAlign": 0, "verticalAlign": 1},
     "mindMap": {"parentId": "mm-root"}}},
    {"id": "mm-right2", "info": {"baseV2": base(780, 40, 160, 40), "compositeShape": {"shapeType": 57},
     "textV2": {"text": "右分支较长文字", "fontSize": 14, "horizontalAlign": 0, "verticalAlign": 1},
     "mindMap": {"parentId": "mm-root"}}},
    {"id": "mm-left", "info": {"baseV2": base(240, -10, 140, 40), "compositeShape": {"shapeType": 57},
     "textV2": {"text": "左分支", "fontSize": 14, "horizontalAlign": 2, "verticalAlign": 1},
     "mindMap": {"parentId": "mm-root"}}},
    # ---- 表格 A：带 metaInfo 行列尺寸 ----
    {"id": "t-meta", "info": {"baseV2": base(0, 200, 360, 120),
     "table": {"metaInfo": {"columns": {"data": [{"size": 120}, {"size": 240}]},
                            "rows": {"data": [{"size": 40}, {"size": 80}]}},
               "tableRowInfo": {"data": [
                   {"data": [table_cell("列A", 0xF2F3F5), table_cell("列B", 0xF2F3F5)]},
                   {"data": [table_cell("值1"), table_cell("值2", 0xE8F0FE)]},
               ]}}}},
    # ---- 表格 B：无 metaInfo，靠 tableRowInfo 推导 + colSpan ----
    {"id": "t-nometa", "info": {"baseV2": base(460, 200, 300, 90),
     "table": {"tableRowInfo": {"data": [
         {"data": [table_cell("跨两列表头", None, 2)]},
         {"data": [table_cell("甲"), table_cell("乙")]},
     ]}}}},
]


def block_entry(token: str, nodes: list) -> dict:
    body = {"code": 0, "data": {"nodes": nodes}}
    return {
        "request": {"method": "GET",
                    "url": f"https://example.feishu.cn/space/api/whiteboard/block?blockToken={token}&t=1"},
        "response": {"status": 200,
                     "content": {"mimeType": "application/json", "text": json.dumps(body, ensure_ascii=False)}},
    }


def image_entry(url: str, mime: str, data: bytes) -> dict:
    return {
        "request": {"method": "GET", "url": url},
        "response": {"status": 200,
                     "content": {"mimeType": mime, "encoding": "base64",
                                 "text": base64.b64encode(data).decode()}},
    }


ENTRIES = [
    block_entry("SYNTH01", BLOCK1_NODES),
    block_entry("SYNTH02", BLOCK2_NODES),
    # 无 token 匹配的图，按顺序兜底分给 block1
    image_entry("https://example.feishu.cn/file/cdp-whiteboard-UNKNOWN/render?token=secret-sig-1",
                "image/png", FAKE_PNG),
    # MIME 谎报 png、实际 JPEG magic bytes：验证 magic 优先
    image_entry("https://example.feishu.cn/file/cdp-whiteboard-SYNTH02/render?token=secret-sig-2",
                "image/png", FAKE_JPG),
    # 多出来的一张 → whiteboard-extra-01
    image_entry("https://example.feishu.cn/file/cdp-whiteboard-EXTRA/render?token=secret-sig-3",
                "image/png", FAKE_PNG),
    # 文档封面图：只在 --extract-related-images 时提取
    image_entry("https://example.feishu.cn/space/api/box/stream/download/v2/cover/cv123?token=secret-sig-4",
                "image/png", FAKE_PNG),
    # 无关请求：应被全部忽略；放在最后，截断版砍掉它
    {"request": {"method": "GET", "url": "https://example.feishu.cn/page.html"},
     "response": {"status": 200, "content": {"mimeType": "text/html", "text": "<html>ignored</html>"}}},
]


def main() -> None:
    har_text = json.dumps({"log": {"version": "1.2", "entries": ENTRIES}}, ensure_ascii=False, indent=1)
    (HERE / "synthetic.har").write_text(har_text, encoding="utf-8")

    # 截断版：砍在最后一个 entry（html 页面）中间，验证恢复逻辑能拿回前面 6 条
    cut = har_text.rfind('"url": "https://example.feishu.cn/page.html"')
    (HERE / "truncated.har").write_text(har_text[:cut], encoding="utf-8")
    print(f"synthetic.har: {len(ENTRIES)} entries; truncated.har cut at byte {cut}")


if __name__ == "__main__":
    main()
