---
name: web-gui-tester
description: "Use the browser automation tooling available in the session to test web frontends interactively in a purely GUI-based, black-box manner: simulate real user clicks, text input, scrolling, and other actions; use screenshots for visual verification and read-only DOM inspection for cross-validation; and produce a final test report. Suitable for verifying whether web functionality works correctly, reproducing frontend bugs, checking interaction feedback and layout styling, or conducting exploratory testing of a page. Use this skill when the user asks to test a webpage/frontend feature, verify UI behavior, reproduce a page bug, or provides only a URL and asks you to “test it.”"
---

# Web GUI 纯黑盒测试技能 (`web-gui-tester`)

本技能指导 Agent 利用当前会话中提供的浏览器自动化工具（无论是 `control-browser` REPL 模式、标准 Playwright MCP，还是其他浏览器工具），以纯粹的真实用户视角对 Web 前端进行**黑盒交互测试**、**缺陷复现**与**视觉走查**，并输出结构化测试报告。

---

## 一、核心准则 (Core Principles)

1. **纯 GUI 黑盒交互 (Pure Black-Box Testing)**：
   - 只能与页面上真实可见、可点击交互的元素打交道，完全模拟真实用户的点击、输入、滚动行为。
   - 严禁通过注入执行有副作用的 JavaScript 代码来强行改变页面状态、绕过前端校验逻辑或模拟点击事件。
2. **忠于真实页面 (Fidelity to Actual Behavior)**：
   - 所有结论必须有确凿证据支撑。如果标准操作失败，应如实记录并分析原因，不得使用非正常手段“伪造”测试通过。
3. **测试与修复严格分离 (Separation of Testing and Fixing)**：
   - 测试阶段严禁修改被测系统的源代码。若遇到阻断性 Bug，应详细记录复现步骤并跳过该路径，继续验证其他不受影响的功能。只有在测试完整结束且用户要求修复时，才进入代码修改阶段。
4. **DOM 与视觉双重校验 (Cross-Validate DOM & Visuals)**：
   - 每个测试用例的判定必须结合“无障碍 DOM 快照状态”与“关键视觉截图证据”，二者互为印证，缺一不可。

---

## 二、测试四阶段工作流 (Four-Phase Workflow)

### 阶段一：用例规划与分级评估 (Assessment & Planning)
当收到测试目标后，快速组织测试重点（按优先级排序）：
- **P0 核心主流程 (Main Flow)**：页面最核心的业务路径（如表单填写与提交、主数据检索、核心业务流）。
- **P1 交互反馈验证 (Feedback & States)**：操作后的即时反馈（Loading 加载状态、成功/失败提示 Toast、按钮禁用状态、路由跳转）。
- **P2 输入边界与异常用例 (Boundary & Edge Cases)**：空输入提交、超长字符、特殊字符、重复点击/提交、防抖与校验提示。
- **P3 界面与布局视觉走查 (Layout & Styling)**：元素重叠遮挡、文本溢出省略、响应式布局自适应、视觉样式一致性。

### 阶段二：环境准备与前置状态初始化 (Environment Preparation)
在正式测试启动前，可通过后端命令、配置修改或种子数据初始化必要环境：
- 启动/重启本地开发服务（如 `npm run dev`）；
- 初始化测试账号或测试数据；
- **注意**：环境准备完毕后，必须明确声明：“测试环境准备完成，正式进入黑盒测试阶段”。进入后全面受黑盒准则约束。

### 阶段三：执行循环 (Action → Observation → Decision)
1. **元素定位**：严格基于最新 DOM 快照/ARIA 树获取可靠定位器（`getByRole`、`getByLabel`、`getByText`）。
2. **真实交互**：执行单次点击、输入、选择操作。
3. **状态校验**：
   - 代码层（只读）：检查 DOM 节点变化、提示文本出现、URL 变更。
   - 视觉层（截图）：在关键动作后捕获截图，确保证据链完整。
4. **异常处理**：若元素无法定位或加载超时，先重新获取快照分析原因（页面崩溃、网络超时还是定位失效），严禁死循环重试。

### 阶段四：输出标准化测试报告 (Reporting)
测试结束后，生成包含以下内容的 Markdown 报告：
- **测试概况**：被测 URL、测试时间、执行状态总览（Pass / Fail / Blocked 数量）。
- **用例详情列表**：
  - 用例编号与测试项（如 P0-登录主流程）；
  - 操作步骤与预期结果；
  - 实际结果与判定结论；
  - **证据关联**：嵌入对应的界面截图（如 `![登录成功截图](./screenshots/login_success.png)`）与关键 DOM 状态。
- **缺陷分析与改进建议 (Bug Findings & Recommendations)**：详细记录 Bug 的触发条件、控制台错误、截图证据以及潜在原因分析。
