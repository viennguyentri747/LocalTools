noti() {
    # Show help if -h or --help is passed
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
        cat <<EOF
Usage: noti [title] [message] [duration]

Arguments:
  title      Notification title (default: "Notification")
  message    Notification message (default: "Your task is done!")
  duration   Notification duration: "short" (7s) or "long" (25s)
             (default: "short")

Examples:
  noti "Build Finished" "All tests passed 🎉" short
  noti "Reminder" "Time to stretch!" long
EOF
        return 0
    fi

    local title="${1:-Notification}"
    local default_message="Your task is done!"
    local message="${2:-$default_message}"
    local default_duration="short"
    local duration="${3:-$default_duration}"

    # Run detached, use disown to avoid hangup signal
    ~/core_repos/local_tools/dev/dev_common/noti_utils.py --title "$title" --message "$message" --duration "$duration"
}

countdown() {
    local duration="${1:-25}"
    while [ $duration -gt 0 ]; do
        printf "\rRemaining: %d second(s)" "$duration"
        sleep 1
        duration=$((duration - 1))
    done
    echo -e "\nCountdown finished!"
    noti "Countdown" "Countdown finished!"
}