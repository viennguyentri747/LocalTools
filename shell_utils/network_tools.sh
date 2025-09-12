#!/bin/bash
# Common Variables
ut_pass='use4Tst!'
NOTE_PERMANENT_COMMAND='May need to copy key to UT (for permanent login) before running this command first time. Try to run login_permanent OR login_permanent_lab'

# Function to get IP based on area
get_ip() {
    case "$1" in
        nor)
            echo "192.168.100"
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

# Function to perform SSH
ssh_acu() {
    local area=$1
    local last_octet=$2
    local ip_prefix=$(get_ip "$area")
    [ $? -ne 0 ] && return 1  # Check if get_ip failed
    
    if [[ -z "$last_octet" ]]; then
        echo "Usage: ssh_acu <area (nor/lab/roof)> <last-octet-of-IP (77)>."
        echo "Ex: ssh_acu nor 77"
        return 1
    fi
    
    sshpass -p $ut_pass ssh -t -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -- "root@${ip_prefix}.$last_octet" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -- "root@192.168.100.254" 
}

ssh_ssm() {
    local area=$1
    local last_octet=$2
    local ip_prefix=$(get_ip "$area")
    [ $? -ne 0 ] && return 1  # Check if get_ip failed
    
    if [[ -z "$last_octet" ]]; then
        echo "Usage: ssh_ssm <area(nor/lab/roof)> <last-octet-of-IP (77)>."
        echo "Ex: ssh_ssm nor 77"
        return 1
    fi
    
    sshpass -p $ut_pass ssh -t -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -- "root@${ip_prefix}.$last_octet"
}

# Function to handle SSH key copying for permanent login
login_permanent() {
    local area=$1
    local last_octet=$2
    local ip_prefix=$(get_ip "$area")
    [ $? -ne 0 ] && return 1  # Check if get_ip failed
    
    if [[ -z "$last_octet" ]]; then
        echo "Usage: login_permanent <area(nor/lab/roof)> <last-octet-of-IP (77)>."
        echo "Ex: login_permanent nor 73"
        return 1
    fi
    
    sshpass -p $ut_pass ssh-copy-id -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@${ip_prefix}.$last_octet
}

ping_acu() {
    SECONDS=0 # reset timer
    local area=$1
    local last_octet=$2
    local user="${ut_user:-root}"
    
    # Get IP prefix using the same function as ssh_acu
    local ip_prefix=$(get_ip "$area")
    [ $? -ne 0 ] && return 1 # Check if get_ip failed
    
    if [[ -z "$last_octet" ]]; then
        echo "Usage: ping_acu <area (nor/lab/roof)> <last-octet-of-IP (70)>."
        echo "Ex: ping_acu nor 70"
        return 1
    fi
    
    local ip="${ip_prefix}.${last_octet}"
    local target="192.168.100.254"
    
    # 1) Wait until the gateway IP is pingable
    while ! ping -c1 -W1 "$ip" >/dev/null 2>&1; do
        echo -ne "\r[$SECONDS s] Waiting for $ip to be reachable..."
        sleep 1
    done
    echo -e "\r[$SECONDS s] ✅ $ip is reachable!"
    
    # 2) Wait until SSH works AND ping target from gateway succeeds
    while ! sshpass -p "$ut_pass" ssh \
        -o ConnectTimeout=2 \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o LogLevel=ERROR \
        -o BatchMode=no \
        "$user@$ip" "ping -c1 -W1 $target >/dev/null 2>&1" 2>/dev/null; do
        echo -ne "\r[$SECONDS s] Waiting for ACU $target ($ip) to be reachable..."
        sleep 1
    done
    
    echo "[$SECONDS s] ✅ $target is reachable from $ip (SSH working)"
    noti
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
        echo "scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -J root@${ip_prefix}.$last_octet $path root@192.168.100.254:$remote_path"
        scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -J "root@${ip_prefix}.$last_octet" "$path" "root@192.168.100.254:$remote_path"
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
    scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -J "root@${ip_prefix}.$last_octet" "root@192.168.100.254:$remote_path" "$local_path"
}

# unset ut_pass
# unset NOTE_PERMANENT_COMMAND
