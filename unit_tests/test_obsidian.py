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
OBSIDIAN_VAULT_PATH = f"{Path.home()}/obsidian_work_vault" # The full local path to your vault.

# --- Template Configuration ---
# Location of your templates within the vault.
TEMPLATE_FOLDER = "Dev/templates_container/"
# The specific template file for a Jira note.
JIRA_TEMPLATE_FILE = "page_tmpl_default.md"


def create_note_with_uri(
    vault_name: str,
    filepath: str,
    content: str,
    mode: str = "new"
) -> bool:
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

        # Construct the full advanced URI.
        uri = (
            f"obsidian://adv-uri?vault={encoded_vault}"
            f"&filepath={encoded_filepath}"
            f"&data={encoded_content}"
            f"&mode={mode}"
        )

        print(f"🚀 Executing Obsidian URI (first 150 chars): {uri[:150]}...")

        # --- UPDATED REPLACEMENT LOGIC ---
        # Use the same approach that works for your WSL environment
        if sys.platform == "win32":
            # Direct Windows execution
            os.startfile(uri)
        elif os.path.exists('/proc/version') and 'microsoft' in open('/proc/version').read().lower():
            # WSL environment - use cmd.exe with proper escaping
            escaped_uri = uri.replace('&', '^&')
            cmd = f'cmd.exe /c start "" "{escaped_uri}"'
            subprocess.run(cmd, shell=True, check=True)
        elif sys.platform == "darwin":  # macOS
            subprocess.run(["open", uri], check=True)
        else:  # Linux and other Unix-like systems
            subprocess.run(["xdg-open", uri], check=True)
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
    Execute an Obsidian command via Advanced URI.
    
    Args:
        vault_name (str): The name of the Obsidian vault.
        command (str): Command name or ID to execute
        filepath (str, optional): File to open before executing command
        line (int, optional): Line number to position cursor
        mode (str, optional): Mode for file operations ('append', 'prepend', 'overwrite')
        confirm (bool): Auto-confirm dialogs by clicking main button
        use_command_id (bool): Whether the command parameter is a command ID (recommended)
        **kwargs: Additional URI parameters
        
    Returns:
        bool: True if command executed successfully
    """
    if not vault_name or "YourVaultName" in vault_name:
        print("❌ ERROR: OBSIDIAN_VAULT_NAME is not configured.")
        return False

    try:
        # Build base URI
        encoded_vault = urllib.parse.quote(vault_name, safe='')
        uri_parts = [f"obsidian://adv-uri?vault={encoded_vault}"]
        
        # Add command (use commandid or commandname)
        command_param = "commandid" if use_command_id else "commandname"
        encoded_command = urllib.parse.quote(command, safe='')
        uri_parts.append(f"{command_param}={encoded_command}")
        
        # Add filepath if specified
        if filepath:
            encoded_filepath = urllib.parse.quote(filepath, safe='')
            uri_parts.append(f"filepath={encoded_filepath}")
        
        # Add line number if specified
        if line is not None:
            uri_parts.append(f"line={line}")
        
        # Add mode if specified
        if mode:
            uri_parts.append(f"mode={mode}")
        
        # Add confirm parameter if needed
        if confirm:
            uri_parts.append("confirm=true")
        
        # Add any additional parameters
        for key, value in kwargs.items():
            encoded_value = urllib.parse.quote(str(value), safe='')
            uri_parts.append(f"{key}={encoded_value}")
        
        # Construct final URI
        uri = "&".join(uri_parts)
        
        print(f"🚀 Executing Obsidian Command URI: {uri[:150]}...")

        # Use the same platform logic as existing function
        if sys.platform == "win32":
            os.startfile(uri)
        elif os.path.exists('/proc/version') and 'microsoft' in open('/proc/version').read().lower():
            escaped_uri = uri.replace('&', '^&')
            cmd = f'cmd.exe /c start "" "{escaped_uri}"'
            subprocess.run(cmd, shell=True, check=True)
        elif sys.platform == "darwin":  # macOS
            subprocess.run(["open", uri], check=True)
        else:  # Linux and other Unix-like systems
            subprocess.run(["xdg-open", uri], check=True)
        
        print(f"✅ Successfully executed Obsidian command: {command}")
        return True

    except Exception as e:
        print(f"❌ Failed to execute Obsidian command URI: {e}")
        print("   Ensure the 'Advanced URI' plugin is installed and enabled in Obsidian.")
        return False


def create_jira_note_in_obsidian(
    ticket_key: str,
    ticket_title: str,
    markdown_content: str,
    target_folder: str = "Jira"
) -> bool:
    """
    High-level function to create a Jira ticket note in Obsidian using commands.
    It reads a template, populates it with Jira info, and uses commands to create the note.
    
    Args:
        ticket_key (str): Jira ticket key (e.g., "FPA-3").
        ticket_title (str): Jira ticket title.
        markdown_content (str): Generated markdown content for the ticket.
        target_folder (str): Folder within the vault to create the note (e.g., "Jira").
        
    Returns:
        bool: True if successful.
    """
    try:
        # --- 1. Define Paths and Note Name ---
        note_name = f"{ticket_key}_{str_to_slug(ticket_title)}.md"
        full_note_path = f"{target_folder}/{note_name}".replace("\\", "/") # Ensure forward slashes

        template_file_path = Path(OBSIDIAN_VAULT_PATH) / TEMPLATE_FOLDER / JIRA_TEMPLATE_FILE
        print(f"📄 Reading template from: {template_file_path}")
        # --- 2. Read Template Content ---
        if not template_file_path.exists():
            print(f"❌ ERROR: Template file not found at '{template_file_path}'.")
            return False
            
        template_content = template_file_path.read_text(encoding='utf-8')

        # --- 3. Populate Template Placeholders ---
        final_content = template_content
        
        # Simple string replacements for your custom placeholders
        final_content = final_content.replace("{{TICKET_KEY}}", ticket_key)
        final_content = final_content.replace("{{TICKET_TITLE}}", ticket_title)
        
        # Replace the main content block
        final_content = final_content.replace("%%JIRA_CONTENT%%", markdown_content)
        
        # Replicate common Templater/dynamic fields with Python equivalents
        today_str = datetime.now().strftime("%Y-%m-%d")
        final_content = final_content.replace("<% tp.date.now(\"YYYY-MM-DD\") %>", today_str)
        final_content = final_content.replace("{{DATE}}", today_str)

        print("✅ Template populated successfully.")

        # --- 4. Create Note using Advanced URI with file creation ---
        # First create the note with content
        success = create_note_with_uri(
            vault_name=OBSIDIAN_VAULT_NAME,
            filepath=full_note_path,
            content=final_content,
            mode="new"
        )
        
        if success:
            # Optional: Execute additional commands after note creation
            # For example, open the note in a new pane
            execute_obsidian_command(
                vault_name=OBSIDIAN_VAULT_NAME,
                command="workspace:split-vertical",
                filepath=full_note_path,
                use_command_id=True
            )
        
        return success
        
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
        test_markdown_content = """
## Ticket Details
- **Status**: In Progress
- **Assignee**: John Doe
- **Description**: This is the main content of the Jira ticket, generated by the script and inserted into the `%%JIRA_CONTENT%%` placeholder in the template.
"""
        test_target_folder = "Tests" # Creates note in "Tests" subfolder of your vault
        
        print(f"\n--- Creating test note for ticket: {test_ticket_key} ---")
        
        success = create_jira_note_in_obsidian(
            ticket_key=test_ticket_key,
            ticket_title=test_ticket_title,
            markdown_content=test_markdown_content,
            target_folder=test_target_folder
        )

        print("\n--- Test Complete ---")
        if success:
            print(f"🎉 Success! Check the '{test_target_folder}' folder in your '{OBSIDIAN_VAULT_NAME}' vault for the new note.")
        else:
            print("❌ Test failed. Please review the error messages above.")