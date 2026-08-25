#!/usr/bin/env bash
# Avisa al agente de que un worktree nativo de Claude Code necesita
# 'ddev worktree up' antes de poder usar DDEV en él.
set -uo pipefail

WT_SUBDIR=".claude/worktrees"
INPUT="$(cat)"
EVENT="$(jq -r '.hook_event_name // ""' <<<"$INPUT")"

# Devuelve la raíz del worktree contenida en la ruta dada, o vacío.
worktree_root_of() {
  local path="$1"
  case "$path" in
    *"/$WT_SUBDIR/"*)
      local main="${path%%/$WT_SUBDIR/*}" rest="${path#*/$WT_SUBDIR/}"
      printf '%s/%s/%s' "$main" "$WT_SUBDIR" "${rest%%/*}"
      ;;
  esac
}

has_ddev_ancestor() {
  local dir="$1"
  while [ -n "$dir" ] && [ "$dir" != "/" ]; do
    [ -d "$dir/.ddev" ] && return 0
    dir="$(dirname "$dir")"
  done
  return 1
}

case "$EVENT" in
  PreToolUse)
    CMD="$(jq -r '.tool_input.command // ""' <<<"$INPUT")"
    CWD="$(jq -r '.cwd // ""' <<<"$INPUT")"

    # Solo nos interesan invocaciones a ddev.
    grep -qE '(^|[;&|(]|[[:space:]])ddev[[:space:]]' <<<"$CMD" || exit 0
    # El propio aprovisionamiento y los comandos globales pasan siempre.
    grep -qE 'ddev[[:space:]]+(worktree|list|poweroff|version|debug|stop)\b' <<<"$CMD" && exit 0

    WT="$(worktree_root_of "$CWD")"
    if [ -z "$WT" ]; then
      # El comando puede llevar un 'cd' a un worktree aunque el cwd no lo sea.
      CANDIDATE="$(grep -oE "[^[:space:]'\"]*$WT_SUBDIR/[^[:space:]'\"/]+" <<<"$CMD" | head -1 || true)"
      case "$CANDIDATE" in
        "") ;;
        /*) WT="$(worktree_root_of "$CANDIDATE/")" ;;
        *)  WT="$(worktree_root_of "$CWD/${CANDIDATE#./}/")" ;;
      esac
    fi
    [ -n "$WT" ] || exit 0
    [ -d "$WT/.ddev" ] || exit 0
    [ -f "$WT/.ddev/config.local.yaml" ] && exit 0

    NAME="$(basename "$WT")"
    jq -n --arg n "$NAME" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: ("El worktree \($n) todavía no está aprovisionado para DDEV: su .ddev/config.yaml lleva el mismo name que el proyecto principal, así que cualquier comando ddev fallará por colisión de nombre. Ejecuta primero `ddev worktree up \($n)`, que le asigna un nombre propio, copia el .env, arranca los contenedores, hace composer install y clona la base de datos y los ficheros del proyecto principal. No edites .ddev/config.yaml, que está versionado.")
      }
    }'
    exit 0
    ;;

  PostToolUse)
    CWD="$(jq -r '.cwd // ""' <<<"$INPUT")"
    WT="$(worktree_root_of "$CWD/")"
    [ -n "$WT" ] || WT="$CWD"
    has_ddev_ancestor "$WT" || exit 0
    [ -f "$WT/.ddev/config.local.yaml" ] && exit 0

    jq -n '{
      systemMessage: "Este proyecto usa DDEV. Si vas a levantar el sitio o ejecutar drush/composer en este worktree, ejecuta antes `ddev worktree up`."
    }'
    exit 0
    ;;
esac

exit 0
