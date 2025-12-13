#!/bin/bash
# Common Variables
common_ip_prefix="192.168.100"
target_acu_ip="$common_ip_prefix.254"
ut_pass='use4Tst!'
NOTE_PERMANENT_COMMAND='May need to copy key to UT (for permanent login) before running this command first time. Try to run login_permanent OR login_permanent_lab'

# Default area if not provided explicitly
DEFAULT_AREA="nor"

# Function to get IP based on area
get_ip() {
    case "$1" in
        nor)
            echo "$common_ip_prefix"
        ;;
        lab)
            echo "172.16.20"
        ;;
        roof)
            echo "192.168.101"
        ;;
        *)
            echo "Invalid area. Use nor, lab, or roof." >&2
            return 1
        ;;
    esac
}

# Resolve optional area + required last octet.
# Sets RESOLVED_AREA, RESOLVED_OCTET, RESOLVED_SHIFT
resolve_area_and_octet() {
    local first_arg="$1"
    local second_arg="$2"

    if [[ -z "$first_arg" ]]; then
        return 1
    fi

    if [[ "$first_arg" =~ ^[0-9]+$ ]]; then
        RESOLVED_AREA="$DEFAULT_AREA"
        RESOLVED_OCTET="$first_arg"
        RESOLVED_SHIFT=1
        return 0
    fi

    if [[ -z "$second_arg" ]]; then
        return 1
    fi

    RESOLVED_AREA="$first_arg"
    RESOLVED_OCTET="$second_arg"
    RESOLVED_SHIFT=2
    return 0
}

ssh_acu() {
    if ! resolve_area_and_octet "$@"; then
        echo "Usage: ssh_acu [area (nor/lab/roof)] <last-octet-of-IP (77)>."
        echo "Ex: ssh_acu 77 / ssh_acu lab 77"
        return 1
    fi
    local last_octet="$RESOLVED_OCTET"
    local ip_prefix=$(get_ip "$RESOLVED_AREA")
    [ $? -ne 0 ] && return 1  # Check if get_ip failed
    
    # Adjusted options (ConnectionAttempts handled by loop, so strictly 1 here is good)
    SSH_OPTS="-o ConnectTimeout=0 -o ConnectionAttempts=1 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
    sshpass -p "$ut_pass" ssh -t $SSH_OPTS \
        "root@${ip_prefix}.${last_octet}" \
        ssh $SSH_OPTS "root@$target_acu_ip"

}

