#!/home/vien/core_repos/local_tools/MyVenvFolder/bin/python
"""
Obsidian integration for Jira using the Obsidian Advanced URI plugin.
This script creates a new note in Obsidian by populating a local template
file and then calling a specially crafted obsidian://adv-uri URL.

Prerequisites:
1. Obsidian Community Plugin "Advanced URI" must be installed and enabled.
2. The Vault Name and local file path to the vault must be configured below.
"""

import re
import subprocess
from typing import Optional
import urllib.parse
from pathlib import Path
from dev.dev_common.constants import OBSIDIAN_VAULT_NAME, OBSIDIAN_VAULT_PATH
from dev.dev_common.core_utils import LOG
from dev.dev_common.format_utils import str_to_slug

# This import is assumed from your original script.
# It should contain a function `str_to_slug` that sanitizes strings for filenames.


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
        LOG("❌ ERROR: OBSIDIAN_VAULT_NAME is not configured.")
        return False

    try:
        # URL-encode all components to ensure they are handled correctly.
        encoded_vault = urllib.parse.quote(vault_name, safe='')
        encoded_filepath = urllib.parse.quote(filepath, safe='')
        encoded_content = urllib.parse.quote(content, safe='')
        if len(encoded_content) == 0:
            LOG("❌ ERROR: Encoded content is empty, the function will behave incorrectly. Skipping...")
            return False

        # Construct the full advanced URI.
        uri = (
            f"obsidian://adv-uri?vault={encoded_vault}"
            f"&filepath={encoded_filepath}"
            f"&data={encoded_content}"
            # f"&data=This%20text%20is%20overwritten&"
            f"&mode={mode}"
        )

        LOG(f"🚀 Executing Obsidian URI (first 150 chars): {uri[:150]}...")
        # WSL environment - use cmd.exe with proper escaping
        escaped_uri = uri.replace('&', '^&')
        cmd = f'cmd.exe /c start "" "{escaped_uri}"'
        subprocess.run(cmd, shell=True, check=True)
        # --- END UPDATED REPLACEMENT ---

        LOG(f"✅ Successfully sent request to Obsidian to create note: {filepath}")
        return True

    except Exception as e:
        LOG(f"❌ Failed to execute Obsidian URI: {e}")
        LOG("   Ensure the 'Advanced URI' plugin is installed and enabled in Obsidian.")
        LOG("   For WSL, ensure you can run cmd.exe commands.")
        LOG("   For Linux/macOS, ensure 'xdg-open' or 'open' command is available.")
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
        LOG("❌ ERROR: OBSIDIAN_VAULT_NAME is not configured.")
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

        LOG(f"⏳ Executing blocking Obsidian Command URI for WSL: {uri[:150]}...")
        escaped_uri = uri.replace('&', '^&')
        # The /wait flag tells cmd.exe to wait for the new process to terminate.
        cmd = f'cmd.exe /c start /wait "" "{escaped_uri}"'
        # LOG(f"🚀 Running command: {cmd} at {datetime.now()}")
        subprocess.run(cmd, shell=True, check=True)
        # LOG(f"✅ Command executed successfully at {datetime.now()}")
        LOG(f"✅ Successfully executed Obsidian command: {command}")
        return True

    except Exception as e:
        LOG(f"❌ Failed to execute Obsidian command URI: {e}")
        LOG("   Ensure 'Advanced URI' is enabled in Obsidian and cmd.exe is accessible from WSL.")
        return False


def create_obsidian_note_with_template(
    note_vault_rel_path: Path,
    markdown_content: str,
    vault_name: str = OBSIDIAN_VAULT_NAME,
    template_command: str = "templater-obsidian:Dev/templates_container/page_tmpl_default.md"
) -> bool:
    """
    Create or update an Obsidian note with a template and append additional content.

    Args:
        note_rel_path: The full relative path (inside vault) to the note, e.g. "Jira/MANP-268_issue.md".
        markdown_content: The markdown text to append after the template.
        vault_name: The Obsidian vault name to target.
        template_command: The templater command ID or path for the template.

    Returns:
        True if successful, False otherwise.
    """
    try:
        note_full_path_str = str(note_vault_rel_path)
        # Generate file if it doesn't exist (using templater command)
        execute_obsidian_command(
            vault_name=vault_name,
            command=template_command,
            filepath=note_full_path_str,
            use_command_id=True,
            mode="overwrite"
        )

        # Append provided markdown content
        create_note_with_uri(
            vault_name=vault_name,
            filepath=note_full_path_str,
            content=markdown_content,
            mode="append"
        )

        return True

    except Exception as e:
        LOG(f"❌ An unexpected error occurred in create_obsidian_note_with_template: {e}")
        return False


def insert_content_after_regex(
    note_vault_rel_path: Path,
    prefix_regex: str,
    content_to_insert: str,
    vault_path: Optional[Path] = None,         # default to OBSIDIAN_VAULT_PATH if None
    flags: int = re.MULTILINE,                  # good default for headings/blocks
    insert_all: bool = False,                   # False = only after the first match
    prevent_duplicate: bool = True,             # skip if content already exists verbatim
) -> bool:
    """
    Insert `content_to_insert` immediately AFTER each regex match (or the first match if insert_all=False)
    in the target note inside the Obsidian vault.

    Returns:
        True if the file was modified (or already contained the content and we skipped),
        False if the target file doesn't exist or the regex didn't match.
    """
    try:
        target_path = vault_path / str(note_vault_rel_path)
        if not target_path.exists():
            LOG(f"❌ Target note does not exist: {target_path}")
            return False

        text = target_path.read_text(encoding="utf-8")

        if prevent_duplicate and content_to_insert in text:
            LOG("ℹ️ Content already present; skipping insert.")
            return True

        pattern = re.compile(prefix_regex, flags)
        matches = list(pattern.finditer(text))
        if not matches:
            LOG(f"❌ No match for regex: {prefix_regex}")
            return False

        # Decide which matches to use
        chosen = matches if insert_all else [matches[0]]

        # Build insertions back-to-front to avoid index shifts
        new_text = text
        inserted_any = False
        for m in reversed(chosen):
            insert_at = m.end()

            payload = content_to_insert
            new_text = new_text[:insert_at] + payload + new_text[insert_at:]
            inserted_any = True

        if inserted_any and new_text != text:
            target_path.write_text(new_text, encoding="utf-8")
            LOG(f"✅ Inserted content after regex into: {note_vault_rel_path}")
            return True

        LOG("ℹ️ Nothing changed (possibly identical content).")
        return True

    except Exception as e:
        LOG(f"❌ insert_content_after_regex failed: {e}")
        return False


def to_wikilink(rel_md_path_or_name: Path | str, alias: str | None = None) -> str:
    """
    Convert a vault-relative MD file path or filename into an Obsidian wikilink.

    Examples:
        "Folder/a.md" -> "[[Folder/a]]"
        "a.md"        -> "[[a]]"
        "a"           -> "[[a]]"
    """
    if isinstance(rel_md_path_or_name, Path):
        path_no_ext = rel_md_path_or_name.as_posix()
    else:
        path_no_ext = str(rel_md_path_or_name)

    # Strip trailing .md if present
    if path_no_ext.lower().endswith(".md"):
        path_no_ext = path_no_ext[:-3]

    return f"[[{path_no_ext}|{alias}]]" if alias else f"[[{path_no_ext}]]"

