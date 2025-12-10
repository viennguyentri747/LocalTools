source_bashrc() {
    if [[ -f "$HOME/.bashrc" ]]; then
        echo "[INFO] Sourcing ~/.bashrc to apply user configurations..."
        source "$HOME/.bashrc"
    else
        echo "[WARN] ~/.bashrc not found. Skipping sourcing."
    fi
}

is_vscode_terminal() {
    [[ -n "$VSCODE_INJECTION" ]] || [[ -n "$TERM_PROGRAM" && "$TERM_PROGRAM" == "vscode" ]]
}

mount_h() {
    # echo "Check if need mount H: drive"
    if powershell.exe -NoProfile -Command "if (Test-Path 'H:') { exit 0 } else { exit 1 }"; then
        has_h_drive=true
    else
        has_h_drive=false
    fi

    # Only proceed with mount logic if H: exists
    if [ "$has_h_drive" = false ]; then
        echo "[mount_h] H: drive does not exist or is not accessible from Windows. Wait for GG Drive to start and try again."
        return 1
    fi

    # Check if already mounted
    if mount | grep -q "H: on /mnt/h"; then
        echo "[mount_h] H: drive exists and is already mounted at /mnt/h"
    else
        # VSCode specific: Always flush input buffer and add delay
        if is_vscode_terminal; then
            sleep 0.2
            while read -t 0.1 -r junk 2>/dev/null; do
                echo "[mount_h] Flushed VSCode input: '$junk'" >&2
            done
        fi

        sudo mkdir -p /mnt/h
        if sudo mount -t drvfs H: /mnt/h 2>/dev/null; then
            echo "[mount_h] Successfully mounted H: to /mnt/h"
        else
            echo "[mount_h] Failed to mount H: drive - drive may not exist or be accessible"
            return 1
        fi
    fi
}

unmount_h() {
    echo "Check if need unmount H: drive"
    if mount | grep -q "H: on /mnt/h"; then
        sleep 1
        if sudo umount /mnt/h; then
            echo "Successfully unmounted H: from /mnt/h"
        else
            echo "Failed to unmount H: drive (may be busy)"
            echo "Try: lsof /mnt/h to see what's using it"
            return 1
        fi
    else
        echo "H: drive is not currently mounted"
    fi
}