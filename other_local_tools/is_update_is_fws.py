#!/usr/bin/env python3

import argparse
import glob
import os
import re
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

# Define the paths and file prefixes
DOWNLOADS_DIR = Path.home() / "downloads"
DEST_DIR = Path.home() / "ow_sw_tools/packaging/opt_etc/kim_ftm_fw/"
IMX_PREFIX = "IS_IMX-5_v"
GPX_PREFIX = "IS-firmware_r"
IMX_SYMLINK = "current_imx_fw.hex"
GPX_SYMLINK = "current_gpx_fw.fpkg"

class FirmwarePair(NamedTuple):
    """A named tuple to hold a pair of firmware files."""
    imx_path: Path
    gpx_path: Path
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

    imx_files: Dict[str, Path] = {}
    gpx_files: Dict[str, Path] = {}

    # Find and match timestamps from filenames
    for f in DOWNLOADS_DIR.glob(f"*{version}*"):
        imx_match = imx_pattern.match(f.name)
        if imx_match:
            imx_files[imx_match.group('ts')] = f
            continue

        gpx_match = gpx_pattern.match(f.name)
        if gpx_match:
            gpx_files[gpx_match.group('ts')] = f

    # Create pairs where both files with a matching timestamp exist
    pairs = []
    common_timestamps = sorted(imx_files.keys() & gpx_files.keys(), reverse=True)

    for ts in common_timestamps:
        pairs.append(FirmwarePair(
            imx_path=imx_files[ts],
            gpx_path=gpx_files[ts],
            timestamp=ts
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
        print(f"✅ Found one matching firmware set: {pairs[0].timestamp}")
        return pairs[0]

    print("🔎 Found multiple firmware sets. Please choose one:")
    # Limit choice to the 3 most recent sets
    display_pairs = pairs[:3]
    for i, pair in enumerate(display_pairs):
        print(f"  [{i+1}] IMX: {pair.imx_path.name}")
        print(f"      GPX: {pair.gpx_path.name}")

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

def update_firmware(pair: FirmwarePair) -> None:
    """
    Updates the firmware files and symlinks in the destination directory.

    Args:
        pair: The firmware pair to use for the update.
    """
    print(f"\n🚀 Starting firmware update process in: {DEST_DIR}")
    os.chdir(DEST_DIR)

    # Store old symlink targets
    old_imx_target = Path(os.readlink(IMX_SYMLINK)) if os.path.islink(IMX_SYMLINK) else None
    old_gpx_target = Path(os.readlink(GPX_SYMLINK)) if os.path.islink(GPX_SYMLINK) else None

    # Copy new files
    print(f"Copying {pair.imx_path.name}...")
    new_imx_path = Path(pair.imx_path.name)
    new_imx_path.write_bytes(pair.imx_path.read_bytes())
    
    print(f"Copying {pair.gpx_path.name}...")
    new_gpx_path = Path(pair.gpx_path.name)
    new_gpx_path.write_bytes(pair.gpx_path.read_bytes())

    # Set permissions and update symlinks
    new_imx_path.chmod(0o755)
    Path(IMX_SYMLINK).unlink(missing_ok=True)
    Path(IMX_SYMLINK).symlink_to(new_imx_path)

    new_gpx_path.chmod(0o755)
    Path(GPX_SYMLINK).unlink(missing_ok=True)
    Path(GPX_SYMLINK).symlink_to(new_gpx_path)
    
    print("\n✅ Symlinks updated successfully:")
    os.system(f"ls -l {IMX_SYMLINK} {GPX_SYMLINK}")

    # Ask to remove old files
    if old_imx_target and old_gpx_target:
        print("\nOld firmware files were:")
        print(f"  IMX: {old_imx_target.name}")
        print(f"  GPX: {old_gpx_target.name}")
        
        try:
            confirm = input("\nRemove old firmware files? [y/N]: ")
            if confirm.lower() == 'y':
                if old_imx_target.exists():
                    old_imx_target.unlink()
                    print(f"Removed: {old_imx_target.name}")
                if old_gpx_target.exists():
                    old_gpx_target.unlink()
                    print(f"Removed: {old_gpx_target.name}")
        except Exception as e:
            print(f"Error during cleanup: {e}")


def main() -> None:
    """Main function to run the firmware update script."""
    parser = argparse.ArgumentParser(
        description="Update firmware files based on version."
    )
    parser.add_argument(
        "version",
        type=str,
        help="The firmware version to find and update (e.g., '2.5.0')."
    )
    args = parser.parse_args()

    firmware_pairs = find_firmware_pairs(args.version)
    selected_pair = select_firmware_pair(firmware_pairs)

    if selected_pair:
        update_firmware(selected_pair)

if __name__ == "__main__":
    main()