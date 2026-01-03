# #!/bin/bash

# __zsh_plugins_is_interactive() { [[ $- == *i* ]]; }
# __zsh_plugins_has_cmd() { command -v "$1" >/dev/null 2>&1; }

# __zsh_plugins_open_url() {
#   local url="$1"
#   if [[ -z "$url" ]]; then echo "Usage: open_url <url>"; return 1; fi
#   if __zsh_plugins_has_cmd xdg-open; then xdg-open "$url" >/dev/null 2>&1 & return 0; fi
#   if __zsh_plugins_has_cmd open; then open "$url" >/dev/null 2>&1 & return 0; fi
#   if __zsh_plugins_has_cmd gio; then gio open "$url" >/dev/null 2>&1 & return 0; fi
#   if __zsh_plugins_has_cmd cmd.exe; then cmd.exe /c start "" "$url" >/dev/null 2>&1; return 0; fi
#   echo "No supported browser opener found (xdg-open/open/gio/cmd.exe)." >&2
#   return 1
# }

# __zsh_plugins_urlencode() {
#   if __zsh_plugins_has_cmd python3; then
#     python3 - "$@" <<'PY'
# import sys, urllib.parse
# print(urllib.parse.quote_plus(" ".join(sys.argv[1:])))
# PY
#     return 0
#   fi
#   local s="$*"; s="${s// /+}"; printf '%s' "$s"
# }

# web_search() {
#   local provider="$1"; shift || true
#   if [[ -z "$provider" || $# -eq 0 ]]; then echo "Usage: web_search <provider> <query...>"; return 1; fi
#   local query url; query="$(__zsh_plugins_urlencode "$@")"
#   case "$provider" in
#     google) url="https://www.google.com/search?q=$query" ;;
#     github) url="https://github.com/search?q=$query" ;;
#     chatgpt) url="https://chatgpt.com/?q=$query" ;;
#     stackoverflow|so) url="https://stackoverflow.com/search?q=$query" ;;
#     duckduckgo|ddg) url="https://duckduckgo.com/?q=$query" ;;
#     bing) url="https://www.bing.com/search?q=$query" ;;
#     youtube|yt) url="https://www.youtube.com/results?search_query=$query" ;;
#     wikipedia|wiki) url="https://en.wikipedia.org/wiki/Special:Search?search=$query" ;;
#     *) echo "Unknown provider: $provider"; return 1 ;;
#   esac
#   __zsh_plugins_open_url "$url"
# }

# alias web-search='web_search'
# alias google='web_search google'
# alias github='web_search github'
# alias chatgpt='web_search chatgpt'
# alias stackoverflow='web_search stackoverflow'
# alias so='web_search stackoverflow'
# alias ddg='web_search duckduckgo'
# alias bing='web_search bing'
# alias yt='web_search youtube'
# alias wiki='web_search wikipedia'

# __zsh_plugins_sudo_command_line_zsh() {
#   [[ -z "$BUFFER" ]] && zle up-history
#   if [[ "$BUFFER" == sudo\ * ]]; then BUFFER="${BUFFER#sudo }"; else BUFFER="sudo $BUFFER"; fi
#   CURSOR=${#BUFFER}
# }

# __zsh_plugins_sudo_command_line_bash() {
#   local line="$READLINE_LINE"
#   if [[ -z "$line" ]]; then READLINE_LINE="sudo "
#   elif [[ "$line" == sudo\ * ]]; then READLINE_LINE="${line#sudo }"
#   else READLINE_LINE="sudo $line"
#   fi
#   READLINE_POINT=${#READLINE_LINE}
# }

# __zsh_plugins_setup_sudo() {
#   __zsh_plugins_is_interactive || return 0
#   if [[ -n "${ZSH_VERSION-}" ]]; then
#     zle -N __zsh_plugins_sudo_command_line_zsh
#     bindkey -M emacs '\e\e' __zsh_plugins_sudo_command_line_zsh
#     bindkey -M viins '\e\e' __zsh_plugins_sudo_command_line_zsh
#   elif [[ -n "${BASH_VERSION-}" ]]; then
#     bind -x '"\e\e":__zsh_plugins_sudo_command_line_bash' 2>/dev/null || true
#   fi
# }

# __dirhistory_update() {
#   local cwd="$PWD" d size; size="${DIRHISTORY_SIZE:-20}"
#   if [[ "${__DIRHISTORY_STACK[0]-}" == "$cwd" ]]; then return 0; fi
#   local -a new_stack=("$cwd")
#   for d in "${__DIRHISTORY_STACK[@]}"; do [[ "$d" == "$cwd" ]] && continue; new_stack+=("$d"); done
#   __DIRHISTORY_STACK=("${new_stack[@]:0:$size}")
# }

# __dirhistory_print_bash() {
#   local i=0 d
#   for d in "${__DIRHISTORY_STACK[@]}"; do printf '%d\t%s\n' "$i" "$d"; i=$((i + 1)); done
# }

# __dirhistory_jump_bash() {
#   local idx="$1" target
#   if ! [[ "$idx" =~ ^[0-9]+$ ]]; then echo "Usage: dirhistory [index]"; return 1; fi
#   target="${__DIRHISTORY_STACK[$idx]}"
#   if [[ -z "$target" ]]; then echo "dirhistory: index $idx out of range"; return 1; fi
#   builtin cd "$target"
# }

# dirhistory() {
#   local idx="${1-}"
#   if [[ -n "${ZSH_VERSION-}" ]]; then
#     if [[ -n "$idx" ]]; then cd +"$idx"; else dirs -v; fi
#     return $?
#   fi
#   if [[ -n "${BASH_VERSION-}" ]]; then
#     __dirhistory_update
#     if [[ -n "$idx" ]]; then __dirhistory_jump_bash "$idx"; else __dirhistory_print_bash; fi
#     return $?
#   fi
#   echo "dirhistory: unsupported shell." >&2
#   return 1
# }

# __dirhistory_init() {
#   : "${DIRHISTORY_SIZE:=20}"
#   if [[ -n "${ZSH_VERSION-}" ]]; then
#     setopt AUTO_PUSHD PUSHD_IGNORE_DUPS PUSHD_SILENT
#     DIRSTACKSIZE="$DIRHISTORY_SIZE"
#   elif [[ -n "${BASH_VERSION-}" ]]; then
#     __dirhistory_update
#     if [[ -z "$PROMPT_COMMAND" ]]; then PROMPT_COMMAND="__dirhistory_update"
#     elif [[ "$PROMPT_COMMAND" != *"__dirhistory_update"* ]]; then PROMPT_COMMAND="__dirhistory_update; $PROMPT_COMMAND"
#     fi
#   fi
# }

# __zsh_plugins_setup_sudo
# __dirhistory_init
# alias d='dirhistory'
