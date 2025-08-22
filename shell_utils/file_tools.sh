trash_dir="$HOME/.local/share/Trash/"
mkdir -p "$trash_dir"

rm() {
    local files_to_remove=()
    local permanent_delete=false
    local rm_options=()
    
    # Create trash directory if it doesn't exist (only if not permanent delete)
    mkdir -p "$trash_dir"
    
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
    
    # Move each file/folder to trash directory
    for file in "${files_to_remove[@]}"; do
        if [ -e "$file" ]; then
            # Generate unique name if file already exists in trash
            local basename=$(basename "$file")
            local trash_target="$trash_dir/$basename"
            # local counter=1 # For extra copies
            # while [ -e "$trash_target" ]; do
            #     trash_target="$trash_dir/${basename}.${counter}"
            #     ((counter++))
            # done
            
            mv "$file" "$trash_target"
            echo "Backed up '$file' to '$trash_target'"
        else
            echo "No '$file' found -> Ignoring!" >&2
        fi
    done
}