# 项目 HTML 全景

用户无需填写 HTML。规划者维护简短解释与来源，工具读取现有任务记录并生成固定页面。仅查看项目时，不需要初始化整套开发流程。

## 接入与更新

1. 确认实际项目根目录及当前工作目录。读取 README、有效需求、入口、主要对象与相关代码；旧计划、原型、演示数据与真实实现分开。有运行证据才写“已核验”。开发完成只是用户提供的阶段，不自动证明验收通过。
2. 使用下列 `init` 创建唯一的 `overview/model.json`，已有文件不覆盖。只补充目标、主要能力关系、总体里程碑、关键实现解释、缺口和下一步；资料正文、任务状态和逐项检查仍在原处。`sources` 对当前依据、规划、历史、冲突注明角色和简短原因。
3. 填写模型后运行 `inspect`，核对返回的项目范围、真实 Git 版本或无版本边界。确认解释与该范围一致，再将 `basis` 原样写入模型。它是规划者核对版本的记录，不是工具证明业务正确。没有把握的能力或里程碑保持 `unknown`。
4. 运行 `render`，打开 `overview/index.html` 检查布局、关系、关键链接和版本。已有 README 或文档站加一次入口；用户只读页面。保留必要截图或验证结果，不每轮另写长报告。
5. 接手完成、目标或依赖改变、执行者有实质进展、集成验证后或用户要求查看时运行 `check`。未变化不重写文件；变化时只查受影响资料、更新必要模型条目及 `basis`，再渲染。模型、模板和读取记录的指纹相同时，`render` 返回 `changed:false`，不改变文件时间。

```bash
python3 <skill绝对路径>/scripts/overview.py init --project <项目根目录>
python3 <skill绝对路径>/scripts/overview.py inspect --project <项目根目录>
python3 <skill绝对路径>/scripts/overview.py render --project <项目根目录>
python3 <skill绝对路径>/scripts/overview.py check --project <项目根目录>
```

`--workflow-dir` 默认 `docs/ai-workflow`，支持项目内相对目录。工具只读取产品文件、Git 和现有记录；不执行记录中的命令，不创建聊天、初始化 Git、提交或改变产品。`init` 只写展示模型；`render` 原子替换自己的 HTML。错误保留上一份页面。check 的失败退出码只表示展示需刷新或资料有问题，不是开发关卡。

页面是静态快照，展示更新时间、工作目录、版本、引用范围与核验边界；不会在浏览器中自行监控仓库。打开前由活跃规划者检查刷新。聊天结束后的定时维护需用户另行提出，沿用实际自动化能力。

## 模型约定

模板位于 `assets/overview.json`。只保存展示所需的简短解释；不是新的需求权威或任务数据库。

| 字段 | 含义 |
|---|---|
| `name / summary / stage` | 当前项目名称、一句话用途、unknown / legacy / development / completed |
| `goal` | `text`、确认来源 `source_refs`、`confirmed`、`roadmap_complete`；缺乏确认时两个布尔值保留 false |
| `basis` | inspect 返回的 `head_sha` 与 `fingerprint`；无 Git 时 SHA 为 null，范围是已引用本地文件 |
| `panorama.nodes` | `id / label / summary / state / source_refs`；state 为 planned / implemented / verified / unknown |
| `panorama.edges` | `from / to / label`，引用真实节点；表达业务关系或数据流，不画成无意义菜单列表 |
| `milestones` | `id / title / done_when / depends_on / state / source_refs`；state 为 planned / active / verified / unknown |
| `technical` | `title / summary / source_refs`，仅保留关键路径和会影响理解的取舍，详情默认折叠 |
| `gaps / next_steps` | 每项 `text / source_refs`，next_steps 可加 owner；不自动产生执行任务 |
| `sources` | 每项 `path / role / note`，role 为 current / plan / historical / conflict / reference |
| `task_sources` | 可选，每项 `task_id / directory`；directory 为规划者已获授权读取的**实际任务目录绝对路径**，只读外部 worktree 进展 |

`source_refs` 使用项目内相对文件路径，可附 `:行号`，或 https 链接。不可引用项目外文件或穿越符号链接；跨 worktree 任务只通过 `task_sources` 显式白名单读取其 task/status/report 文件。外部报告来源不可冒充当前项目代码基线；离线页面显示该实际路径，不承诺文件跨设备可达。公开网页只链接，不抓取正文或宣称已核实。

能力的 implemented/verified、里程碑的 verified 需要本地证据引用；文件存在本身不证明语义正确，规划者仍需检查。来源缺失、basis 不符、资料冲突会降为待复核，不能保持“已核验”外观。

进度只在目标已有确认、路线明确覆盖当前目标且每个里程碑都有完成条件时，显示“当前范围已核验里程碑 n/N”。不输出总完成百分比；未定义范围显示无法计算。任务列表只显示执行阶段，与已集成、已核验和用户接受分开。

## 来源与多人协作

只维护集成目录中的中央入口。分支预览注明目录和基线；执行者照常写各自任务记录，规划者从实际分配目录读取，避免读取中央目录过期副本。未取得报告显示未知或缺口。

工具自动读取中央 `coordination.json`、项目入口文件、`tasks/*/{task,status}.json` 与对应 revision 的报告，以及明确列入 `task_sources` 的记录。外部执行合同必须与中央当前合同一致；中央合同缺失、revision 或内容不一致时显示待核对，保留执行者自报阶段供追查，不当作可送验。无需执行者再写一套 HTML。

`model.json` 和单文件 `index.html` 可按项目规则纳入 Git；页面内置样式、交互与数据，不依赖 CDN、服务端或构建依赖。有效性依据排除协作目录后的产品树、工作区差异和引用文件指纹；仅提交展示文件不会使版本反复失效。页面显示核对时的 Git 提交，后续仅协作资料提交不代表产品改变。改变模板或渲染器会触发重建。

工具不递归核验脏或未初始化的 Git 子模块；遇到时明确提示并撤下已核验外观，不能用外层 gitlink 的 dirty 标记当作内部内容指纹。需要呈现其核验结论时先明确子模块版本和检查范围。

展示不是执行依赖。用户没看、生成失败或资料不足时，继续其他已明确授权工作；保留旧页时间，并在交付中说明展示缺口。需要用户的业务问题单独指出，不以展示审批代替必要决定。
