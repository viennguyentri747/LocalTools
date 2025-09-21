"""Utilities for updating the Inertial Sense SDK repository."""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Optional
from dev_common import *

# --- Configuration ---
SDK_INSTALL_DIR = INSENSE_SDK_REPO_PATH / "InsenseSDK"
LIBUSB_ZIP_PATH = Path.home() / "downloads" / "libusb-master-1-0.zip"
NO_PROMPT: bool = False


# ─────────────────────────── Git helpers ──────────────────────────── #
# ─────────────────────────── Core SDK logic ────────────────────────── #


def extract_version_from_zip(zip_path: Path) -> Optional[str]:
    prefix = "inertial-sense-sdk-"
    match = re.search(rf"{prefix}([\d\.]+)\.zip", zip_path.name)
    if match:
        version = match.group(1)
        LOG(f"✅ Found SDK version: {version}")
        return version
    LOG(
        f"⚠️ WARNING: Could not extract version number from filename: {zip_path.name}, falling back to getting whole text after {prefix}"
    )
    match = re.search(rf"{prefix}(.+)\.zip", zip_path.name)
    if match:
        version = match.group(1)
        LOG(f"✅ Found SDK version: {version}")
        return version
    LOG(f"❌ FATAL: Could not extract version from filename: {zip_path.name}")
    return None


