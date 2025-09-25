#!/home/vien/local_tools/MyVenvFolder/bin/python
"""
Obsidian integration for Jira using the Obsidian Advanced URI plugin.
This script creates a new note in Obsidian by populating a local template
file and then calling a specially crafted obsidian://adv-uri URL.

Prerequisites:
1. Obsidian Community Plugin "Advanced URI" must be installed and enabled.
2. The Vault Name and local file path to the vault must be configured below.
"""

import os
import sys
import subprocess
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Optional

# This import is assumed from your original script.
# It should contain a function `str_to_slug` that sanitizes strings for filenames.
from dev_common import *

# --- Configuration ---
# ⚠️ IMPORTANT: Update these two variables with your Obsidian vault details.
OBSIDIAN_VAULT_NAME = "ObsidianWorkVault"  # The exact name of your Obsidian vault.
OBSIDIAN_VAULT_PATH = f"{Path.home()}/obsidian_work_vault"  # The full local path to your vault.

# --- Template Configuration ---
# Location of your templates within the vault.
TEMPLATE_FOLDER = "Dev/templates_container/"
# The specific template file for a Jira note.
JIRA_TEMPLATE_FILE = "page_tmpl_default.md"


def create_note_with_uri(vault_name: str, filepath: str, content: str, mode: str = "new") -> bool:
    """
    Constructs and executes an Obsidian Advanced URI to write content to a file.

    Args:
        vault_name (str): The name of the Obsidian vault.
        filepath (str): The target file path within the vault (e.g., "Jira/TEST-123.md").
        content (str): The markdown content to write to the file.
        mode (str): The write mode. 'new' ensures a new file is always created,
                    appending a number if the file already exists.

    Returns:
        bool: True if the command was executed, False otherwise.
    """
    if not vault_name or "YourVaultName" in vault_name:
        print("❌ ERROR: OBSIDIAN_VAULT_NAME is not configured.")
        return False

    try:
        # URL-encode all components to ensure they are handled correctly.
        encoded_vault = urllib.parse.quote(vault_name, safe='')
        encoded_filepath = urllib.parse.quote(filepath, safe='')
        encoded_content = urllib.parse.quote(content, safe='')
        print(f"Encoded content: {encoded_content}")
        if len(encoded_content) == 0:
            print("❌ ERROR: Encoded content is empty, the function will behave incorrectly. Skipping...")
            return False

        # Construct the full advanced URI.
        uri = (
            f"obsidian://adv-uri?vault={encoded_vault}"
            f"&filepath={encoded_filepath}"
            f"&data={encoded_content}"
            # f"&data=This%20text%20is%20overwritten&"
            f"&mode={mode}"
        )

        print(f"🚀 Executing Obsidian URI (first 150 chars): {uri[:150]}...")
        # WSL environment - use cmd.exe with proper escaping
        escaped_uri = uri.replace('&', '^&')
        cmd = f'cmd.exe /c start "" "{escaped_uri}"'
        subprocess.run(cmd, shell=True, check=True)
        # --- END UPDATED REPLACEMENT ---

        print(f"✅ Successfully sent request to Obsidian to create note: {filepath}")
        return True

    except Exception as e:
        print(f"❌ Failed to execute Obsidian URI: {e}")
        print("   Ensure the 'Advanced URI' plugin is installed and enabled in Obsidian.")
        print("   For WSL, ensure you can run cmd.exe commands.")
        print("   For Linux/macOS, ensure 'xdg-open' or 'open' command is available.")
        return False


