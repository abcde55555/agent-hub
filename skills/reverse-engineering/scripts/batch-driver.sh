#!/usr/bin/env bash
# batch-driver.sh — walk a directory, give every target its own case, triage it,
# scan it for crypto indicators, and emit a per-target report plus an aggregate
# summary that is guaranteed to account for every target.
#
#   batch-driver.sh <dir> --list                 enumerate only, no analysis
#   batch-driver.sh <dir> --only <target>        run one target (pilot)
#   batch-driver.sh <dir> [--out DIR]            full run
#   batch-driver.sh <dir> --out DIR --ext apk,so restrict extensions
#
# Design rule: a failure never aborts the run. Every target ends up in the
# summary as 成功 / 失败 / 跳过 with a reason, so the row count always matches
# the target count. See BATCH.md.

set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN_PY="$SELF_DIR/crypto-scan.py"

DEFAULT_EXT="apk,so,elf,dex,bin,exe,ko"
MAX_DEPTH=6

SRC=""; OUT=""; ONLY=""; LIST_ONLY=0; EXTS="$DEFAULT_EXT"

usage() { sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --list)  LIST_ONLY=1; shift ;;
        --only)  ONLY="${2:-}"; shift 2 ;;
        --out)   OUT="${2:-}"; shift 2 ;;
        --ext)   EXTS="${2:-}"; shift 2 ;;
        --depth) MAX_DEPTH="${2:-}"; shift 2 ;;
        -h|--help) usage 0 ;;
        -*) echo "unknown option: $1" >&2; usage 1 ;;
        *)  SRC="$1"; shift ;;
    esac
done

[ -n "$SRC" ] || { echo "error: no source directory given" >&2; usage 1; }
[ -d "$SRC" ] || { echo "error: not a directory: $SRC" >&2; exit 1; }

SRC="$(cd "$SRC" && pwd)"

# ---- enumerate ------------------------------------------------------------

# Build a find expression from the comma-separated extension list.
build_find_expr() {
    local first=1 e
    IFS=',' read -ra parts <<< "$EXTS"
    for e in "${parts[@]}"; do
        e="${e#"${e%%[![:space:]]*}"}"; e="${e%"${e##*[![:space:]]}"}"  # trim
        [ -n "$e" ] || continue
        if [ $first = 1 ]; then printf -- '-iname *.%s' "$e"; first=0
        else printf -- ' -o -iname *.%s' "$e"; fi
    done
}

mapfile -t TARGETS < <(find "$SRC" -maxdepth "$MAX_DEPTH" -type f \( $(build_find_expr) \) -print 2>/dev/null | sort)

if [ "${#TARGETS[@]}" -eq 0 ]; then
    echo "no targets matching [$EXTS] under $SRC" >&2
    exit 0
fi

# --only narrows to a single target (pilot run). Match on basename or path substring.
if [ -n "$ONLY" ]; then
    mapfile -t TARGETS < <(printf '%s\n' "${TARGETS[@]}" | grep -F -- "$ONLY" || true)
    [ "${#TARGETS[@]}" -gt 0 ] || { echo "no target matching '$ONLY'" >&2; exit 1; }
fi

# ---- --list ---------------------------------------------------------------

if [ "$LIST_ONLY" = 1 ]; then
    printf '%-52s %10s  %s\n' "TARGET" "SIZE" "SHA256(前16)"
    total=0
    for t in "${TARGETS[@]}"; do
        sz=$(stat -c%s "$t" 2>/dev/null || echo 0)
        h=$(sha256sum "$t" 2>/dev/null | cut -c1-16)
        printf '%-52s %10s  %s\n' "$(basename "$t")" "$sz" "$h"
        total=$((total + sz))
    done
    printf '\n%d 个目标，合计 %.1f MB\n' "${#TARGETS[@]}" "$(awk -v t="$total" 'BEGIN{printf "%.1f", t/1048576}')"
    echo "先用 --only <目标> 试跑，按实测耗时估算全量墙钟。"
    exit 0
fi

# ---- set up the batch workspace -------------------------------------------

if [ -z "$OUT" ]; then
    OUT="$SRC/../work/batch-$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$OUT/cases" || exit 1
OUT="$(cd "$OUT" && pwd)"

# targets.txt is the exhaustiveness baseline: one line per target.
: > "$OUT/targets.txt"
for t in "${TARGETS[@]}"; do
    printf '%s\t%s\n' "$(sha256sum "$t" | cut -d' ' -f1)" "$t" >> "$OUT/targets.txt"
done

echo "源目录   : $SRC"
echo "工作目录 : $OUT"
echo "目标数   : ${#TARGETS[@]}"
echo

# ---- helpers ---------------------------------------------------------------

# Sanitize a target into a safe directory name.
# Only path-hostile characters are replaced; every other byte is kept, so
# non-ASCII names (e.g. 有声小说.apk) survive intact instead of collapsing to
# a row of underscores. `cut -c` counts characters, not bytes, in a UTF-8 locale.
case_name() {
    local b; b="$(basename "$1")"; b="${b%.*}"
    printf '%s' "$b" \
        | sed 's|[/\\:*?"<>|]|_|g; s|[[:space:]]|_|g; s|^\.\+||' \
        | cut -c1-60
}

# Classify a file into apk / elf / pe / macho / dex / other.
classify() {
    local f="$1" out
    out="$(file -b "$f" 2>/dev/null)"
    case "$out" in
        *"Android package"*)   echo "apk" ;;
        *"Dalvik dex"*)        echo "dex" ;;
        *ELF*)                 echo "elf" ;;
        *PE32*)                echo "pe" ;;
        *Mach-O*)              echo "macho" ;;
        *)                     echo "other" ;;
    esac
}

