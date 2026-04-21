source_shell_config() {
    local shell_type config_path
    if [ -n "$ZSH_VERSION" ]; then
        shell_type="zsh"
        config_path="$HOME/.zshrc"
    else
        shell_type="bash"
        config_path="$HOME/.bashrc"
    fi

    if [[ -f "$config_path" ]]; then
        echo "[INFO] Sourcing ${config_path} for ${shell_type} to apply user configurations..."
        source "$config_path"
    else
        echo "[WARN] ${config_path} not found. Skipping sourcing."
    fi
}

is_vscode_terminal() {
    [[ -n "$VSCODE_INJECTION" ]] || [[ -n "$TERM_PROGRAM" && "$TERM_PROGRAM" == "vscode" ]]
}

_H_MOUNT="/mnt/h"
_H_DRIVE="H:"

_h_drive_accessible() { 
    cmd.exe /c "if exist H:\ (echo True) else (echo False)" 2>/dev/null | tr -d '[:space:]\r\n' | grep -q "True"; 
}

_h_is_stale() {
    # Stale = mounted in /proc but ls fails (drvfs disconnected)
    if mount | grep -q "${_H_DRIVE} on ${_H_MOUNT}"; then
        if ! ls "${_H_MOUNT}" &>/dev/null; then
            return 0  # stale
        fi
    fi
    return 1  # not stale
}

_h_force_unmount() {
    if mount | grep -q "${_H_DRIVE} on ${_H_MOUNT}"; then
        sudo umount -l "${_H_MOUNT}" 2>/dev/null || sudo umount -f "${_H_MOUNT}" 2>/dev/null
    fi
}

mount_h() {
    local max_attempts=3
    local attempt=1

    # Auto-heal stale mount before doing anything
    if _h_is_stale; then
        echo "[mount_h] Stale mount detected — cleaning up..."
        _h_force_unmount
        sleep 1
    fi

    # Already healthy?
    if mount | grep -q "${_H_DRIVE} on ${_H_MOUNT}" && ls "${_H_MOUNT}" &>/dev/null; then
        echo "[mount_h] Already mounted and healthy at ${_H_MOUNT}"
        return 0
    fi

    while [ "$attempt" -le "$max_attempts" ]; do
        echo "[mount_h] Attempt ${attempt}/${max_attempts}..."

        if ! _h_drive_accessible; then
            echo "[mount_h] H: not visible to Windows — is Google Drive running?"
            return 1  # No point retrying if Windows can't see it
        fi

        sudo mkdir -p "${_H_MOUNT}"

        if sudo mount -t drvfs "${_H_DRIVE}" "${_H_MOUNT}"; then
            # Verify the mount is actually usable
            if ls "${_H_MOUNT}" &>/dev/null; then
                echo "[mount_h] Mounted and verified at ${_H_MOUNT}"
                return 0
            else
                echo "[mount_h] Mounted but not readable — retrying..."
                _h_force_unmount
            fi
        else
            echo "[mount_h] mount failed on attempt ${attempt}"
        fi

        sleep $((attempt * 2))  # Back off: 2s, 4s
        ((attempt++))
    done

    echo "[mount_h] All ${max_attempts} attempts failed."
    echo "[mount_h] Debug: $(mount | grep -i 'h:' || echo 'no H: entries in mount table')"
    return 1
}

unmount_h() {
    if ! mount | grep -q "${_H_DRIVE} on ${_H_MOUNT}"; then
        echo "[unmount_h] Not mounted — nothing to do"
        return 0
    fi

    # Check what's holding it open
    local users
    users=$(lsof "${_H_MOUNT}" 2>/dev/null | tail -n +2)
    if [ -n "$users" ]; then
        echo "[unmount_h] Warning — these processes have open files:"
        echo "$users"
        echo "[unmount_h] Attempting lazy unmount..."
        sudo umount -l "${_H_MOUNT}" && echo "[unmount_h] Lazy unmount queued" && return 0
    fi

    if sudo umount "${_H_MOUNT}"; then
        echo "[unmount_h] Unmounted ${_H_MOUNT}"
    else
        echo "[unmount_h] Clean unmount failed — forcing lazy unmount"
        sudo umount -l "${_H_MOUNT}" || { echo "[unmount_h] Could not unmount — reboot may be needed"; return 1; }
    fi
}