run_acu_cmd() {
    # Usage: run_acu_cmd [area (nor/lab/roof)] <last-octet-of-IP> <command...>
    if [[ $# -lt 2 ]]; then
        echo "Usage: run_acu_cmd [area(nor/lab/roof)] <last-octet-of-IP> <command...>"
        echo "Ex: run_acu_cmd 77 reboot"
        echo "    run_acu_cmd lab 77 'systemctl status diagnostics'"
        return 1
    fi
    
    # Resolve area + octet using existing helper
    if ! resolve_area_and_octet "$1" "$2"; then
        echo "Usage: run_acu_cmd [area(nor/lab/roof)] <last-octet-of-IP> <command...>"
        return 1
    fi
    
    # Drop the resolved args, keep only the command part
    shift "$RESOLVED_SHIFT"
    
    local ip_prefix
    ip_prefix=$(get_ip "$RESOLVED_AREA")
    [ $? -ne 0 ] && return 1
    local full_ip="${ip_prefix}.$RESOLVED_OCTET"
    
    local cmd_to_run=( "$@" )
    local quoted_run_cmd=\""${cmd_to_run[*]}"\" # Wrap the entire command in quotes so it's treated as one unit through both SSH hops
    echo "Running command on ACU $target_acu_ip via UT $full_ip: $quoted_run_cmd"
    sshpass -p "$ut_pass" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        "root@$full_ip" \
        ssh -q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        "root@$target_acu_ip" "$quoted_run_cmd"
    
    local ssh_status=$?
    if [[ $ssh_status -ne 0 ]]; then
        echo "[ERROR] SSH ACU command failed (exit $ssh_status) via $full_ip -> $target_acu_ip."
        return "$ssh_status"
    else
        echo -e "\n[INFO] SSH ACU command successfully executed on $target_acu_ip (via $full_ip)."
        return 0
    fi
}

ssh_ssm() {
    if ! resolve_area_and_octet "$@"; then
        echo "Usage: ssh_ssm [area(nor/lab/roof)] <last-octet-of-IP (77)>. Ex: ssh_ssm 77 / ssh_ssm lab 77"
        return 1
    fi
    local ip_prefix=$(get_ip "$RESOLVED_AREA") || return 1
    sshpass -p $ut_pass ssh -t -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -- "root@${ip_prefix}.$RESOLVED_OCTET"
}

reboot_ssm() {
    if ! resolve_area_and_octet "$@"; then
        echo "Usage: reboot_ssm [area(nor/lab/roof)] <last-octet-of-IP (77)>."
        echo "Ex: reboot_ssm 77 / reboot_ssm lab 77"
        return 1
    fi

    local ip_prefix
    ip_prefix=$(get_ip "$RESOLVED_AREA") || return 1
    local full_ip="${ip_prefix}.$RESOLVED_OCTET"

    if curl -fsS "$full_ip/api/system/reboot"; then
        echo -e "\n[INFO] HTTP reboot request successfully executed."
        return 0
    fi

    echo "[WARN] HTTP reboot failed. Falling back to SSH reboot..."
    # Re-use the helper; this will re-resolve but keeps the call site simple.
    run_ssm_cmd "$@" reboot
}

run_ssm_cmd() {
    # Usage: run_ssm_cmd [area(nor/lab/roof)] <last-octet> <command...>
    if [[ $# -lt 2 ]]; then
        echo "Usage: run_ssm_cmd [area(nor/lab/roof)] <last-octet-of-IP> <command...>"
        echo "Ex: run_ssm_cmd 77 reboot"
        echo "    run_ssm_cmd lab 77 'systemctl status diagnostics'"
        return 1
    fi

    # Resolve area + octet using your existing helper
    if ! resolve_area_and_octet "$1" "$2"; then
        echo "Usage: run_ssm_cmd [area(nor/lab/roof)] <last-octet-of-IP> <command...>"
        return 1
    fi

    # Drop the resolved args, keep the command
    shift "$RESOLVED_SHIFT"

    local ip_prefix=$(get_ip "$RESOLVED_AREA") || return 1
    local full_ip="${ip_prefix}.$RESOLVED_OCTET"
    local cmd=( "$@" )

    sshpass -p "$ut_pass" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        root@"$full_ip" "${cmd[@]}"
    local ssh_status=$?

    if [[ $ssh_status -ne 0 ]]; then
        echo "[ERROR] SSH command failed (exit $ssh_status) on $full_ip."
        return "$ssh_status"
    else
        echo -e "\n[INFO] SSH command successfully executed on $full_ip."
        return 0
    fi
}

login_permanent_ssm() {
    if ! resolve_area_and_octet "$@"; then
        echo "Usage: login_permanent_ssm [area(nor/lab/roof)] <last-octet-of-IP (77)>. Ex: login_permanent 73 / login_permanent roof 73"
        return 1
    fi
    local ip_prefix=$(get_ip "$RESOLVED_AREA")
    [ $? -ne 0 ] && return 1  # Check if get_ip failed
    login_permanent "root" "${ip_prefix}.$RESOLVED_OCTET" "$ut_pass"
}

login_permanent() {
    local user="$1"
    local ip="$2"
    local password="$3"
    
    if [[ -z "$user" || -z "$ip" ]]; then
        echo "Usage: login_permanent <user> <ip> [password]"
        echo "Ex: login_permanent root $common_ip_prefix.70 my_password"
        echo "    login_permanent root $common_ip_prefix.70  # Interactive password prompt"
        return 1
    fi
    
    # If password is provided and not empty, use sshpass; otherwise let ssh-copy-id prompt
    if [[ -n "$password" ]]; then
        if ! sshpass -p "$password" ssh-copy-id -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$user@$ip"; then
            echo "Error: Failed to copy SSH key to $user@$ip"
            return 1
        fi
    else
        echo "No password provided, you will be prompted to enter it interactively..."
        if ! ssh-copy-id -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$user@$ip"; then
            echo "Error: Failed to copy SSH key to $user@$ip"
            return 1
        fi
    fi
    
    echo "Success: SSH key copied to $user@$ip -> You should now be able to login without a password."
}

ping_ssm_ip() {
    SECONDS=0
    local ip=""
    local mute=0

    # Parse args
    for arg in "$@"; do
        case "$arg" in
            --mute) mute=1 ;;
            *) ip="$arg" ;;
        esac
    done

    if [[ -z "$ip" ]]; then
        echo "Usage: ping_ssm <ip> [--mute]"
        echo "Ex: ping_ssm $common_ip_prefix.70 --mute"
        return 1
    fi

    echo "Pinging $ip..."
    while ! ping -c2 -W1 "$ip" >/dev/null 2>&1; do
        echo -ne "\r[$SECONDS s] Waiting for $ip to be reachable..."
        sleep 1
    done
    echo -e "\r[$SECONDS s] ✅ $ip is reachable!"

    if [[ "$mute" -ne 1 ]]; then
        noti
    else
        echo "✅ Task complete (no notification)"
    fi
}

ping_acu_ip() {
    SECONDS=0
    local ip=""
    local mute=0
    local user="${ut_user:-root}"
    local target="${target_acu_ip}"

    # Parse args
    for arg in "$@"; do
        case "$arg" in
            --mute) mute=1 ;;
            *) ip="$arg" ;;
        esac
    done

    if [[ -z "$ip" ]]; then
        echo "Usage: ping_acu_ip <ip> [--mute]"
        echo "Ex: ping_acu_ip $common_ip_prefix.70 --mute"
        return 1
    fi

    # First part: ping UT (call ping_ssm)
    ping_ssm_ip "$ip" --mute

    # Second part: ping ACU from UT
    echo "Pinging ACU $target from UT $ip..."
    # c3 = send 3 pings (sequentially), W1 = wait max 1 second for each reply
    while ! sshpass -p "$ut_pass" ssh \
        -o ConnectTimeout=2 \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -o BatchMode=no \
        "$user@$ip" "ping -c3 -W1 $target >/dev/null 2>&1" 2>/dev/null; do
        echo -ne "\r[$SECONDS s] Waiting for ACU $target ($ip) to be reachable..."
        sleep 1
    done

    echo "[$SECONDS s] ✅ $target is reachable from $ip (SSH working)"

    if [[ "$mute" -ne 1 ]]; then
        noti
    else
        echo "✅ Task complete (no notification)"
    fi
}

