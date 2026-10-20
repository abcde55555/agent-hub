# 项目协作协议 v1

本文件是新协作目录的初始协议。初始化后，项目内 `protocol.md` 是共同读取的版本；已有项目采用已确认的协议，升级需记录影响。

## 文件与写入责任

默认 `<workflow>` 为 `docs/ai-workflow`，可映射现有权威资料。

| 文件 | 维护者 | 用途 |
|---|---|---|
| `project.md` | 规划 agent | 目标、资料索引、事实与未知、业务关系、入口 |
| `iteration.md` | 规划 agent | 当前完整任务、流程、取舍、候选、验收与下一步；只链接任务 |
| `coordination.json` | 规划 agent | 项目连接、授权和模型来源、任务到聊天/目录/提交的对应、派单与集成记录 |
| `protocol.md` | 规划 agent | 共同协议及来源 |
| `tasks/<id>/task.json` | 规划 agent | 唯一合同，revision 标识当前要求，ready 表示可派单 |
| `tasks/<id>/status.json` | 对应执行者 | 当前进度、合同 revision、实际目录、代码 SHA、阻塞 |
| `tasks/<id>/report-r<revision>.md` | 对应执行者 | 实现或独立验证结果、逐项证据、缺口、交接 |
| `tasks/<id>/evidence/` | 对应执行者 | 必要截图、日志和复现产物 |
| `overview/model.json` | 规划 agent | 展示用的简短解释、能力关系、里程碑及资料引用；不复制任务状态 |
| `overview/index.html` | 工具生成，规划 agent 负责 | 固定的人类阅读入口；嵌入版本与来源快照，可离线打开 |

用户不负责填表。草稿中的空值由规划 agent 从实际资料、代码和反馈填实；模板内容不构成业务决定。

仅生成展示时只需 `overview/`，不强制初始化任务、调度或迭代文件。已有项目内协议不会因更新个人 skill 自动升级；采用这些可选扩展时记录来源并保留原约定。

## 资料与展示

项目现有资料是事实和要求的来源；skill 提供方法。按主题引用当前依据、规划、历史或冲突资料，不凭时间新旧推定权威；注明代码与期望不一致的地方。历史报告和证据保留对应版本，从当前入口链接，不整篇重复。

规划 agent 单独维护中央展示，执行者只维护各自记录。展示规则、模型字段和工具见已安装规划 skill 的 `references/overview.md`，由规划者提供实际绝对路径。任务状态由工具读取，里程碑完成必须有明确条件、证据和已核对版本，不能由提交数、任务数量或 READY_FOR_INTEGRATION 推断。

默认入口为 `<workflow>/overview/index.html`，已有文档站时可在其入口链接。模型和 HTML 可按项目规则纳入 Git，复用同一入口；独立分支预览必须标明工作目录，不能覆盖集成目录的中央页面。README 添加一次链接即可，用户不填内容。

页面是注明时间和版本的快照。实质变化或用户要求查看时检查并刷新；没有变化则保留原文件。展示失败、过期或用户未阅读，仅影响展示和依赖该信息的判断，其他已明确授权的工作继续。浏览器里的静态页面和 skill 均不会自行监控仓库或在聊天结束后运行。

## coordination.json

`authority.source` 记录直接人类指令的日期、聊天和具体范围。布尔值只是其摘要，不能独立授予权限。

- `create_chats`：本项目内新建执行聊天。
- `message_new_chats`：向本次授权创建的聊天派单和修复。
- `message_threads`：用户指定且允许发消息的既有真实 threadId。
- `worktrees`：用户允许独立 worktree；`starting_state` 只记实际指定起点。
- `local_integration`：本轮本地集成；远端写入、部署和发布依实际授权。
- `models.*.source`：明确指定模型的直接人类来源。无来源时工具调用省略模型覆盖，不能仅凭模板预设赋值。

`assignments` 按 taskId 记录合同 revision、执行身份、实际目录、分支或 detached HEAD 与基线。派单记录含：

- `dispatch_key`：项目 + taskId + revision + 意图；同一意图先恢复再重派。
- 实际请求参数、PREPARED / PENDING / SENT / UNKNOWN / COMPLETE 状态。
- 真实 threadId/hostId，以及实际返回的 clientThreadId 或 operationId；未知保持空值。
- 最后读取游标、已消费的报告版本与代码 SHA。
- 集成候选 SHA、验证与验证者、用户接受状态和直接来源。

