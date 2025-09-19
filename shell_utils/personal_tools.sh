monitor_stock() {
    # Absolute paths (avoid ~ in patterns)
    local PY="$HOME/stock_alert/MyVenvFolder/bin/python"
    local APP="$HOME/stock_alert/stock_alert/main.py"
    local ARGS="monitor --provider finnhub"
    local STORAGE_DIR="$HOME/stock_alert/.stockalert"

    local should_start=true
    local ps_output=$(ps -u "$USER" -o pid=,lstart=,args= | grep -F "$APP $ARGS" | grep -v grep)
    local pids=$(echo "$ps_output" | awk '{print $1}')
    local should_start=true

    if [ -n "$pids" ]; then
        echo "Already running processes:"
        echo "$ps_output" | while IFS= read -r line; do
            local pid=$(echo "$line" | awk '{print $1}')
            local start_time=$(echo "$line" | awk '{for(i=2;i<=6;i++) printf "%s ", $i}' | sed 's/ $//')
            echo "  PID: $pid, Started: $start_time"
        done
    
        read -r -p "Kill all + restart it? [y/N] " ans
        if [[ "$ans" =~ ^[Yy]$ ]]; then
            # Kill all matching PIDs + wait a bit for clean exit
            echo "$pids" | xargs -r kill && sleep 0.2
        else
            echo "Keeping existing process."
            should_start=false
        fi
    fi

    if [ "$should_start" = true ]; then
        nohup "$PY" "$APP" $ARGS &
        local pid=$!
        echo "Started (PID: $pid)"
    fi
}