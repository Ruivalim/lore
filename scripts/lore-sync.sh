#!/usr/bin/env bash
# lore-sync: reconcilia o acervo Lore com o remoto Git.
#
# É o lado "que lê do remoto" da parceria: o CLI (auto_commit) só escreve,
# este script puxa, reindexa e envia. Sob o MESMO lock do auto_commit.
#
# Nunca resolve conflito sozinho. Em qualquer conflito ou erro de rebase:
# aborta a operação, deixa a árvore como encontrou e notifica o usuário.
#
# Uso: lore-sync [-q|--quiet]
#   -q  silencioso (para timer); erros ainda notificam.
set -euo pipefail

QUIET=0
[[ "${1:-}" == "-q" || "${1:-}" == "--quiet" ]] && QUIET=1

log() { [[ "$QUIET" == 1 ]] || echo "[lore-sync] $*"; }

notify() {
  local title="$1" body="$2"
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "$title" "$body" || true
  elif command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"$body\" with title \"$title\"" || true
  fi
  echo "[lore-sync] ERRO: $title: $body" >&2
}

# Raiz do acervo: $LORE_ROOT, ou descoberta via git do cwd.
ROOT="${LORE_ROOT:-}"
if [[ -z "$ROOT" ]]; then
  ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
fi
if [[ -z "$ROOT" || ! -d "$ROOT/.lore" ]]; then
  notify "lore-sync" "não achei repositório Lore (defina LORE_ROOT)"
  exit 1
fi

cd "$ROOT"

# Lock compartilhado com o auto_commit do CLI (gitops.LOCK_NAME).
LOCK="$ROOT/.lore/git.lock"
mkdir -p "$ROOT/.lore"
exec 9>>"$LOCK"
if ! flock -n 9; then
  log "outra operação git em andamento; adiando"
  exit 0
fi

# Trabalho não commitado (ex.: edição manual fora do CLI) vira commit de sync.
HEAD_BEFORE="$(git rev-parse HEAD)"
if [[ -n "$(git status --porcelain -- knowledge drafts archive 2>/dev/null)" ]]; then
  git add -- knowledge drafts archive
  git commit -qm "lore(sync): alterações locais ($(hostname -s))" || true
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
REMOTE="$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)"

# Puxa o remoto com rebase. Conflito = aborta e notifica, não decide nada.
if [[ -n "$REMOTE" ]]; then
  if ! git pull --rebase --autostash 2>/dev/null; then
    git rebase --abort 2>/dev/null || true
    notify "lore-sync: conflito" "conflito ao rebasear em $ROOT. Resolva manualmente (git status)."
    exit 1
  fi
else
  log "sem upstream configurado; pulando pull"
fi

# Reindexa só se o acervo mudou (ou índice ausente). Reindex sem mudança
# re-embedaria à toa e ainda apagaria os vetores (reindex reconstrói o
# index.sqlite do zero, vetores incluídos).
LORE_BIN="${LORE_BIN:-lore}"
HEAD_AFTER="$(git rev-parse HEAD)"
if [[ "$HEAD_BEFORE" != "$HEAD_AFTER" || ! -f "$ROOT/.lore/index.sqlite" ]]; then
  if command -v "$LORE_BIN" >/dev/null 2>&1; then
    log "acervo mudou; reindexando"
    "$LORE_BIN" --root "$ROOT" reindex --semantic >/dev/null || true
  else
    log "binário lore não encontrado; pulando reindex"
  fi
else
  log "acervo sem mudanças; reindex pulado"
fi

# Envia commits pendentes. Recusa por remoto avançado não é fatal aqui.
if [[ -n "$REMOTE" ]]; then
  if ! git push 2>/dev/null; then
    log "push adiado (remoto avançou ou sem rede); tenta no próximo ciclo"
  fi
fi

log "sincronizado ($BRANCH)"
