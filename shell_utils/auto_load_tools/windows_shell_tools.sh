if ! command -v to_windows_path >/dev/null 2>&1; then
    echo "Required helper 'to_windows_path' is missing. Load common_utils.sh before windows_shell_tools.sh." >&2
fi

explorer() {
    local file_path="$1"

    # Convert using helper
    local windows_path
    if ! windows_path=$(to_windows_path "$file_path"); then
        return 1
    fi

    # Print what will be executed
    printf "Running: explorer.exe /select,%q\n" "$windows_path"

    # Execute
    explorer.exe /select,"$windows_path"
}


win_home_dir="/mnt/c/Users/Vien.Nguyen"

open_wsl_config() {
    local wsl_config_path="$win_home_dir/.wslconfig"
    echo "Opening WSL config file: $wsl_config_path"
    vi "$wsl_config_path"
}

sync_ssh_keys_to_windows() {
  local win_ssh="$win_home_dir/.ssh"
  
  echo "Syncing SSH keys to: $win_ssh"
  cp -v ~/.ssh/id_{ed25519,rsa,ecdsa}* "$win_ssh/" 2>/dev/null
  
  chmod 600 "$win_ssh"/id_* 2>/dev/null
  chmod 644 "$win_ssh"/id_*.pub 2>/dev/null
  echo "✓ Sync complete"
}

rm_known_hosts_windows() {
    local win_known_hosts="$win_home_dir/.ssh/known_hosts"
    
    if [ -f "$win_known_hosts" ]; then
        echo "Removing Windows known_hosts file: $win_known_hosts"
        rm -v "$win_known_hosts"
        echo "✓ Removal complete"
    else
        echo "No Windows known_hosts file found at: $win_known_hosts"
    fi
}
