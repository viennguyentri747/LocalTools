#!/bin/bash
# Common Variables
nor_ip_prefix="192.168.100"
ip_range=255
lab_ip_prefix="172.16.20"
target_acu_ip="$nor_ip_prefix.254"
ut_pass='use4Tst!'
nir_nuc_pass='nirnuc123'
_nir_nuc_user='snuc'
_nir_nuc_host="10.1.26.92"
_nir_nuc_dst_base="/home/${_nir_nuc_user}/vien"
NOTE_PERMANENT_COMMAND='May need to copy key to UT (for permanent login) before running this command first time. Try to run login_permanent OR login_permanent_lab'
LEGACY_RSA_SSH_OPTS=(-o HostKeyAlgorithms=+ssh-rsa)

# Default area if not provided explicitly
DEFAULT_AREA="nor"

# Function to get IP based on area
get_ip() {
    case "$1" in
        nor)
            printf "%s\n" "$nor_ip_prefix"
        ;;
        lab)
            printf "%s\n" "$lab_ip_prefix"
        ;;
        #roof)
        #    printf "%s\n" "192.168.101"
        #;;
        *)
            log_err "Invalid area. Use nor, lab, or roof."
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

    # Allow full IP as the first arg when area is omitted; infer area from known prefixes.
    if [[ "$first_arg" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
        case "$first_arg" in
            "$nor_ip_prefix".*)
                RESOLVED_AREA="nor"
            ;;
            "$lab_ip_prefix".*)
                RESOLVED_AREA="lab"
            ;;
            *)
                log_err "Error: Full IP '$first_arg' must start with $nor_ip_prefix or $lab_ip_prefix when area is omitted."
                return 1
            ;;
        esac
        RESOLVED_OCTET="${first_arg##*.}"
        RESOLVED_SHIFT=1
        return 0
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
        log "Usage: ssh_acu [area (nor/lab/roof)] <last-octet-of-IP (77)>."
        log "Ex: ssh_acu 77 / ssh_acu lab 77"
        return 1
    fi
    local last_octet="$RESOLVED_OCTET"
    local ip_prefix=$(get_ip "$RESOLVED_AREA")
    [ $? -ne 0 ] && return 1  # Check if get_ip failed
    local full_ip="${ip_prefix}.$last_octet"
    
    # Adjusted options (ConnectionAttempts handled by loop, so strictly 1 here is good)
    ssh_acu_ip "$full_ip"
}

ssh_acu_ip() {
    local ip="$1"
    if [ -z "$ip" ]; then
        log "Usage: ssh_acu_ip <IP>"
        return 1
    fi
    local full_ip="$ip"
    SSH_OPTS=(-o ConnectTimeout=0 -o ConnectionAttempts=1 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)
    sshpass -p "$ut_pass" ssh -t "${SSH_OPTS[@]}" "root@$full_ip" ssh "${SSH_OPTS[@]}" "${LEGACY_RSA_SSH_OPTS[@]}" "root@$target_acu_ip"
}

