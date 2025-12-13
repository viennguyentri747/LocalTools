#!/home/vien/local_tools/MyVenvFolder/bin/python
import sys
import json
from dev.dev_common.noti_utils import show_noti


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: codex_noti.py <NOTIFICATION_JSON>")
        return 1

    try:
        notification = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print("Error: Invalid JSON string provided.")
        return 1

    notification_type = notification.get("type")

    if notification_type == "agent-turn-complete":
        assistant_message = notification.get("last-assistant-message", "")
        
        # Extract just the first line or summary from assistant message
        if assistant_message:
            # Split by newlines and take first meaningful line
            lines = [line.strip() for line in assistant_message.split('\n') if line.strip()]
            if lines:
                first_line = lines[0]
                # Remove markdown formatting
                import re
                first_line = re.sub(r'[*`#\-_]', '', first_line).strip()
                # Limit length
                if len(first_line) > 50:
                    first_line = first_line[:47] + "..."
                title = f"Codex: {first_line}"
            else:
                title = "Codex: Task Complete"
        else:
            title = "Codex: Task Complete"
        
        # Get input messages and create a clean summary
        input_messages = notification.get("input_messages", [])
        if input_messages:
            # Join messages and clean up
            combined_input = " ".join(input_messages)
            if len(combined_input) > 150:
                combined_input = combined_input[:147] + "..."
            message = combined_input
        else:
            message = "Task completed successfully"
            
    else:
        print(f"Not sending a push notification for: {notification_type}")
        return 0
    
    try:
        # Call the show_noti function directly
        show_noti(title=title, message=message, duration="long", no_log_on_success=True)
    except Exception as e:
        print(f"❌ Failed to send notification: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
