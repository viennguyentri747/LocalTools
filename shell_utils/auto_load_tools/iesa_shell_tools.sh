#!/bin/bash
ow_sw_path=$HOME/ow_sw_tools

docker_ow_build() {
    local OW_SW_PATH="$ow_sw_path"
    local docker_image="${1:-oneweb_sw:latest}"
    [ -z "$1" ] && echo "docker_image not provided, using default: ${docker_image}"
    local chmod_cmd="find ${OW_SW_PATH}/packaging -type f \\( -name '*.py' -o -name '*.sh' \\) -exec chmod +x {} \\; -exec echo 'Granted execute permission to: {}' \\;" keep_interactive_shell="exec bash"
    # Build the full bash command
    local bash_cmd="echo 'Granting execute permissions to script files...' && ${chmod_cmd} && ${keep_interactive_shell}"
    # Build and run the docker command
    docker run -it --rm \
        -v "${OW_SW_PATH}:${OW_SW_PATH}" \
        -w "${OW_SW_PATH}" \
        "${docker_image}" \
        bash -c "${bash_cmd}"
}

iesa_docker(){
  docker run -it --rm -v $(pwd):$(pwd) oneweb_sw
}

# Common function to select and validate repository
_select_repo() {
  echo -e "Available Repositories:\n---------------------"
  repo_list=($(grep -oP 'name="\K[^"]+' "$ow_sw_path/tools/manifests/iesa_manifest_gitlab.xml" | grep -v -w -E "intellian_adc|oneweb_legacy|oneweb_n|prototyping|third_party_apps"))
  local i=1
  for repo in "${repo_list[@]}"; do
    echo "$i. $repo"
    i=$((i + 1))
  done
  echo -e "---------------------\n"
  
  printf "%s" "Enter repo name OR repo index from list above: "
  read -r repo_input
  
  # Check if input is a number (index) or name
  if [[ "$repo_input" =~ ^[0-9]+$ ]] && [ "$repo_input" -ge 1 ] && [ "$repo_input" -le "${#repo_list[@]}" ]; then
    if [ -n "${ZSH_VERSION-}" ]; then
      selected_repo="${repo_list[$repo_input]}"
    else
      selected_repo="${repo_list[$((repo_input - 1))]}"
    fi
  else
    selected_repo="$repo_input"
  fi
  
  # Validate repo_name
  valid_repo=false
  for repo in "${repo_list[@]}"; do
    if [ "$repo" = "$selected_repo" ]; then
      valid_repo=true
      break
    fi
  done
  
  if [ "$valid_repo" = false ]; then
    echo "Error: Repository '$selected_repo' not found in the list. Aborting."
    return 1
  fi
  
  echo "Selected: $selected_repo"
  return 0
}

# Common function to perform intelligent sync
_perform_sync() {
  local source_dir="$1"
  local dest_dir="$2"
  local repo_name="$3"
  
  echo -e "\nSource:      $source_dir\nDestination: $dest_dir"

  start_time=$(date +%s)
  echo "Scanning for potential file changes..."

  FINAL_LIST_FILE=$(mktemp)
  trap 'rm -f "$FINAL_LIST_FILE"' EXIT

  CANDIDATE_LIST=$(rsync -ain --out-format="%n" --exclude='.git' --exclude='.vscode' "$source_dir" "$dest_dir")
  if [ -z "$CANDIDATE_LIST" ]; then
      echo "No file changes detected by rsync. Sync complete."
      return 0
  fi

  echo "Verifying actual content changes (ignoring line-endings)..."
  while IFS= read -r relative_path; do
      [ -d "$source_dir/$relative_path" ] && continue
      
      source_file="$source_dir/$relative_path"
      dest_file="$dest_dir/$relative_path"

      if [ ! -f "$dest_file" ] || ! diff -q -B --strip-trailing-cr "$source_file" "$dest_file" > /dev/null 2>&1; then
        echo "Found change in: $relative_path"
        echo "$relative_path" >> "$FINAL_LIST_FILE"
      fi
  done <<< "$CANDIDATE_LIST"

  if [ -s "$FINAL_LIST_FILE" ]; then
      echo "Syncing verified file changes..."
      rsync -a --files-from="$FINAL_LIST_FILE" --exclude='.git' --exclude='.vscode' "$source_dir" "$dest_dir"
  else
      echo "No actual content changes found after verification."
  fi

  echo "Sync complete for repository: $repo_name"
  
  end_time=$(date +%s)
  elapsed_seconds=$((end_time - start_time))
  echo "--------------------------------------------------"
  echo "🚀 Performance Check: Total elapsed time was $elapsed_seconds seconds."
  echo "--------------------------------------------------"
}

# Sync FROM tmp_build TO workspace
sync_from_tmp_build() {
  _select_repo || return 1
  
  local repo_name="$selected_repo"
  local source_dir="$HOME/ow_sw_tools/tmp_build/$(grep -oP "name=\"$repo_name\" path=\"\K[^\"]+" "$HOME/ow_sw_tools/tools/manifests/iesa_manifest_gitlab.xml")/"
  local dest_dir="$HOME/workspace/intellian_core_repos/$repo_name/"
  
  _perform_sync "$source_dir" "$dest_dir" "$repo_name"
}

# Sync FROM workspace TO tmp_build
sync_to_tmp_build() {
  _select_repo || return 1
  
  local repo_name="$selected_repo"
  local source_dir="$HOME/workspace/intellian_core_repos/$repo_name/"
  local dest_dir="$HOME/ow_sw_tools/tmp_build/$(grep -oP "name=\"$repo_name\" path=\"\K[^\"]+" "$HOME/ow_sw_tools/tools/manifests/iesa_manifest_gitlab.xml")/"
  
  _perform_sync "$source_dir" "$dest_dir" "$repo_name"
}