run_acu_cmd() {
    # Usage: run_acu_cmd [area (nor/lab/roof)] <last-octet-of-IP> <command...>
    if [[ $# -lt 2 ]]; then
        log "Usage: run_acu_cmd [area(nor/lab/roof)] <last-octet-of-IP> <command...>"
        log "Ex: run_acu_cmd 77 reboot"
        log "    run_acu_cmd lab 77 'systemctl status diagnostics'"
        return 1
    fi
    
    # Resolve area + octet using existing helper
    if ! resolve_area_and_octet "$1" "$2"; then
        log "Usage: run_acu_cmd [area(nor/lab/roof)] <last-octet-of-IP> <command...>"
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
    log "Running command on ACU $target_acu_ip via UT $full_ip: $quoted_run_cmd"
    sshpass -p "$ut_pass" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        "root@$full_ip" \
        ssh -q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "${LEGACY_RSA_SSH_OPTS[@]}" \
        "root@$target_acu_ip" "$quoted_run_cmd"
    
    local ssh_status=$?
    if [[ $ssh_status -ne 0 ]]; then
        log_err "[ERROR] SSH ACU command failed (exit $ssh_status) via $full_ip -> $target_acu_ip."
        return "$ssh_status"
    else
        log "[INFO] SSH ACU command successfully executed on $target_acu_ip (via $full_ip)."
        return 0
    fi
}

ssh_ssm() {
    if ! resolve_area_and_octet "$@"; then
        log "Usage: ssh_ssm [area(nor/lab/roof)] <last-octet-of-IP (77)>. Ex: ssh_ssm 77 / ssh_ssm lab 77"
        return 1
    fi
    local ip_prefix=$(get_ip "$RESOLVED_AREA") || return 1
    sshpass -p "$ut_pass" ssh -t -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -- "root@${ip_prefix}.$RESOLVED_OCTET"
}

ssh_nir_nuc() {
    sshpass -p "$nir_nuc_pass" ssh -t -X -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -- "${_nir_nuc_user}@${_nir_nuc_host}"
}

sync_nir_nuc() {
    #--exclude='.git'
    sshpass -p "$nir_nuc_pass" rsync -avz --progress --exclude='MyVenvFolder' --exclude='__pycache__' --exclude='oneweb_project_sw_tools/tmp_build/' --exclude='oneweb_project_sw_tools/iesa_board_release.tar.xz' --exclude='packaging/tmp/' --exclude='MY_AGENT' --exclude='.codex' --exclude='tmp_local_gitlab_ci' --exclude='.gitlab-ci-local/builds' --exclude='.idea' -e "ssh -o StrictHostKeyChecking=no" ~/workspace/intellian_core_repos/ "${_nir_nuc_user}@${_nir_nuc_host}:${_nir_nuc_dst_base}/core_repos/"
}

reboot_ssm() {
    if ! resolve_area_and_octet "$@"; then
        log "Usage: reboot_ssm [area(nor/lab/roof)] <last-octet-of-IP (77)>."
        log "Ex: reboot_ssm 77 / reboot_ssm lab 77"
        return 1
    fi

    local ip_prefix
    ip_prefix=$(get_ip "$RESOLVED_AREA") || return 1
    local full_ip="${ip_prefix}.$RESOLVED_OCTET"

    if curl -fsS "$full_ip/api/system/reboot"; then
        log "[INFO] HTTP reboot request successfully executed."
        return 0
    fi

    log "[WARN] HTTP reboot failed. Falling back to SSH reboot..."
    # Re-use the helper; this will re-resolve but keeps the call site simple.
    run_ssm_cmd "$@" reboot
}

run_ssm_cmd() {
    # Usage: run_ssm_cmd [area(nor/lab/roof)] <last-octet> <command...>
    if [[ $# -lt 2 ]]; then
        log "Usage: run_ssm_cmd [area(nor/lab/roof)] <last-octet-of-IP> <command...>"
        log "Ex: run_ssm_cmd 77 reboot"
        log "    run_ssm_cmd lab 77 'systemctl status diagnostics'"
        return 1
    fi

    # Resolve area + octet using your existing helper
    if ! resolve_area_and_octet "$1" "$2"; then
        log "Usage: run_ssm_cmd [area(nor/lab/roof)] <last-octet-of-IP> <command...>"
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
        log_err "[ERROR] SSH command failed (exit $ssh_status) on $full_ip."
        return "$ssh_status"
    else
        log "[INFO] SSH command successfully executed on $full_ip."
        return 0
    fi
}

login_permanent_ssm() {
    if ! resolve_area_and_octet "$@"; then
        log "Usage: login_permanent_ssm [area(nor/lab/roof)] <last-octet-of-IP (77)>. Ex: login_permanent 73 / login_permanent roof 73"
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
        log "Usage: login_permanent <user> <ip> [password]"
        log "Ex: login_permanent root $nor_ip_prefix.70 my_password"
        log "    login_permanent root $nor_ip_prefix.70  # Interactive password prompt"
        return 1
    fi
    
    # If password is provided and not empty, use sshpass; otherwise let ssh-copy-id prompt
    if [[ -n "$password" ]]; then
        if ! sshpass -p "$password" ssh-copy-id -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$user@$ip"; then
            log_err "Error: Failed to copy SSH key to $user@$ip"
            return 1
        fi
    else
        log "No password provided, you will be prompted to enter it interactively..."
        if ! ssh-copy-id -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$user@$ip"; then
            log_err "Error: Failed to copy SSH key to $user@$ip"
            return 1
        fi
    fi
    
    log "Success: SSH key copied to $user@$ip -> You should now be able to login without a password."
}

ping_ssm_ip() {
    SECONDS=0
    local ip=""
    local mute=0
    local did_inline_wait=0

    # Parse args
    for arg in "$@"; do
        case "$arg" in
            --mute) mute=1 ;;
            *) ip="$arg" ;;
        esac
    done

    if [[ -z "$ip" ]]; then
        log "Usage: ping_ssm <ip> [--mute]"
        log "Ex: ping_ssm $nor_ip_prefix.70 --mute"
        return 1
    fi

    log "Pinging $ip..."
    while ! ping -c3 -W1 "$ip" >/dev/null 2>&1; do
        log_inline "[$SECONDS s] Waiting for $ip to be reachable..."
        did_inline_wait=1
        sleep 1
    done
    [ "$did_inline_wait" -eq 1 ] && printf "\n"
    log "[$SECONDS s] ✅ $ip is reachable!"

    if [[ "$mute" -ne 1 ]]; then
        noti
    else
        log "✅ Task complete (no notification)"
    fi
}

ping_acu_ip() {
    SECONDS=0
    local ip=""
    local mute=0
    local user="${ut_user:-root}"
    local target="${target_acu_ip}"
    local did_inline_wait=0

    # Parse args
    for arg in "$@"; do
        case "$arg" in
            --mute) mute=1 ;;
            *) ip="$arg" ;;
        esac
    done

    if [[ -z "$ip" ]]; then
        log "Usage: ping_acu_ip <ip> [--mute]"
        log "Ex: ping_acu_ip $nor_ip_prefix.70 --mute"
        return 1
    fi

    # First part: ping UT (call ping_ssm)
    ping_ssm_ip "$ip" --mute

    # Second part: ping ACU from UT
    log "Pinging ACU $target from UT $ip..."
    # c3 = send 3 pings (sequentially), W1 = wait max 1 second for each reply
    while ! sshpass -p "$ut_pass" ssh \
        -o ConnectTimeout=2 \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -o BatchMode=no \
        "$user@$ip" "ping -c3 -W1 $target >/dev/null 2>&1" 2>/dev/null; do
        log_inline "[$SECONDS s] Waiting for ACU $target ($ip) to be reachable..."
        did_inline_wait=1
        sleep 1
    done
    [ "$did_inline_wait" -eq 1 ] && printf "\n"

    log "[$SECONDS s] ✅ $target is reachable from $ip (SSH working)"

    if [[ "$mute" -ne 1 ]]; then
        noti
    else
        log "✅ Task complete (no notification)"
    fi
}

