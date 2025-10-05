#!/home/vien/local_tools/MyVenvFolder/bin/python
import os
import subprocess
import re
import time
from dev_common.core_utils import LOG

# Constants for duration string matching
NOTI_DURATION_LONG = "long"
NOTI_DURATION_SHORT = "short"


def show_noti(title="Notification", message="Notification Message", duration=NOTI_DURATION_LONG, app_name="Python App", no_log_on_success: bool = False):
    snore_duration, duration_seconds = get_duration_info(duration)
    title = sanitize_string(title, max_length=100)  # Shorter limit for title
    message = sanitize_string(message, max_length=300)  # Longer limit for message
    is_wsl_env = is_wsl()
    is_wsl_env = True
    success = False
    if is_wsl_env:
        success = show_wsl_notification(title, message, snore_duration)
    else:
        success = show_native_notification(title, message, duration_seconds, app_name)

    if success and not no_log_on_success:
        LOG(
            f"📱 Notification sent success from {'wsl' if is_wsl_env else 'native' }: {title[:40]}{'...' if len(title) > 40 else ''}")

    return success


def is_wsl():
    """Check if running in Windows Subsystem for Linux - improved detection"""
    try:
        # Method 1: Check WSL environment variables
        if os.environ.get('WSL_DISTRO_NAME') or os.environ.get('WSL_INTEROP'):
            return True

        # Method 2: Check /proc/version
        if os.path.exists('/proc/version'):
            with open('/proc/version', 'r') as f:
                content = f.read().lower()
                if 'microsoft' in content or 'wsl' in content:
                    return True

        return False
    except Exception as e:
        LOG(f"WSL detection error: {e}")
        return False


def get_duration_info(duration_input):
    """Convert duration input to SnoreToast format and seconds"""
    if isinstance(duration_input, str):
        if duration_input == NOTI_DURATION_LONG:
            return "long", 25
        elif duration_input == NOTI_DURATION_SHORT:
            return "short", 7
        else:
            return "long", 25
    elif isinstance(duration_input, (int, float)):
        # Convert numeric duration to short/long
        if duration_input > 15:
            return "long", 25
        else:
            return "short", 7
    else:
        # Default to LONG
        return "long", 25


def find_snoretoast():
    """Find SnoreToast executable with comprehensive search"""
    snoretoast_common_paths = [
        "/mnt/c/MyWorkspace/Miscs/SnoreToast/snoretoast.exe",
    ]

    for path in snoretoast_common_paths:
        if os.path.exists(path):
            return path
    return None


def sanitize_string(s, max_length=200):
    """Remove potentially problematic characters from notification strings"""
    if not isinstance(s, str):
        s = str(s)

    # Replace newlines and tabs with spaces
    s = s.replace('\n', ' ').replace('\t', ' ').replace('\r', ' ')
    # Remove other control characters but keep LOGable ones
    s = ''.join(char for char in s if ord(char) >= 32 or char.isspace())
    # Collapse multiple spaces into single space
    s = re.sub(r'\s+', ' ', s).strip()

    # Truncate to max length
    if len(s) > max_length:
        s = s[:max_length-3] + "..."

    return s


def show_wsl_notification(title, message, snore_duration):
    """Show notification in WSL using SnoreToast - improved version with better argument handling"""
    try:
        snoretoast_exe = find_snoretoast()

        if not snoretoast_exe:
            LOG("SnoreToast not found. More info on: https://github.com/KDE/snoretoast/releases")
            return False

        # Build command with proper argument handling, use a list approach to avoid shell parsing issues
        cmd = [
            snoretoast_exe, '-t', title, '-m', message, '-d', snore_duration
        ]

        # Use subprocess.Popen for non-blocking call
        subprocess.Popen(
            cmd,
            # Use DEVNULL to send output to discard (blackhole) instead of inherit file handle from parent
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        # subprocess.run(cmd, check=False)
        return True
    except Exception as e:
        LOG(f"Error showing WSL notification: {e}")
        return False


def show_native_notification(title, message, duration_seconds, app_name):
    """Show notification using plyer on native systems"""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            timeout=duration_seconds,
            app_name=app_name
        )
        return True

    except Exception as e:
        LOG(f"Error showing native notification: {e}")
        return False


def run_notification():
    """Run the notification function"""
    import argparse

    parser = argparse.ArgumentParser(description='Test notification system')
    parser.add_argument('--title', default='Test Notification', help='Notification title')
    parser.add_argument('--message', default='This is a test message from Python!', help='Notification message')
    parser.add_argument('--duration', default=NOTI_DURATION_LONG,
                        help='Duration: "short", "long", or number of seconds')
    args = parser.parse_args()

    # Convert duration using direct string comparison
    try:
        # Try to convert to int first for numeric inputs
        duration_input = int(args.duration)
    except ValueError:
        duration_input = args.duration

    success = show_noti(
        title=args.title,
        message=args.message,
        duration=duration_input,
    )
    return success

if __name__ == "__main__":
    run_notification()