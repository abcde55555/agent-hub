# 加密与签名算法的定位与还原

目标：还原某个参数（sign / token / cipher / 密文）的**完整计算过程**——输入、变换、密钥、输出编码——并做到能离线复算出同值。

还原失败的首要原因不是技术难，是**在没确认调用点的情况下就开始读反编译代码**。顺序永远是：先定位调用点，再回溯数据流，最后才精读算法。

## 一、Java 层：先扫标准 API 四族

绝大多数 Android 应用用的是标准 JCA/JCE API。**打点这四族就能覆盖大多数场景**：

| 族 | 类 | 典型调用 | 打印什么 |
|---|---|---|---|
| 对称 | `javax.crypto.Cipher` | `getInstance("AES/CBC/PKCS5Padding")` → `init` → `doFinal` | algorithm / mode / padding / key(hex) / iv(hex) / in / out |
| HMAC | `javax.crypto.Mac` | `getInstance("HmacSHA256")` → `init` → `doFinal` | algorithm / key(hex) / in / out |
| 哈希 | `java.security.MessageDigest` | `getInstance("SHA-256")` → `digest` | algorithm / in / out |
| 非对称 | `java.security.Signature` | `getInstance("SHA256withRSA")` → `sign` | algorithm / key / in / out |

配套类型同样要盯：`SecretKeySpec`、`IvParameterSpec`、`PBEKeySpec`、`KeyGenerator`、`KeyFactory`、`X509EncodedKeySpec`、`Base64`、`CipherInputStream`。

smali 里定位（全量 grep，很快）：

```bash
apktool d -f -o out target.apk
grep -rn "Ljavax/crypto/Cipher;->\|Ljavax/crypto/Mac;->\|Ljava/security/MessageDigest;->\|Ljava/security/Signature;->" \
     out/smali* --include=*.smali -l
```

命中的文件就是要精读的对象。然后在文件里找算法串：

```bash
grep -rn 'const-string.*"\(AES\|DES\|RSA\|Hmac\|SHA\|MD5\|Blowfish\|ChaCha\)' out/smali* --include=*.smali
```

`Cipher.getInstance` 的第一个参数直接告诉你算法/模式/填充。**密钥常在同一个类的 `const-string` 里**，或在 `SecretKeySpec` 构造前几行。

jadx 交叉验证（有 Java 视图更好读）：

```bash
jadx --single-class com.example.SignUtil -d jadxout target.apk
sed -n '1,200p' jadxout/sources/com/example/SignUtil.java
```

**关键点：混淆改得掉类名和方法名，改不掉 `getInstance("AES/CBC/PKCS5Padding")` 里的字符串。** 算法串是最稳的锚点。

## 二、自实现算法：按常量特征识别

标准 API 无命中 → 算法是自己实现的（或白盒）。此时靠**特征常量**识别：

| 算法 | 特征常量 | 备注 |
|---|---|---|
| AES | S-box 起始 `63 7c 77 7b f2 6b 6f c5`；Rcon `01 02 04 08 10 20 40 80 1b 36` | S-box 是最强信号 |
| TEA/XTEA/XXTEA | delta `0x9E3779B9` | 定长分组 + 移位异或 |
| RC4 | 初始化 `for i in 0..255 { S[i]=i }` + 交换循环 | KSA/PRGA 两段结构 |
| MD5 | 初值 `0x67452301 0xefcdab89 0x98badcfe 0x10325476` | 与 SHA1 前四字相同 |
| SHA-1 | 上列四字 + `0xC3D2E1F0` | 第五个常量是区分点 |
| SHA-256 | 初值 `0x6a09e667 0xbb67ae85 0x3c6ef372 ...` | 前 8 个质数平方根小数部分 |
| ChaCha/Salsa20 | ASCII `"expand 32-byte k"` | 直接以字符串存在 |
| CRC32 | 多项式 `0xEDB88320` | 表驱动时是一张 256 项表 |
| SM4 | S-box 起始 `d6 90 e9 fe cc e1 3d b7` | 国密 |
| Blowfish | P-array 起始 `0x243F6A88 0x85A308D3` | π 的小数位 |

搜常量（十六进制字节序列，注意大小端）：

