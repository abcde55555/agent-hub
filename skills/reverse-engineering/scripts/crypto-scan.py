#!/usr/bin/env python3
"""crypto-scan.py — static crypto-indicator scanner.

Finds *candidates* for cryptographic algorithms in a reverse-engineering case
directory: JCA/JCE API call sites and algorithm strings in dex/smali/Java, and
known constant signatures / library symbols in ELF binaries.

    python3 crypto-scan.py <case-dir-or-file> [--json] [--min-confidence medium]

WHAT THIS IS NOT: candidates are not conclusions. A hit means "look here", not
"the algorithm is X". Confirm every candidate by recomputing offline — see
CRYPTO.md, section 4.

Offsets reported for binaries are FILE OFFSETS (not vaddr); the view is labelled
in the output so it is never confused with a disassembler address.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict

# --------------------------------------------------------------------------
# Signatures
# --------------------------------------------------------------------------

# JCA/JCE API call sites, as they appear in smali type descriptors.
JCA_APIS = {
    "Ljavax/crypto/Cipher;": ("对称加密 Cipher", "high"),
    "Ljavax/crypto/Mac;": ("HMAC Mac", "high"),
    "Ljava/security/MessageDigest;": ("哈希 MessageDigest", "high"),
    "Ljava/security/Signature;": ("数字签名 Signature", "high"),
    "Ljavax/crypto/spec/SecretKeySpec;": ("对称密钥构造", "medium"),
    "Ljavax/crypto/spec/IvParameterSpec;": ("IV 构造", "medium"),
    "Ljavax/crypto/spec/PBEKeySpec;": ("口令派生密钥", "medium"),
    "Ljavax/crypto/KeyGenerator;": ("密钥生成", "medium"),
    "Ljava/security/KeyFactory;": ("密钥工厂", "medium"),
    "Ljavax/crypto/CipherInputStream;": ("流式加解密", "medium"),
}

# Algorithm-name strings. Matched case-insensitively as substrings.
ALGO_STRINGS = [
    (re.compile(rb"AES[-/]?\d*", re.I), "AES"),
    (re.compile(rb"DESede|3DES|TripleDES", re.I), "3DES"),
    (re.compile(rb"\bDES\b", re.I), "DES"),
    (re.compile(rb"RSA[-/]?\d*", re.I), "RSA"),
    (re.compile(rb"Blowfish", re.I), "Blowfish"),
    (re.compile(rb"ChaCha20|Salsa20", re.I), "ChaCha20/Salsa20"),
    (re.compile(rb"RC4|ARCFOUR", re.I), "RC4"),
    (re.compile(rb"\bSM4\b"), "SM4"),
    (re.compile(rb"Hmac(?:MD5|SHA1|SHA224|SHA256|SHA384|SHA512)", re.I), "HMAC"),
    (re.compile(rb"\bMD5\b", re.I), "MD5"),
    (re.compile(rb"SHA-?1\b", re.I), "SHA-1"),
    (re.compile(rb"SHA-?(?:224|256|384|512)", re.I), "SHA-2"),
    (re.compile(rb"PKCS[57]Padding|NoPadding|ISO10126", re.I), "填充方案"),
    (re.compile(rb"\b(?:CBC|ECB|CTR|GCM|CFB|OFB)\b"), "分组模式"),
]

# Exact byte constants. A 256-byte S-box match is decisive; short magic numbers
# can occur by chance, so they carry lower confidence.
BINARY_SIGNATURES: list[tuple[str, bytes, str, str]] = [
    # (name, pattern, confidence, note)
    ("AES S-box", bytes.fromhex(
        "637c777bf26b6fc53001672bfed7ab76"
        "ca82c97dfa5947f0add4a2af9ca472c0"
        "b7fd9326363ff7cc34a5e5f171d83115"), "high", "AES S-box 前 64 字节"),
    ("AES Rcon", bytes.fromhex("01020408102040801b36"), "medium", "AES 轮常量"),
    # 0x9E3779B9 is the golden-ratio constant and shows up in plenty of
    # non-TEA code, so it is a lead rather than a verdict.
    ("TEA/XTEA delta", bytes.fromhex("b979379e"), "medium", "小端 0x9E3779B9"),
    ("MD5 init", bytes.fromhex("0123456789abcdeffedcba9876543210"), "high", "0x67452301..."),
    ("SHA-1 init", bytes.fromhex("0123456789abcdeffedcba9876543210f0e1d2c3"), "high", "MD5 初值 + 0xC3D2E1F0"),
    ("SHA-256 init", bytes.fromhex("67e6096a85ae67bb72f36e3c3af54fa5"), "high", "0x6a09e667..."),
    ("ChaCha/Salsa constant", b"expand 32-byte k", "high", "ChaCha20/Salsa20"),
    ("CRC32 poly", bytes.fromhex("2083b8ed"), "medium", "小端 0xEDB88320"),
    ("SM4 S-box", bytes.fromhex("d690e9fecce13db716b614c228fb2c05"), "high", "国密 SM4"),
    ("Blowfish P-array", bytes.fromhex("886a3f2488a38503"), "high", "π 小数位"),
]

# Native crypto library symbols.
NATIVE_SYMBOLS = re.compile(
    rb"(EVP_(?:Encrypt|Decrypt|Cipher|Digest|ae?[sd]s?_\w+|MD5|SHA\w*|PKEY)\w*"
    rb"|AES_(?:set_\w+|cbc_encrypt|ctr128_encrypt|gcm\w*)"
    rb"|DES_\w+"
    rb"|HMAC_\w+"
    rb"|mbedtls_\w+"
    rb"|(?:MD5|SHA1|SHA256|SHA512|RC4)_\w+"
    rb"|sodium_\w+"
    rb"|crypto_\w+)"
)

TEXT_EXTS = {".smali", ".java", ".kt", ".xml", ".txt", ".json", ".js", ".ts", ".properties"}
BINARY_EXTS = {".so", ".elf", ".dex", ".bin", ".ko", ".exe", ".dylib",
               ".apk", ".jar", ".zip", ""}

CONF_RANK = {"high": 3, "medium": 2, "low": 1}


@dataclass
class Hit:
    file: str
    view: str          # "line" or "file-offset"
    location: str
    category: str      # API / algorithm-string / constant / symbol
    detail: str
    confidence: str

    def sort_key(self):
        return (-CONF_RANK.get(self.confidence, 0), self.file, self.location)


@dataclass
class Result:
    target: str
    hits: list[Hit] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def by_algorithm(self) -> dict[str, list[Hit]]:
        out: dict[str, list[Hit]] = {}
        for h in self.hits:
            out.setdefault(h.detail, []).append(h)
        return out


# --------------------------------------------------------------------------
# Scanners
# --------------------------------------------------------------------------

MAX_TEXT_BYTES = 64 * 1024 * 1024   # skip absurdly large text files

# Types that are never worth scanning even though they are binary.
IGNORE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp",
               ".ttf", ".otf", ".woff", ".woff2", ".eot",
               ".mp3", ".mp4", ".wav", ".ogg", ".webm",
               ".pdf", ".psd", ".svgz"}


def looks_binary(path: str, sniff: int = 8192) -> bool:
    """Sniff content: a NUL byte, or mostly non-text bytes, means binary."""
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(sniff)
    except OSError:
        return False
    if not chunk:
        return False
    if b"\x00" in chunk:
        return True
    printable = sum(1 for b in chunk if 9 <= b <= 13 or 32 <= b <= 126 or b >= 128)
    return printable / len(chunk) < 0.85


def scan_text(path: str, rel: str, res: Result) -> None:
    """Scan a text file by reading it and delegating to scan_text_bytes."""
    try:
        if os.path.getsize(path) > MAX_TEXT_BYTES:
            res.errors.append(f"{rel}: 文件过大，跳过文本扫描")
            return
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError as exc:
        res.errors.append(f"{rel}: {exc}")
        return
    scan_text_bytes(blob, rel, res)


def scan_bytes(data: bytes, rel: str, res: Result) -> None:
    """Byte-pattern, symbol and algorithm-string scan over an in-memory buffer.

    Offsets are FILE OFFSETS relative to the buffer named by `rel`. For an
    archive entry the offset is within that entry, and `rel` names the entry
    (e.g. `app.apk!classes.dex`) — so the view stays unambiguous.
    """
    for name, pattern, conf, note in BINARY_SIGNATURES:
        start = 0
        found = 0
        while found < 5:
            i = data.find(pattern, start)
            if i < 0:
                break
            res.hits.append(
                Hit(rel, "file-offset", f"0x{i:x}", "constant", f"{name} ({note})", conf)
            )
            start = i + 1
            found += 1

    # Native symbol names only mean something in an ELF. The same bytes in a
    # dex are ordinary Java string constants (TLS cipher-suite names, etc.),
    # and calling those "symbols" would be a lie.
    if data[:4] == ELF_MAGIC:
        for m in set(NATIVE_SYMBOLS.findall(data)):
            sym = m.decode("ascii", "replace")
            res.hits.append(
                Hit(rel, "file-offset", "-", "symbol", f"native 符号 {sym}", "high")
            )

    # Algorithm strings inside the binary.
    for rx, label in ALGO_STRINGS:
        m = rx.search(data)
        if m:
            idx = data.find(m.group(0))
            conf = "low" if label == "分组模式" else "medium"
            res.hits.append(
                Hit(rel, "file-offset", f"0x{idx:x}", "algorithm-string",
                    f"{label}: {m.group(0).decode('utf-8','replace')}", conf)
            )


ZIP_MAGIC = b"PK\x03\x04"
ELF_MAGIC = b"\x7fELF"
MAX_ARCHIVE_ENTRY = 256 * 1024 * 1024


def scan_binary(path: str, rel: str, res: Result) -> None:
    """Scan a file; if it is a zip/APK, scan its entries' decompressed bytes.

    An APK's dex and .so are compressed inside the archive, so scanning the raw
    file would find almost nothing. Reading entries in memory keeps the origin
    sample read-only, which CASE.md requires.
    """
    try:
        size = os.path.getsize(path)
        if size > 512 * 1024 * 1024:
            res.errors.append(f"{rel}: 超过 512MB，跳过二进制扫描")
            return
        with open(path, "rb") as fh:
            head = fh.read(4)
            fh.seek(0)
            data = fh.read()
    except OSError as exc:
        res.errors.append(f"{rel}: {exc}")
        return

    if head == ZIP_MAGIC:
        scan_archive(data, path, rel, res)
        return

    scan_bytes(data, rel, res)


def scan_archive(data: bytes, path: str, rel: str, res: Result) -> None:
    """Scan the interesting entries of a zip/APK/jar in memory."""
    import io
    import zipfile

    interesting = (".dex", ".so", ".xml", ".json", ".js", ".txt", ".properties")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(interesting)]
            if not names:
                res.errors.append(f"{rel}: 压缩包内无可扫描条目")
                return
            for name in names:
                try:
                    info = zf.getinfo(name)
                    if info.file_size > MAX_ARCHIVE_ENTRY:
                        res.errors.append(f"{rel}!{name}: 条目过大，跳过")
                        continue
                    blob = zf.read(name)
                except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                    res.errors.append(f"{rel}!{name}: {exc}")
                    continue
                entry_rel = f"{rel}!{name}"
                if name.lower().endswith((".xml", ".json", ".js", ".txt", ".properties")):
                    scan_text_bytes(blob, entry_rel, res)
                else:
                    scan_bytes(blob, entry_rel, res)
    except zipfile.BadZipFile as exc:
        res.errors.append(f"{rel}: 压缩包损坏 ({exc})")
        scan_bytes(data, rel, res)


def scan_text_bytes(blob: bytes, rel: str, res: Result) -> None:
    """Line-oriented scan over an in-memory text buffer."""
    for lineno, raw in enumerate(blob.split(b"\n"), 1):
        line = raw.decode("utf-8", "replace")
        for needle, (label, conf) in JCA_APIS.items():
            if needle in line:
                res.hits.append(Hit(rel, "line", f"{lineno}", "API", label, conf))
        for rx, label in ALGO_STRINGS:
            m = rx.search(raw)
            if m:
                conf = "low" if label == "分组模式" else "medium"
                res.hits.append(
                    Hit(rel, "line", f"{lineno}", "algorithm-string",
                        f"{label}: {m.group(0).decode('utf-8','replace')}", conf)
                )


def walk(target: str) -> list[tuple[str, str]]:
    """Return (absolute, relative) pairs to scan. Follows symlinks (origin.sample)."""
    if os.path.isfile(target):
        return [(target, os.path.basename(target))]
    out = []
    for root, dirs, files in os.walk(target, followlinks=True):
        dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__"}]
        for fn in files:
            ap = os.path.join(root, fn)
            out.append((ap, os.path.relpath(ap, target)))
    return sorted(out)


def scan_target(target: str) -> Result:
    res = Result(target=target)
    for ap, rel in walk(target):
        # Skip our own outputs so a re-run does not scan its own report.
        if rel.startswith(("notes/", "evidence/")) and rel.endswith((".md", ".json")):
            continue
        ext = os.path.splitext(ap)[1].lower()
        if ext in TEXT_EXTS:
            scan_text(ap, rel, res)
        elif ext in BINARY_EXTS or ext == "":
            scan_binary(ap, rel, res)
        elif ext not in IGNORE_EXTS and looks_binary(ap):
            # Unknown extension but binary content — scan it anyway rather than
            # silently skipping (renamed samples, extensionless payloads).
            scan_binary(ap, rel, res)

    # Dedupe: a cipher-suite string appears once per dex per usage; keeping the
    # first occurrence per (file, category, detail) is what a reader wants.
    seen: set[tuple[str, str, str]] = set()
    deduped: list[Hit] = []
    for h in res.hits:
        key = (h.file, h.category, h.detail)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(h)

    deduped.sort(key=Hit.sort_key)
    res.hits = deduped
    return res


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def render_text(results: list[Result], min_conf: str) -> str:
    floor = CONF_RANK[min_conf]
    lines = []
    for res in results:
        hits = [h for h in res.hits if CONF_RANK[h.confidence] >= floor]
        lines.append(f"\n=== {res.target} ===")
        if not hits:
            lines.append("  未发现加密特征。")
            continue
        lines.append(f"  {len(hits)} 条候选（候选不是结论，须按 CRYPTO.md 复算验证）\n")
        lines.append(f"  {'置信度':<8} {'类别':<18} {'位置':<28} 说明")
        lines.append(f"  {'-'*8} {'-'*18} {'-'*28} {'-'*40}")
        for h in hits:
            loc = f"{h.file}:{h.location}"
            if len(loc) > 27:
                loc = "…" + loc[-26:]
            lines.append(f"  {h.confidence:<8} {h.category:<18} {loc:<28} {h.detail}")
        if res.errors:
            lines.append("\n  跳过：")
            for e in res.errors:
                lines.append(f"    - {e}")
    lines.append("\n注意：二进制命中给出的是 FILE OFFSET（文件偏移），不是 vaddr。")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="静态加密特征扫描（候选，非结论）")
    ap.add_argument("targets", nargs="+", help="case 目录或文件")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--min-confidence", choices=["low", "medium", "high"],
                    default="low", help="最低置信度（默认 low）")
    args = ap.parse_args()

    results = [scan_target(t) for t in args.targets if os.path.exists(t)]

    if args.json:
        print(json.dumps(
            [{"target": r.target, "hits": [asdict(h) for h in r.hits], "errors": r.errors}
             for r in results], ensure_ascii=False, indent=2))
    else:
        print(render_text(results, args.min_confidence))
    return 0


if __name__ == "__main__":
    sys.exit(main())
