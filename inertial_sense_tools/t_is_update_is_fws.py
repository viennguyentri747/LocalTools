#!/home/vien/local_tools/MyVenvFolder/bin/python

import argparse
import os
import re
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional
from dev_common import *
from dev_common.tools_utils import ToolTemplate


# Define the paths and file prefixes
DOWNLOADS_DIR = Path.home() / "downloads"
IMX_PREFIX = "IS_IMX-5_v"
GPX_PREFIX = "IS-firmware_r"
IMX_EXTENSION = ".hex"
GPX_EXTENSION = ".fpkg"
IMX_SYMLINK = f"current_imx_fw{IMX_EXTENSION}"
GPX_SYMLINK = f"current_gpx_fw{GPX_EXTENSION}"


class FirmwarePair(NamedTuple):
    """A named tuple to hold a pair of firmware files."""
    imx_full_path: Path
    gpx_full_path: Path
    timestamp: str
    version: str  # Add version to the tuple for easier access


def find_firmware_pairs(version_or_fw_path: str) -> List[FirmwarePair]:
    """
    Scans for firmware pairs based on a version string or a firmware file path.
    If a firmware file path is given, it searches that file's directory.
    If a version is given, it searches the downloads directory.

    Args:
        version_or_fw_path: The firmware version (e.g., '2.5.0') or path to a firmware file.

    Returns:
        A list of FirmwarePair objects, sorted from newest to oldest.
    """
    input_path = Path(version_or_fw_path)
    final_version_pattern = None
    search_dir = DOWNLOADS_DIR
    # Check if input is a path to a firmware file
    if (input_path.suffix == f'{IMX_EXTENSION}' or input_path.suffix == f'{GPX_EXTENSION}'):
        if input_path.is_file():
            # Input == File path
            search_dir = input_path.parent.expanduser()
            file_name = input_path.name
        elif version_or_fw_path.startswith(f'{IMX_PREFIX}') or version_or_fw_path.startswith(f'{GPX_PREFIX}'):
            # Input == File name
            file_name = version_or_fw_path
        if file_name:
            file_version_pattern = r"(\d+\.\d+\.\d+[^+]*)"  # Captures version until +
            version_match = re.search(file_version_pattern, version_or_fw_path)
            if version_match:
                final_version_pattern = re.escape(version_match.group(1))  # Pattern = version

    else:
        # Input = version
        final_version_pattern = re.escape(version_or_fw_path)
    if final_version_pattern is None:
        LOG(f"❌ FATAL: Could not determine version pattern from input: {version_or_fw_path}")
        return []

    LOG(f"🔎 Using version pattern: {final_version_pattern}, search dir {search_dir}")
    # Create patterns to capture both version and timestamp
    imx_pattern = re.compile(
        rf"{re.escape(IMX_PREFIX)}(?P<version>{final_version_pattern})\+(?P<ts>[\d-]+)\{IMX_EXTENSION}")
    gpx_pattern = re.compile(
        rf"{re.escape(GPX_PREFIX)}(?P<version>{final_version_pattern})\+(?P<ts>[\d-]+)\{GPX_EXTENSION}")

    imx_candidates: List[tuple[str, str, Path]] = []  # (version, timestamp, path)
    gpx_candidates: List[tuple[str, str, Path]] = []

    # Find and extract version and timestamps from filenames
    for file_path in search_dir.glob("*"):
        imx_match = imx_pattern.match(file_path.name)
        if imx_match:
            LOG(f"Found IMX firmware file: {file_path}")
            imx_candidates.append((imx_match.group("version"), imx_match.group("ts"), file_path))
            continue

        gpx_match = gpx_pattern.match(file_path.name)
        if gpx_match:
            LOG(f"Found GPX firmware file: {file_path}")
            gpx_candidates.append((gpx_match.group("version"), gpx_match.group("ts"), file_path))

    # Sort candidates by timestamp in reverse (newest to oldest)
    imx_candidates.sort(key=lambda x: x[1], reverse=True)  # Sort by timestamp (index 1)
    gpx_candidates.sort(key=lambda x: x[1], reverse=True)

    # Create pairs by matching versions
    pairs = []
    matched_gpx = set()

    for imx_version, imx_timestamp, imx_path in imx_candidates:
        # Find a GPX file with the same version
        for gpx_version, gpx_timestamp, gpx_path in gpx_candidates:
            if imx_version == gpx_version and gpx_path not in matched_gpx:
                pairs.append(FirmwarePair(
                    imx_full_path=imx_path,
                    gpx_full_path=gpx_path,
                    timestamp=imx_timestamp,
                    version=imx_version  # Store the version in the tuple
                ))
                matched_gpx.add(gpx_path)
                break
    return pairs


def extract_version_from_filename(filename: str) -> Optional[str]:
    """Extracts version (e.g., '2.5.0') from a firmware filename."""
    match = re.search(r'(\d+\.\d+\.\d+)', filename)
    return match.group(1) if match else None


def select_firmware_pair(pairs: List[FirmwarePair]) -> Optional[FirmwarePair]:
    """
    Prompts the user to select a firmware pair if multiple are found.

    Args:
        pairs: A list of available firmware pairs.

    Returns:
        The selected FirmwarePair, or None if no selection is made.
    """
    if not pairs:
        LOG("❌ Error: No matching firmware file sets found.")
        return None

    if len(pairs) == 1:
        LOG(f"✅ Found one matching firmware set: {pairs[0].imx_full_path.name}, {pairs[0].gpx_full_path.name}")
        return pairs[0]

    LOG("🔎 Found multiple firmware sets. Please choose one:")

    # Limit choice to the 3 most recent sets
    display_pairs = pairs[:3]

    for i, pair in enumerate(display_pairs):
        LOG(f"  [{i + 1}] IMX: {pair.imx_full_path.name}")
        LOG(f"     GPX: {pair.gpx_full_path.name}")

    while True:
        try:
            choice = input(f"Enter your choice (1-{len(display_pairs)}): ")
            choice_index = int(choice) - 1
            if 0 <= choice_index < len(display_pairs):
                return display_pairs[choice_index]
            else:
                LOG("Invalid choice. Please try again.")
        except (ValueError, IndexError):
            LOG("Invalid input. Please enter a number from the list.")


