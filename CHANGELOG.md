# Changelog

## v1.1.1 - 2026-06-12

- 非矩形形状的文字按内接矩形排版（菱形 1/2、椭圆 1/√2），换行点与飞书一致，
  修复菱形文字戳出斜边（如 "badcase分析结|果" → "badcase|分析结果"）

## v1.1.0 - 2026-06-12

通用化重构：渲染规则全部改为数据驱动，删除内容特判，并补齐回归测试安全网。

### 渲染修正（对照源图逐项验证）

- **删除全部文本特判**（`is_output_node`/`is_agent_box`）：渲染颜色不再依据节点文字内容。原"含 agent 即深蓝"的特判实际渲染错误——源图中无样式数据的节点是浅色默认样式
- **主题色板数据驱动还原**：从多份真实 HAR 的 `cdp-whiteboard` 源图逐节点像素采样，反推 `fillColorCode` 色板（0/1/2/6/9/10/16），并修正码 10 为 `#5178c6`
- **主题码优先于 fillV2**：用户在飞书 UI 换主题色只更新 code、旧 fillV2 残留。已用真实样本验证（显式绿+码 6 → 飞书渲染粉）
- **按形状默认色**取代"椭圆众数猜色"hack：处理框浅蓝灰、椭圆浅紫、菱形奶黄、卡片深蓝（均采样验证）
- **文字颜色按底色亮度自动反白**（WCAG 相对亮度），取代逐形状文字色特判
- **z-order 按面积降序**：真实数据 `zIndexCapabilityV2` 为空且文档顺序不可靠，大框垫底、小框浮上（修复"评测体系"大框盖住评分小框）
- **连接线颜色只取 borderV2**：连接线 `fillV2` 是无效占位（恒为 `#bacefd`），源图线条始终为 border 色（修复连接线整体偏浅蓝）
- **新增连接线 caption 渲染**：`connectorV2.captions` 沿线弧长参数 `t` 定位，白底垫片（修复"调用工具/多轮交互"标签丢失）

### 工程

- 新增 `tests/`：合成 HAR fixture（覆盖思维导图/表格/便签/嵌套/截断恢复等真实样本盲区）+ golden 逐字节回归 + 真实 HAR 本地快照对比脚本
- `absolute_nodes` 去掉递归 deepcopy（深嵌套大白板 O(n²) → O(n)）
- 图片与 block 匹配改用下标身份，不再做整图 bytes 值比较
- `all-images/index.md` 的 URL 去 query，防飞书签名 token 泄露
- `--fit-text` 由全局可变量改为参数传递；shapeType 魔法数字命名为常量
- SKILL.md 瘦身，渲染器实现细节移至 `references/renderer-notes.md`

## v1.0.0 - 2026-06-05

第一个稳定版，用本地 HAR 提取飞书/Lark 白板数据，并生成可编辑、可审查的 SVG 预览。

### 新增

- 增加 `process_har.py`，作为稳定的 HAR 解析和 SVG 渲染入口。
- 从本地 HAR 中提取 `/space/api/whiteboard/block` 响应。
- 从 HAR 中提取 `cdp-whiteboard` 源图。
- 输出 `summary.json`、`index.md`、`whiteboard-XX.simple.svg` 和匹配后的 `whiteboard-XX.source.*`。
- 增加 `--audit-package`，由脚本抽取精简审核包，避免评审模型默认读取完整大 HAR。
- 增加 `--margin`，控制 SVG 画布留白。
- 增加 `--fit-text`，作为可选的文字溢出兜底。
- 增加 Chrome DevTools 抓 HAR 简单教程。

### 渲染改进

- 递归展开嵌套 `children`，并叠加父节点相对坐标。
- 默认保留飞书原始 `textV2.fontSize`。
- 分开处理 `textV2.horizontalAlign` 和 `textV2.verticalAlign`。
- 支持常见流程图形状、圆角节点、椭圆、菱形、圆柱、分组、便签和表格。
- 根据 `mindMap.parentId` 渲染思维导图连线。
- 思维导图连线垂直对齐节点中心。
- 文本型思维导图节点按“可见文字边缘 + 小间距”接线，避免线条压字或短词后留白过大。
- 支持思维导图右侧和左侧分支。
- 普通 connector 保留 `fillV2`/border 颜色，并按颜色生成箭头 marker。
- 源图和 block 改为按 `blockToken` 与 `cdp-whiteboard-<token>` 匹配，不再只按出现顺序。
- 给空白/异常 block 加保护，避免 `board_bbox()` 直接崩溃。
- 表格优先使用 `table.metaInfo` 行列尺寸，缺失时用 `tableRowInfo` 推导行列。
- 优化文字宽度估算，区分英文、空格、全角括号和中文标点。

### 验证

- 用 `060501zhipu-ai.feishu.cn.har` 验证，包含 3 个白板 block 和 3 张 `cdp-whiteboard` 源图。
- 多轮对比源 PNG 与 SVG 预览，修正缺失节点、字号、对齐、画布留白、mind-map 连线锚点等问题。
- 跑过 `python3 -m py_compile` 语法检查。
- 使用脚本抽取的 audit package 让 Claude 进行两轮 readonly 审核，并按审核结果修复核心问题。

### 已知限制

- SVG 是对飞书原生渲染的近似还原，不是飞书官方渲染器。
- 字体精确宽度仍受本机 SVG 渲染器和字体影响。
- 左侧 mind-map 分支、缺失表格 metadata、connector 起点箭头已经有代码支持，但还需要更多真实 HAR 样本回归。
