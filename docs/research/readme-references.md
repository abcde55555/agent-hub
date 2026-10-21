# agent-hub README 参考调研

查询日期：2026-10-21（Asia/Shanghai）。
目的：参考相关高星项目如何介绍自己，提炼适合 agent-hub 的首页结构。
范围：仅观察一手仓库和真实 README；不把参考项目的能力视为 agent-hub 的能力。

## 参考对象与热度依据

| 项目 | GitHub 首页显示 | API 核对 | 参考价值 |
| --- | --- | --- | --- |
| [anthropics/skills](https://github.com/anthropics/skills) | 约 183k stars | 本次 API 未能访问，以首页约数为准 | Skills 对象定义、使用场景、内容与许可边界 |
| [obra/superpowers](https://github.com/obra/superpowers) | 约 303k stars | [302,658](https://api.github.com/repos/obra/superpowers) | 工作流程、平台入口、能力分组与维护说明 |
| [vercel-labs/skills](https://github.com/vercel-labs/skills) | 约 35.9k stars | [35,811](https://api.github.com/repos/vercel-labs/skills) | 简洁定位、快速开始、命令索引与文档分层 |

以上是查询时返回的快照；页面存在取整，页面与 API 也可能存在缓存或更新时间差异。
Stars 仅用于筛选参考对象，不代表效果、兼容性或质量认证，不建议复制到 agent-hub 的宣传文案。

## anthropics/skills：先讲清楚对象，再给实际入口

- 开头说明 skills 的组成及加载方式，再举文档、数据分析等任务场景。[README](https://github.com/anthropics/skills/blob/main/README.md)
- 随后交代仓库用途、目录和示例性质，让读者知道可以找到什么。[README](https://github.com/anthropics/skills/blob/main/README.md)
- 使用入口按 Claude Code、Claude.ai、API 分开；安装后紧跟一个 PDF 任务示例。[README](https://github.com/anthropics/skills/blob/main/README.md)
- 创建教程给最小 `SKILL.md` 模板，并解释必要字段。[README](https://github.com/anthropics/skills/blob/main/README.md)
- 许可按内容区分：大量 skills 使用 Apache 2.0，部分文档 skills 是 source-available。[README](https://github.com/anthropics/skills/blob/main/README.md)

可采用：先说明 agent-hub 管的三类资产，再用一个真实任务说明价值；第三方内容必须保留各自来源和许可。
不宜照搬：Claude 专属安装入口、付费计划说明，以及参考项目对自身能力的描述。

## obra/superpowers：把目录变成可理解的工作流程

- 首段给出产品类型，后文用一次开发过程说明如何使用，而非只罗列技能名。[README](https://github.com/obra/superpowers/blob/main/README.md)
- 目录链接到各平台安装入口、基本流程、问题处理、能力、贡献和更新。[README](https://github.com/obra/superpowers/blob/main/README.md)
- 基本流程按设计、计划、执行、测试、审查、收尾组织；能力库另按任务类别整理。[README](https://github.com/obra/superpowers/blob/main/README.md)
- 安装方式按 coding agent 分开，并提供需要重启或验证的具体说明。[README](https://github.com/obra/superpowers/blob/main/README.md)
- 末尾有贡献约束、测试入口、更新、MIT 许可和可视化功能的遥测说明。[README](https://github.com/obra/superpowers/blob/main/README.md)

可采用：以“整理配置 → 分发 → 检查”为主线；把技能目录按用户要完成的事分类。
不宜照搬：其强制开发方法论、自动触发或长时间自主执行的效果表述。

## vercel-labs/skills：首屏让用户立即知道如何开始

- 用一句话说明自己是 skills CLI，并在首屏标出主要支持的 agents。[README](https://github.com/vercel-labs/skills/blob/main/README.md)
- 第一段安装指南明确运行条件、命令和安装范围，随后才展开更多选项。[README](https://github.com/vercel-labs/skills/blob/main/README.md)
- 其他命令使用两列表格，详细参数、平台路径和故障排查移到独立文档。[README](https://github.com/vercel-labs/skills/blob/main/README.md)
- 创建 skill、实验功能、遥测退出和 MIT 许可各有单独入口。[README](https://github.com/vercel-labs/skills/blob/main/README.md)

可采用：一句定位、少量命令、可验证的预期结果、支持矩阵和简短文档导航。
不宜照搬：npm 安装方式、平台数量、包发现能力；这些都不能从参考项目迁移为本项目承诺。

## 对 agent-hub 的建议

以下是写作建议，需以本仓库实现和验证结果为准。

### 首页定位

推荐表达：**用一个 Git 仓库管理 coding agents 的 skills、共享规则和 MCP 配置。**
第二句再解释 `bin/agent-sync` 负责分发与检查，说明用户得到的是可维护的配置源。
用“换电脑、切换 agent、减少重复配置”三个具体场景解释动机。
避免使用“全能智能体平台”“一键全自动”“全平台通用”等缺少证据的说法。

### 首页顺序

1. 名称、定位、三项核心价值。
2. 一张简明关系图：Git 中的资产 → `agent-sync` → 各 agent 配置。
3. 快速开始：前提、仓库位置、预览、应用、检查及预期结果。
4. 支持矩阵：skills、规则、MCP 各列实际处理方式与限制。
5. 日常用法：修改技能、更新规则、增加 MCP、在新设备同步。
6. 技能目录：按场景分组，链接到真实 `SKILL.md`。
7. 设计与边界、文档导航、贡献、来源与许可。

### 快速开始的验收条件

- 命令能够从干净目录照着执行；依赖版本来自本项目代码。
- 用户能分辨只读查看、预览和会写入个人配置的命令。
- 说明脚本默认使用的 hub 路径，以及放在其他路径时如何指定。
- 检查命令旁说明覆盖内容，不把“配置生成成功”写成“服务已经可用”。
- 涉及个人端点或环境变量时，说明本地配置方法；示例不包含凭据。

### 目录与维护

- README 保留开始使用所需内容，参数细节进入命令参考。
- 平台兼容性区分“脚本实现”“本次验证”“仍待验证”。
- 技能目录描述适用任务和入口，避免只列文件夹名。
- 增加技能或 MCP 的维护步骤应包含更新后如何检查。
- 许可应先清点仓库来源；上游使用 MIT 或 Apache 2.0 不等于本仓库已经采用相同许可。

## 致谢建议

可以在 README 中感谢 [Anthropic Skills](https://github.com/anthropics/skills)、
[Superpowers](https://github.com/obra/superpowers) 和 [Vercel Skills](https://github.com/vercel-labs/skills)
提供的介绍结构与文档组织参考，措辞应明确只是写作参考。
只有核实具体技能来源后，才将相应项目列为内容来源，并保留原作者及许可信息。
本调研不证明 agent-hub 与以上项目存在合作、官方支持或代码依赖关系。
