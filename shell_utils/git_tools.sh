# git_tools.sh

_git_qhelp() {
  printf '%s\n' \
    "ghelp       → Show this help" \
    "qpush       → Quick push (add + commit + prompt push)" \
    "qlog        → One-line commit log" \
    "qdiff       → Clean diff (no warning ...)" | column -t
}

_git_qpush() {
  # Add + Commit + Push to ALL remotes, interactive confirm, tolerant of "nothing to commit"
  command git add .
  # The `|| true` prevents the script from exiting if there's nothing to commit.
  command git commit -m "Quick Push" || true

  # Get the current branch name
  _b=$(command git rev-parse --abbrev-ref HEAD)
  # Get a list of all configured remotes
  _remotes=$(command git remote)

  # Exit if no remotes are configured
  if [ -z "$_remotes" ]; then
    echo "No remotes found to push to."
    return 1
  fi

  # Check if the local branch is ahead of ANY of the remotes
  any_ahead=0
  for _r in $_remotes; do
    # Count commits on the local branch that are not on the remote branch.
    # `2>/dev/null` suppresses errors if the remote branch doesn't exist yet.
    ahead=$(command git rev-list --count "${_r}/${_b}..${_b}" 2>/dev/null || echo 0)
    if [ "${ahead:-0}" -gt 0 ]; then
      any_ahead=1
      break # Found a remote that's behind, no need to check others.
    fi
  done

  # If no remotes are behind, there's nothing to push.
  if [ "$any_ahead" -eq 0 ]; then
    echo "Nothing to push. All remotes are up-to-date."
    return 0
  fi

  # Format the list of remotes for the confirmation message
  _remotes_list=$(echo "$_remotes" | tr '\n' ' ')
  
  # Ask for confirmation before pushing to all remotes
  printf "Push branch [%s] to ALL remotes [%s]? (y/N) " "$_b" "$_remotes_list"
  read -r confirm
  case "$confirm" in
    [yY])
      all_pushed=true
      # Loop through each remote and push the current branch
      for _r in $_remotes; do
        echo "--> Pushing to remote '$_r'..."
        if ! command git push "$_r" "$_b"; then
            echo "!! Failed to push to '$_r'."
            all_pushed=false
        fi
      done

      if $all_pushed; then
        echo "Quick push to all remotes completed successfully!"
      else
        echo "Quick push completed with one or more failures."
      fi
      ;;
    *)
      echo "Quick push cancelled."
      ;;
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
