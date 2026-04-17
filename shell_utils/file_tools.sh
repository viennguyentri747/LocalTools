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

# rm() {
#     local files_to_remove=()
#     local permanent_delete=false
#     local rm_options=()
    
#     # Parse arguments
#     for arg in "$@"; do
#         case "$arg" in
#             -permanent|--permanent)
#                 permanent_delete=true
#                 ;;
#             -*)
#                 # Collect other options for permanent delete mode
#                 rm_options+=("$arg")
#                 ;;
#             *)
#                 # This is a file or folder argument
#                 files_to_remove+=("$arg")
#                 ;;
#         esac
#     done
    
#     # Check if we have any files to process
#     if [ ${#files_to_remove[@]} -eq 0 ]; then
#         echo "rm: no files specified" >&2
#         return 1
#     fi
    
#     # Handle permanent delete mode
#     if $permanent_delete; then
#         echo "Deleting permanently: ${files_to_remove[*]}"
#         command rm "${rm_options[@]}" "${files_to_remove[@]}"
#         return $?
#     fi
    
#     # Create trash directory if it doesn't exist (only for trash mode)
#     mkdir -p "$trash_dir"
    
#     # Get absolute path of trash directory for comparison
#     local trash_realpath=$(realpath "$trash_dir" 2>/dev/null)
    
#     # Move each file/folder to trash directory
#     for file in "${files_to_remove[@]}"; do
#         if [ -e "$file" ]; then
#             local file_realpath=$(realpath "$file" 2>/dev/null)
#             local should_backup=false
            
#             if [ "$file_realpath" = "$trash_realpath" ] || [ "$file" -ef "$trash_dir" ] || [[ "$file_realpath" == "$trash_realpath"/* ]]; then
#                 # File/folder is already in trash directory, delete directly
#                 should_backup=false
#             else
#                 local filesize=0
#                 if [ -f "$file" ]; then
#                     filesize=$(stat -c%s "$file")
#                 elif [ -d "$file" ]; then
#                     filesize=$(du -sb "$file" | cut -f1)
#                 fi

#                 # --- Confirm backup if file/dir size is over 1GB ---
#                 if [ "$filesize" -ge $((1024*1024*1024)) ]; then
#                     printf "%s" "File or folder '$file' is over 1GB ($(numfmt --to=iec "$filesize")). Still move to trash regardless? [y/N]: "
#                     read -r confirm
#                     case "$confirm" in
#                         [yY][eE][sS]|[yY]) 
#                             should_backup=true
#                             ;;
#                     esac
#                 else
#                     should_backup=true
#                 fi
#                 # --- End confirm over 1GB ---
#             fi
            
#             if [ "$should_backup" = true ]; then
#                 local basename=$(basename "$file")
#                 local trash_target="$trash_dir/$basename"
#                 mv "$file" "$trash_target" && echo "Moved '$file' to trash: '$trash_target'"
#             else
#                 command rm "${rm_options[@]}" "$file" && echo "Removed '$file' directly (not backed up)"
#             fi
#         else
#             echo "rm: cannot remove '$file': No such file or directory" >&2
#         fi
#     done
# }


#deep_extract() {
#    case "$1" in
#        -h|--help)
#            echo "Usage: deep_extract [DIRECTORY]"
#            echo "  Recursively extract all nested archives in DIRECTORY"
#            return 0 ;;
#    esac

#    if [ -z "$1" ]; then
#        echo "Error: directory argument is required." >&2
#        echo "Usage: deep_extract [DIRECTORY]" >&2
#        return 1
#    fi

#    local dir="$1"

#    if [ ! -d "$dir" ]; then
#        echo "Error: '$dir' is not a valid directory." >&2
#        return 1
#    fi

#    find "$dir" -type f \( -name "*.tar" -o -name "*.tar.gz" -o -name "*.tgz" -o -name "*.tar.bz2" -o -name "*.tbz2" -o -name "*.tar.xz" -o -name "*.txz" -o -name "*.tar.zst" -o -name "*.zip" -o -name "*.gz" -o -name "*.bz2" -o -name "*.xz" -o -name "*.zst" -o -name "*.7z" -o -name "*.rar" \) | sort --reverse | while read -r archive; do
#        local parent_dir base_name extract_dir
#        parent_dir="$(dirname "$archive")"
#        base_name="$(basename "$archive")"
#        extract_dir="$parent_dir/$(echo "$base_name" | sed 's/\(\.\(tar\|gz\|bz2\|xz\|zst\|zip\|tgz\|tbz2\|txz\|7z\|rar\)\)\+$//')"

#        echo "Extracting: $archive -> $extract_dir"
#        mkdir -p "$extract_dir"

#        case "$base_name" in
#            *.tar.gz|*.tgz)   tar -xzf  "$archive" -C "$extract_dir" ;;
#            *.tar.bz2|*.tbz2) tar -xjf  "$archive" -C "$extract_dir" ;;
#            *.tar.xz|*.txz)   tar -xJf  "$archive" -C "$extract_dir" ;;
#            *.tar.zst)        tar -x --zstd -f "$archive" -C "$extract_dir" ;;
#            *.tar)            tar -xf   "$archive" -C "$extract_dir" ;;
#            *.zip)            unzip -q  "$archive" -d "$extract_dir" ;;
#            *.gz)             gunzip -c "$archive" > "$extract_dir/${base_name%.gz}" ;;
#            *.bz2)            bunzip2 -c "$archive" > "$extract_dir/${base_name%.bz2}" ;;
#            *.xz)             xz -dc    "$archive" > "$extract_dir/${base_name%.xz}" ;;
#            *.zst)            zstd -dc  "$archive" > "$extract_dir/${base_name%.zst}" ;;
#            *.7z)             7z x -o"$extract_dir" "$archive" ;;
#            *.rar)            unrar x   "$archive" "$extract_dir/" ;;
#        esac

#        if [ $? -eq 0 ]; then
#            # Clean up target archive
#            rm -f "$archive"
#        else
#            echo "  ERROR extracting $archive, leaving in place"
#            rmdir --ignore-fail-on-non-empty "$extract_dir"
#        fi
#    done

#    if find "$dir" -type f \( -name "*.tar" -o -name "*.tar.gz" -o -name "*.tgz" -o -name "*.tar.bz2" -o -name "*.tbz2" -o -name "*.tar.xz" -o -name "*.txz" -o -name "*.tar.zst" -o -name "*.zip" -o -name "*.gz" -o -name "*.bz2" -o -name "*.xz" -o -name "*.zst" -o -name "*.7z" -o -name "*.rar" \) | grep -q .; then
#        deep_extract "$dir"
#    fi

#    echo "Done. All archives extracted in: $dir"
#}

deep_extract() {
    local script="/home/vien/workspace/intellian_core_repos/local_tools/independent_scripts/deep_extract.py"

    if [ ! -f "$script" ]; then
        echo "Error: script not found: $script" >&2
        return 1
    fi

    if command -v python3 >/dev/null 2>&1; then
        python3 "$script" "$@"
    elif command -v python >/dev/null 2>&1; then
        python "$script" "$@"
    else
        echo "Error: python interpreter not found." >&2
        return 1
    fi
}

_extract_py() {
    deep_extract_py "$@"
}
