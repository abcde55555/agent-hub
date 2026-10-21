# agent-hub 使用指南

[返回 README](../README.md) · [English README](../README.en.md)

这份指南说明当前 `bin/agent-sync` 的行为。默认 Hub 路径为 `~/.agents`；可通过 `AGENT_SYNC_HUB` 指向另一目录。该变量只改变 Hub 位置，各工具的配置仍写入当前用户目录。

## 首次使用

准备 Git、Python 3.11+ 和支持符号链接的环境。使用浏览器 MCP 或其他外部服务时，再按服务要求准备 Node.js、npm、浏览器等依赖。客户端安装与账号登录分别完成。

1. 获取仓库，或使用自己的 Fork。
2. 调整 `AGENTS.md`，将 `mcp/servers.json` 中的维护者预设改成自己需要的服务。
3. 配置本机变量和依赖。仅体验技能与规则时，可先使用空的 `mcpServers` 对象。
4. 运行 `apply --dry-run` 查看计划，再运行 `apply`。
5. 运行 `doctor`，重启相关客户端会话，并实际试用一项技能。

```bash
python3 "$HOME/.agents/bin/agent-sync" apply --dry-run
python3 "$HOME/.agents/bin/agent-sync" apply
python3 "$HOME/.agents/bin/agent-sync" doctor
```

默认 `apply` 会准备 Claude Code、Codex、Antigravity 的配置路径，不以客户端是否已经安装作为过滤条件。限制本次写入范围可用：

```bash
python3 "$HOME/.agents/bin/agent-sync" apply --targets claude,codex --dry-run
python3 "$HOME/.agents/bin/agent-sync" apply --targets claude,codex
```

`--targets` 仅属于 `apply`，取值为 `claude,codex,agy`。它不会限制 `deps` 或 `doctor` 的检查范围；只应用部分工具后，`doctor` 仍可能报告其他工具缺少配置。

## MCP 配置

正本在 [mcp/servers.json](../mcp/servers.json)。`targets` 和 `requires` 写在每个服务声明里；`manifest.json` 是资产清单快照，运行时服务配置以 `servers.json` 为准。

下面是一个**示例** stdio 服务声明，其中程序和参数需要换成真实值：

```json
{
  "version": 1,
  "mcpServers": {
    "my-server": {
      "transport": "stdio",
      "command": "node",
      "args": ["${HUB_ROOT}/mcp/my-server/server.mjs"],
      "env": {"API_TOKEN": "${MY_SERVICE_TOKEN}"},
      "targets": {"claude": true, "codex": true, "agy": false},
      "requires": {"bins": ["node"]}
    }
  }
}
```

脚本支持 stdio 和远程 `http` / `sse` 声明；客户端的传输兼容性仍需按其实际版本核对。远程声明使用 `url`，可带 `headers`。Antigravity 当前 JSON 生成器不写入远程 headers，遇到此配置会提示。

### 本机变量

`${HUB_ROOT}` 在应用时展开为 Hub 路径。`${HUB_PYTHON}` 优先使用 `local.env` 中记录的解释器，否则使用运行同步脚本的 Python。其他 `${VAR}` 从当前进程环境、`local.env`、`secrets.env` 解析；两个文件都被 Git 忽略。

本机变量文件的格式如下，按实际环境填写：

```dotenv
# ~/.agents/local.env：示例，替换路径与值
HUB_PYTHON=/absolute/path/to/python3
MY_SERVICE_TOKEN=replace-with-your-local-value
```

```bash
chmod 600 "$HOME/.agents/local.env"
python3 "$HOME/.agents/bin/agent-sync" deps
```

`deps` 检查声明的 Python 包、CLI、部分系统依赖和变量。它也检查 `HUB_PYTHON`，即使当前 MCP 只使用 Node.js 或远程服务；可在 `local.env` 中填写本机可用的 Python 绝对路径。

### 仓库内的预设

| 服务 | 配置内容 | 首次使用要准备什么 |
| --- | --- | --- |
| `basic-memory` | 远程 SSE 知识库连接 | 替换为自己的服务地址、网络和认证配置；默认不分发给 Codex |
| `clawo` | 通过 `clawo-mcp` 启动的 stdio 服务 | 可用的 Node.js / npm 和对应 CLI；声明了 npm 安装来源 |
| `browser-use` | 随仓库携带的 Node.js 浏览器 MCP | 本地 npm 依赖与匹配的 Playwright 浏览器 |

保留 `browser-use` 时，使用仓库自己的锁文件安装依赖：

```bash
cd "$HOME/.agents/mcp/browser-use"
npm ci
npx playwright install chromium
```

这一步与 `agent-sync deps --install` 分开。当前浏览器服务只声明了 `node` 二进制依赖，`deps` 不会替它运行本地 `npm ci`，也不会校验 Node 项目的浏览器 revision。

`deps --install` 会尝试建立 Python 虚拟环境、安装声明的 pip 包、按已记录来源安装全局 npm CLI，以及处理声明的 Chromium 依赖。当前版本在未配置 `HUB_PYTHON` 且 pip 包列表为空时，仍会尝试调用没有包参数的 `pip install`；对于当前预设，可先配置有效的 `HUB_PYTHON`，再使用依赖检查或安装命令。

