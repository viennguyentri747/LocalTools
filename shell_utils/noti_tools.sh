noti() {
    local snore_path="/mnt/c/MyWorkspace/Miscs/SnoreToast/snoretoast.exe"

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

    if [ ! -x "$snore_path" ]; then
        echo "❌ SnoreToast not found at $snore_path"
        return 1
    fi

    local title="${1:-Notification}"
    local default_message="Your task is done!"
    local message="${2:-$default_message}"
    local default_duration="short"
    local duration="${3:-$default_duration}"

    # Run detached, use disown to avoid hangup signal
	nohup "$snore_path" -t "$title" -m "$message" -d "$duration" >/dev/null 2>&1 & disown
}