```bash
# AES S-box 前 8 字节
grep -rP '\x63\x7c\x77\x7b\xf2\x6b\x6f\xc5' --include=*.smali out/ 2>/dev/null
python3 scripts/crypto-scan.py <case目录>        # 封装好的扫描，见下
```

`scripts/crypto-scan.py` 把这些特征做成了扫描器，输出「候选算法 → 证据位置(文件:偏移/行号) → 置信度」。**它给的是候选，不是结论。**

## 三、native 层

```bash
unzip -o target.apk 'lib/*' -d libs
rabin2 -I libs/arm64-v8a/libtarget.so     # 先看 crypto 标志
```

导入表直接暴露库：

```bash
rabin2 -i libtarget.so | grep -E 'EVP_|AES_|DES_|SHA|MD5|HMAC|mbedtls'
```

| 看到 | 说明 |
|---|---|
| `EVP_DecryptInit_ex` / `EVP_CipherUpdate` / `EVP_CipherFinal_ex` | OpenSSL/BoringSSL 的 EVP 接口 |
| `EVP_aes_128_cbc` / `EVP_aes_256_gcm` | 算法与模式直接在符号名里 |
| `AES_set_encrypt_key` / `AES_cbc_encrypt` | OpenSSL 低层接口 |
| `mbedtls_aes_setkey_dec` / `mbedtls_aes_crypt_cbc` | mbedTLS |
| 无任何密码学导入 | **自实现**，回上面按常量识别 |

密钥常以立即数出现在指令里。在 r2 里找交叉引用：

```bash
r2 -A -q -c "axt @ sym.imp.EVP_DecryptInit_ex" libtarget.so   # 谁在调
r2 -A -q -c "afl~aes; pdf @ sym.<func>" libtarget.so
```

## 四、复算验证——这一步才算「还原完成」

**反编译读懂了不算还原。能离线复算出同值才算。**

对每组样本：

1. 固定输入 → 记录真实输出（从抓包、日志、或样本自带测试向量）。
2. 按还原出的算法写独立脚本复算。
3. **byte 级比对**。

```python
# verify.py 骨架 —— 复算与真实值逐字节比对
import hmac, hashlib, sys

def recompute(data: bytes, key: bytes) -> bytes:
    """按还原出的算法实现。这里是 HMAC-SHA256 的例子。"""
    return hmac.new(key, data, hashlib.sha256).digest()

SAMPLES = [                      # ≥3 组独立样本
    # (输入, 真实输出hex)
    (b"a=1&b=2", "3f2a..."),
    (b"a=9&b=7", "8c11..."),
    (b"x=0",     "d4e5..."),
]

ok = 0
for data, expected in SAMPLES:
    got = recompute(data, KEY).hex()
    match = got == expected
    ok += match
    print(f"{'PASS' if match else 'FAIL'}  in={data!r}  got={got}  want={expected}")
sys.exit(0 if ok == len(SAMPLES) else 1)
```

**验收线：≥3 组独立样本全部 byte 级一致。** 一组对上可能是巧合（尤其定长哈希截断、或输出恰好同长），三组对上才排除巧合。

常见导致「看起来不匹配」的坑，按顺序排查：
- **编码层**：输入先做了 URL encode / UTF-8 vs UTF-16；输出做了 hex 还是 base64，大小写。
- **拼接顺序**：参数是否排序、时间戳/nonce 插在哪个位置。
- **时间敏感**：`timestamp`/`nonce` 参与计算时，复算要用**同一时刻**的值；报告里标注其有效期窗口。
- **有符号/无符号**：Java 的 `int` 溢出、`>>>` 与 `>>` 的差别（JS/Java 互操作时高频）。

## 五、边界（如实写进报告）

以下情况**静态还原不出完整算法**，不要写成「已还原」：

- **加壳**：真实 dex 不在文件里，先脱壳（动态或半动态）。
- **白盒密码学**：密钥被融进查找表，还原出的是等价变换而非算法本身。
- **服务端密钥/密钥协商**：客户端只有公钥或派生参数，完整算法在服务端。
- **纯 native 白盒 + 反调试**：静态可拿到结构，但密钥可能需要运行时提取。

这些情况的正确交付：写清**观察到什么、卡在哪、还需要什么条件才能继续**，并把已验证的部分（算法族、模式、分组长度、编码方式）单独列出——部分结论依然有价值。
