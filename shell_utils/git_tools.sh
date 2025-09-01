# git_tools.sh

_git_qhelp() {
  printf '%s\n' \
    "ghelp       → Show this help" \
    "qpush       → Quick push (add + commit + prompt push)" \
    "qlog        → One-line commit log" \
    "qdiff       → Clean diff (no warning ...)" | column -t
}

_git_qpush() {
  # Add + Commit + Push, interactive confirm, tolerant of "nothing to commit"
  command git add .
  command git commit -m "Quick Push" || true

  _b=$(command git rev-parse --abbrev-ref HEAD)
  _r=$(command git config remote.pushdefault || echo origin)

  ahead=$(command git rev-list --count "${_r}/${_b}..${_b}" 2>/dev/null || echo 0)
  if [ "${ahead:-0}" -le 0 ]; then
    echo "Nothing to push."
    return 0
  fi

  _p=$(basename -s .git "$(command git remote get-url "$_r")")
  printf "Push to branch [%s] of [remote %s] of project [%s]? (y/N) " "$_b" "$_r" "$_p"
  read -r confirm
  case "$confirm" in
    [yY]) command git push "$_r" "$_b" && echo "Quick push completed!" ;;
    *)    echo "Quick push cancelled." ;;
  esac
}

_git_qlog() {
  # One-line log; forwards any extra args (e.g., -n 10, pathspec)
  command git log \
    --pretty=format:"%h %s %ad %an" \
    --date=format:"%Y-%m-%d %H:%M" \
    "$@"
}

_git_qdiff() {
  # Clean diff (no safecrlf warnings); forwards args
  command git -c core.safecrlf=false diff "$@"
}

# --- Wrapper: override `git` to dispatch q*; fall through to real git ---
git() {
  if [ $# -eq 0 ]; then
    command git
    return
  fi

  case "$1" in
    qhelp) shift; _git_qhelp "$@"; return ;;
    qpush) shift; _git_qpush "$@"; return ;;
    qlog)  shift; _git_qlog  "$@"; return ;;
    qdiff) shift; _git_qdiff "$@"; return ;;
  esac

  # Everything else → real git
  command git "$@"
}
