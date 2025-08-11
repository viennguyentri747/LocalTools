trash_dir="$HOME/.local/share/Trash/"
mkdir -p "$trash_dir"

rm() {
    has_options=false
    for arg in "$@"; do
        case "$arg" in
            -*) has_options=true ;;
        esac
    done

    if $has_options; then
        echo "Warning: using original rm $@ —> Deletion is permanent!"
        command rm "$@"
    else
        # Move files to trash directory
        for file in "$@"; do
            if [ -e "$file" ]; then
                mv "$file" "$trash_dir"
                echo "Backed up '$file' at '$trash_dir'"
            else
                echo "rm: cannot remove '$file': No such file or directory" >&2
                return 1
            fi
        done
    fi
}