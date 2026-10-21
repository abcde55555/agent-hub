# agent-hub 项目介绍

以下文案基于仓库当前实现，可用于 GitHub About、项目分享和介绍页。

## 一句话定位

**一套配置，多个 Agent，多台设备。**

agent-hub 是一个用 Git 管理 AI 编程助手的 Skills、MCP 服务配置和全局规则，并通过脚本在工具与设备之间复用的配置中心。

## GitHub About

中文：

> 统一管理 AI 编程助手的 Skills、MCP 和全局规则，通过 agent-sync 分发配置，通过 Git 跨设备复用。

English:

> A Git-backed hub for coding-agent skills, MCP servers, and global rules. Distribute your setup across tools and reuse it across machines.

## 简短介绍

当你同时使用 Claude Code、Codex、Antigravity 等编程助手时，规则、技能与 MCP 配置很容易散落在不同目录。agent-hub 将可复用内容集中到一个 Git 仓库，通过 `agent-sync` 创建技能与规则链接、生成受管配置，再用检查命令确认本机状态。换工具、换设备时，可以沿用已有积累，并按本机环境配置依赖与凭据。

## 完整介绍

AI 编程助手用得越久，积累的价值就越多：一套有效的代码审查流程、一组常用 MCP 服务、一份经过反复调整的工作规则，以及适合自己的需求分析、开发与验证方法。这些内容一旦分散在多个工具和设备中，维护就会变成重复劳动。

agent-hub 把这些资产放进 `~/.agents`，用 Git 保存和传递内容。Skills 以 `SKILL.md` 组织，全局规则写入 `AGENTS.md`，MCP 服务通过统一声明记录地址、目标工具与依赖。随仓库携带的 `agent-sync` 脚本负责将这些内容应用到本机工具：建立技能与规则链接，合并 JSON 配置，或更新 TOML 中的受管区域。

你可以先用它管理自己的编程环境，再逐步加入适合自己的技能。仓库中的技能覆盖从想法澄清、原型试用、任务拆分，到实现、审查、浏览器验证和逆向分析的不同任务。Codex 产品规划与执行技能还提供一套协作约定，并可生成供人按需查看的项目 HTML 全景。

日常使用围绕一个简单循环：修改 Hub 正本，预览同步，应用配置，再检查结果。另一台设备拉取相同仓库后，结合自己的解释器、依赖、凭据和网络环境重新应用。随着工作方式不断改进，这些积累也可以持续复用。

## English introduction

agent-hub keeps reusable coding-agent assets in one Git repository: skills, MCP server declarations, and global working rules. Its bundled `agent-sync` script distributes them through symbolic links and managed configuration for Claude Code, Codex, and Antigravity. dsh and OpenCode rely on their own discovery of the Hub's skills directory.

The collection includes workflows for discovery, prototyping, implementation, review, browser testing, and reverse engineering. You can inspect the current setup, preview changes, apply configuration, and check MCP handshakes, skill counts, and rule links. Git carries the source files between machines, while dependencies, credentials, and local state are configured separately on each machine.

## 适合哪些场景

| 场景 | agent-hub 的作用 |
| --- | --- |
| 同时使用多个编程助手 | 在 Hub 维护规则和技能，由脚本处理已支持的配置差异 |
| 经常更换开发设备 | 拉取仓库后，在本机应用配置并检查依赖和连接 |
| 希望沉淀有效工作方式 | 将反复使用的流程整理为技能，随 Git 维护 |
| 需要接手或持续推进产品项目 | 通过 Codex 产品技能整理任务、交接、验证与项目全景 |

## 推荐 Topics

`ai-agents` · `coding-agents` · `agent-skills` · `mcp` · `configuration-management` · `dotfiles` · `developer-tools`

## 使用文案时的范围

对外介绍可突出当前已经具备的资产管理、配置分发和检查能力。自动同步 hooks / prompts / subagents、自动登录、实时项目监控和全平台兼容均不在当前实现范围内。具体配置路径、预设依赖和已知缺口以 [使用指南](usage.md) 为准。