# ---- per-target analysis --------------------------------------------------

declare -a ROWS=()
: > "$OUT/errors.md"
{
    echo "# 失败与跳过清单"
    echo
    echo "| 目标 | 分类 | 原因 |"
    echo "|---|---|---|"
} >> "$OUT/errors.md"

idx=0
for t in "${TARGETS[@]}"; do
    idx=$((idx + 1))
    base="$(basename "$t")"
    cname="$(case_name "$t")"
    cdir="$OUT/cases/$cname"

    # De-duplicate case dir names.
    if [ -e "$cdir" ]; then cdir="${cdir}-${idx}"; fi
    mkdir -p "$cdir/notes" "$cdir/evidence" "$cdir/derived"

    kind="$(classify "$t")"
    rel="${t#"$SRC"/}"
    printf '[%d/%d] %-46s %s\n' "$idx" "${#TARGETS[@]}" "$(printf '%.46s' "$base")" "$kind"

    note="$cdir/notes/triage.md"
    {
        echo "# Triage — $base"
        echo
        echo "- 路径: \`$rel\`"
        echo "- 分类: $kind"
        echo "- 大小: $(stat -c%s "$t") bytes"
        echo "- sha256: \`$(sha256sum "$t" | cut -d' ' -f1)\`"
        echo "- file: \`$(file -b "$t" 2>/dev/null)\`"
        echo
    } > "$note"

    # Link the origin sample rather than copying it (keeps large batches cheap).
    # The extension is preserved: scanners dispatch on it, and a bare
    # "origin.sample" would be skipped as an unknown type.
    ext="${t##*.}"
    [ "$ext" = "$t" ] && ext="bin"
    ln -sf "$t" "$cdir/origin.sample.$ext" 2>/dev/null || true

    status="成功"; reason=""

    case "$kind" in
        apk)
            { echo "## 层结构"; echo '```'; unzip -l "$t" 2>/dev/null | grep -E '\.so$|classes.*\.dex' || echo "(未发现 dex/so)"; echo '```'; echo; } >> "$note"
            # Manifest / component overview when androguard is available.
            if python3 -c "import androguard" 2>/dev/null; then
                {
                    echo "## androguard"
                    echo '```'
                    timeout 300 python3 - "$t" <<'PY' 2>&1 | tail -20
import sys
from loguru import logger
logger.remove()          # androguard logs every AXML header at DEBUG; silence it
from androguard.misc import AnalyzeAPK
a, d, dx = AnalyzeAPK(sys.argv[1])
print("package   :", a.get_package())
print("app_name  :", a.get_app_name())
print("min/target:", a.get_min_sdk_version(), "/", a.get_target_sdk_version())
print("dex files :", len(d))
print("activities:", len(a.get_activities()))
print("services  :", len(a.get_services()))
print("permissions:", len(a.get_permissions()))
PY
                    echo '```'
                    echo
                } >> "$note"
            else
                echo "_(androguard 未安装，跳过 manifest 概览)_" >> "$note"
            fi
            ;;
        elf|pe|macho)
            if command -v rabin2 >/dev/null 2>&1; then
                { echo "## rabin2 -I"; echo '```'; timeout 120 rabin2 -I "$t" 2>&1 | head -25; echo '```'; echo; } >> "$note"
            fi
            ;;
        dex)
            if command -v rabin2 >/dev/null 2>&1; then
                { echo "## rabin2 -I"; echo '```'; timeout 120 rabin2 -I "$t" 2>&1 | head -15; echo '```'; echo; } >> "$note"
            fi
            ;;
        *)
            reason="无法识别的文件类型"; status="跳过"
            ;;
    esac

    # Static crypto scan — candidates only, never conclusions.
    if [ -f "$SCAN_PY" ]; then
        if timeout 600 python3 "$SCAN_PY" "$cdir" --json > "$cdir/evidence/crypto-candidates.json" 2>"$cdir/notes/crypto-scan.err"; then
            timeout 600 python3 "$SCAN_PY" "$cdir" > "$cdir/notes/crypto-candidates.md" 2>/dev/null || true
        else
            status="失败"; reason="crypto-scan 失败，见 notes/crypto-scan.err"
        fi
    fi

    # Seed the per-case report with what triage established.
    {
        echo "# $cname 逆向报告"
        echo
        echo "## 目标信息"
        echo "- 样本: \`$rel\`"
        echo "- 分类: $kind"
        echo "- sha256: \`$(sha256sum "$t" | cut -d' ' -f1)\`"
        echo
        echo "## Findings"
        echo
        echo "_待填写。候选算法见 [crypto-candidates.md](../notes/crypto-candidates.md)（候选不是结论）。_"
        echo
        echo "## 复现路径"
        echo '```bash'
        echo "# 由 batch-driver.sh 生成；补上实际使用的命令"
        echo '```'
        echo
        echo "## 未决问题"
        echo
        echo "_待填写_"
    } > "$cdir/report.md"

    if [ "$status" != "成功" ]; then
        printf '| %s | %s | %s |\n' "$base" "$kind" "$reason" >> "$OUT/errors.md"
    fi

    ROWS+=("| $idx | $base | $kind | $status | [case](cases/$cname/report.md) |")
