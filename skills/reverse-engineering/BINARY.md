# 通用二进制：ELF / PE / Mach-O / 固件

适用于 APK 之外的独立二进制：Linux ELF、Windows PE、macOS Mach-O、嵌入式固件、crackme。

## 第一步永远是定格式与架构

```bash
file target
rabin2 -I target          # 一站式：arch/bits/bintype/compiler/canary/nx/pic/crypto/injprot
```

`rabin2 -I` 一次给出关键信息，尤其注意两行：
- `crypto: true` —— 检出已知密码学常量，直接是个强信号。
- `injprot` / `canary` / `nx` —— 缓解措施，判断利用难度。

按格式分流：

| 格式 | 主力命令 |
|---|---|
| ELF | `readelf -h/-S/-d/-s`、`objdump -d`、`nm -D` |
| PE | `objdump -x -p`、`rabin2 -I`、`lief` 解析导入导出 |
| Mach-O | `rabin2 -I`、`otool`（如有）、`lief` |
| 固件/镜像 | `binwalk -e`、`unblob`、`7z l` |

`LIEF` 适合脚本化批量提取（导入表、段、符号），比解析文本输出稳：

```python
import lief
b = lief.parse("target")
print(b.header.machine_type, [s.name for s in b.sections][:10])
```

## 定位关键逻辑

顺序：**字符串 → 导入表 → 交叉引用 → 反汇编**。

```bash
strings -a -n 6 target | grep -iE 'pass|key|flag|auth|licen|error|invalid'
rabin2 -z target | head -50                 # 带偏移的字符串，可直接跳转
rabin2 -i target                            # 导入函数，看它用了什么库
```

导入表是最高效的线索。看到 `EVP_DecryptInit` 就知道是 OpenSSL 对称解密；看到 `getenv`/`execve` 就知道有环境相关行为。

反汇编：

```bash
r2 -A -q -c "afl" target                    # 函数列表
r2 -A -q -c "axt @ str.suspicious_string" target   # 谁引用了这个字符串
objdump -d --no-show-raw-insn target
```

`axt`（交叉引用）是从字符串回到代码的主路径——**先找到可疑字符串，再问谁引用了它**。

Ghidra 无头模式出伪代码（装了才有）：

```bash
analyzeHeadless /tmp/proj proj1 -import target -postScript Decomp.py -scriptPath ./scripts
```

## 加壳与混淆

```bash
upx -d target -o unpacked        # UPX 壳直接脱
binwalk target                    # 看是否嵌套了其他格式
```

`rabin2 -I` 报 `crypto: true` 但导入表里没有任何密码学函数 → 说明算法是**自实现**的，去 [CRYPTO.md](CRYPTO.md) 按常量特征识别。

## 固件

```bash
binwalk -e firmware.bin                    # 自动提取
unblob firmware.bin -o out/                # 对现代格式通常更干净
binwalk --signature firmware.bin           # 只看识别结果
```

固件提取常见产出：squashfs / cramfs / erofs 文件系统、内核、UBI 镜像。提取出的文件系统里再找 `/etc/`、`/bin/`、证书与密钥。

```bash
unsquashfs -d rootfs squashfs-root.squashfs
```

## 质量门：偏移必须注明视图

这是本件最容易出错的地方。同一个字节在三种视图里有三个不同的「地址」：

| 视图 | 含义 | 谁给的 |
|---|---|---|
| `file offset` | 文件里的字节位置 | `xxd`、`binwalk`、`strings` 的偏移 |
| `vaddr` / `VA` | 加载后的虚拟地址 | `objdump -d`、`r2`、Ghidra |
| `RVA` (PE) | 相对虚拟地址 | PE 头、`objdump -x` |

**同一结论里只用一个视图，并写明是哪个。** 例：
「`str.key` 位于 vaddr `0x4050`（file offset `0x1050`），被 `sub_401230` 引用」——
两个视图都给、各自标注，就不会出现「按 file offset 去 r2 里跳转」这类错位。

引用反汇编时，未经确认的函数统一命名 `sub_<地址>`，并在报告里注明这是自动命名。
