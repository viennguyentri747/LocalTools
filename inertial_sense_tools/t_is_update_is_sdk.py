#!/usr/bin/env python3.10
import argparse
import os
import re
import shutil
import subprocess
import sys
from typing import Optional, List
import zipfile
from pathlib import Path

from dev_common.tools_utils import ToolTemplate, build_examples_epilog

# --- Configuration ---
# Base directory for the SDK repositories.
CORE_REPOS_DIR = Path.home() / "core_repos"
# Parent directory where the versioned SDK folder (e.g., inertial-sense-sdk-2.5.0) is located.
INSENSE_SDK_REPO_DIR = CORE_REPOS_DIR / "insensesdk"
# Directory where the SDKs are extracted.
SDK_INSTALL_DIR = INSENSE_SDK_REPO_DIR / "InsenseSDK"
# Location of the libusb zip file.
LIBUSB_ZIP_PATH = Path.home() / "downloads" / "libusb-master-1-0.zip"
# --- End Configuration ---


def extract_version_from_zip(zip_path: Path) -> Optional[str]:
    """Extracts the version number from the SDK zip filename."""
    prefix = "inertial-sense-sdk-"
    match = re.search(rf"{prefix}([\d\.]+)\.zip", zip_path.name)
    if match:
        version = match.group(1)
        print(f"✅ Found SDK version: {version}")
        return version
    # TODO: if not found, try use text after inertial-sense-sdk- and before .zip
    print(
        f"⚠️ WARNING: Could not extract version number from filename: {zip_path.name}, falling back to getting whole text after {prefix}")
    match = re.search(rf"{prefix}(.+)\.zip", zip_path.name)
    if match:
        version = match.group(1)
        print(f"✅ Found SDK version: {version}")
        return version
    print(f"❌ FATAL: Could not extract version from filename: {zip_path.name}")
    return None


