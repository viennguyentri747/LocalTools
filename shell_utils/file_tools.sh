trash_dir="$HOME/.local/share/Trash/files"
mkdir -p "$trash_dir"

rm() {
    if [ $# -gt 0 ]; then
        echo "Warning: using original rm — deletion is permanent!"
        command rm "$@"
    else
        # No args — back up a default file
        file_to_backup="$HOME/important_file.txt"
        if [ -f "$file_to_backup" ]; then
            mv "$file_to_backup" "$trash_dir"
            echo "Backed up '$file_to_backup' to $trash_dir"
        else
            echo "No file to back up: $file_to_backup not found."
        fi
    fi
}