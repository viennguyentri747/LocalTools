monitor_stock() {
    local PY="$HOME/stock_alert/MyVenvFolder/bin/python"
    local APP="$HOME/stock_alert/stock_alert/main.py"
    local ARGS=(monitor --provider finnhub)
    local ARGS_STR="${ARGS[*]}"
    local STORAGE_DIR="$HOME/stock_alert/.stockalert"

    local not_restart_if_running_arg="$1"
    local run_in_background_arg="$2"
    local should_start=true

    local ps_output
    ps_output=$(ps -u "$USER" -o pid=,lstart=,args= | grep -F "$APP $ARGS_STR" | grep -v grep)
    local pids
    pids=$(printf "%s\n" "$ps_output" | awk '{print $1}')

    if [ -n "$pids" ]; then
        if [ "$not_restart_if_running_arg" = "not_restart_if_running" ]; then
            should_start=false
        fi

        log "[monitor_stock] Existing processes (try_restart = $should_start):"
        printf "%s\n" "$ps_output" | while IFS= read -r line; do
            local pid=$(printf "%s\n" "$line" | awk '{print $1}')
            local start_time=$(printf "%s\n" "$line" | awk '{for(i=2;i<=6;i++) printf "%s ", $i}' | sed 's/ $//')
            log "  PID: $pid, Started: $start_time"
        done

        if [ "$should_start" = false ]; then
            return
        fi

        printf "%s" "[monitor_stock] Kill all + restart it? [y/N] "
        read -r ans
        if [[ "$ans" =~ ^[Yy]$ ]]; then
            printf "%s\n" "$pids" | xargs -r kill && sleep 0.2
        else
            log "[monitor_stock] Keeping existing process."
            should_start=false
        fi
    fi

    if [ "$should_start" = true ]; then
        if [ "$run_in_background_arg" = "run_in_background" ]; then
            log "[monitor_stock] Starting in background..."
            nohup "$PY" "$APP" "${ARGS[@]}" > /dev/null 2>&1 &
        else
            log "[monitor_stock] Starting in foreground..."
            "$PY" "$APP" "${ARGS[@]}"
        fi
        
        local pid=$!
        log "[monitor_stock] Started (PID: $pid)"
    fi
}