ping_ssm() {
    if ! resolve_area_and_octet "$@"; then
        echo "Usage: ping_ssm [area] <last-octet> [--mute]"
        echo "Ex: ping_ssm 70 --mute   or   ping_ssm lab 70 --mute"
        return 1
    fi
    local area="$RESOLVED_AREA"
    local last_octet="$RESOLVED_OCTET"
    shift "$RESOLVED_SHIFT"

    local ip_prefix
    ip_prefix=$(get_ip "$area")
    [ $? -ne 0 ] && return 1

    local ip="${ip_prefix}.${last_octet}"

    # Pass all remaining args (e.g. --mute) to ping_ssm_ip
    ping_ssm_ip "$ip" "$@"
}

ping_acu() {
    if ! resolve_area_and_octet "$@"; then
        echo "Usage: ping_acu [area] <last-octet> [--mute]"
        echo "Ex: ping_acu 70 --mute   or   ping_acu roof 70 --mute"
        return 1
    fi
    local area="$RESOLVED_AREA"
    local last_octet="$RESOLVED_OCTET"
    shift "$RESOLVED_SHIFT"

    local ip_prefix
    ip_prefix=$(get_ip "$area")
    [ $? -ne 0 ] && return 1

    local ip="${ip_prefix}.${last_octet}"

    # Pass all remaining args (e.g. --mute) to ping_acu_ip
    ping_acu_ip "$ip" "$@"
}

# Wrapper for scp: run real scp with all args, then echo a completion message. Note: if use sshpass -p $ut_pass scp ... it does work but will not show progress -> Avoid for now
scp() {
    # Use 'command' to bypass this function and call the real scp binary
    command scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$@"
    local status=$?
    local message=""
    if [ $status -eq 0 ]; then
        message="SCP completed successfully."
    else
        message="SCP failed with status $status."
    fi
    echo "$message"
    noti "SCP Command" "$message"
    return $status
}

# Function to perform SCP
scp_acu() {
    local area=$1
    local last_octet=$2
    local remote_path=${@: -1}  # Capture the last argument as the remote path
    local ip_prefix=$(get_ip "$area")
    if [ $? -ne 0 ]; then
        return 1  # Check if get_ip failed
    fi

    if [[ -z "$last_octet" || -z "${@:3:$#-3}" || -z "$remote_path" ]]; then
        echo "Usage: scp_acu <area> <last-octet-of-IP> <local-path(s)> <remote-path>"
        echo "Ex: scp_acu nor 73 ~/workspace/ut_data_from_remote/cal_files_76/* /var/volatile/calibration/"
        return 1
    fi

    # Process all arguments except the first two and the last one as local paths
    local local_paths=("${@:3:$#-3}") # This captures all arguments from the 3rd to the penultimate as local paths
    echo "Attempting to SCP files from: ${local_paths[@]} to $remote_path on remote"
    for path in "${local_paths[@]}"; do
        echo "scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -J root@${ip_prefix}.$last_octet $path root@$common_ip_prefix.254:$remote_path"
        scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -J "root@${ip_prefix}.$last_octet" "$path" "root@$common_ip_prefix.254:$remote_path"
    done
}

scp_acu_to_local() {
    local area=$1
    local last_octet=$2
    local remote_path=$3
    local local_path=$4
    local ip_prefix=$(get_ip "$area")
    [ $? -ne 0 ] && return 1  # Check if get_ip failed

    # Validate input parameters
    if [[ -z "$last_octet" || -z "$remote_path" || -z "$local_path" ]]; then
        echo "$NOTE_PERMANENT_COMMAND"
        echo "Usage: scp_acu_to_local <area(nor/lab/roof)> <last-octet-of-SSM-IP> <remote-path> <local-path>."
        echo "Ex: scp_acu_to_local nor 73 /home/root/download/ ~/workspace/ut_data_from_remote/"
        return 1
    fi

    # Use the SSM as a jump host and copy from the ACU to the local machine
    scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -J "root@${ip_prefix}.$last_octet" "root@$common_ip_prefix.254:$remote_path" "$local_path"
}

# unset ut_pass
# unset NOTE_PERMANENT_COMMAND
