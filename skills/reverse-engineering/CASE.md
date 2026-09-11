# Case 目录与证据纪律

每个逆向任务一个 case。目录结构固定，产物落盘，过程可审计。

## 目录布局

```
work/<case>/
├── scope.md      # 授权与范围（见下）
├── origin/       # 原始样本 —— 一律只读，任何工具都不得写回
├── derived/      # 派生副本：解包产物、反编译输出、格式化副本
├── evidence/     # 证据：dump、trace、哈希清单（每条带获取时间与工具版本）
├── notes/        # 阶段笔记：triage / static / rebuild 各一份
└── report.md     # 结论报告
```

`origin/` 只读这条是硬约束，实操上用文件权限兜底：

```bash
chmod -R a-w work/<case>/origin
```

大样本（jadx 全量反编译可达数分钟）先只解需要的部分：`jadx --single-class` 或 `apktool d` 出 smali 后按需 grep，比全量产出快一个量级。

## scope.md

```markdown
---
case: <case-id>
target: <样本/系统说明>
auth: pending        # pending | granted | denied
granted_by:
granted_at:
---
```

`auth` 是门禁标记。**静态分析（读样本、反编译、反汇编）不需要 granted**——它不接触运行中的目标。
进入动态取证、注入、对目标发起请求前，`auth` 必须是 `granted`；否则只做被动分析与方案准备。

## 证据纪律：Evidence → Finding → Path

一份能被人复核的报告由三种陈述构成，逐层收紧：

- **Evidence（证据）** —— 一条可指认的观察。必须有 `文件:偏移/行号`、trace 片段、或 dump 哈希。
  写「`classes.dex` 里 `LoginActivity.smali:412` 调用了 `Cipher.getInstance("AES/CBC/PKCS5Padding")`」，不写「用了 AES」。
- **Finding（发现）** —— 由 ≥1 条 Evidence 支撑的结论。格式：**结论 + 依据（evidence 路径）+ 置信度**。
- **Path（复现路径）** —— 从输入到结论的可重放步骤：命令序列、脚本、参数。第三方照做能得到同一结果。

**事实与推断分开写。** 反编译出的代码是事实；「这大概就是签名函数」是推断，单独标注。

## report.md 模板

```markdown
# <case-id> 逆向报告

## 结论
<一句话回答四问开局里的「目标」>

## 目标信息
- 样本: <路径> sha256: <hash>
- 类型/架构: <file 输出要点>
- 保护: <加壳/混淆情况>

## Findings
### F1. <结论>
- 置信度: 高 / 中 / 低
- 依据: <evidence 路径:行号>
- 说明: <事实与推断分开>

## 复现路径
```bash
<命令序列>
```

## 未决问题
<卡在哪、还需什么>
```

## 哈希清单

分析前先记录样本哈希，写进 `evidence/hashes.txt`：

```bash
sha256sum work/<case>/origin/* | tee work/<case>/evidence/hashes.txt
```

这样任何一条后续证据都能锚定到确定版本的输入上。
