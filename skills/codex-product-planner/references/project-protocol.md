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

用户不负责填表。草稿中的空值由规划 agent 从实际资料、代码和反馈填实；模板内容不构成业务决定。

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

实现自检、集成技术通过、用户接受、正式发布分别记录；review 也不代替用户体验接受。

## 多 worktree 的可见性

Git worktree 共享仓库元数据，文件各自独立。路径存在不代表任何 agent 都能访问。

规划者派单提供可访问的合同绝对路径或完整内容、SHA-256、revision、预期代码基线。新 worktree 缺最新材料时，执行者可从指定来源复制同版本合同/协议到自己的协作目录；这是材料交付，不是自动同步或修订。执行代码、状态和证据写自己的分配目录。

执行者在本聊天报告真实目录。规划者从该路径读取进度和证据，核对 Git 与运行行为后更新中央协调文件。跨设备无法读目录时，通过已授权消息或附件交接，不能宣称本机文件自动跨设备共享。

产品工作提交优先只含任务拥有的代码、测试和必要产品文档；报告与运行状态可另作文档提交或保留供读取。集成前检查提交差异，不整包覆盖全局协调、其他任务状态或规划文件。报告已读取且证据已保留后再按授权清理工作目录。

## 恢复与边界

恢复先核对协调记录、真实聊天状态、执行目录 Git 和最新报告，再计算下一动作。派单结果不明先查，候选或合同变化后重判旧报告有效性。一个项目同时只有一个明确的协调文件写入者，换规划者须交接。

阻塞只影响依赖它的工作。超出接口或业务归属的发现写变更说明，由规划者协调。凭据只记位置和获取方式。项目共享知识库规则继续适用：长期决定、原因和索引可入记忆，当前派单和代码以项目文件及 Git 为准。
