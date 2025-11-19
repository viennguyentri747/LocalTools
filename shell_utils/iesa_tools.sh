#!/bin/bash

sync_from_tmp_build() {
  echo -e "Available Repositories:\n---------------------"
  repo_list=($(grep -oP 'name="\K[^"]+' "$HOME/ow_sw_tools/tools/manifests/iesa_manifest_gitlab.xml" | grep -v -w -E "intellian_adc|oneweb_legacy|oneweb_n|prototyping|third_party_apps"))
  for i in "${!repo_list[@]}"; do
    echo "$((i+1)). ${repo_list[i]}"
  done
  echo -e "---------------------\n"
  
  read -p "Enter repo name OR repo index from list above: " repo_input
  
  # Check if input is a number (index) or name
  if [[ "$repo_input" =~ ^[0-9]+$ ]] && [ "$repo_input" -ge 1 ] && [ "$repo_input" -le "${#repo_list[@]}" ]; then
    repo_name="${repo_list[$((repo_input-1))]}"
  else
    repo_name="$repo_input"
  fi
  
  # Validate repo_name
  valid_repo=false
  for repo in "${repo_list[@]}"; do
    if [ "$repo" = "$repo_name" ]; then
      valid_repo=true
      break
    fi
  done
  
  if [ "$valid_repo" = false ]; then
    echo "Error: Repository '$repo_name' not found in the list. Aborting."
    return 1
  fi
  
  echo "Selected: $repo_name"

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

iesa_docker(){
  docker run -it --rm -v $(pwd):$(pwd) oneweb_sw
}