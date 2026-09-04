#!/usr/bin/env bash
# agent-sync bootstrap — wire up a new machine in one command.
#
#   curl -fsSL <hub-raw-url>/bootstrap.sh | bash -s -- [hub-git-url]
#   or: AGENT_SYNC_HUB_URL=<git-url> curl -fsSL <url> | bash
#
# Idempotent: safe to re-run (pulls hub, converges configs, verifies).
set -euo pipefail

HUB_URL="${1:-${AGENT_SYNC_HUB_URL:-}}"
HUB="${AGENT_SYNC_HUB:-$HOME/.agents}"

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# 1. runtime: python >= 3.11, git
command -v python3 >/dev/null || die "python3 not found — install Python 3.11+ first"
PYVER=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
case "$PYVER" in
  3.1[1-9]|3.[2-9][0-9]) ;;
  *) die "need Python 3.11+, found $PYVER" ;;
esac
command -v git >/dev/null || die "git not found — install git first"

# 2. hub: clone or update
if [ -d "$HUB/.git" ]; then
  say "hub found at $HUB — pulling latest"
  git -C "$HUB" pull --ff-only || say "pull skipped (no remote or local changes); using current hub"
elif [ -d "$HUB" ]; then
  say "hub dir $HUB exists without git — using as-is"
elif [ -n "$HUB_URL" ]; then
  say "cloning hub from $HUB_URL"
  git clone "$HUB_URL" "$HUB"
else
  die "$HUB not found and no hub URL given. Pass it as argument or set AGENT_SYNC_HUB_URL."
fi

SYNC="$HUB/bin/agent-sync"
[ -f "$SYNC" ] || die "hub has no bin/agent-sync — is this an agent-hub repo?"

# 3. put agent-sync on PATH
mkdir -p "$HOME/.local/bin"
ln -sf "$SYNC" "$HOME/.local/bin/agent-sync"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) say "note: ~/.local/bin not on PATH; add it or use $SYNC directly" ;;
esac

# 4. initialize skeleton (idempotent; re-vendors the tool on updates)
say "init hub"
python3 "$SYNC" init

# 5. dependencies — auto-install everything automatable
say "checking/installing dependencies (venv, pip, npm, system)"
python3 "$SYNC" deps --install || say "deps reported items needing manual action (see above)"

# 6. reconcile hub -> all detected agents
say "applying hub configuration to agents"
python3 "$SYNC" apply

# 7. verify
say "running doctor"
if python3 "$SYNC" doctor; then
  say "bootstrap complete — all green"
else
  cat <<EOF

\033[33mSome checks failed. The three things bootstrap cannot do for you:\033[0m
  🔐 secrets:   add to $HUB/local.env   (echo 'VAR=value' >> local.env; chmod 600)
  🔑 logins:    claude login / codex login / agy auth … (each once)
  🌐 network:   e.g. join the tailnet this hub's MCP endpoints live on
Then re-run:  agent-sync doctor
EOF
  exit 1
fi
