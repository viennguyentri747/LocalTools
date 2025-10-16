#!/bin/bash

trash_dir="$HOME/.local/share/Trash/"

rm() {
    local files_to_remove=()
    local permanent_delete=false
    local rm_options=()
    
    # Parse arguments
    for arg in "$@"; do
        case "$arg" in
            -permanent|--permanent)
                permanent_delete=true
                ;;
            -*)
                # Collect other options for permanent delete mode
                rm_options+=("$arg")
                ;;
            *)
                # This is a file or folder argument
                files_to_remove+=("$arg")
                ;;
        esac
    done
    
    # Check if we have any files to process
    if [ ${#files_to_remove[@]} -eq 0 ]; then
        echo "rm: no files specified" >&2
        return 1
    fi
    
    # Handle permanent delete mode
    if $permanent_delete; then
        echo "Deleting permanently: ${files_to_remove[*]}"
        command rm "${rm_options[@]}" "${files_to_remove[@]}"
        return $?
    fi
    
    # Create trash directory if it doesn't exist (only for trash mode)
    mkdir -p "$trash_dir"
    
    # Get absolute path of trash directory for comparison
    local trash_realpath=$(realpath "$trash_dir" 2>/dev/null)
    
    # Move each file/folder to trash directory
    for file in "${files_to_remove[@]}"; do
        if [ -e "$file" ]; then
            local file_realpath=$(realpath "$file" 2>/dev/null)
            local should_backup=false
            
            if [ "$file_realpath" = "$trash_realpath" ] || [ "$file" -ef "$trash_dir" ] || [[ "$file_realpath" == "$trash_realpath"/* ]]; then
                should_backup=false
            else
                local filesize=0
                if [ -f "$file" ]; then
                    filesize=$(stat -c%s "$file")
                elif [ -d "$file" ]; then
                    filesize=$(du -sb "$file" | cut -f1)
                fi

                # --- Confirm backup if file/dir size is over 1GB ---
                if [ "$filesize" -ge $((1024*1024*1024)) ]; then
                    read -p "File or folder '$file' is over 1GB ($(numfmt --to=iec "$filesize")). Move to trash? [y/N]: " confirm
                    case "$confirm" in
                        [yY][eE][sS]|[yY]) 
                            should_backup=true
                            ;;
                    esac
                else
                    should_backup=true
                fi
                # --- End confirm over 1GB ---
            fi
            
            if [ "$should_backup" = true ]; then
                local basename=$(basename "$file")
                local trash_target="$trash_dir/$basename"
                mv "$file" "$trash_target" && echo "Moved '$file' to trash: '$trash_target'"
            else
                command rm "${rm_options[@]}" "$file" && echo "Removed '$file' directly (not backed up)"
            fi
        else
            echo "rm: cannot remove '$file': No such file or directory" >&2
        fi
    done
}

explorer() {
    local file_path="$1"
    
    # Convert WSL path to Windows path
    local windows_path
    if ! windows_path=$(wslpath -w "$file_path" 2>&1); then
        echo "Failed to convert path: $windows_path" >&2
        return 1
    fi
    
    # Open Explorer with file selected
    explorer.exe /select,"$windows_path"
    
    # if [ $? -eq 0 ]; then
    #     echo "Opened Explorer to highlight '$file_path'"
    # else
    #     echo "Failed to open Explorer" >&2
    #     return 1
    # fi
}