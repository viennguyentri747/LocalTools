#!/bin/bash

trash_dir="$HOME/.local/share/Trash/"

clean_trash() {
    # check if directory exists first
    if [ ! -d "$trash_dir" ]; then
        echo "Trash directory not found at: $trash_dir"
        return 1
    fi

    if [ -n "${ZSH_VERSION-}" ]; then
        setopt localoptions nullglob globdots
    else
        shopt -s nullglob dotglob # Enable nullglob and dotglob to include hidden files
    fi
    files=("$trash_dir"*)
    if [ -z "${ZSH_VERSION-}" ]; then
        shopt -u nullglob dotglob # Disable nullglob and dotglob to restore previous behavior
    fi
    
    if [ ${#files[@]} -eq 0 ]; then
        echo "Trash directory '$trash_dir' is already empty."
    else
        #Remove all files including hidden files
        rm -rf "${files[@]}"
        echo "Trash cleaned (including hidden files)."
    fi
}

dos2unix_dir() {
    local dir="$1"
    
    # Validation
    if [[ -z "$dir" ]]; then echo "Usage: dos2unix_dir <dir_path>"; return 1; fi
    if [[ ! -d "$dir" ]]; then echo "Directory not found: $dir"; return 1; fi
    if ! command -v dos2unix >/dev/null 2>&1; then echo "Error: dos2unix not installed."; return 1; fi

    local total=0 ok=0 fail=0
    
    echo "--- Starting targeted conversion in: $dir ---"
    local total=0 ok=0 fail=0
    while IFS= read -r -d '' file; do
        ((total++))
        
        # Running dos2unix
        if dos2unix "$file"; then
            ((ok++))
        else
            ((fail++))
        fi
        # Define targeted extensions (case-insensitive)
    done < <(find "$dir" -type f -not -path "*/.git/*" \
            \( -name "*.sh" -o -name "*.py" -o -name "*.bash" -o -name "*.pl" \) -print0)
            
    echo "------------------------------------------"
    echo "Finished: Total=$total | OK=$ok | Failed=$fail"
}

deep_extract() {
    #Ex: deep_extract --input_dir_or_archive ~/downloads/ETOWL_LOG0416 --archive_name_regex '^(350928590056204|350928590056205|master|backup|live)'
    local script="/home/vien/workspace/intellian_core_repos/local_tools/independent_scripts/deep_extract.py"
    local win_script="$script"
    local -a raw_args=("$@")
    local -a normalized_args=()
    local first_arg="${1-}"
    local usage_msg="Usage: deep_extract --input_dir_or_archive <path> [--archive_name_regex <regex>] [--should_remove_orig_dir true|false] [--jobs <n>]"

    if [ ! -f "$script" ]; then
        echo "Error: script not found: $script" >&2
        return 1
    fi

    if [ ${#raw_args[@]} -eq 0 ]; then
        echo "Error: --input_dir_or_archive is required." >&2
        echo "$usage_msg" >&2
        return 1
    fi

    if [[ "$first_arg" != -* ]]; then
        echo "Error: positional argument is not supported. Use --input_dir_or_archive <path>." >&2
        echo "$usage_msg" >&2
        return 1
    fi

    case "$first_arg" in
        -h|--help)
            echo "$usage_msg"
            echo "Example (prefix filter): deep_extract --input_dir_or_archive /path/to/logs --archive_name_regex '^(350928590056204|350928590056205|master)'"
            ;;
    esac

    local arg="" expect_input_path_value=0
    for arg in "${raw_args[@]}"; do
        if [ "$expect_input_path_value" -eq 1 ]; then
            normalized_args+=("$arg")
            expect_input_path_value=0
            continue
        fi
        case "$arg" in
            --input_dir_or_archive)
                normalized_args+=("$arg")
                expect_input_path_value=1
                ;;
            --input_dir)
                normalized_args+=("--input_dir_or_archive")
                expect_input_path_value=1
                ;;
            --input_dir_or_archive=*)
                normalized_args+=("$arg")
                ;;
            --input_dir=*)
                normalized_args+=("--input_dir_or_archive=${arg#--input_dir=}")
                ;;
            *)
                normalized_args+=("$arg")
                ;;
        esac
    done
    if [ "$expect_input_path_value" -eq 1 ]; then
        echo "Error: --input_dir_or_archive requires a path value." >&2
        return 1
    fi

    if alias win_python >/dev/null 2>&1 || command -v win_python >/dev/null 2>&1; then
        local -a win_args=()
        local input_dir_value="" expect_input_dir_value=0
        win_script=$(convert_wsl_to_win_path "$script")
        for arg in "${normalized_args[@]}"; do
            if [ "$expect_input_dir_value" -eq 1 ]; then
                input_dir_value=$(convert_wsl_to_win_path "$arg")
                win_args+=("$input_dir_value")
                expect_input_dir_value=0
                continue
            fi
            case "$arg" in
                --input_dir_or_archive)
                    win_args+=("$arg")
                    expect_input_dir_value=1
                    ;;
                --input_dir_or_archive=*)
                    input_dir_value="${arg#--input_dir_or_archive=}"
                    input_dir_value=$(convert_wsl_to_win_path "$input_dir_value")
                    win_args+=("--input_dir_or_archive=$input_dir_value")
                    ;;
                *)
                    win_args+=("$arg")
                    ;;
            esac
        done
        if [ "$expect_input_dir_value" -eq 1 ]; then
            echo "Error: --input_dir_or_archive requires a path value." >&2
            return 1
        fi
        echo "[deep_extract] Using python via win_python"
        win_python "$win_script" "${win_args[@]}"
    elif command -v python3 >/dev/null 2>&1; then
        echo "[deep_extract] Using python3: $(command -v python3)"
        python3 "$script" "${normalized_args[@]}"
    elif command -v python >/dev/null 2>&1; then
        echo "[deep_extract] Using python: $(command -v python)"
        python "$script" "${normalized_args[@]}"
    else
        echo "[deep_extract] No usable python interpreter found (checked: win_python, python3, python)." >&2
        echo "Error: python interpreter not found." >&2
        return 1
    fi
}

deep_extraction() { deep_extract "$@"; }

_extract_py() {
    deep_extract_py "$@"
}
