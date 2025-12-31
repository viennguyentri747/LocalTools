# git_tools.sh

_git_qhelp() {
  printf '%s\n' \
    "ghelp       → Show this help" \
    "qpush       → Quick push (add + commit + prompt push)" \
    "qlog        → One-line commit log" \
    "qdiff       → Clean diff (no warning ...)" | column -t
}

_git_qpush() {
  # Get a list of all configured remotes
  _remotes=($(command git remote))

  # Exit if no remotes are configured
  if [ ${#_remotes[@]} -eq 0 ]; then
    echo "No remotes found to push to."
    return 1
  fi

  # Get the current branch name
  _b=$(command git rev-parse --abbrev-ref HEAD)

  # Check if there are any changes or extra untracked files to stage
  if command git diff --quiet && command git diff --cached --quiet && [ -z "$(command git ls-files --others --exclude-standard)" ]; then
    echo "No changes or untracked files to commit. Checking if there is anything to push..."
    
    # Check if the local branch is ahead of ANY remote
    any_ahead=0
    for _r in "${_remotes[@]}"; do
      # Count commits on the local branch that are not on the remote branch.
      ahead=$(command git rev-list --count "${_r}/${_b}..${_b}" 2>/dev/null || echo 0)
      if [ "${ahead:-0}" -gt 0 ]; then
        any_ahead=1
        break
      fi
    done

    # If no remotes are behind, nothing to do
    if [ "$any_ahead" -eq 0 ]; then
      echo "Nothing to push. All remotes are up-to-date."
      return 0
    fi
    
    echo "Found unpushed commits. Proceeding ..."
  else
    # Show what files would be changed
    echo "Files to be committed:"
    if ! command git diff --quiet; then
      echo "  Modified files:"
      command git diff --name-status | sed 's/^/    /'
    fi
    if ! command git diff --cached --quiet; then
      echo "  Already staged files:"
      command git diff --cached --name-status | sed 's/^/    /'
    fi
    echo

    # Show untracked files
    _untracked=$(command git ls-files --others --exclude-standard)
    if [ -n "$_untracked" ]; then
      echo "  Untracked files (will be added):"
      echo "$_untracked" | sed 's/^/    ?? /'
    fi
    echo

    # Format the list of remotes for the confirmation message
    _remotes_list="${_remotes[*]}"
    
    # Ask for confirmation before staging, committing, and pushing
    printf "Stage, commit, and push branch [%s] to ALL remotes [%s]? (y/N) " "$_b" "$_remotes_list"
    read -r confirm
    case "$confirm" in
      [yY])
        # Now do the actual staging and committing
        echo "--> Staging changes..."
        command git add .
        
        echo "--> Committing changes..."
        # The `|| true` prevents the script from exiting if there's nothing to commit.
        if ! command git commit -m "Quick Push"; then
          echo "Nothing new to commit after staging."
          return 0
        fi
        ;;
      *)
        echo "Quick push cancelled."
        return 0
        ;;
    esac
  fi

  # Push to all remotes
  all_pushed=true
  for _r in "${_remotes[@]}"; do
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

_ensure_ssh_agent() {
  # Check if agent is running and accessible, start if not
  if [ -z "$SSH_AGENT_PID" ] || ! kill -0 "$SSH_AGENT_PID" 2>/dev/null; then
    eval "$(ssh-agent -s)" > /dev/null
  fi
}

load_ssh_keys() {
  _ensure_ssh_agent

  KEYS=(id_ed25519_intel_github id_ed25519_personal_github)
  for KEY_NAME in "${KEYS[@]}"; do
    ssh-add -l | grep -q "$KEY_NAME" || ssh-add "$HOME/.ssh/$KEY_NAME"
  done
}
