# HAR 抓取教程

把飞书/Lark 白板给 agent 处理时，最稳的输入是 Chrome 导出的完整 HAR 文件。

## Chrome 操作步骤

1. 用 Chrome 打开飞书/Lark 文档或白板页面。
2. 打开开发者工具：
   - macOS：`Command + Option + I`
   - 或者右键页面，点 `检查`
3. 切到 `Network` 面板。
4. 点 Network 里的清空按钮，把旧请求清掉。
5. 刷新飞书页面。
6. 等白板内容加载得差不多。白板很大时，可以稍微拖动画布或缩放一次，让懒加载内容也出来。
7. 加载完后不要点某个具体请求，也不要挑某个包。
8. 直接找 Network 面板里的“下载/导出 HAR”按钮，导出完整 HAR。
   - Chrome 常见文案是 `Export HAR...`
   - 有些版本显示为下载图标
   - 目标是导出整页 Network 记录，不是导出单个请求
9. 把 `.har` 文件保存到本地。
10. 把这个 HAR 文件路径交给 agent，让 agent 调用 `feishu-whiteboard-har` skill 处理。

## Agent 需要什么

agent 只需要 HAR 文件路径。它会在本地读取 HAR，提取飞书 `whiteboard/block` 响应和 `cdp-whiteboard` 图片，然后生成 SVG 预览和源 PNG。

## 隐私提醒

HAR 可能包含页面 URL、请求信息、响应内容，以及少量认证相关 header 或 cookie。只把 HAR 发给有权限查看这个飞书页面的工具或人。
