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
            # Get absolute path of the file for comparison
            local file_realpath=$(realpath "$file" 2>/dev/null)
            
            # Skip backing up the trash directory itself (multiple checks)
            if [ "$file_realpath" = "$trash_realpath" ] || [ "$file" -ef "$trash_dir" ] ||  [[ "$file_realpath" == "$trash_realpath"/* ]]; then
                echo "Skipping trash directory or its contents: '$file'" >&2
                continue
            fi
            
            # Generate unique name if file already exists in trash
            local basename=$(basename "$file")
            local trash_target="$trash_dir/$basename"
            # local counter=1
            
            # while [ -e "$trash_target" ]; do
            #     trash_target="$trash_dir/${basename}.${counter}"
            #     ((counter++))
            # done
            
            mv "$file" "$trash_target"
            echo "Moved '$file' to trash: '$trash_target'"
        else
            echo "rm: cannot remove '$file': No such file or directory" >&2
        fi
    done
}