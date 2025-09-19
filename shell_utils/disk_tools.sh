is_vscode_terminal() {
    [[ -n "$VSCODE_INJECTION" ]] || [[ -n "$TERM_PROGRAM" && "$TERM_PROGRAM" == "vscode" ]]
}

mount_h() {
    echo "Check if need mount H: drive"
    
    # First check if H: exists in Windows
    powershell.exe -Command '$result = if (Test-Path H:) { "SUCCESS" } else { "FAIL" }; $result | Out-File -FilePath "$env:TEMP\ps_result.txt" -Encoding UTF8 -NoNewline'
    # Read the result from the temp file
    if cat /mnt/c/Users/VIEN~1.NGU/AppData/Local/Temp/ps_result.txt | grep -q "SUCCESS"; then
        echo "H: drive exists"
    else
        echo "H: drive does not exist or is not accessible from Windows. Wait for GG D"
        return 1
    fi  
    
    if mount | grep -q "H: on /mnt/h"; then
        echo "H: drive is already mounted at /mnt/h"
    else
        # VSCode specific: Always flush input buffer and add delay
        if is_vscode_terminal; then
            sleep 0.2
            while read -t 0.1 -r junk 2>/dev/null; do
                echo "Flushed VSCode input: '$junk'" >&2
            done
        fi
        
        sudo mkdir -p /mnt/h
        if sudo mount -t drvfs H: /mnt/h 2>/dev/null; then
            echo "Successfully mounted H: to /mnt/h"
        else
            echo "Failed to mount H: drive - drive may not exist or be accessible"
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