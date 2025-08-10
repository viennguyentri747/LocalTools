#!/bin/bash

# Find the directory where this script itself lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get the absolute path to this script
THIS_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

# Loop through all .sh files in that directory except this one
loaded_str=""
for script in "$SCRIPT_DIR"/*.sh; do
    # Skip if this is the current script
    if [[ "$script" != "$THIS_SCRIPT" && -f "$script" ]]; then
        if source "$script"; then
            script_name=$(basename "$script")
            if [[ -z "$loaded_str" ]]; then # first
                loaded_str="$script_name"
            else
                loaded_str="$loaded_str, $script_name"
            fi
        fi
    fi
done

if [[ -n "$loaded_str" ]]; then
    echo "Loaded utils: $loaded_str"
fi