ping_ssm() {
    if ! resolve_area_and_octet "$@"; then
        log "Usage: ping_ssm [area] <last-octet> [--mute]"
        log "Ex: ping_ssm 70 --mute OR ping_ssm lab 70 --mute"
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
        log "Usage: ping_acu [area] <last-octet> [--mute]"
        log "Ex: ping_acu 70 --mute   or   ping_acu roof 70 --mute"
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

# Wrapper for scp: run real scp with all args, then log a completion message. Note: if use sshpass -p $ut_pass scp ... it does work but will not show progress -> Avoid for now
scp() {
    # Use 'command' to bypass this function and call the real scp binary
    command scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$@"
    local scp_status=$?
    local message=""
    if [ $scp_status -eq 0 ]; then
        message="SCP completed successfully."
    else
        message="SCP failed with status $scp_status."
    fi
    log "$message"
    noti "SCP Command" "$message"
    return $scp_status
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

    local local_path_count=$(( $# - 3 ))
    if [[ -z "$last_octet" || "$local_path_count" -le 0 || -z "$remote_path" ]]; then
        log "Usage: scp_acu <area> <last-octet-of-IP> <local-path(s)> <remote-path>"
        log "Ex: scp_acu nor 73 ~/workspace/ut_data_from_remote/cal_files_76/* /var/volatile/calibration/"
        return 1
    fi

    # Process all arguments except the first two and the last one as local paths
    local local_paths=("${@:3:$local_path_count}") # This captures all arguments from the 3rd to the penultimate as local paths
    log "Attempting to SCP files from: ${local_paths[@]} to $remote_path on remote"
    for path in "${local_paths[@]}"; do
        log "scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -J root@${ip_prefix}.$last_octet $path root@$nor_ip_prefix.254:$remote_path"
        scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -J "root@${ip_prefix}.$last_octet" "$path" "root@$nor_ip_prefix.254:$remote_path"
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
        log "$NOTE_PERMANENT_COMMAND"
        log "Usage: scp_acu_to_local <area(nor/lab/roof)> <last-octet-of-SSM-IP> <remote-path> <local-path>."
        log "Ex: scp_acu_to_local nor 73 /home/root/download/ ~/workspace/ut_data_from_remote/"
        return 1
    fi

    # Use the SSM as a jump host and copy from the ACU to the local machine
    scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -J "root@${ip_prefix}.$last_octet" "root@$nor_ip_prefix.254:$remote_path" "$local_path"
}

search_ip() {
    # Usage:
    #   search_ip                  # defaults to nor prefix
    #   search_ip 172.16.20        # scan custom prefix
    local input_prefix="$1"
    local ip_prefix="$nor_ip_prefix"
    local ips=()

    if [[ -n "$input_prefix" ]]; then
        if [[ "$input_prefix" =~ ^([0-9]{1,3}\.){2}[0-9]{1,3}$ ]]; then
            ip_prefix="$input_prefix"
        else
            log "Usage: search_ip [<ip-prefix>]"
            log "Ex: search_ip            # scans ${nor_ip_prefix}.1-${ip_range}"
            log "    search_ip ${lab_ip_prefix}"
            return 1
        fi
    fi

    log "Scanning ${ip_prefix}.1-${ip_range}..."
    while read -r ip; do
        ips+=("$ip")
    done < <(
        for ((i=1; i<=ip_range; i++)); do
            (ping -c1 -W1 "${ip_prefix}.${i}" >/dev/null 2>&1 && printf "%s\n" "${ip_prefix}.${i}") &
        done
        wait
    )

    if [[ ${#ips[@]} -eq 0 ]]; then
        log "No reachable IPs found in ${ip_prefix}.1-${ip_range}."
        return 0
    fi

    printf "Reachable IPs:\n%s\n" "${ips[@]}"
}

test_search_ip(){
    search_ip
}

# unset ut_pass
# unset NOTE_PERMANENT_COMMAND