## 已有配置如何归集

`ingest` 用于将已有配置纳入 Hub：读取 `~/.claude.json` 的 MCP、尝试采纳全局 `CLAUDE.md`，并从 `~/.dsh/skills`、`~/.claude/skills` 移动尚未归集的技能，再建立原位链接。已存在的 Hub `AGENTS.md` 或 `servers.json` 会保留。

```bash
python3 "$HOME/.agents/bin/agent-sync" ingest --dry-run
```

检查计划及当前 Git 状态后再执行实际 `ingest`。实际执行会尝试 `git add -A` 和提交，因此在已有改动的仓库中，要先确认本轮要纳入的内容。它不是任意工具配置的双向合并器。

## 新设备初始化入口

`bootstrap.sh` 依次完成环境检查、克隆或拉取、创建 `~/.local/bin/agent-sync` 链接、`init`、依赖安装、`apply` 和 `doctor`。

在准备好自己的 Hub 配置、依赖及网络环境后，可从本地克隆中执行：

```bash
bash "$HOME/.agents/bootstrap.sh"
```

已有 Git Hub 会尝试 `pull --ff-only`；如果拉取失败，脚本会提示后继续使用本地内容。最终应以 `doctor` 输出和客户端实际试用为准。该入口不负责处理账号登录，当前预设也仍需要上文的浏览器本地安装步骤。

## 日常修改与多机同步

- 修改技能正文或 `AGENTS.md`：已建立的符号链接指向同一份正本；运行中客户端可能缓存内容，重启后确认加载结果。
- 新增或删除技能、调整 MCP：运行 `apply --dry-run`、`apply`，再检查结果。
- 向其他设备同步：提交本轮明确要共享的文件并推送；其他设备 `pull --ff-only` 后重新 `apply`。
- 其他设备的 `local.env`、登录状态和依赖按当地环境配置，Git 拉取不会补齐这些内容。

只调整生成后的配置，后续 `apply` 可能将同名受管项恢复到 Hub 声明。希望长期保留的共享变更，应回到 Hub 正本维护。

## 检查与排错

| 观察到的情况 | 先检查什么 |
| --- | --- |
| `hub not initialized` / 缺少 `servers.json` | Hub 路径、克隆是否完整、`AGENT_SYNC_HUB` 是否正确 |
| 缺少 CLI、模块或变量 | `deps` 输出、服务 `requires`、`local.env` 中的本机解释器 |
| MCP 握手失败 | 实际启动命令、依赖、服务地址、认证与网络；浏览器服务还需检查本地 npm 包 |
| 客户端看不到新技能 | `SKILL.md` 是否存在、目标链接、客户端发现路径及会话缓存 |
| 清单中的技能在新克隆里缺失 | Git 是否真正跟踪技能文件，是否存在未配置好的 gitlink / 子模块 |
| 只应用两个工具，`doctor` 报第三个缺配置 | `doctor` 不提供按 `--targets` 过滤的检查 |

`doctor` 的 MCP 检查会实际启动 stdio 服务或访问远程端点。握手成功证明服务能响应初始化；业务工具调用、浏览器操作和具体技能流程还需另行试用。

## 使用范围与边界

以下内容依据当前脚本及仓库快照核对，便于区分已实现范围和后续工作。

- **配置适配**：MCP 生成器只有 Claude Code、Codex、Antigravity 三个；dsh / OpenCode 仅按原生发现 Hub 技能的约定处理。原生 Windows 尚无本轮验证结论。
- **预览与写入**：`apply --dry-run` 跳过配置写入和链接替换，但链接辅助函数仍可能创建父目录。实际 `apply` 会更新本机 `.sync-state.json`，重复运行不等于整个文件系统零写入。
- **备份与保留**：覆盖已有配置时会尝试备份；同名条目可能归入 Hub 管理。已有实体技能目录与 Hub 同名时，目录备份可能失败，先检查并处理冲突，再应用。
- **检查粒度**：`doctor` 核对 MCP 初始化、技能数量和规则链接；技能数量一致不代表每个技能都完整、正确或已经通过业务验证。
- **清理范围**：可清理指向 Hub 的失效技能链接，以及部分已记录的受管 MCP 项；不会自动接管所有第三方目录或配置。
- **清单与实际文件**：当前 `manifest.json` 列出 35 项技能；干净克隆可得到 34 个 `SKILL.md`。`skills/orchestrator-init` 是一个 gitlink，当前没有 `.gitmodules` 地址映射，无法仅靠普通克隆获取其内容。清单不能作为完整分发证明。
- **暂未实现**：统一同步 hooks / prompts / subagents、`overlays` 配置适配、项目级 Hub 应用、登录流程编排和后台自动同步。`init` 创建的预留目录不表示已有对应能力。

根目录尚无统一 `LICENSE`。引入或分发第三方技能时，需保留可确认的来源与对应许可；本指南不替各组件指定许可证。