def update_firmware(pair: FirmwarePair) -> None:
    """
    Updates the firmware files and symlinks in the destination directory.

    Args:
        pair: The firmware pair to use for the update.
    """
    LOG(f"\n🚀 Starting firmware update process in: {OW_KIM_FTM_FW_PATH}")
    os.chdir(OW_KIM_FTM_FW_PATH)  # Change to the destination directory

    # Copy new files
    new_imx_path = Path(pair.imx_full_path.name)
    LOG(f"Copying from {pair.imx_full_path} to {OW_KIM_FTM_FW_PATH/new_imx_path}")
    new_imx_path.write_bytes(pair.imx_full_path.read_bytes())

    new_gpx_path = Path(pair.gpx_full_path.name)
    LOG(f"Copying from {pair.gpx_full_path} to {OW_KIM_FTM_FW_PATH/new_gpx_path}")
    new_gpx_path.write_bytes(pair.gpx_full_path.read_bytes())

    # Set permissions and update symlinks
    new_imx_path.chmod(0o755)
    Path(IMX_SYMLINK).unlink(missing_ok=True)
    Path(IMX_SYMLINK).symlink_to(new_imx_path)

    new_gpx_path.chmod(0o755)
    Path(GPX_SYMLINK).unlink(missing_ok=True)
    Path(GPX_SYMLINK).symlink_to(new_gpx_path)

    LOG("\n✅ Seeds updated successfully:")
    os.system(f"ls -l {IMX_SYMLINK} {GPX_SYMLINK}")

    # 🔧 Extra cleanup of OLD matching files in kim_ftm_fw
    LOG("\n🧹 Scanning for OLD firmware files to remove...")

    extra_files = [
        f for f in OW_KIM_FTM_FW_PATH.iterdir()
        if (
            f.name.startswith(IMX_PREFIX) or f.name.startswith(GPX_PREFIX)
        ) and f.name not in {new_imx_path.name, new_gpx_path.name}
    ]

    if extra_files:
        LOG("Found OLD firmware files:")
        for f in extra_files:
            LOG(f"  - {f.name}")

        try:
            is_ok = prompt_confirmation("Do you want to remove these old firmware files?")
            if is_ok:
                for f in extra_files:
                    try:
                        f.unlink()
                        LOG(f"Removed: {f.name}")
                    except Exception as e:
                        LOG(f"Failed to remove {f.name}: {e}")
        except Exception as e:
            LOG(f"Error during extra cleanup: {e}")
    else:
        LOG("✅ No extra matching firmware files found.")

    LOG(f"\n✅ Firmware update complete!")
    LOG("\n✅ Dashboard updated successfully!")

    # Log git commands for manual execution
    LOG(LINE_SEPARATOR)
    LOG(f"Change receiver version with below command:")
    LOG(f'"', show_time=False)
    LOG(LINE_SEPARATOR, show_time=False)
    LOG("Stage and commit changes with below command:")
    LOG(
        f'read -e -i "$(cat {OW_KIM_RCVR_VERSION_FILE_PATH})" -p "Edit or Enter to use current RCVR version: " version && '
        f'if [ "$version" != "$(cat {OW_KIM_RCVR_VERSION_FILE_PATH})" ]; then '
        f'echo "$version" > {OW_KIM_RCVR_VERSION_FILE_PATH} && '
        f'echo "Version updated to $version!"; '
        f'fi && '
        f'cd {OW_SW_PATH} && git stage {OW_KIM_FTM_FW_PATH} && '
        f'git commit -m "Update firmware to version {pair.version}"',
        show_time=False
    )



def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Update Firmware from path",
            description="Update firmware files from a specific directory",
            args={
                ARG_VERSION_OR_FW_PATH: f"{DOWNLOADS_DIR}/IS_IMX-5_v2.6.0-rc.22+2025-09-13-011835{IMX_EXTENSION}",
            },
            no_need_live_edit=True,
        ),
        ToolTemplate(
            name="Update Firmware",
            description="Update firmware files based on version",
            args={
                ARG_VERSION_OR_FW_PATH: "2.6.0-rc.22",
            },
            no_need_live_edit=True,
        ),
    ]


def main() -> None:
    """Main function to run the firmware update script."""
    parser = argparse.ArgumentParser(
        description="Update firmware files based on version.",
    )
    parser.formatter_class = argparse.RawTextHelpFormatter
    # Fill help epilog from templates
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    parser.add_argument(
        "-v", ARG_VERSION_OR_FW_PATH, type=str, required=True, help="The firmware version (e.g., '2.5.0') or path to firmware directory"
    )
    args = parser.parse_args()

    version_or_fw_path = get_arg_value(args, ARG_VERSION_OR_FW_PATH)
    firmware_pairs = find_firmware_pairs(version_or_fw_path)
    selected_pair = select_firmware_pair(firmware_pairs)

    if selected_pair:
        version_from_path = extract_version_from_filename(selected_pair.imx_full_path.name)
        if not version_from_path:
            LOG("Could not extract version from firmware filename.")
            return
        update_firmware(selected_pair)


if __name__ == "__main__":
    main()
