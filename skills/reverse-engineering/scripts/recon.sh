#!/usr/bin/env bash
# recon.sh — reverse-engineering environment self-check.
# Idempotent and read-only: reports what is present and how to get what is not.
#
#   bash recon.sh            # human-readable report
#   bash recon.sh --quiet    # only failures (exit 1 if a required tool is missing)

set -uo pipefail

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; OFF=$'\033[0m'

missing_required=0

# has <label> <command> [<fix>] [required|optional]
has() {
    local label="$1" cmd="$2" fix="${3:-}" level="${4:-required}"
    if command -v "$cmd" >/dev/null 2>&1; then
        [ "$QUIET" = 1 ] || printf '  %s✓%s %-16s %s\n' "$GREEN" "$OFF" "$label" "$(command -v "$cmd")"
    else
        if [ "$level" = required ]; then missing_required=1; fi
        printf '  %s✗%s %-16s %s%s\n' "$RED" "$OFF" "$label" \
               "${level:+(missing, $level)} " "$fix"
    fi
}

# pymod <module> <pip-name> [required|optional]
pymod() {
    local mod="$1" pkg="$2" level="${3:-required}"
    if python3 -c "import $mod" >/dev/null 2>&1; then
        [ "$QUIET" = 1 ] || printf '  %s✓%s %-16s %s\n' "$GREEN" "$OFF" "$mod" \
            "$(python3 -c "import $mod;print(getattr($mod,'__version__','ok'))" 2>/dev/null)"
    else
        if [ "$level" = required ]; then missing_required=1; fi
        printf '  %s✗%s %-16s %s%s\n' "$RED" "$OFF" "$mod" \
               "${level:+(missing, $level)} " "pip3 install $pkg"
    fi
}

[ "$QUIET" = 1 ] || { printf '\n%sReverse-engineering environment check%s\n' "$BOLD" "$OFF"; printf '%s  python: %s\n  host:   %s%s\n' "$DIM" "$(command -v python3)" "$(uname -sm)" "$OFF"; }

[ "$QUIET" = 1 ] || printf '\n%sBase%s\n' "$BOLD" "$OFF"
has file      file
has unzip     unzip
has strings   strings
has xxd       xxd
has java      java      "apt install default-jre"
has python3   python3

[ "$QUIET" = 1 ] || printf '\n%sAndroid (Java layer)%s\n' "$BOLD" "$OFF"
has jadx          jadx          "apt install jadx  |  https://github.com/skylot/jadx/releases"
has apktool       apktool       "see install note below"
has d2j-dex2jar   d2j-dex2jar   "see install note below"
has adb           adb           "apt install adb" optional
pymod androguard  androguard

[ "$QUIET" = 1 ] || printf '\n%sBinary / native layer%s\n' "$BOLD" "$OFF"
has rabin2    rabin2    "apt install radare2"
has r2        r2        "apt install radare2"
has objdump   objdump   "apt install binutils"
has readelf   readelf   "apt install binutils"
has nm        nm        "apt install binutils"
has binwalk   binwalk   "pipx install binwalk" optional
has upx       upx       "apt install upx-ucl" optional
has nasm      nasm      "apt install nasm" optional
has analyzeHeadless analyzeHeadless "apt install ghidra (≈1.5GB) — optional; radare2 covers most static work" optional

[ "$QUIET" = 1 ] || printf '\n%sPython libraries%s\n' "$BOLD" "$OFF"
pymod lief         lief
pymod capstone     capstone
pymod cryptography cryptography

[ "$QUIET" = 1 ] || printf '\n%sKali 上 apktool / dex2jar 的无 root 安装%s\n' "$BOLD" "$OFF"
if ! command -v apktool >/dev/null 2>&1; then
    cat <<'EOF'
  官方 fat jar（自包含，无需 root）:
    mkdir -p ~/.local/opt/re-tools && cd ~/.local/opt/re-tools
    curl -L -o apktool.jar https://github.com/iBotPeaches/Apktool/releases/latest/download/apktool_3.0.3.jar
    printf '#!/bin/sh\nexec java -jar %s/.local/opt/re-tools/apktool.jar "$@"\n' "$HOME" > ~/.local/bin/apktool
    chmod +x ~/.local/bin/apktool
EOF
fi
if ! command -v d2j-dex2jar >/dev/null 2>&1; then
    cat <<'EOF'
  dex2jar（从 Kali 的 .deb 无 root 提取）:
    ls ~/.local/debs/dex2jar_*.deb   # 若无: apt download dex2jar
    dpkg-deb -x ~/.local/debs/dex2jar_*.deb ~/.local/opt/re-tools/dex2jar
    # 再用本 skill 附带的 wrapper（见 SKILL 仓库 scripts/ 说明）
EOF
fi

if [ "$missing_required" = 1 ]; then
    printf '\n%s结果：缺少必需工具，按上面的提示补齐。%s\n' "$YELLOW" "$OFF"
    exit 1
fi
[ "$QUIET" = 1 ] || printf '\n%s结果：必需工具齐备。%s\n' "$GREEN" "$OFF"
exit 0
