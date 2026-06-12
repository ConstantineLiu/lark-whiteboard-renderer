# Changelog

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
