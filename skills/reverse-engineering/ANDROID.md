# 安卓 APK：Java 层与 native 层

APK 是双层结构，两层都要看：Java 层（dex → smali/Java）承载业务逻辑，native 层（`lib/<abi>/*.so`）承载加固、加密和反调试。**先 triage 定位，再决定深挖哪层。**

## Java 层

### triage（先跑这个，秒级）

```bash
unzip -l target.apk | grep -E '\.so$|\.dex$'        # 看有几层、几个 dex、哪些 abi
androguard analyze target.apk                        # manifest / 权限 / 组件 / dex 概览
file target.apk
```

`androguard` 比全量反编译快得多，先拿它的 manifest、dex 数、组件列表和字符串，判断值不值得深挖。

### 反编译

```bash
jadx -d out target.apk                    # 全量 Java
jadx --no-res -d out target.apk           # 跳过资源，快很多
jadx --deobf -d out target.apk            # 打开去混淆重命名
jadx --single-class com.example.Sign -d out target.apk   # 只要一个类，最快
```

实务：**先用 `--single-class` 或 `--no-res` 拿结论，需要全量时再全量跑。**
参考量级——13MB / 3 个 dex 的 APK，`jadx --no-res` 约 2 分钟出 ~11.8k 个 Java 文件。

### smali 层

需要改包、或 jadx 反编译失败（混淆/加固）时，下到 smali：

```bash
apktool d -f -o out target.apk            # 出 smali + 资源 + AndroidManifest.xml
apktool d -f -s -o out target.apk         # 不反汇编，只复制 dex（快，只看结构时用）
apktool b out -o rebuilt.apk              # 重打包
```

同样 13MB 的 APK，`apktool d` 出 ~24k 个 smali 文件。**smali 是可靠的兜底层**——jadx 反编译出乱码时，smali 指令仍然可读。

重打包后要签名才能装：

```bash
keytool -genkey -keystore debug.keystore -alias dbg -keyalg RSA -keysize 2048 \
        -validity 10000 -storepass android -keypass android -dname "CN=dbg"
apksigner sign --ks debug.keystore --ks-pass pass:android rebuilt.apk
```

### 直接读 dex

`dex2jar` 把 dex 转成 jar，交给通用 Java 反编译器（如 `javap`、CFR）处理：

```bash
unzip -o target.apk 'classes*.dex' -d dexdir
d2j-dex2jar dexdir/classes.dex -o classes.jar
```

## native 层（.so / JNI）

### 定位与 triage

```bash
unzip -l target.apk | grep '\.so$'                   # 列出所有 native 库与其 abi
rabin2 -I lib/arm64-v8a/libtarget.so                 # 架构/位数/编译器/加固迹象
readelf -h libtarget.so | grep -E 'Class|Machine|Type'
readelf -d libtarget.so | grep -E 'NEEDED|INIT'      # 依赖 + 构造器（反调试常藏在 init_array）
```

一个 APK 常带多 abi 的同名 `.so`。**选一个 abi 深挖**（arm64-v8a 优先），各 abi 逻辑一致。

### 判断 JNI 注册方式——这决定下一步怎么走

```bash
nm -D libtarget.so | grep -c 'Java_'                 # 静态注册的导出符号数
```

- **有 `Java_com_example_Foo_bar` 这类符号** → 静态注册，函数名直接给出 Java 类与方法的对应关系，直接定位。
- **几乎没有（0 或个位数）却确实被 Java 调用** → **动态注册**，`JNI_OnLoad` 里调 `RegisterNatives`。此时符号表帮不上忙，需要还原映射表。

动态注册的静态还原思路：
1. 找 `JNI_OnLoad`（`readelf -d` 的 INIT/INIT_ARRAY，或符号表）。
2. 在其中定位 `RegisterNatives` 调用——它在 `JNIEnv` 函数表里的固定槽位（`JNIEnv*` 解引用后按索引取函数指针，索引 ≈ 215）。
3. 第 2 个参数是 `JNINativeMethod[]` 数组，每个元素是 `{char* name, char* sig, void* fnPtr}` 三连。
4. `name`/`sig` 是指向字符串的指针——交叉引用字符串就能把「方法名 + 签名 → 函数地址」整张表拉出来。

```bash
r2 -A -q -c "afl; izz~RegisterNatives; axt @ str.<method>" libtarget.so
strings -a libtarget.so | grep -E '^\(.*\)' | head -40    # JNI 签名串，如 (Ljava/lang/String;)I
```

### 反汇编与反编译

```bash
r2 -A -q -c "afl" libtarget.so                       # 函数列表
r2 -A -q -c "afl; iz; ii; q" libtarget.so            # 函数 + 字符串 + 导入
objdump -d --no-show-raw-insn libtarget.so | head -100
```

需要高质量伪代码时上 Ghidra 无头模式（装了才有）：

```bash
analyzeHeadless /tmp/ghidra-proj proj1 -import libtarget.so \
  -postScript ExportDecomp.py -scriptPath ./scripts
```

`recon.sh` 会报告 Ghidra 是否可用。没有 Ghidra 时 `radare2` + `objdump` 足以支撑大部分静态结论。

### 加壳的 .so

若 `readelf -h` 报错、段表异常、或 `rabin2 -I` 显示 `crypto: true`/入口点异常，多半是加壳：
- 先看 `readelf -S` 是否有反常的小段表、`init_array` 是否指向可疑地址。
- 内存 dump 与重建属于动态/半动态工作，需要运行环境；静态阶段先把「观察到什么」写进报告。

## 与加密算法的衔接

Java 层扫 `javax.crypto.*`、`java.security.*`；native 层扫 OpenSSL `EVP_*`、AES S-box 常量。
完整流程见 [CRYPTO.md](CRYPTO.md)。
