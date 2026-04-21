#!/bin/bash

normalize_script_line_endings() {
    local script_path="$1"
    if [ -z "$script_path" ] || [ ! -f "$script_path" ]; then return 0; fi
    if command -v dos2unix >/dev/null 2>&1; then dos2unix --quiet "$script_path" 2>/dev/null || true; fi
}

join_csv_line() {
    local existing="$1" next="$2"
    if [ -z "$existing" ]; then printf "%s" "$next"; else printf "%s, %s" "$existing" "$next"; fi
}

source_shell_utils_script() {
    local script_path="$1"
    normalize_script_line_endings "$script_path"
    source "$script_path"
}

_is_windows_path() {
    [[ "$1" == [A-Za-z]:\\* ]] || [[ "$1" == \\\\* ]]
}

convert_wsl_to_win_path() {
    local source_path="$1" windows_path=""
    if [ -z "$source_path" ]; then
        echo "Usage: convert_wsl_to_win_path <wsl_path>" >&2
        return 1
    fi

    if [[ "$source_path" == "~" ]]; then source_path="$HOME"; fi
    if [[ "$source_path" == "~/"* ]]; then source_path="$HOME/${source_path:2}"; fi
    if _is_windows_path "$source_path"; then
        printf "%s" "$source_path"
        return 0
    fi

    if ! command -v wslpath >/dev/null 2>&1; then
        echo "wslpath not found; cannot convert '$source_path' to Windows path." >&2
        return 1
    fi
    if ! windows_path=$(wslpath -w "$source_path" 2>/dev/null); then
        echo "Failed to convert path: $source_path" >&2
        return 1
    fi
    if ! _is_windows_path "$windows_path"; then
        echo "Invalid converted Windows path: $windows_path" >&2
        return 1
    fi
    printf "%s" "$windows_path"
}

to_windows_path() { convert_wsl_to_win_path "$@"; }

convert_win_to_wsl_path() {
    local win_path="$*" clean_path wsl_path drive rest
    if [ -z "$win_path" ]; then
        echo "Usage: convert_win_to_wsl_path <windows_path>" >&2
        return 1
    fi

    clean_path="${win_path%\"}"; clean_path="${clean_path#\"}"
    clean_path="${clean_path%\'}"; clean_path="${clean_path#\'}"
    if [ "${#clean_path}" -ge 3 ] && [ "${clean_path:1:1}" = ":" ] && [[ "$clean_path" != *"/"* ]] && [[ "$clean_path" != *"\\"* ]]; then
        echo "Invalid Windows path formatting. Use quotes, doubled backslashes, or forward slashes. Example: \"C:\\\\Users\\\\...\\\\python.exe\" or C:/Users/.../python.exe" >&2
        return 1
    fi

    if command -v wslpath >/dev/null 2>&1; then
        if wsl_path=$(wslpath -u "$clean_path" 2>/dev/null); then
            printf "%s\n" "$wsl_path"
            return 0
        fi
    fi

    clean_path="${clean_path//\\//}"
    if [ "${#clean_path}" -ge 3 ] && [ "${clean_path:1:2}" = ":/" ]; then
        drive="${clean_path:0:1}"
        rest="${clean_path:3}"
        drive=$(printf "%s" "$drive" | tr '[:upper:]' '[:lower:]')
        wsl_path="/mnt/$drive"
        [ -n "$rest" ] && wsl_path="$wsl_path/$rest"
        printf "%s\n" "$wsl_path"
        return 0
    fi

    printf "%s\n" "$clean_path"
}

# Keep compatibility with existing typo alias.
covert_win_to_wsl_path() { convert_win_to_wsl_path "$@"; }
