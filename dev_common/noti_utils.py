import os
import platform
import subprocess
import sys
from pathlib import Path
import shlex

# Constants for duration string matching
NOTI_DURATION_LONG = "long"
NOTI_DURATION_SHORT = "short"
def show_noti(title="Notification", message="Notification Message", duration=NOTI_DURATION_LONG, app_name="Python App"):
    # Convert duration to appropriate values
    def get_duration_info(duration_input):
        """Convert duration input to SnoreToast format and seconds"""
        if isinstance(duration_input, str):
            # Handle fixed string constants
            if duration_input == NOTI_DURATION_LONG:
                return "long", 25
            elif duration_input == NOTI_DURATION_SHORT:
                return "short", 7
            else:
                # Default to LONG for any unmatched strings
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
    
    snore_duration, duration_seconds = get_duration_info(duration)
    
    # Sanitize inputs
    def sanitize_string(s):
        """Remove potentially problematic characters from notification strings"""
        if not isinstance(s, str):
            s = str(s)
        s = ''.join(char for char in s if ord(char) >= 32 or char in '\n\t')
        return s[:200]
    
    title = sanitize_string(title)
    message = sanitize_string(message)
    
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
            
            # Method 3: Check if we can access Windows drives
            if os.path.exists('/mnt/c') or os.path.exists('/mnt/c/Windows'):
                return True
            
            # Method 4: Check uname for WSL indicators
            try:
                result = subprocess.run(['uname', '-r'], capture_output=True, text=True)
                if result.returncode == 0:
                    uname_output = result.stdout.lower()
                    if 'microsoft' in uname_output or 'wsl' in uname_output:
                        return True
            except:
                pass
                
            return False
        except Exception as e:
            print(f"WSL detection error: {e}")
            return False
    
    def find_snoretoast():
        """Find SnoreToast executable with comprehensive search"""
        # Expanded list of common paths
        snoretoast_paths = [
            "/mnt/c/MyWorkspace/Miscs/SnoreToast/snoretoast.exe",
        ]
        
        # Check common paths
        for path in snoretoast_paths:
            if os.path.exists(path):
                # print(f"Found SnoreToast at: {path}")
                return path
        
        # Try to find in Windows PATH via PowerShell
        try:
            # Use PowerShell to find snoretoast.exe
            ps_cmd = ['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', 
                     '-Command', 'Get-Command snoretoast.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source']
            result = subprocess.run(ps_cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                # Convert Windows path to WSL path
                win_path = result.stdout.strip()
                wsl_path = win_path.replace('C:', '/mnt/c').replace('\\', '/')
                if os.path.exists(wsl_path):
                    # print(f"Found SnoreToast via PowerShell: {wsl_path}")
                    return wsl_path
        except Exception as e:
            print(f"PowerShell search failed: {e}")
        
        # Try which command in case snoretoast is in WSL PATH
        try:
            result = subprocess.run(['which', 'snoretoast.exe'], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip()
                # print(f"Found SnoreToast via which: {path}")
                return path
        except:
            pass
        
        return None
    
    def show_wsl_notification(title, message, snore_duration):
        """Show notification in WSL using SnoreToast - improved version"""
        try:
            snoretoast_exe = find_snoretoast()
            
            if not snoretoast_exe:
                print("SnoreToast not found. Install it with:")
                print("  - Download from: https://github.com/KDE/snoretoast/releases")
                print("  - Or use chocolatey: choco install snoretoast")
                print("  - Or use winget: winget install KDE.SnoreToast")
                return False
            
            # Build command using snore_duration string
            cmd = [snoretoast_exe, '-t', title, '-m', message, '-d', snore_duration]
            
            # Run with better error handling and timeout
            # result = subprocess.run(
            #     cmd, 
            #     capture_output=True, 
            #     text=True, 
            #     timeout=30,
            #     cwd='/'  # Use root directory as working directory
            # )
            # return result.returncode == 0
            subprocess.Popen(cmd, cwd='/') # Avoid blocking call
            return True
            
        except subprocess.TimeoutExpired:
            print("SnoreToast command timed out")
            return False
        except Exception as e:
            print(f"Error showing WSL notification: {e}")
            return False
    
    def show_native_notification(title, message, duration_seconds, app_name):
        """Show notification using plyer on native systems"""
        try:
            from plyer import notification
            
            print(f"Duration: {duration_seconds}s")
            
            notification.notify(
                title=title,
                message=message,
                timeout=duration_seconds,
                app_name=app_name
            )
            return True
            
        except ImportError:
            print("plyer not installed. Install it with: pip install plyer")
            return False
        except Exception as e:
            print(f"Error showing native notification: {e}")
            return False
    
    def show_fallback_notification(title, message):
        """Fallback notification methods"""
        print(f"\n{'='*50}")
        print(f"NOTIFICATION: {title}")
        print(f"MESSAGE: {message}")
        print(f"{'='*50}\n")
        
        # Try to beep if available
        try:
            print('\a')  # ASCII bell character
        except:
            pass
        
        return True
    
    # Detect environment
    is_wsl_env = is_wsl()
    # print(f"Detected WSL: {is_wsl_env}")
    
    if is_wsl_env:
        # print("Using WSL notification method")
        success = show_wsl_notification(title, message, snore_duration)
        if not success:
            print("WSL notification failed, trying fallback")
            return show_fallback_notification(title, message)
        return success
    else:
        print("Using native notification method")
        success = show_native_notification(title, message, duration_seconds, app_name)
        if not success:
            print("Native notification failed, trying fallback")
            return show_fallback_notification(title, message)
        return success


# Test function with command line arguments
def test_notification():
    """Test the notification function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test notification system')
    parser.add_argument('--title', default='Test Notification', help='Notification title')
    parser.add_argument('--message', default='This is a test message from Python!', help='Notification message')
    parser.add_argument('--duration', default=NOTI_DURATION_LONG, 
                       help='Duration: "NotiDurationShort" (7s), "NotiDurationLong" (25s), "short", "long", or number of seconds')
    args = parser.parse_args()
    
    # Convert duration using direct string comparison
    try:
        # Try to convert to int first for numeric inputs
        duration_input = int(args.duration)
    except ValueError:
        # Keep as string if it's not a number
        duration_input = args.duration
    
    success = show_noti(
        title=args.title,
        message=args.message,
        duration=duration_input,
    )
    
    if success:
        print("✓ Notification sent successfully!")
    else:
        print("✗ Failed to send notification")
    
    return success


# Example usage demonstrating the enum
def example_usage():
    """Show examples of how to use the duration constants"""
    print("=== Duration Constants Examples ===")
    
    # Fixed string constants usage (recommended)
    show_noti("Constant Test", "Using NOTI_DURATION_SHORT", NOTI_DURATION_SHORT)
    show_noti("Constant Test", "Using NOTI_DURATION_LONG", NOTI_DURATION_LONG)
    
    # Direct string usage
    show_noti("String Test", "Using 'NotiDurationShort'", "NotiDurationShort")
    show_noti("String Test", "Using 'NotiDurationLong'", "NotiDurationLong")
    
    # Legacy string conversion (still supported)
    show_noti("Legacy Test", "Using 'short' string", "short")
    show_noti("Legacy Test", "Using 'long' string", "long")
    
    # Numeric conversion
    show_noti("Numeric Test", "Using 5 seconds (becomes SHORT)", 5)
    show_noti("Numeric Test", "Using 20 seconds (becomes LONG)", 20)
    
    # Default behavior (should be LONG now)
    show_noti("Default Test", "Using default duration")
    
    # Test unmatched strings (should default to LONG)
    show_noti("Unmatched Test", "Using invalid string", "invalid_string")
    
    # Show constants
    print(f"\nDuration constants:")
    print(f"  NOTI_DURATION_SHORT = '{NOTI_DURATION_SHORT}' (7 seconds)")
    print(f"  NOTI_DURATION_LONG = '{NOTI_DURATION_LONG}' (25 seconds)")


if __name__ == "__main__":
    # Uncomment the line below to see examples
    # example_usage()
    
    test_notification()