def execute_obsidian_command(
    vault_name: str,
    command: str,
    filepath: str = None,
    line: int = None,
    mode: str = None,
    confirm: bool = False,
    use_command_id: bool = True,
    **kwargs
) -> bool:
    """
    Execute an Obsidian command via Advanced URI and wait for the handler to close.
    Args:
        vault_name (str): The name of the Obsidian vault.
        command (str): Command name or ID to execute.
        filepath (str, optional): File to open before executing command.
        line (int, optional): Line number to position cursor.
        mode (str, optional): Mode for file operations ('append', 'prepend', 'overwrite').
        confirm (bool): Auto-confirm dialogs by clicking main button.
        use_command_id (bool): Whether the command parameter is a command ID (recommended).
        **kwargs: Additional URI parameters.
    Returns:
        bool: True if command executed successfully.
    """
    if not vault_name or "YourVaultName" in vault_name:
        print("❌ ERROR: OBSIDIAN_VAULT_NAME is not configured.")
        return False

    encoded_vault = urllib.parse.quote(vault_name, safe='')
    try:
        # --- URI Construction ---
        uri_parts = [f"obsidian://adv-uri?vault={encoded_vault}"]

        command_param = "commandid" if use_command_id else "commandname"
        uri_parts.append(f"{command_param}={urllib.parse.quote(command, safe='')}")

        if filepath:
            uri_parts.append(f"filepath={urllib.parse.quote(filepath, safe='')}")
        if line is not None:
            uri_parts.append(f"line={line}")
        if mode:
            uri_parts.append(f"mode={mode}")
        if confirm:
            uri_parts.append("confirm=true")

        for key, value in kwargs.items():
            uri_parts.append(f"{key}={urllib.parse.quote(str(value), safe='')}")

        uri = "&".join(uri_parts)

        print(f"⏳ Executing blocking Obsidian Command URI for WSL: {uri[:150]}...")
        escaped_uri = uri.replace('&', '^&')
        # The /wait flag tells cmd.exe to wait for the new process to terminate.
        cmd = f'cmd.exe /c start /wait "" "{escaped_uri}"'
        # print(f"🚀 Running command: {cmd} at {datetime.now()}")
        subprocess.run(cmd, shell=True, check=True)
        # print(f"✅ Command executed successfully at {datetime.now()}")
        print(f"✅ Successfully executed Obsidian command: {command}")
        return True

    except Exception as e:
        print(f"❌ Failed to execute Obsidian command URI: {e}")
        print("   Ensure 'Advanced URI' is enabled in Obsidian and cmd.exe is accessible from WSL.")
        return False


def create_obsidian_default_note(
    ticket_key: str,
    ticket_title: str,
    markdown_content: str,
    target_folder: str = "Jira"
) -> bool:
    try:
        # --- 1. Define Paths and Note Name ---
        note_name = f"{ticket_key}_{str_to_slug(ticket_title)}.md"
        full_note_path = f"{target_folder}/{note_name}".replace("\\", "/")  # Ensure forward slashes
        #This will gen file if not exist
        execute_obsidian_command(
            vault_name=OBSIDIAN_VAULT_NAME,
            command="templater-obsidian:Dev/templates_container/page_tmpl_default.md",
            filepath=full_note_path,
            use_command_id=True,
            mode="overwrite"
        )
        create_note_with_uri(
            vault_name=OBSIDIAN_VAULT_NAME,
            filepath=full_note_path,
            content=f"{markdown_content}",
            mode="append"  # Append content after the template
        )

    except Exception as e:
        print(f"❌ An unexpected error occurred in create_jira_note_in_obsidian: {e}")
        return False


if __name__ == "__main__":
    print("--- Running Obsidian Advanced URI Integration Test ---")

    if "YourVaultName" in OBSIDIAN_VAULT_NAME or "YourUser" in OBSIDIAN_VAULT_PATH:
        print("🛑 STOP: Please update OBSIDIAN_VAULT_NAME and OBSIDIAN_VAULT_PATH before running.")
    else:
        # --- Test Content ---
        test_ticket_key = "TEST-456"
        test_ticket_title = "Advanced URI Integration Test"
        test_markdown_content = """## Ticket Details
- **Status**: In Progress
- **Assignee**: John Doe
- **Description**: This is the main content of the Jira ticket, generated by the script and inserted into the `%%JIRA_CONTENT%%` placeholder in the template.
"""
        test_target_folder = "Tests"  # Creates note in "Tests" subfolder of your vault

        print(f"\n--- Creating test note for ticket: {test_ticket_key} ---")

        success = create_obsidian_default_note(
            ticket_key=test_ticket_key,
            ticket_title=test_ticket_title,
            markdown_content=test_markdown_content,
            target_folder=test_target_folder
        )