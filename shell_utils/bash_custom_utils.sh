#!/bin/bash
# Common Variables
ut_pass='use4Tst!'
NOTE_PERMANENT_COMMAND='May need to copy key to UT (for permanent login) before running this command first time. Try to run login_permanent OR login_permanent_lab'

# Alias without argument
alias rmh="rm -f ~/.ssh/known_hosts"
alias sshp="sshpass -p"
alias cb="xclip -selection clipboard"

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

sync_from_tmp_build() {
  echo -e "Available Repositories:\n---------------------"
  grep -oP 'name="\K[^"]+' "$HOME/ow_sw_tools/tools/manifests/iesa_manifest_gitlab.xml" | grep -v -w -E "intellian_adc|oneweb_legacy|oneweb_n|prototyping|third_party_apps"
  echo -e "---------------------\n"
  
  read -p "Enter repo name from list above: " repo_name
  if [ -z "$repo_name" ]; then
    echo "Error: No repository name entered. Aborting."
    return 1
  fi

  # --- 3. Define paths and ask for confirmation ---
  SOURCE_DIR="$HOME/ow_sw_tools/tmp_build/$(grep -oP "name=\"$repo_name\" path=\"\K[^\"]+" "$HOME/ow_sw_tools/tools/manifests/iesa_manifest_gitlab.xml")/"
  DEST_DIR="$HOME/workspace/intellian_core_repos/$repo_name/"

  echo -e "\nSource:      $SOURCE_DIR\nDestination: $DEST_DIR"

  # --- 4. Execute FAST intelligent sync if confirmed ---
  start_time=$(date +%s)
  echo "Scanning for potential file changes..."

  FINAL_LIST_FILE=$(mktemp)
  trap 'rm -f "$FINAL_LIST_FILE"' EXIT

  CANDIDATE_LIST=$(rsync -ain --out-format="%n" --exclude='.git' --exclude='.vscode' "$SOURCE_DIR" "$DEST_DIR")
  if [ -z "$CANDIDATE_LIST" ]; then
      echo "No file changes detected by rsync. Sync complete."
      return
  fi

  echo "Verifying actual content changes (ignoring line-endings)..."
  while IFS= read -r relative_path; do
      [ -d "$SOURCE_DIR/$relative_path" ] && continue
      
      source_file="$SOURCE_DIR/$relative_path"
      dest_file="$DEST_DIR/$relative_path"

      if [ ! -f "$dest_file" ] || ! diff -q -B --strip-trailing-cr "$source_file" "$dest_file" > /dev/null 2>&1; then
      echo "Found change in: $relative_path"
      echo "$relative_path" >> "$FINAL_LIST_FILE"
      fi
  done <<< "$CANDIDATE_LIST"

  if [ -s "$FINAL_LIST_FILE" ]; then
      echo "Syncing verified file changes..."
      rsync -a --files-from="$FINAL_LIST_FILE" --exclude='.git' --exclude='.vscode' "$SOURCE_DIR" "$DEST_DIR"
  else
      echo "No actual content changes found after verification."
  fi

  echo "Sync complete for repository: $repo_name"
  # STOP TIMER AND LOG PERFORMANCE
  end_time=$(date +%s)
  elapsed_seconds=$((end_time - start_time))
  echo "--------------------------------------------------"
  echo "🚀 Performance Check: Total elapsed time was $elapsed_seconds seconds."
  echo "--------------------------------------------------"
}