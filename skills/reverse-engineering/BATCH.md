# 批量逆向：一个目录，多个目标

用于「帮我逆向这个目录下所有 APK」这类任务。单目标任务不必读本件，直接走 [SKILL.md](SKILL.md) 四问开局。

批处理的难点不是循环，是**穷尽**与**隔离**：目标多了以后，漏掉一个、或把两个目标的产物混在一起，报告就失去意义。

## 两步走

**先试跑一个，再全量。** 目录里目标的大小/形态可能差一个数量级，直接全量跑会在某个大样本上撞墙钟超时。

```bash
bash scripts/batch-driver.sh <目录> --list                # 只枚举，不执行
bash scripts/batch-driver.sh <目录> --only <单个目标>     # 试跑，记录耗时
bash scripts/batch-driver.sh <目录> --out work/batch-<name>   # 全量
```

`--list` 的产出是**工作量预估**：每个目标的体积、类型、dex/so 数。按它决定要不要分批。

参考量级（13MB / 3 dex / 4 so 的 APK）：`apktool d` 约 1 分钟，`jadx --no-res` 约 2 分钟。
50MB 以上的目标先单独试跑一次，用实测耗时 × 目标数估算全量墙钟，再决定并行度。

## 目录布局

```
work/batch-<name>/
├── targets.txt          # 枚举清单 + 每个目标的 sha256
├── cases/
│   ├── <target-1>/      # 每个目标一个独立 case，结构同 CASE.md
│   ├── <target-2>/
│   └── ...
├── errors.md            # 失败清单：目标 + 失败原因分类
└── SUMMARY.md           # 汇总报告
```

**每个目标一个独立 case**，`origin/` 只放该目标，产物互不污染。目录命名去掉扩展名并做字符清洗，避免 `a b.apk` 这类名字把脚本搞乱。

## 执行契约

1. **枚举**：递归找 `*.apk`、`*.so`、`*.elf`、`*.bin`、`*.exe`，记录 sha256。清单落 `targets.txt`——**这是穷尽性的基准**。
2. **逐目标 triage**：按 [SKILL.md](SKILL.md) 的路由给每个目标定类型，选择分析路径。
3. **失败不中断**：单个目标失败写进 `errors.md`（附分类：`unpack-failed` / `timeout` / `packed` / `not-a-valid-file` / `tool-missing`），**继续跑完剩下的**。
4. **汇总**：所有目标跑完后统一回看，不是边跑边总结。

## 完成判据（穷尽）

批处理最典型的失败是「跑了 47 个，报了 45 个成功」——另外 2 个悄无声息。所以：

> **`SUMMARY.md` 的行数必须等于 `targets.txt` 的行数。**

每个目标一行，状态三选一：`成功` / `失败` / `跳过`。失败和跳过都要写原因。
用这条对账：

```bash
echo "清单 $(wc -l < work/batch-*/targets.txt) 个，汇总 $(grep -c '^|' work/batch-*/SUMMARY.md) 行"
```

数目对不上就回去查是哪个目标被吞了。

## SUMMARY.md 模板

```markdown
# 批量逆向汇总 — <name>

目标数: N ｜ 成功: A ｜ 失败: B ｜ 跳过: C

| # | 目标 | 类型 | 结论 | 状态 | 详情 |
|---|---|---|---|---|---|
| 1 | app-a.apk | APK(1 dex, 2 so) | 签名算法 = HMAC-SHA256 | 成功 | [case](cases/app-a/report.md) |
| 2 | app-b.apk | APK(加固) | 加壳，静态不可还原 | 跳过 | [error](cases/app-b/notes/triage.md) |
| 3 | lib-x.so | ELF arm64 | AES-CBC，密钥硬编码 | 成功 | [case](cases/lib-x/report.md) |

## 横向发现
<跨目标的共性：同一套加密实现、同一签名方案、同一加固厂商>

## 失败清单
详见 [errors.md](errors.md)
```

「横向发现」是批处理相对单目标的**独有价值**——多个样本用同一套算法时，批量跑能直接看出来。

## 并行

目标之间彼此独立，可以并行。但注意：

- **内存**：`jadx` 和 `Ghidra` 都是 JVM，各自默认吃 1–2GB。并行度按可用内存定，不要按 CPU 核数定。
- **产物隔离**：并行时每个目标写自己的 `cases/<target>/`，共享的输出目录会互相覆盖。
- 目标是 native 二进制时，`ghidra-headless-analysis` 的批处理路径更合适（复用 Ghidra 工程，避免每个文件重启 JVM）。

## 与加密还原的衔接

批处理最常见的诉求就是「找出所有目标里的加密算法」。跑完 triage 后：

```bash
python3 scripts/crypto-scan.py work/batch-<name>/cases --json > crypto-candidates.json
```

它对每个 case 的 dex/smali/so 做静态特征扫描，输出候选算法与证据位置。**候选不是结论**——按 [CRYPTO.md](CRYPTO.md) 逐个复算验证后才写进 `SUMMARY.md`。