def unzip_to_dest(zip_path: Path, dest_dir: Path) -> bool:
    """Unzips a file and verifies its extraction."""
    print(f"📦 Unzipping '{zip_path.name}' to '{dest_dir}'...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(dest_dir)
        print("   -> Unzip complete.")
        return True
    except FileNotFoundError:
        print(f"❌ ERROR: Zip file not found at '{zip_path}'")
        return False
    except Exception as e:
        print(f"❌ ERROR: Failed to unzip '{zip_path.name}': {e}")
        return False


def integrate_libusb(new_sdk_path: Path):
    """Integrates the libusb source files into the new SDK."""
    print("⚙️ Integrating libusb...")
    libusb_src_dir = new_sdk_path / "src" / "libusb"
    libusb_temp_dir = libusb_src_dir / "libusb-master"

    if not LIBUSB_ZIP_PATH.exists():
        print(f"⚠️ WARNING: libusb zip not found at '{LIBUSB_ZIP_PATH}'. Skipping integration.")
        return

    # 1. Unzip libusb
    if not unzip_to_dest(LIBUSB_ZIP_PATH, libusb_src_dir):
        return

    if not libusb_temp_dir.exists():
        print(f"❌ ERROR: Expected '{libusb_temp_dir.name}' folder after unzipping libusb. Aborting integration.")
        return

    # 2. Move contents up one level
    print(f"   -> Moving files from '{libusb_temp_dir.name}' up one level...")
    for item in libusb_temp_dir.iterdir():
        shutil.move(str(item), str(libusb_src_dir))

    # 3. Remove the now-empty temporary directory
    print(f"   -> Removing empty directory '{libusb_temp_dir.name}'...")
    shutil.rmtree(libusb_temp_dir)
    print("   -> libusb integration complete.")
    check_commit_changes_to_git("Integrate libusb")


def modify_sdk_cmake_files(new_sdk_version, new_sdk_path: Path):
    """Modifies the CMakeLists.txt files within the new SDK."""
    print("📝 Modifying CMake files...")

    # 1. Add subdirectory to root CMakeLists.txt
    root_cmake_path = new_sdk_path / "CMakeLists.txt"
    add_line = "add_subdirectory(cltool)"
    try:
        content = root_cmake_path.read_text()
        if add_line in content:
            print(f"   -> ⚠️ WARNING: '{add_line}' already exists in '{root_cmake_path.name}'.")
        else:
            with root_cmake_path.open("a") as f:
                f.write(f"\n{add_line}\n")
            print(f"   -> Added '{add_line}' to '{root_cmake_path.name}'.")
    except FileNotFoundError:
        print(f"❌ ERROR: Cannot find '{root_cmake_path}'. Skipping.")

    # 2. Change project name in cltool/CMakeLists.txt
    cltool_cmake_path = new_sdk_path / "cltool" / "CMakeLists.txt"
    old_project = "project(cltool)"
    new_project = "project(insense_cltool)"
    try:
        content = cltool_cmake_path.read_text()
        if new_project in content:
            print(f"   -> Project name in '{cltool_cmake_path.name}' is already correct.")
        elif old_project in content:
            new_content = content.replace(old_project, new_project)
            cltool_cmake_path.write_text(new_content)
            print(f"   -> Changed project name in '{cltool_cmake_path.name}'.")
        else:
            print(f"   -> ⚠️ WARNING: Could not find '{old_project}' in '{cltool_cmake_path.name}'.")
    except FileNotFoundError:
        print(f"❌ ERROR: Cannot find '{cltool_cmake_path}'. Skipping.")

    # 3. Update top level CMakeList.txt
    print("🚀 Updating top-level SDK version...")
    cmake_path = INSENSE_SDK_REPO_DIR / "CMakeLists.txt"
    try:
        content = cmake_path.read_text()
        pattern = r'(set\(INSENSE_SDK_VERSION\s+")[^"]*("\))'

        if not re.search(pattern, content):
            print(f"   -> ⚠️ WARNING: Could not find INSENSE_SDK_VERSION variable in '{cmake_path}'.")
            return

        new_content, count = re.subn(pattern, rf'\g<1>{new_sdk_version}\g<2>', content)

        if count > 0:
            cmake_path.write_text(new_content)
            print(f"   -> Set INSENSE_SDK_VERSION to \"{new_sdk_version}\" in '{cmake_path.name}'.")
        else:
            print(f"   -> ⚠️ WARNING: Version already set or pattern mismatch in '{cmake_path}'.")

    except FileNotFoundError:
        print(f"❌ ERROR: Top-level CMakeLists.txt not found at '{cmake_path}'.")
    except Exception as e:
        print(f"❌ ERROR: Failed to update top-level CMakeLists.txt: {e}")

    check_commit_changes_to_git("Update CMakeLists.txt files", show_diff=True)


def cleanup_old_sdks(install_dir: Path, new_sdk_dir_name: str):
    """Removes old SDK directories."""
    print("🧹 Cleaning up old SDK versions...")
    for item in install_dir.glob("inertial-sense-sdk-*"):
        if item.is_dir() and item.name != new_sdk_dir_name:
            print(f"   -> Removing old SDK: {item.name}")
            try:
                shutil.rmtree(item)
            except Exception as e:
                print(f"❌ ERROR: Failed to remove '{item.name}': {e}")
    print("   -> Cleanup complete.")
    check_commit_changes_to_git("Cleanup old SDKs")


def get_current_git_branch() -> Optional[str]:
    """Returns the current git branch name, or None if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=INSENSE_SDK_REPO_DIR  # Run git command in the parent directory of the SDK
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        print("⚠️ WARNING: Not in a git repository or git command failed.")
        return None
    except FileNotFoundError:
        print("❌ ERROR: Git command not found. Please ensure Git is installed and in your PATH.")
        return None


def check_commit_changes_to_git(message: str, show_diff: bool = False):
    """Checks if changes need to be committed to Git."""
    if not confirm_action(f"Do you want to commit '{message}' to Git?"):
        return

    print(f"Adding and committing changes to Git: '{message}'")
    try:
        subprocess.run(["git", "add", "."], check=True, cwd=INSENSE_SDK_REPO_DIR)
        if show_diff:
            subprocess.run(["git", "--no-pager", "diff", "--cached"], check=True, cwd=INSENSE_SDK_REPO_DIR)
        subprocess.run(["git", "commit", "-m", message], check=True, cwd=INSENSE_SDK_REPO_DIR)
        print("✅ Changes committed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: Git commit failed: {e}")
    except FileNotFoundError:
        print("❌ ERROR: Git command not found. Please ensure Git is installed and in your PATH.")


def confirm_action(prompt: str) -> bool:
    """Asks the user for confirmation and returns True for 'y' (case-insensitive), False otherwise."""
    while True:
        current_branch = get_current_git_branch()
        branch_info = f" (on branch: {current_branch})" if current_branch else ""
        response = input(f"{prompt}{branch_info} (y/n): ").strip().lower()
        if response == "y":
            return True
        elif response == "n":
            return False
        else:
            print("Invalid input. Please enter 'y' or 'n'.")



def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Update SDK",
            description="Update Inertial Sense SDK",
            args={
                "--sdk_path": "~/downloads/inertial-sense-sdk-2.5.0.zip",
            }
        ),
    ]


def main():
    """Main function to orchestrate the SDK update process."""
    parser = argparse.ArgumentParser(
        description="Automate the Inertial Sense SDK update process.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.formatter_class = argparse.RawTextHelpFormatter
    # Fill help epilog from templates
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    parser.add_argument("--sdk_path", "-p", type=Path, required=True,
  help="Path to the new SDK zip file (e.g., ~/downloads/inertial-sense-sdk-2.5.0.zip)")
    args = parser.parse_args()
    sdk_zip_path = args.sdk_path.expanduser()

    if not sdk_zip_path.exists():
        print(f"❌ FATAL: SDK zip file not found at '{sdk_zip_path}'")
        sys.exit(1)

    # Step 1: Extract version and set up paths
    version = extract_version_from_zip(sdk_zip_path)
    if not version:
        sys.exit(1)
    else:
        print(f"   -> Extracted version: {version}")
    new_sdk_dir_name = f"inertial-sense-sdk-{version}"
    new_sdk_path = SDK_INSTALL_DIR / new_sdk_dir_name

    if new_sdk_path.exists():
        print(
            f"❌ FATAL: SDK folder '{new_sdk_path}' already exists:\n1. 'cd {INSENSE_SDK_REPO_DIR}' and undo all commits\n2. Run 'cd /home/vien/core_repos/insensesdk && git reset --hard && git clean -fd'!")  # &&rm -rf {new_sdk_path}'
        sys.exit(1)

    # Step 2: Unzip the new SDK
    if not unzip_to_dest(sdk_zip_path, SDK_INSTALL_DIR):
        sys.exit(1)
    check_commit_changes_to_git(f"Unzip new SDK {version}")

    # Step 3: Integrate libusb
    integrate_libusb(new_sdk_path)

    # Step 4: Modify CMakeLists.txt files
    modify_sdk_cmake_files(version, new_sdk_path)

    # Step 5: Remove old SDK folders
    cleanup_old_sdks(SDK_INSTALL_DIR, new_sdk_dir_name)

    print("\n🎉 SDK update process finished successfully!")

if __name__ == "__main__":
    main()
