#!/home/vien/local_tools/MyVenvFolder/bin/python
"""
Obsidian integration for Jira using the Obsidian Local REST API with cmd.exe curl.
This version uses subprocess to call cmd.exe with curl commands instead of requests library.

Prerequisites:
1. Obsidian Community Plugin "Local REST API" must be installed and enabled.
2. The API Key must be copied from the plugin's settings page.
3. curl must be available in Windows (built-in for Windows 10+)
"""

import os
import re
import subprocess
import json
from pathlib import Path
from typing import Optional, Dict, List

from dev_common import *

# --- Configuration ---
OBSIDIAN_API_KEY = read_value_from_credential_file(CREDENTIALS_FILE_PATH, OBSIDIAN_API_TOKEN_KEY_NAME)
# OBSIDIAN_API_URL = "https://127.0.0.1:27124/" #ENCRYPTED
OBSIDIAN_API_URL = "http://127.0.0.1:27123/"


class ObsidianAPIIntegrator:
    """Obsidian note creator using cmd.exe curl calls to the Local REST API."""
    
    def __init__(self, api_key: str, base_url: str = OBSIDIAN_API_URL):
        if not api_key or "YOUR_API_KEY" in api_key:
            raise ValueError("Obsidian API key is not set. Please configure OBSIDIAN_API_KEY.")
            
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key

    def _run_curl_command(self, endpoint: str, method: str = "GET", data: Optional[Dict] = None, content_type: str = "application/json") -> Dict:
        """Run curl command via cmd.exe and return parsed JSON response"""
        url = f"{self.base_url}{endpoint}"
        
        # Base curl command using cmd.exe
        cmd = [
            "cmd.exe", "/c", "curl",
            "-X", method,
            url,
            "-H", "accept: application/json",
            "-H", f"Authorization: Bearer {self.api_key}",
            "-s"  # Silent mode to reduce noise
        ]
        
        # Add data for POST requests
        if data and method == "POST":
            cmd.extend([
                "-H", f"Content-Type: {content_type}",
                "-d", json.dumps(data)
            ])
        
        try:
            # Run the command and capture output
            print(f"🚀 Running curl command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Parse JSON response
            if result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    print(f"✅ Response: {data}")
                    return data
                except json.JSONDecodeError:
                    print(f"Warning: Non-JSON response: {result.stdout}")
                    return {"response": result.stdout}
            else:
                return {"success": True}
                
        except subprocess.CalledProcessError as e:
            print(f"❌ Curl command failed: {e}")
            print(f"   Command: {' '.join(cmd)}")
            if e.stderr:
                print(f"   Error output: {e.stderr}")
            raise Exception(f"API call failed: {e}")

    def get_available_commands(self) -> List[Dict]:
        """Get all available Obsidian commands including Templater templates"""
        try:
            response = self._run_curl_command("/commands/")
            # The API returns {"commands": [list of command objects]}
            if isinstance(response, dict) and "commands" in response:
                commands_list = response["commands"]
                print(f"🎨 Available commands: {len(commands_list)}")
                return commands_list
            else:
                print(f"❌ Unexpected response format: {response}")
                return []
        except Exception as e:
            print(f"❌ Failed to get commands: {e}")
            return []

    def find_template_commands(self, template_name: str = None, command_type: str = "create") -> List[Dict]:
        """
        Find Templater commands, optionally filtering by template name
        
        Args:
            template_name: Template name to search for
            command_type: Either "insert" or "create" (default: "create")
        """
        commands_list = self.get_available_commands()
        
        # Filter for Templater commands based on type
        if command_type == "create":
            # Look for "create-" commands that create new files
            template_commands = [
                cmd for cmd in commands_list 
                if cmd.get("id", "").startswith("templater-obsidian:create-")
            ]
        else:
            # Look for regular insert commands
            template_commands = [
                cmd for cmd in commands_list 
                if cmd.get("id", "").startswith("templater-obsidian:") and 
                   not cmd.get("id", "").startswith("templater-obsidian:create-")
            ]
        
        if template_name:
            template_commands = [
                cmd for cmd in template_commands
                if template_name.lower() in cmd.get("name", "").lower() or 
                   template_name.lower() in cmd.get("id", "").lower()
            ]
        
        return template_commands

    def execute_command(self, command_id: str) -> bool:
        """Execute an Obsidian command by its ID"""
        try:
            payload = {"command": command_id}
            self._run_curl_command("/commands/execute/", method="POST", data=payload)
            print(f"✅ Command executed: {command_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to execute command {command_id}: {e}")
            return False

    def create_note_with_template_command(self, template_command_id: str, note_path: str = None) -> bool:
        """
        Create a note using a Templater command.
        For "create" commands, set the file path first, then execute the command.
        """
        try:
            # If using a "create" command and note_path is provided, we need to set the target path
            if "create-" in template_command_id and note_path:
                print(f"📄 Setting target path for new file: {note_path}")
                
                # For Templater "create" commands, we might need to set the active folder
                # or handle this differently. Let's try executing the command first
                # and see if Templater prompts for the location
                
            # Execute the template command
            return self.execute_command(template_command_id)
            
        except Exception as e:
            print(f"❌ Failed to create note with template: {e}")
            return False

    def create_note_with_template(self,
                                  note_name: str,
                                  content: str,
                                  template_path: str,
                                  folder: str = "") -> bool:
        """
        Creates a note in Obsidian from a template and appends content.
        Uses Templater "create" commands which create new files.
        """
        full_note_path = f"{folder}/{note_name}.md" if folder else f"{note_name}.md"
        
        print(f"📄 Attempting to create note '{full_note_path}' from template '{template_path}'...")

        # Look for "create" commands first (these create new files)
        template_commands = self.find_template_commands(template_path, command_type="create")
        
        if not template_commands:
            print(f"❌ No 'create' template command found for '{template_path}'")
            print("Available 'create' template commands:")
            all_create_templates = self.find_template_commands(command_type="create")
            for cmd in all_create_templates[:5]:  # Show first 5
                print(f"   - {cmd.get('name', 'Unknown')} (ID: {cmd.get('id', 'Unknown')})")
            
            # Fallback to insert method
            print("\n🔄 Falling back to 'insert' method...")
            return self._create_note_with_insert_template(note_name, content, template_path, folder)

        # Use the first matching create command
        template_command = template_commands[0]
        print(f"🎯 Found create command: {template_command.get('name')}")

        # Execute the create command (this should prompt for file location/name)
        if not self.create_note_with_template_command(template_command["id"], full_note_path):
            return False

        print(f"✅ Template applied successfully")

        # The create command should have created the file, but we don't know the exact name
        # Templater might have prompted the user or used a different naming convention
        
        # Try to append content if provided
        if content.strip():
            # We'll try to append to the expected path, but this might fail if the actual
            # file name is different from what we expect
            content_to_append = f"\n\n---\n\n{content}"
            try:
                payload = {
                    "path": full_note_path,
                    "content": content_to_append
                }
                self._run_curl_command("/vault/append/", method="POST", data=payload)
                print(f"✅ Appended content to: {full_note_path}")
            except Exception as e:
                print(f"⚠️  Could not append content to {full_note_path}: {e}")
                print("   The file may have been created with a different name by Templater.")

        return True
        
    def _create_note_with_insert_template(self, note_name: str, content: str, template_path: str, folder: str = "") -> bool:
        """Fallback method using insert templates with manual file creation"""
        full_note_path = f"{folder}/{note_name}.md" if folder else f"{note_name}.md"
        
        # First, try to find insert commands
        template_commands = self.find_template_commands(template_path, command_type="insert")
        
        if not template_commands:
            print(f"❌ No template command found for '{template_path}'")
            return False

        template_command = template_commands[0]
        print(f"🎯 Found insert command: {template_command.get('name')}")

        try:
            # Create the file first
            payload = {"path": full_note_path, "content": ""}
            self._run_curl_command("/vault/", method="POST", data=payload)
            print(f"📄 Created file: {full_note_path}")
            
            # Open the file to make it active
            payload = {"file": full_note_path}
            self._run_curl_command("/open/", method="POST", data=payload)
            print(f"📂 Opened file: {full_note_path}")
            
            # Execute the insert template command
            if not self.execute_command(template_command["id"]):
                return False
            
            # Append additional content if provided
            if content.strip():
                content_to_append = f"\n\n---\n\n{content}"
                payload = {
                    "path": full_note_path,
                    "content": content_to_append
                }
                self._run_curl_command("/vault/append/", method="POST", data=payload)
                print(f"✅ Appended content to: {full_note_path}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed with insert method: {e}")
            return False

    def list_templates(self):
        """List all available Templater templates"""
        print("\n🎨 Available Templater Commands:")
        print("=" * 50)
        
        commands_list = self.get_available_commands()
        
        # Separate create and insert commands
        create_commands = [
            cmd for cmd in commands_list 
            if cmd.get("id", "").startswith("templater-obsidian:create-")
        ]
        
        insert_commands = [
            cmd for cmd in commands_list 
            if cmd.get("id", "").startswith("templater-obsidian:") and 
               not cmd.get("id", "").startswith("templater-obsidian:create-") and
               not cmd.get("name", "").startswith("Templater: Open") and
               not cmd.get("name", "").startswith("Templater: Replace") and
               not cmd.get("name", "").startswith("Templater: Jump") and
               not cmd.get("name", "").startswith("Templater: Create new note")
        ]
        
        if create_commands:
            print("CREATE Commands (create new files):")
            for i, cmd in enumerate(create_commands, 1):
                name = cmd.get("name", "Unknown")
                cmd_id = cmd.get("id", "Unknown")
                template_file = cmd_id.split(":")[-1] if ":" in cmd_id else "Unknown"
                
                print(f"{i:2d}. {name}")
                print(f"    Template: {template_file}")
                print(f"    Command ID: {cmd_id}")
                print()
        
        if insert_commands:
            print("INSERT Commands (insert into current file):")
            for i, cmd in enumerate(insert_commands, 1):
                name = cmd.get("name", "Unknown")
                cmd_id = cmd.get("id", "Unknown")
                template_file = cmd_id.split(":")[-1] if ":" in cmd_id else "Unknown"
                
                print(f"{i:2d}. {name}")
                print(f"    Template: {template_file}")
                print(f"    Command ID: {cmd_id}")
                print()
        
        if not create_commands and not insert_commands:
            print("No Templater commands found.")
            print(f"Total commands found: {len(commands_list)}")
            # Show a few example commands for debugging
            print("\nFirst few commands (for debugging):")
            for i, cmd in enumerate(commands_list[:5]):
                print(f"  {cmd.get('id', 'Unknown')}: {cmd.get('name', 'Unknown')}")
            return


# Integration function for your Jira script
def create_jira_note_in_obsidian(ticket_key: str, ticket_title: str, markdown_content: str, template_path: str = "tmpl_NoteNormal", folder: str = "Jira") -> bool:
    """
    High-level function to create a Jira ticket note in Obsidian via API.
    
    Args:
        ticket_key: Jira ticket key (e.g., "FPA-3")
        ticket_title: Jira ticket title
        markdown_content: Generated markdown content for the ticket
        template_path: Template name to search for (e.g., "tmpl_NoteNormal")
        folder: Folder within vault to create the note (e.g., "Jira/FPA")
        
    Returns:
        bool: True if successful
    """
    try:
        integrator = ObsidianAPIIntegrator(api_key=OBSIDIAN_API_KEY)
        
        # This import can be moved to the top of the file if dev_common is always available
        from dev_common import str_to_slug
        note_name = f"{ticket_key}_{str_to_slug(ticket_title)}"
        
        return integrator.create_note_with_template(
            note_name=note_name,
            content=markdown_content,
            template_path=template_path,
            folder=folder
        )
        
    except (ValueError, ImportError, Exception) as e:
        print(f"❌ Error creating Obsidian note: {e}")
        return False


if __name__ == "__main__":
    # --- Quick Test ---
    
    print("--- Running Obsidian API Integration Test ---")
    
    if "YOUR_API_KEY" in OBSIDIAN_API_KEY:
        print("🛑 ERROR: Please update the OBSIDIAN_API_KEY in the script before running.")
    else:
        try:
            integrator = ObsidianAPIIntegrator(api_key=OBSIDIAN_API_KEY)
            
            # List available templates
            integrator.list_templates()
            
            # Test content
            test_content = """# Test Jira Ticket

REF: https://company.atlassian.net/browse/TEST-123

## Ticket Overview:
- **Title**: Test ticket for Obsidian API integration
- **Description**: This is a test ticket to verify the CMD curl-based integration.
"""
            
            # Test with the template name you mentioned
            test_template = "tmpl_NoteNormal"  # This will search for templates containing this name
            test_folder = "Tests"
            
            print(f"\n--- Testing with template: {test_template} ---")
            success = create_jira_note_in_obsidian(
                ticket_key="TEST-123",
                ticket_title="cmd curl api integration test",
                markdown_content=test_content,
                template_path=test_template,
                folder=test_folder
            )
        
            print("\n--- Test Complete ---")
            if success:
                print("🎉 Test successful! Check the 'Tests' folder in your Obsidian vault.")
            else:
                print("❌ Test failed. Check the error messages above.")
                
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")