done

# ---- aggregate -------------------------------------------------------------

success=$(printf '%s\n' "${ROWS[@]}" | grep -c '| 成功 |' || true)
failed=$(printf '%s\n' "${ROWS[@]}" | grep -c '| 失败 |' || true)
skipped=$(printf '%s\n' "${ROWS[@]}" | grep -c '| 跳过 |' || true)

{
    echo "# 批量逆向汇总"
    echo
    echo "目标数: ${#TARGETS[@]} ｜ 成功: $success ｜ 失败: $failed ｜ 跳过: $skipped"
    echo
    echo "| # | 目标 | 类型 | 状态 | 详情 |"
    echo "|---|---|---|---|---|"
    printf '%s\n' "${ROWS[@]}"
    echo
    echo "## 横向发现"
    echo
    echo "_跨目标的共性：同一套加密实现、同一签名方案、同一加固厂商。待填写。_"
    echo
    echo "## 失败清单"
    echo
    echo "详见 [errors.md](errors.md)"
} > "$OUT/SUMMARY.md"

# ---- exhaustiveness gate ---------------------------------------------------

rows=$(grep -c '^| [0-9]' "$OUT/SUMMARY.md" || true)
want=$(wc -l < "$OUT/targets.txt")

echo
echo "汇总: $OUT/SUMMARY.md"
if [ "$rows" -eq "$want" ]; then
    printf '\033[32m✓ 穷尽性检查通过\033[0m: %d 个目标，%d 行结论\n' "$want" "$rows"
else
    printf '\033[31m✗ 穷尽性检查失败\033[0m: 清单 %d 个目标，汇总只有 %d 行\n' "$want" "$rows"
    exit 1
fi