def unzip_to_dest(zip_path: Path, dest_dir: Path) -> bool:
    LOG(f"📦 Unzipping '{zip_path.name}' to '{dest_dir}'...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(dest_dir)
        LOG("   -> Unzip complete.")
        return True
    except FileNotFoundError:
        LOG(f"❌ ERROR: Zip file not found at '{zip_path}'")
        return False
    except Exception as exc:
        LOG(f"❌ ERROR: Failed to unzip '{zip_path.name}': {exc}")
        return False


def integrate_libusb(new_sdk_path: Path) -> None:
    LOG("⚙️ Integrating libusb...")
    libusb_src_dir = new_sdk_path / "src" / "libusb"
    libusb_temp_dir = libusb_src_dir / "libusb-master"

    if not LIBUSB_ZIP_PATH.exists():
        LOG(f"⚠️ WARNING: libusb zip not found at '{LIBUSB_ZIP_PATH}'. Skipping integration.")
        return

    if not unzip_to_dest(LIBUSB_ZIP_PATH, libusb_src_dir):
        return

    if not libusb_temp_dir.exists():
        LOG(f"❌ ERROR: Expected '{libusb_temp_dir.name}' folder after unzipping libusb. Aborting integration.")
        return

    LOG(f"   -> Moving files from '{libusb_temp_dir.name}' up one level...")
    for item in libusb_temp_dir.iterdir():
        shutil.move(str(item), str(libusb_src_dir))

    LOG(f"   -> Removing empty directory '{libusb_temp_dir.name}'...")
    shutil.rmtree(libusb_temp_dir)
    LOG("   -> libusb integration complete.")
    git_stage_and_commit(INSENSE_SDK_REPO_PATH, "Integrate libusb", auto_confirm=NO_PROMPT)


def modify_sdk_cmake_files(new_sdk_version: str, new_sdk_path: Path) -> None:
    LOG("📝 Modifying CMake files...")

    root_cmake_path = new_sdk_path / "CMakeLists.txt"
    add_line = "add_subdirectory(cltool)"
    try:
        content = root_cmake_path.read_text()
        if add_line in content:
            LOG(f"   -> ⚠️ WARNING: '{add_line}' already exists in '{root_cmake_path.name}'.")
        else:
            with root_cmake_path.open("a") as fp:
                fp.write(f"\n{add_line}\n")
            LOG(f"   -> Added '{add_line}' to '{root_cmake_path.name}'.")
    except FileNotFoundError:
        LOG(f"❌ ERROR: Cannot find '{root_cmake_path}'. Skipping.")

    cltool_cmake_path = new_sdk_path / "cltool" / "CMakeLists.txt"
    old_project = "project(cltool)"
    new_project = "project(insense_cltool)"
    try:
        content = cltool_cmake_path.read_text()
        if new_project in content:
            LOG(f"   -> Project name in '{cltool_cmake_path.name}' is already correct.")
        elif old_project in content:
            cltool_cmake_path.write_text(content.replace(old_project, new_project))
            LOG(f"   -> Changed project name in '{cltool_cmake_path.name}'.")
        else:
            LOG(f"   -> ⚠️ WARNING: Could not find '{old_project}' in '{cltool_cmake_path.name}'.")
    except FileNotFoundError:
        LOG(f"❌ ERROR: Cannot find '{cltool_cmake_path}'. Skipping.")

    LOG("🚀 Updating top-level SDK version...")
    cmake_path = INSENSE_SDK_REPO_PATH / "CMakeLists.txt"
    try:
        content = cmake_path.read_text()
        pattern = r'(set\(INSENSE_SDK_VERSION\s+")[^"]*("\))'

        if not re.search(pattern, content):
            LOG(f"   -> ⚠️ WARNING: Could not find INSENSE_SDK_VERSION variable in '{cmake_path}'.")
            return

        new_content, count = re.subn(pattern, rf"\g<1>{new_sdk_version}\g<2>", content)

        if count > 0:
            cmake_path.write_text(new_content)
            LOG(f"   -> Set INSENSE_SDK_VERSION to \"{new_sdk_version}\" in '{cmake_path.name}'.")
        else:
            LOG(f"   -> ⚠️ WARNING: Version already set or pattern mismatch in '{cmake_path}'.")
    except FileNotFoundError:
        LOG(f"❌ ERROR: Top-level CMakeLists.txt not found at '{cmake_path}'.")
    except Exception as exc:
        LOG(f"❌ ERROR: Failed to update top-level CMakeLists.txt: {exc}")

    git_stage_and_commit(INSENSE_SDK_REPO_PATH, "Update CMakeLists.txt files", show_diff=True, auto_confirm=NO_PROMPT)


def cleanup_old_sdks(install_dir: Path, new_sdk_dir_name: str) -> None:
    LOG("🧹 Cleaning up old SDK versions...")
    for item in install_dir.glob("inertial-sense-sdk-*"):
        if item.is_dir() and item.name != new_sdk_dir_name:
            LOG(f"   -> Removing old SDK: {item.name}")
            try:
                shutil.rmtree(item)
            except Exception as exc:
                LOG(f"❌ ERROR: Failed to remove '{item.name}': {exc}")
    LOG("   -> Cleanup complete.")
    git_stage_and_commit(INSENSE_SDK_REPO_PATH, "Cleanup old SDKs", auto_confirm=NO_PROMPT)


def get_current_git_branch() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=INSENSE_SDK_REPO_PATH,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        LOG("⚠️ WARNING: Not in a git repository or git command failed.")
        return None
    except FileNotFoundError:
        LOG("❌ ERROR: Git command not found. Please ensure Git is installed and in your PATH.")
        return None


def check_commit_changes_to_git(message: str, show_diff: bool = False) -> None:
    if not confirm_action(f"Do you want to commit '{message}' to Git?"):
        return

    LOG(f"Adding and committing changes to Git: '{message}'")
    try:
        subprocess.run(["git", "add", "."], check=True, cwd=INSENSE_SDK_REPO_PATH)
        if show_diff:
            subprocess.run(["git", "--no-pager", "diff", "--cached"], check=True, cwd=INSENSE_SDK_REPO_PATH)
        subprocess.run(["git", "commit", "-m", message], check=True, cwd=INSENSE_SDK_REPO_PATH)
        LOG("✅ Changes committed successfully.")
    except subprocess.CalledProcessError as exc:
        LOG(f"❌ ERROR: Git commit failed: {exc}")
    except FileNotFoundError:
        LOG("❌ ERROR: Git command not found. Please ensure Git is installed and in your PATH.")


def confirm_action(prompt: str) -> bool:
    if NO_PROMPT:
        LOG(f"{prompt} (auto-confirmed due to --no-prompt)")
        return True
    while True:
        current_branch = get_current_git_branch()
        branch_info = f" (on branch: {current_branch})" if current_branch else ""
        response = input(f"{prompt}{branch_info} (y/n): ").strip().lower()
        if response == "y":
            return True
        if response == "n":
            return False
        LOG("Invalid input. Please enter 'y' or 'n'.")


def apply_signal_handler(stash_ref: str) -> None:
    try:
        proceed = True if NO_PROMPT else prompt_confirmation(
            f"Apply signal handler changes from stash '{stash_ref}' and create a commit?"
        )
        if not proceed:
            LOG("Skipping applying signal handler changes.")
            return

        try:
            res_subject = subprocess.run(
                ["git", "log", "--format=%s", "-n", "1", stash_ref],
                capture_output=True,
                text=True,
                check=True,
                cwd=INSENSE_SDK_REPO_PATH,
            )
            subject = res_subject.stdout.strip() or f"Apply stash {stash_ref}"
        except subprocess.CalledProcessError:
            subject = f"Apply stash {stash_ref}"

        try:
            res_files = subprocess.run(
                ["git", "stash", "show", "--name-only", stash_ref],
                capture_output=True,
                text=True,
                check=True,
                cwd=INSENSE_SDK_REPO_PATH,
            )
            files = [f.strip() for f in res_files.stdout.splitlines() if f.strip()]
        except subprocess.CalledProcessError:
            files = []

        LOG(f"Applying stash '{stash_ref}' in repo '{INSENSE_SDK_REPO_PATH}'...")
        subprocess.run(["git", "stash", "apply", stash_ref], check=True, cwd=INSENSE_SDK_REPO_PATH)

        if files:
            LOG(f"Staging {len(files)} file(s) from stash...")
            try:
                subprocess.run(["git", "add", *files], check=True, cwd=INSENSE_SDK_REPO_PATH)
            except subprocess.CalledProcessError:
                LOG("Some files from stash don't exist at original paths; staging all changes as fallback.")
                subprocess.run(["git", "add", "-A"], check=True, cwd=INSENSE_SDK_REPO_PATH)
        else:
            LOG("No files reported by 'git stash show'; staging all changes as fallback.")
            subprocess.run(["git", "add", "-A"], check=True, cwd=INSENSE_SDK_REPO_PATH)

        LOG(f"Committing with subject: {subject}")
        subprocess.run(["git", "commit", "-m", subject], check=True, cwd=INSENSE_SDK_REPO_PATH)
        LOG("✅ Applied signal handler stash and committed successfully.")
    except subprocess.CalledProcessError as exc:
        LOG(f"❌ ERROR: Failed while applying stash '{stash_ref}': {exc}")
    except FileNotFoundError:
        LOG("❌ ERROR: Git command not found. Please ensure Git is installed and in your PATH.")


# ─────────────────────────── Public entry point ─────────────────────── #


def run_sdk_update(sdk_zip_path: Path, *, no_prompt: bool = False) -> None:
    global NO_PROMPT
    sdk_zip_path = sdk_zip_path.expanduser()
    NO_PROMPT = no_prompt

    if not sdk_zip_path.exists():
        LOG(f"❌ FATAL: SDK zip file not found at '{sdk_zip_path}'")
        return

    version = extract_version_from_zip(sdk_zip_path)
    if not version:
        return
    LOG(f"   -> Extracted version: {version}")

    new_sdk_dir_name = f"inertial-sense-sdk-{version}"
    new_sdk_path = SDK_INSTALL_DIR / new_sdk_dir_name

    if new_sdk_path.exists():
        LOG(
            f"❌ FATAL: SDK folder '{new_sdk_path}' already exists:\n1. 'cd {INSENSE_SDK_REPO_PATH}' and undo all commits\n2. Run 'cd {INSENSE_SDK_REPO_PATH} && git reset --hard && git clean -fd'!"
        )
        return

    branch_name = f"update-sdk-{str_to_slug(version)}-{str_to_slug(get_short_date_now())}"
    if not checkout_branch(INSENSE_SDK_REPO_PATH, branch_name):
        return

    if not unzip_to_dest(sdk_zip_path, SDK_INSTALL_DIR):
        return
    git_stage_and_commit(INSENSE_SDK_REPO_PATH, f"Unzip new SDK {version}", auto_confirm=NO_PROMPT)

    integrate_libusb(new_sdk_path)
    modify_sdk_cmake_files(version, new_sdk_path)
    cleanup_old_sdks(SDK_INSTALL_DIR, new_sdk_dir_name)

    LOG("\n🎉 SDK update process finished successfully!")
    signal_handler_stash_ref = "bca3b5c"
    apply_signal_handler(signal_handler_stash_ref)