工具支持的身份和进度字段以当前返回值为准，不从标题猜 ID。状态只在有对应证据后改变。

## task.json

结构以 skill 的 `assets/task.json` 为初始模板；复制后的合同是本任务唯一要求来源。

- `task_id`、`revision`：稳定编号和递增需求版本，派单/状态/报告一致。
- `mode`：prototype / implement / review；`ready` 由规划 agent 设置。
- `user_goal`、`scenario`：完整用户任务、起点、动作与产物。
- `baseline`：代码基线、已有未提交改动及处理方式、权威资料路径。Git 使用真实 SHA；无 Git 明确 kind 为 unversioned，不承诺 worktree 或提交。
- `scope.write_paths`：允许改动的仓库相对路径，可用 glob。执行者自己的状态、报告和证据自动允许；合同与规划文件仍属规划者。
- `rules`、`dependencies`：业务不变量、接口来源和前置工作及就绪证据。
- `acceptance`：每项包括 id、given、when、then、verification、required（布尔）、requires_human（布尔）。条件描述观察结果，独立于实现。
- `verification`：相关 commands、入口 entrypoint、数据 data_refs、限制 limits。
- `review_target`：review 模式填写真实 base_sha 和 head_sha，检查固定候选。

派单前填实关键空值。实质变更先在 `history/task-rN.json` 留旧版再增 revision，确认旧执行者已停止或完成后再派新版本。保留旧报告证据，不追溯覆盖要求。

## status.json 与报告

执行状态：NOT_STARTED → IN_PROGRESS → READY_FOR_INTEGRATION。业务决定缺失用 NEEDS_DECISION；执行条件缺失用 BLOCKED；review 完成用 REVIEW_COMPLETE，是否通过见具体检查。

状态含 schema_version、task_id、revision、phase、updated_at_utc、workspace、head_sha、summary、blocker、next_action。时间使用 UTC；有实质进展时更新。规划者初始化 NOT_STARTED，此后由对应执行者写。规划者的集成和用户验收另存在 coordination/iteration 中。

报告最少包含：

1. taskId/revision/mode、实际目录、基线、代码候选 SHA、相关提交。
2. 实际完成与范围，模拟/真实边界，保留的外部改动。
3. 每个 AC 的 **PASS / FAIL / NOT_TESTED / BLOCKED / INCONCLUSIVE**、观察、证据。真人条件待真人判断，无法验证不等于失败。
4. 实际命令及结果，UI 实际操作、必要截图、保存重入结果；只记录确实执行的部分。
5. 未完成、依赖、失败尝试与结果，以及下一位如何启动、复现、继续。
6. 需要解释实现时，简短列出“业务动作 → 关键实现位置 → 验证证据”和重要取舍；复用现有段落，低影响修改无需额外长篇报告。由规划者提取展示内容。

实现自检、集成技术通过、用户接受、正式发布分别记录；review 也不代替用户体验接受。

## 多 worktree 的可见性

Git worktree 共享仓库元数据，文件各自独立。路径存在不代表任何 agent 都能访问。

规划者派单提供可访问的合同绝对路径或完整内容、SHA-256、revision、预期代码基线。新 worktree 缺最新材料时，执行者可从指定来源复制同版本合同/协议到自己的协作目录；这是材料交付，不是自动同步或修订。执行代码、状态和证据写自己的分配目录。

执行者在本聊天报告真实目录。规划者从该路径读取进度和证据，核对 Git 与运行行为后更新中央协调文件。跨设备无法读目录时，通过已授权消息或附件交接，不能宣称本机文件自动跨设备共享。

产品工作提交优先只含任务拥有的代码、测试和必要产品文档；报告与运行状态可另作文档提交或保留供读取。集成前检查提交差异，不整包覆盖全局协调、其他任务状态或规划文件。报告已读取且证据已保留后再按授权清理工作目录。

## 恢复与边界

恢复先核对协调记录、真实聊天状态、执行目录 Git 和最新报告，再计算下一动作。派单结果不明先查，候选或合同变化后重判旧报告有效性。一个项目同时只有一个明确的协调文件写入者，换规划者须交接。

阻塞只影响依赖它的工作。超出接口或业务归属的发现写变更说明，由规划者协调。凭据只记位置和获取方式。项目共享知识库规则继续适用：长期决定、原因和索引可入记忆，当前派单和代码以项目文件及 Git 为准。
