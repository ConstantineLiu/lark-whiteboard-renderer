# 渲染器实现笔记

> 仅在做 PNG-Guided Refinement（改 `scripts/process_har.py` 渲染逻辑）时需要读。
> 改动前先跑 `python3 -m unittest discover tests`，改完重跑 + 目检。
>
> [PROTOCOL]: 变更时更新此文档，然后检查 SKILL.md

## 颜色解析（核心设计，全部数据驱动，禁止按文字内容特判）

填充色三层优先级（`effective_shape_fill`）：

1. `theme.fillColorCode >= 0` 且在 `THEME_FILL` 色板 → 用色板色
2. 显式 `fillV2.fillStyleList` → 用显式色
3. 都没有 → `SHAPE_DEFAULT_FILL` 按 shapeType 给默认色（处理框浅蓝灰、椭圆浅紫、菱形奶黄、卡片深蓝）

关键事实：**主题码优先于 fillV2**。用户在飞书 UI 里换主题色只更新
fillColorCode，旧 fillV2 残留在数据里。已在真实样本验证（显式绿 + 码 6 粉
→ 飞书渲染粉色）。

文字色与之同构（`forced_text_color`）：主题码生效时按底色亮度全自动反白
（显式文字色同样视为残留）；否则尊重显式文字色，缺失时按亮度兜底。
亮度判断用 WCAG 相对亮度（`is_dark`，阈值 140）。

`THEME_FILL` 色板和 `SHAPE_DEFAULT_FILL` 默认色都是从真实 HAR 的
`cdp-whiteboard` 源图逐节点像素采样反推的（多板交叉验证）。遇到色板缺码：
先在源图上采样该码节点的真实颜色，再补表——不要猜。

## 连接线

- 线色只取 `borderV2.colorFillStyleList`（缺省 `#222222`）。连接线的
  `fillV2` 是无效占位（真实数据恒为 `#bacefd`），源图线条从不跟随它
- 虚线：`theme.connectStyleCode == 3` 或 `advanceSettings.dashes`
- 箭头：`advanceSettings.start/end`，marker 按线色逐色生成
- 标签：`connectorV2.captions.data[].textStyle`，`t` 为沿折线弧长的参数位置
  （`point_along`），渲染时垫白底矩形防止线条穿字

## 层级（z-order）

数据里 `zIndexCapabilityV2` 为空，文档顺序也不可靠（真实样本中大框出现在
小框之后却渲染在底层）。规则：

1. 容器层最先：table、带 title 的 group、SHAPE_FRAME(11)
2. 思维导图连线、普通连接线
3. 普通形状按 **bbox 面积降序**（大的垫底、小的浮上，稳定排序保留同面积文档序）
4. 文字最后

## 思维导图

- 节点 = `info.mindMap` 存在；树边按 `mindMap.parentId` 连接
- 连线垂直锚点取节点盒中心；支持左右两侧分支
- 文本节点（shapeType 57）的水平锚点按"可见文字宽度 + MIND_TEXT_GAP"
  计算（`mind_anchor_left/right` + `visual_units` 字宽估算），避免线条压字
  或短词后留白过大

## 表格

- 行列尺寸优先 `table.metaInfo.rows/columns`，缺失时按 `tableRowInfo`
  行数/最大跨列数均分
- 首行无填充时给浅灰表头色
- 已知限制：`colSpan > 1` 只参与列数推导，渲染不合并单元格

## 文本

- 默认保留飞书原始 `textV2.fontSize`；`--fit-text` 仅在溢出时按盒尺寸缩字
  （`fitted_font_size`）
- `horizontalAlign` / `verticalAlign` 是独立轴，分开映射 flex 属性
- 列表（`paragraphStyles.listType`）渲染圆点/序号；`overrideInfo` 支持
  按字符区间加粗
- 字宽估算 `visual_units` 区分 ASCII、空格、中文标点、全角括号

## 图片匹配

- block ↔ 源图按 `blockToken` ↔ `cdp-whiteboard-<token>` 配对，剩余按顺序
  兜底；完全多余的写 `whiteboard-extra-XX.source.*`
- 扩展名以 magic bytes 优先（飞书会报 PNG MIME 实发 JPEG）

## 画布

- 默认 2560×2560 方形居中，`--no-square` 保持自然纵横比
- `--margin N` 控制画布留白（白板坐标单位，默认 160）

## 验证手段

- `python3 -m unittest discover tests` — 合成 fixture vs golden 逐字节
- `bash tests/run_real_har_check.sh` — 真实 HAR 与本地基准 diff（`--rebase` 重建）
- 视觉对照：Chrome headless 截图 SVG，与 `whiteboard-XX.source.*` 并排比对；
  `qlmanage -t` 可做快速预览但长图会变形
