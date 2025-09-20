monitor_stock() {
    local PY="$HOME/stock_alert/MyVenvFolder/bin/python"
    local APP="$HOME/stock_alert/stock_alert/main.py"
    local ARGS="monitor --provider finnhub"
    local STORAGE_DIR="$HOME/stock_alert/.stockalert"

    local not_restart_if_running_arg="$1"
    local should_start=true

    local ps_output
    ps_output=$(ps -u "$USER" -o pid=,lstart=,args= | grep -F "$APP $ARGS" | grep -v grep)
    local pids
    pids=$(echo "$ps_output" | awk '{print $1}')

    if [ -n "$pids" ]; then
        if [ "$not_restart_if_running_arg" == "not_restart_if_running" ]; then
            should_start=false
        fi

        echo "[monitor_stock] Existing processes (try_restart = $should_start):"
        echo "$ps_output" | while IFS= read -r line; do
            local pid=$(echo "$line" | awk '{print $1}')
            local start_time=$(echo "$line" | awk '{for(i=2;i<=6;i++) printf "%s ", $i}' | sed 's/ $//')
            echo "  PID: $pid, Started: $start_time"
        done

        if [ "$should_start" = false ]; then
            return
        fi

        read -r -p "[monitor_stock] Kill all + restart it? [y/N] " ans
        if [[ "$ans" =~ ^[Yy]$ ]]; then
            echo "$pids" | xargs -r kill && sleep 0.2
        else
            echo "[monitor_stock] Keeping existing process."
            should_start=false
        fi
    fi

    if [ "$should_start" = true ]; then
        nohup "$PY" "$APP" $ARGS > /dev/null 2>&1 &
        local pid=$!
        echo "[monitor_stock] Started (PID: $pid)"
    fi
}
