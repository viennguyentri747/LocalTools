#!/usr/bin/env python3.10

import argparse
import glob
import os
import re
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional
from dev_common import *

# Define the paths and file prefixes
DOWNLOADS_DIR = Path.home() / "downloads"
OW_SW_TOOLS_DIR = Path.home() / "ow_sw_tools"
DEST_DIR = OW_SW_TOOLS_DIR / "packaging/opt_etc/kim_ftm_fw/"
IMX_PREFIX = "IS_IMX-5_v"
GPX_PREFIX = "IS-firmware_r"
IMX_SYMLINK = "current_imx_fw.hex"
GPX_SYMLINK = "current_gpx_fw.fpkg"


class FirmwarePair(NamedTuple):
    """A named tuple to hold a pair of firmware files."""
    imx_full_path: Path
    gpx_full_path: Path
    timestamp: str


def find_firmware_pairs(version: str) -> List[FirmwarePair]:
    """
    Scans the downloads directory to find matching pairs of IMX and GPX
    firmware files for the given version.

    Args:
        version: The firmware version string (e.g., "2.5.0").

    Returns:
        A list of FirmwarePair objects, sorted from newest to oldest.
    """
    imx_pattern = re.compile(rf"{re.escape(IMX_PREFIX)}{re.escape(version)}\+(?P<ts>[\d-]+)\.hex")
    gpx_pattern = re.compile(rf"{re.escape(GPX_PREFIX)}{re.escape(version)}\+(?P<ts>[\d-]+)\.fpkg")

    imx_candidates: List[tuple[str, Path]] = []
    gpx_candidates: List[tuple[str, Path]] = []

    # Find and extract timestamps from filenames
    for file_path in DOWNLOADS_DIR.glob(f"*{version}*"):
        imx_match = imx_pattern.match(file_path.name)
        if imx_match:
            imx_candidates.append((imx_match.group('ts'), file_path))
            continue

        gpx_match = gpx_pattern.match(file_path.name)
        if gpx_match:
            gpx_candidates.append((gpx_match.group('ts'), file_path))

    # Sort candidates by timestamp in reverse (newest to oldest)
    imx_candidates.sort(key=lambda x: x[0], reverse=True)
    gpx_candidates.sort(key=lambda x: x[0], reverse=True)

    # Create pairs by matching the sorted lists
    pairs = []
    min_len = min(len(imx_candidates), len(gpx_candidates))

    for i in range(min_len):
        imx_ts, imx_path = imx_candidates[i]
        gpx_ts, gpx_path = gpx_candidates[i]
        pairs.append(FirmwarePair(
            imx_full_path=imx_path,
            gpx_full_path=gpx_path,
            timestamp=imx_ts  # Using IMX timestamp as the primary for the pair
        ))

    return pairs


def select_firmware_pair(pairs: List[FirmwarePair]) -> Optional[FirmwarePair]:
    """
    Prompts the user to select a firmware pair if multiple are found.

    Args:
        pairs: A list of available firmware pairs.

    Returns:
        The selected FirmwarePair, or None if no selection is made.
    """
    if not pairs:
        print("❌ Error: No matching firmware file sets found.")
        return None

    if len(pairs) == 1:
        print(f"✅ Found one matching firmware set: {pairs[0].imx_full_path.name}, {pairs[0].gpx_full_path.name}")
        return pairs[0]

    print("🔎 Found multiple firmware sets. Please choose one:")
    # Limit choice to the 3 most recent sets
    display_pairs = pairs[:3]
    for i, pair in enumerate(display_pairs):
        print(f"  [{i+1}] IMX: {pair.imx_full_path.name}")
        print(f"      GPX: {pair.gpx_full_path.name}")

    while True:
        try:
            choice = input(f"Enter your choice (1-{len(display_pairs)}): ")
            choice_index = int(choice) - 1
            if 0 <= choice_index < len(display_pairs):
                return display_pairs[choice_index]
            else:
                print("Invalid choice. Please try again.")
        except (ValueError, IndexError):
            print("Invalid input. Please enter a number from the list.")


def update_firmware(pair: FirmwarePair, version: str) -> None:
    """
    Updates the firmware files and symlinks in the destination directory.

    Args:
        pair: The firmware pair to use for the update.
    """
    print(f"\n🚀 Starting firmware update process in: {DEST_DIR}")
    os.chdir(DEST_DIR)  # Change to the destination directory

    # Copy new files
    new_imx_path = Path(pair.imx_full_path.name)
    print(f"Copying from {pair.imx_full_path} to {DEST_DIR/new_imx_path}")
    new_imx_path.write_bytes(pair.imx_full_path.read_bytes())

    new_gpx_path = Path(pair.gpx_full_path.name)
    print(f"Copying from {pair.gpx_full_path} to {DEST_DIR/new_gpx_path}")
    new_gpx_path.write_bytes(pair.gpx_full_path.read_bytes())

    # Set permissions and update symlinks
    new_imx_path.chmod(0o755)
    Path(IMX_SYMLINK).unlink(missing_ok=True)
    Path(IMX_SYMLINK).symlink_to(new_imx_path)

    new_gpx_path.chmod(0o755)
    Path(GPX_SYMLINK).unlink(missing_ok=True)
    Path(GPX_SYMLINK).symlink_to(new_gpx_path)

    print("\n✅ Symlinks updated successfully:")
    os.system(f"ls -l {IMX_SYMLINK} {GPX_SYMLINK}")

    # 🔧 Extra cleanup of OLD matching files in kim_ftm_fw
    print("\n🧹 Scanning for extra firmware files to remove...")

    extra_files = [
        f for f in DEST_DIR.iterdir()
        if (
            (f.name.startswith(IMX_PREFIX) or f.name.startswith(GPX_PREFIX))
            and f.name not in {new_imx_path.name, new_gpx_path.name}
        )
    ]

    if extra_files:
        print("Found extra firmware files:")
        for f in extra_files:
            print(f"  - {f.name}")
        try:
            is_ok = prompt_confirmation("Do you want to remove these extra files?")
            if is_ok.lower() == 'y':
                for f in extra_files:
                    try:
                        f.unlink()
                        print(f"Removed: {f.name}")
                    except Exception as e:
                        print(f"Failed to remove {f.name}: {e}")
        except Exception as e:
            print(f"Error during extra cleanup: {e}")
    else:
        print("✅ No extra matching firmware files found.")

    print(
        f"\n✅ Firmware update complete! Update change with command below:\ncd {OW_SW_TOOLS_DIR} && git stage {DEST_DIR} && git commit -m 'Firmware update to {version}'")


def main() -> None:
    """Main function to run the firmware update script."""
    parser = argparse.ArgumentParser(
        description="Update firmware files based on version."
    )
    parser.formatter_class = argparse.RawTextHelpFormatter
    parser.epilog = """Examples:

# Example 1
#KIM RELEASE (insense_sdk)
~/local_tools/inertial_sense_tools/is_update_is_sdk.py -p ~/downloads/inertial-sense-sdk-2.5.1.zip
#KIM FW (oneweb_project_sw_tools)
~/local_tools/inertial_sense_tools/is_update_is_fws.py
"""
    parser.add_argument(
        "-v", "--version", type=str, required=True, help="The firmware version to find and update (e.g., '2.5.0')."
    )
    args = parser.parse_args()

    version = args.version
    firmware_pairs = find_firmware_pairs(version)
    selected_pair = select_firmware_pair(firmware_pairs)

    if selected_pair:
        update_firmware(selected_pair, version)


if __name__ == "__main__":
    main()
