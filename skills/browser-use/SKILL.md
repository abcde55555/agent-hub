---
name: browser-use
description: "Interactive browser automation and web testing suite. Use to open URLs, inspect pages using ARIA DOM snapshots, click buttons, fill forms, take screenshots, and run web testing workflows using the browser-use MCP server."
---

# Browser Use 自动化与网页交互全能套件 (`/browser-use`)

当用户输入 `/browser-use` 或需要操作浏览器、自动化测试网页、抓取渲染内容、排查前端交互 Bug 时触发本技能。

---

## 1. 核心可用工具集 (`browser-use` MCP)

本技能直接驱动已挂载的 `browser-use` MCP 服务，包含以下核心工具：

- `browser_navigate`: 打开目标 URL（支持等待级别 `domcontentloaded` / `load` / `networkidle`）
- `browser_snapshot`: 获取当前页面精炼的 ARIA 无障碍语义树快照（定位元素的核心依据）
- `browser_click`: 精准点击元素（支持 `role` + `name`、`text`、或 CSS 选择器）
- `browser_type`: 在输入框或文本域中输入内容（默认自动清空旧文本）
- `browser_screenshot`: 捕获页面截图（自动落盘至 `screenshots/` 目录并向大模型回传多模态图像）
- `browser_tabs`: 多标签页管理（查看列表、新建标签、切换活跃标签）
- `browser_exec_js`: 在浏览器上下文中执行自定义异步 JavaScript 代码
- `browser_close`: 关闭浏览器并清理所有会话资源

---

## 2. 交互操作基本范式 (Action Loop)

1. **第一步：导航到目标网页**
   ```text
   调用 browser_navigate(url="https://example.com")
   ```
2. **第二步：获取页面语义快照 (ARIA Tree)**
   ```text
   调用 browser_snapshot()
   从返回的语义树中寻找目标按钮、链接或输入框的角色（Role）和名称（Name）。
   ```
3. **第三步：精准交互**
   ```text
   调用 browser_click(role="button", name="提交")
   或
   调用 browser_type(text="admin@example.com", name="邮箱地址")
   ```
4. **第四步：状态校验与截图**
   - 检查 URL、标题或页面元素变化；
   - 遇到关键验证点、样式排版走查或 Bug 证据留存，调用 `browser_screenshot()` 捕获多模态截图。

---

## 3. 子技能联动

- 需进行严格定位与高级选择器调试时，参考 **`control-browser`** 技能；
- 需进行端到端纯黑盒测试、测试用例规划（P0-P3）与输出测试报告时，联动 **`web-gui-tester`** 技能。
