
from typing import Optional


def prompt_confirmation(message: str) -> bool:
    """Prompt the user for a yes/no confirmation."""
    while True:
        response = input(f"{message} (y/n): ").strip().lower()
        if response in ('y', 'yes'):
            return True
        elif response in ('n', 'no'):
            return False
        else:
            print("Please enter 'y' or 'n'.")


def prompt_input(message: str, default: Optional[str] = None) -> str:
    """Prompt the user for input, with an optional default value."""
    if default:
        prompt = f"{message} [{default}]: "
    else:
        prompt = f"{message}: "
    response = input(prompt).strip()
    return response if response else (default if default is not None else "")
