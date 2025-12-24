"""Utilities for updating Inertial Sense firmware packages within OW SW repo."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, NamedTuple, Optional

from dev.dev_common import *
from dev.dev_common.git_utils import checkout_branch, git_stage_and_commit

# Define the paths and file prefixes
IMX_PREFIX = "IS_IMX-5_v"
GPX_PREFIX = "IS-firmware_r"
IMX_EXTENSION = ".hex"
GPX_EXTENSION = ".fpkg"
IMX_SYMLINK = f"current_imx_fw{IMX_EXTENSION}"
GPX_SYMLINK = f"current_gpx_fw{GPX_EXTENSION}"

# Module-level flag to control prompting (aligned with SDK utils)
NO_PROMPT: bool = False


class FirmwarePair(NamedTuple):
    """A named tuple to hold a pair of firmware files."""

    imx_full_path: Path
    gpx_full_path: Path
    timestamp: str
    version: str


# ─────────────────────────── Core firmware logic ───────────────────── #


def find_firmware_pairs_recursively(version_or_fw_path: str) -> List[FirmwarePair]:
    """Locate firmware pairs based on an explicit path or version string."""
    input_path = Path(version_or_fw_path)
    final_version_pattern: Optional[str] = None
    search_dir = DOWNLOADS_PATH

    file_name: Optional[str] = None
    if (
        (input_path.name.startswith(IMX_PREFIX) or input_path.suffix == IMX_EXTENSION)
        or (input_path.suffix == IMX_EXTENSION or input_path.name.startswith(GPX_PREFIX))
        or input_path.suffix == GPX_EXTENSION
    ):
        if input_path.is_file():
            search_dir = input_path.parent.expanduser()
            file_name = input_path.name
        elif version_or_fw_path.startswith(IMX_PREFIX) or version_or_fw_path.startswith(GPX_PREFIX):
            file_name = version_or_fw_path
        if file_name:
            file_version_pattern = r"(\d+\.\d+\.\d+[^+]*)"
            version_match = re.search(file_version_pattern, version_or_fw_path)
            if version_match:
                final_version_pattern = re.escape(version_match.group(1))
    else:
        final_version_pattern = re.escape(version_or_fw_path)

    if final_version_pattern is None:
        LOG(f"❌ FATAL: Could not determine version pattern from input: {version_or_fw_path}")
        return []

    LOG(f"🔎 Using version pattern: {final_version_pattern}, search dir {search_dir}")
    imx_pattern = re.compile(
        rf"{re.escape(IMX_PREFIX)}(?P<version>{final_version_pattern})\+(?P<ts>[\d-]+){re.escape(IMX_EXTENSION)}"
    )
    gpx_pattern = re.compile(
        rf"{re.escape(GPX_PREFIX)}(?P<version>{final_version_pattern})\+(?P<ts>[\d-]+){re.escape(GPX_EXTENSION)}"
    )

    imx_candidates: List[tuple[str, str, Path]] = []
    gpx_candidates: List[tuple[str, str, Path]] = []

    for file_path in search_dir.rglob("*"):
        imx_match = imx_pattern.match(file_path.name)
        if imx_match:
            LOG(f"Found IMX firmware file: {file_path}")
            imx_candidates.append((imx_match.group("version"), imx_match.group("ts"), file_path))
            continue

        gpx_match = gpx_pattern.match(file_path.name)
        if gpx_match:
            LOG(f"Found GPX firmware file: {file_path}")
            gpx_candidates.append((gpx_match.group("version"), gpx_match.group("ts"), file_path))

    imx_candidates.sort(key=lambda x: x[1], reverse=True)
    gpx_candidates.sort(key=lambda x: x[1], reverse=True)

    firmware_pairs: List[FirmwarePair] = []
    matched_gpx_set: set[Path] = set()

    for imx_version, imx_timestamp, imx_path in imx_candidates:
        for gpx_version, gpx_timestamp, gpx_path in gpx_candidates:
            if imx_version == gpx_version and gpx_path not in matched_gpx_set:
                firmware_pairs.append(
                    FirmwarePair(
                        imx_full_path=imx_path,
                        gpx_full_path=gpx_path,
                        timestamp=imx_timestamp,
                        version=imx_version,
                    )
                )
                matched_gpx_set.add(gpx_path)
                break
    return firmware_pairs


def extract_version_from_filename(filename: str) -> Optional[str]:
    match = re.search(r"(\d+\.\d+\.\d+)", filename)
    return match.group(1) if match else None


def select_firmware_pair(pairs: List[FirmwarePair]) -> Optional[FirmwarePair]:
    if not pairs:
        LOG("❌ Error: No matching firmware file sets found.")
        return None

    # Auto-select latest by timestamp if no_prompt is set
    if NO_PROMPT:
        best = sorted(pairs, key=lambda p: p.timestamp, reverse=True)[0]
        LOG(f"✅ Auto-selected firmware set: {best.imx_full_path.name}, {best.gpx_full_path.name} (--no_prompt)")
        return best

    if len(pairs) == 1:
        LOG(
            f"✅ Found one matching firmware set: {pairs[0].imx_full_path.name}, {pairs[0].gpx_full_path.name}"
        )
        return pairs[0]

    LOG("🔎 Found multiple firmware sets. Please choose one:")
    display_pairs = pairs[:3]

    for i, pair in enumerate(display_pairs):
        LOG(f"  [{i + 1}] IMX: {pair.imx_full_path.name}")
        LOG(f"     GPX: {pair.gpx_full_path.name}")

    options = [str(i + 1) for i in range(len(display_pairs))]
    while True:
        choice_str = prompt_input_with_options(
            f"Enter your choice (1-{len(display_pairs)})",
            options=options,
            default_input="1",
        )
        if choice_str is None:
            LOG("Input cancelled. Defaulting to option 1.")
            return display_pairs[0]
        try:
            choice_index = int(choice_str) - 1
            if 0 <= choice_index < len(display_pairs):
                return display_pairs[choice_index]
            LOG("Invalid choice. Please try again.")
        except (ValueError, IndexError):
            LOG("Invalid input. Please enter a number from the list.")


def update_firmware(pair: FirmwarePair) -> None:
    LOG(f"\n🚀 Starting firmware update process in: {OW_SW_KIM_FTM_FW_PATH}")
    os.chdir(OW_SW_KIM_FTM_FW_PATH)

    new_imx_path = Path(pair.imx_full_path.name)
    LOG(f"Copying from {pair.imx_full_path} to {OW_SW_KIM_FTM_FW_PATH / new_imx_path}")
    new_imx_path.write_bytes(pair.imx_full_path.read_bytes())

    new_gpx_path = Path(pair.gpx_full_path.name)
    LOG(f"Copying from {pair.gpx_full_path} to {OW_SW_KIM_FTM_FW_PATH / new_gpx_path}")
    new_gpx_path.write_bytes(pair.gpx_full_path.read_bytes())

    new_imx_path.chmod(0o755)
    Path(IMX_SYMLINK).unlink(missing_ok=True)
    Path(IMX_SYMLINK).symlink_to(new_imx_path)

    new_gpx_path.chmod(0o755)
    Path(GPX_SYMLINK).unlink(missing_ok=True)
    Path(GPX_SYMLINK).symlink_to(new_gpx_path)

    LOG("\n✅ Seeds updated successfully:")
    os.system(f"ls -l {IMX_SYMLINK} {GPX_SYMLINK}")

    LOG("\n🧹 Scanning for OLD firmware files to remove...")
    extra_files = [
        f
        for f in OW_SW_KIM_FTM_FW_PATH.iterdir()
        if (f.name.startswith(IMX_PREFIX) or f.name.startswith(GPX_PREFIX))
        and f.name not in {new_imx_path.name, new_gpx_path.name}
    ]

    if extra_files:
        LOG("Found OLD firmware files:")
        for f in extra_files:
            LOG(f"  - {f.name}")

        try:
            is_ok = True if NO_PROMPT else prompt_confirmation("Do you want to remove these old firmware files?")
            if is_ok:
                for f in extra_files:
                    try:
                        f.unlink()
                        LOG(f"Removed: {f.name}")
                    except Exception as exc:
                        LOG(f"Failed to remove {f.name}: {exc}")
        except Exception as exc:
            LOG(f"Error during extra cleanup: {exc}")
    else:
        LOG("✅ No extra matching firmware files found.")

    LOG("\n✅ Firmware update complete!")

    LOG(LINE_SEPARATOR)
    # Interactive receiver version update and commit
    current_rcvr_version = ""
    try:
        if OW_SW_KIM_RCVR_VERSION_FILE_PATH.exists():
            current_rcvr_version = OW_SW_KIM_RCVR_VERSION_FILE_PATH.read_text(encoding="utf-8").strip()
    except Exception as exc:
        LOG(f"⚠️ WARNING: Failed to read current receiver version: {exc}")

    # if NO_PROMPT:
    #     LOG("Skipping interactive receiver version update due to --no_prompt.")
    # else:
    # ALWAYS PROMPT for this
    LOG("Change receiver version interactively:")
    prompt_msg = "Edit or press Enter to use current RCVR version:"
    user_input_opt = prompt_input(prompt_msg, default_input=current_rcvr_version)
    user_input = (user_input_opt or "").strip()

    new_rcvr_version = user_input if user_input else current_rcvr_version
    if new_rcvr_version != current_rcvr_version:
        try:
            OW_SW_KIM_RCVR_VERSION_FILE_PATH.write_text(new_rcvr_version + "\n", encoding="utf-8")
            LOG(f"Version updated to {new_rcvr_version}!")
        except Exception as exc:
            LOG(f"❌ ERROR: Failed to write receiver version file: {exc}")

    # Stage and commit changes in OW_SW_PATH
    try:
        rel_fw_dir = str(OW_SW_KIM_FTM_FW_PATH.relative_to(OW_SW_PATH))
        rel_rcvr_file = str(OW_SW_KIM_RCVR_VERSION_FILE_PATH.relative_to(OW_SW_PATH))
    except Exception:
        # Fallback to absolute paths if relative computation fails
        rel_fw_dir = str(OW_SW_KIM_FTM_FW_PATH)
        rel_rcvr_file = str(OW_SW_KIM_RCVR_VERSION_FILE_PATH)

    git_stage_and_commit(
        OW_SW_PATH,
        f"Update firmware to version {pair.version}",
        stage_paths=[rel_fw_dir, rel_rcvr_file],
        auto_confirm=NO_PROMPT,
    )


def run_fw_update(version_or_fw_path: str, *, no_prompt: bool = False) -> None:
    global NO_PROMPT
    NO_PROMPT = no_prompt
    firmware_pairs = find_firmware_pairs_recursively(version_or_fw_path)
    selected_pair = select_firmware_pair(firmware_pairs)

    if not selected_pair:
        return

    version = selected_pair.version or extract_version_from_filename(selected_pair.imx_full_path.name)
    if not version:
        LOG("Could not extract version from firmware filename.")
        return

    branch_name = f"update-fw-{str_to_slug(version)}-{str_to_slug(get_short_date_now())}"
    if not checkout_branch(OW_SW_PATH, branch_name):
        return
    update_firmware(selected_pair)
