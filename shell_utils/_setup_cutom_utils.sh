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

# Loop through all .sh files in that directory except this one
loaded_str=""
for script in "$SCRIPT_DIR"/*.sh; do
    # Skip if this is the current script
    if [[ "$script" != "$THIS_SCRIPT" && -f "$script" ]]; then
        dos2unix --quiet "$script"
        if source "$script"; then
            script_name=$(basename "$script")
            if [[ -z "$loaded_str" ]]; then # first
                loaded_str="$script_name"
            else
                loaded_str="$loaded_str, $script_name"
            fi
        fi
    fi
done

if [[ -n "$loaded_str" ]]; then
    echo "Loaded utils: $loaded_str"
fi

# Run startup utils
echo "Running startup scripts..."
load_ssh_keys
mount_h
#monitor_stock not_restart_if_running run_in_background
