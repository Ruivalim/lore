#!/usr/bin/env bash
# Install lore (CLI) and lore-tui (TUI).
#
#   ./install.sh                 from a clone
#   curl -fsSL https://raw.githubusercontent.com/Ruivalim/lore/main/install.sh | bash
#
# Options:
#   --no-tui      skip building the TUI (needs Go)
#   --uninstall   remove lore and lore-tui
#
# Environment:
#   LORE_REPO     git URL to clone when not run from a clone
#   LORE_SRC      where that clone lives (default ~/.local/share/lore/src)
#   LORE_VENV     venv used when neither pipx nor uv exist (default ~/.local/share/lore/venv)
#   BIN_DIR       where lore-tui (and lore, in venv mode) go (default ~/.local/bin)
set -euo pipefail

LORE_REPO="${LORE_REPO:-https://github.com/Ruivalim/lore.git}"
LORE_SRC="${LORE_SRC:-${XDG_DATA_HOME:-$HOME/.local/share}/lore/src}"
LORE_VENV="${LORE_VENV:-${XDG_DATA_HOME:-$HOME/.local/share}/lore/venv}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
WITH_TUI=1
ACTION=install

for arg in "$@"; do
  case "$arg" in
    --no-tui) WITH_TUI=0 ;;
    --uninstall) ACTION=uninstall ;;
    -h|--help) sed -n '2,15p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "install.sh: unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then
  C_SAY=$'\033[1;35m' C_WARN=$'\033[1;33m' C_ERR=$'\033[1;31m' C_OFF=$'\033[0m'
else
  C_SAY="" C_WARN="" C_ERR="" C_OFF=""
fi
say() { printf '%s==>%s %s\n' "$C_SAY" "$C_OFF" "$*"; }
warn() { printf '%swarning:%s %s\n' "$C_WARN" "$C_OFF" "$*" >&2; }
die() { printf '%serror:%s %s\n' "$C_ERR" "$C_OFF" "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
# Roda calado; só mostra a saída da ferramenta se ela falhar.
quiet() {
  local out
  if ! out="$("$@" 2>&1)"; then
    printf '%s\n' "$out" >&2
    return 1
  fi
}

uninstall() {
  local removed=0
  if have pipx && pipx list --short 2>/dev/null | grep -q '^lore '; then
    quiet pipx uninstall lore && removed=1 && say "removed lore (pipx)"
  fi
  if have uv && uv tool list 2>/dev/null | grep -q '^lore '; then
    quiet uv tool uninstall lore && removed=1 && say "removed lore (uv)"
  fi
  if [ -d "$LORE_VENV" ]; then
    if [ "$(readlink "$BIN_DIR/lore" 2>/dev/null)" = "$LORE_VENV/bin/lore" ]; then
      rm -f "$BIN_DIR/lore"
    fi
    rm -rf "$LORE_VENV" && removed=1 && say "removed $LORE_VENV"
  fi
  if [ -f "$BIN_DIR/lore-tui" ]; then
    rm -f "$BIN_DIR/lore-tui" && removed=1 && say "removed $BIN_DIR/lore-tui"
  fi
  [ "$removed" = 1 ] || say "nothing to remove"
  say "your knowledge bases and ~/.config/lore were left untouched"
}

if [ "$ACTION" = uninstall ]; then
  uninstall
  exit 0
fi

# --- Python ------------------------------------------------------------------

PYTHON=""
for candidate in python3 python; do
  if have "$candidate" && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done
[ -n "$PYTHON" ] || die "lore needs Python 3.11 or newer"
"$PYTHON" -c 'import sqlite3; sqlite3.connect(":memory:").execute("create virtual table t using fts5(x)")' 2>/dev/null \
  || die "this Python's sqlite3 has no FTS5 support, which lore's search needs"

# --- source --------------------------------------------------------------------

script_dir=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -n "$script_dir" ] && grep -qs '^name = "lore"' "$script_dir/pyproject.toml"; then
  SRC="$script_dir"
else
  have git || die "git is needed to download lore"
  if [ -d "$LORE_SRC/.git" ]; then
    say "updating $LORE_SRC"
    git -C "$LORE_SRC" pull --ff-only --quiet || die "could not update $LORE_SRC (local changes?)"
  else
    say "cloning $LORE_REPO"
    mkdir -p "$(dirname "$LORE_SRC")"
    git clone --depth 1 --quiet "$LORE_REPO" "$LORE_SRC" || die "could not clone $LORE_REPO"
  fi
  SRC="$LORE_SRC"
fi

# --- CLI -----------------------------------------------------------------------

if have pipx; then
  say "installing lore with pipx"
  quiet pipx install --force --python "$(command -v "$PYTHON")" "$SRC" || die "pipx install failed"
elif have uv; then
  say "installing lore with uv"
  quiet uv tool install --force --python "$(command -v "$PYTHON")" "$SRC" || die "uv tool install failed"
else
  # pip --user é recusado em distro com Python gerenciado (PEP 668): venv próprio.
  say "installing lore in its own venv ($LORE_VENV)"
  if [ ! -x "$LORE_VENV/bin/python" ]; then
    quiet "$PYTHON" -m venv "$LORE_VENV" \
      || die "could not create a venv; install python3-venv or pipx and run again"
  fi
  quiet "$LORE_VENV/bin/python" -m pip install --upgrade "$SRC" || die "pip install failed"
  mkdir -p "$BIN_DIR"
  ln -sf "$LORE_VENV/bin/lore" "$BIN_DIR/lore"
fi

# --- TUI -----------------------------------------------------------------------

if [ "$WITH_TUI" = 1 ]; then
  if have go; then
    say "building lore-tui"
    mkdir -p "$BIN_DIR"
    (cd "$SRC/tui" && quiet go build -trimpath -o "$BIN_DIR/lore-tui" .) || die "TUI build failed"
  else
    warn "Go not found, skipping the TUI; lore works without it (install Go and run again for 'lore ask' with no question)"
  fi
fi

# --- done ----------------------------------------------------------------------

if ! have lore; then
  warn "lore is installed but not on your PATH; add ~/.local/bin to PATH"
fi
say "$(lore --version 2>/dev/null || echo lore) installed"
cat <<'EOF'

Next steps:
  lore init ~/notes --lang en       # a new knowledge base (or --lang pt)
  lore config --global --init       # then set repository.root: ~/notes
  lore ask "how do I approve a draft"
EOF
