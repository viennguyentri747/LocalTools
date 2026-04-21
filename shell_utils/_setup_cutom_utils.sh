#!/bin/bash

# case ":$PATH:" in
#   *":/usr/local/bin:"*) ;;
#   *) export PATH="/usr/local/bin:$PATH" && echo "Added /usr/local/bin to PATH" ;;
# esac

#Homebrew:
eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"

#Pyenv
export PYENV_ROOT="$HOME/.pyenv"
# pyenv executable
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
# pyenv shims (THIS is what makes python/python3 work)
[[ -d $PYENV_ROOT/shims ]] && export PATH="$PYENV_ROOT/shims:$PATH"
# initialize pyenv
eval "$(pyenv init - zsh)"

#NVM
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm

#Custom utils
echo "[DEBUG] Current shell: $0, BASH_VERSION: ${BASH_VERSION-}, ZSH_VERSION: ${ZSH_VERSION-}, SHELL env: $SHELL"

# Common aliases
alias rmh="rm -f ~/.ssh/known_hosts"
# alias clean_trash="cmd rm -rf ~/.local/share/Trash/*"
alias sshp="sshpass -p"
# alias cb="tee >(xclip -selection clipboard -in) | wc -l | xargs -I{} echo '{} lines copied to clipboard!'"
alias cb='tee >(xclip -selection clipboard -in >/dev/null) | wc -l | xargs -I{} echo "{} lines copied to clipboard!"' #Redirect >/dev/null inside the process substitution so wc isn’t stuck waiting for input
alias pb='xclip -selection clipboard -out' # Paste from clipboard
alias subl='/mnt/c/Program\ Files/Sublime\ Text/subl.exe'
alias win_python='/mnt/c/Users/Vien.Nguyen/AppData/Local/Microsoft/WindowsApps/python.exe'
alias stock_alert='~/stock_alert/MyVenvFolder/bin/python ~/stock_alert/stock_alert/main.py'
alias win_git='/mnt/c/Program\ Files/Git/bin/git.exe'

# Find the directory where this script itself lives (bash/zsh compatible)
if [[ -n "${BASH_VERSION-}" ]]; then
    THIS_SOURCE="${BASH_SOURCE[0]}"
elif [[ -n "${ZSH_VERSION-}" ]]; then
    THIS_SOURCE="${(%):-%N}"
    THIS_SOURCE="${THIS_SOURCE:A}"
else
    THIS_SOURCE="$0"
fi
SCRIPT_DIR="$(cd "$(dirname "$THIS_SOURCE")" && pwd)"
THIS_SCRIPT="$SCRIPT_DIR/$(basename "$THIS_SOURCE")"
AUTO_LOAD_DIR="$SCRIPT_DIR/auto_load_tools"

# Deterministic loading order:
# 1) common utils (shared helpers), 2) explicit dependency scripts, 3) remaining scripts.
loaded_str=""
loaded_keys="|"
core_script_name="common_utils.sh"
priority_scripts=("windows_shell_tools.sh" "file_shell_tools.sh")

_append_loaded_script() {
    local script_name="$1"
    loaded_keys="${loaded_keys}${script_name}|"
    if command -v join_csv_line >/dev/null 2>&1; then
        loaded_str="$(join_csv_line "$loaded_str" "$script_name")"
    elif [[ -z "$loaded_str" ]]; then
        loaded_str="$script_name"
    else
        loaded_str="$loaded_str, $script_name"
    fi
}

_source_script_if_needed() {
    local script_path="$1" script_name="$(basename "$script_path")"
    if [[ "$script_path" == "$THIS_SCRIPT" ]] || [[ ! -f "$script_path" ]]; then return 0; fi
    if [[ "$loaded_keys" == *"|$script_name|"* ]]; then return 0; fi
    if command -v source_shell_utils_script >/dev/null 2>&1; then
        source_shell_utils_script "$script_path" || return 1
    else
        if command -v dos2unix >/dev/null 2>&1; then dos2unix --quiet "$script_path" 2>/dev/null || true; fi
        source "$script_path" || return 1
    fi
    _append_loaded_script "$script_name"
}

# Load common utils first so other scripts can reuse helper functions.
if ! _source_script_if_needed "$SCRIPT_DIR/$core_script_name"; then
    echo "Failed to load core shell utils: $core_script_name" >&2
fi

for script_name in "${priority_scripts[@]}"; do
    _source_script_if_needed "$AUTO_LOAD_DIR/$script_name"
done

if [[ ! -d "$AUTO_LOAD_DIR" ]]; then
    echo "Auto-load tool directory not found: $AUTO_LOAD_DIR" >&2
fi

for script_path in "$AUTO_LOAD_DIR"/*.sh; do
    [[ -f "$script_path" ]] || continue
    _source_script_if_needed "$script_path"
done

if [[ -n "$loaded_str" ]]; then
    echo "Loaded utils: $loaded_str"
fi

# Run startup utils
echo "Running startup scripts..."
load_ssh_keys
mount_h
#monitor_stock not_restart_if_running run_in_background
