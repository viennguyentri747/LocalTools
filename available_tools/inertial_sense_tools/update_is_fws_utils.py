"""Utilities for updating Inertial Sense firmware packages within OW SW repo."""

from __future__ import annotations

import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

from dev.dev_common import *
from dev.dev_common.git_utils import (
    BranchExistRequirement,
    checkout_branch,
    git_is_local_branch_existing,
    git_stage_and_commit,
)

# Define the paths and file prefixes
IMX_PREFIX = "IS_IMX-5_v"
GPX_PREFIX = "IS-firmware_r"
IMX_EXTENSION = ".hex"
GPX_EXTENSION = ".fpkg"
IMX_SYMLINK = f"current_imx_fw{IMX_EXTENSION}"
GPX_SYMLINK = f"current_gpx_fw{GPX_EXTENSION}"

# Module-level flag to control prompting (aligned with SDK utils)
NO_PROMPT: bool = False


class KimFwSet(NamedTuple):
    """A named tuple to hold a pair of firmware files."""
    imx_full_path: Optional[Path]
    gpx_full_path: Optional[Path]
    version: str
    rcvr_version: Optional[str]


# ─────────────────────────── Core firmware logic ───────────────────── #


def _extract_rcvr_version_from_entries(entries: List[str]) -> Optional[str]:
    LOG(f"🔎 Extracting receiver version from .fpkg entries. Available entries: {entries}")
    for entry in sorted(entries):
        name = Path(entry).name
        if name.endswith(".fpk") and not name.endswith(".efpk"):
            # Match pattern: _v{VERSION}_{anything}.fpk. Ex input = "cxd5610_v0.213_ISv3.0_app.fpk"
            # Captures everything between _v and the last underscore before .fpk
            match = re.search(r"_(v[^_]+(?:_[^_]+)*)_app.fpk$", name)
            if match:
                LOG(f"🔢 Extracted receiver version: {match.group(1)}")
                return match.group(1)
            else:
                LOG("⚠️ WARNING: Could not extract receiver version from .fpkg name.")
    return None


def _extract_fpkg_data(fpkg_path: Path, *, extract_imx: bool = True) -> Tuple[Optional[Path], Optional[str]]:
    """Extract IMX .hex (if present) and receiver version from a .fpkg."""
    if extract_imx:
        LOG(f"🔎 Checking for IMX .hex inside: {fpkg_path}")
    try:
        with zipfile.ZipFile(fpkg_path, "r") as zip_ref:
            entries = zip_ref.namelist()
            rcvr_version = _extract_rcvr_version_from_entries(entries)
            if not extract_imx:
                return None, rcvr_version
            hex_entries = [name for name in entries if name.lower().endswith(IMX_EXTENSION)]
            if not hex_entries:
                LOG("⚠️ WARNING: No IMX .hex found inside fpkg.")
                return None, rcvr_version

            imx_entries = [name for name in hex_entries if Path(name).name.startswith(IMX_PREFIX)]
            selected_entry = sorted(imx_entries or hex_entries)[0]

            temp_dir = Path(TEMP_PATH)
            temp_dir.mkdir(parents=True, exist_ok=True)
            target_imx_path = temp_dir / Path(selected_entry).name
            LOG(f"📦 Extracting IMX firmware from fpkg: {selected_entry} -> {target_imx_path}")
            with zip_ref.open(selected_entry) as src, target_imx_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            target_imx_path.chmod(0o755)
            return target_imx_path, rcvr_version
    except Exception as exc:
        LOG(f"⚠️ WARNING: Failed to extract IMX firmware from fpkg: {exc}")
    return None, None


def find_fpkg_entry_name(fpkg_path: Path, pattern: str) -> Optional[str]:
    """Return the first entry name in an fpkg that matches the pattern."""
    try:
        with zipfile.ZipFile(fpkg_path, "r") as zip_ref:
            for entry in zip_ref.namelist():
                if re.search(pattern, entry):
                    return entry
    except Exception as exc:
        LOG(f"⚠️ WARNING: Failed to read fpkg entries from {fpkg_path}: {exc}")
    return None


def extract_version_from_filename(filename: str) -> Optional[str]:
    match = re.search(r"(\d+\.\d+\.\d+[^+]*)", filename)
    return match.group(1) if match else None


def extract_version_from_fpkg(fpkg_path: Path) -> Optional[str]:
    """Extract firmware version from fpkg entries (prefer GPX)."""
    entry = find_fpkg_entry_name(fpkg_path, r"IS_GPX-.*\.encrypted\.bin$")
    if not entry:
        entry = find_fpkg_entry_name(fpkg_path, r"IS_GPX-.*\.bin$")
    return extract_version_from_filename(entry) if entry else None


def get_fw_pair(fpkg_fw_path: str, *, fpkg_only: bool = False) -> Optional[KimFwSet]:
    """Locate a firmware pair based on an explicit fpkg path."""
    input_path = Path(fpkg_fw_path).expanduser()
    if input_path.suffix != GPX_EXTENSION or not input_path.is_file():
        LOG(f"❌ FATAL: Firmware update requires a .fpkg file path. Got: {fpkg_fw_path}")
        return None

    gpx_path = input_path
    gpx_version = extract_version_from_fpkg(gpx_path)
    if not gpx_version:
        fallback_version = extract_version_from_filename(gpx_path.name)
        if fallback_version:
            LOG(f"⚠️ WARNING: Falling back to version from fpkg filename: {fallback_version}")
            gpx_version = fallback_version
    if not gpx_version:
        LOG(f"❌ FATAL: Could not determine version from fpkg: {gpx_path} -> Returning None.")
        return None

    imx_from_fpkg, rcvr_version = _extract_fpkg_data(gpx_path, extract_imx=not fpkg_only)
    return KimFwSet(
        imx_full_path=imx_from_fpkg,
        gpx_full_path=gpx_path,
        version=gpx_version or "",
        rcvr_version=rcvr_version,
    )


def extract_timestamp_from_fw_filename(filename: str) -> Optional[str]:
    match = re.search(r"\+([\d-]+)", filename)
    return match.group(1) if match else None


def update_firmwares(fw_set: KimFwSet) -> None:
    LOG(f"\n🚀 Starting firmware update process in: {OW_SW_KIM_FTM_FW_PATH}")
    os.chdir(OW_SW_KIM_FTM_FW_PATH)

    def copy_firmware(src_path: Optional[Path], symlink: str) -> str:
        if not src_path:
            return ""
        new_path = Path(src_path.name)
        LOG(f"Copying from {src_path} to {OW_SW_KIM_FTM_FW_PATH / new_path}")
        new_path.write_bytes(src_path.read_bytes())
        new_path.chmod(0o755)
        Path(symlink).unlink(missing_ok=True)
        Path(symlink).symlink_to(new_path)
        return new_path.name

    new_imx_name = copy_firmware(fw_set.imx_full_path, IMX_SYMLINK)
    new_gpx_name = copy_firmware(fw_set.gpx_full_path, GPX_SYMLINK)

    LOG("\n✅ Seeds updated successfully:")
    symlinks_to_list = []
    if fw_set.imx_full_path:
        symlinks_to_list.append(IMX_SYMLINK)
    if fw_set.gpx_full_path:
        symlinks_to_list.append(GPX_SYMLINK)
    os.system(f"ls -l {' '.join(symlinks_to_list)}")

    LOG("\n🧹 Scanning for OLD firmwares files to remove...")
    # Only remove imx if there is new_imx, only remove gpx if there is new_gpx
    redundant_paths: List[Path] = [
        path
        for path in OW_SW_KIM_FTM_FW_PATH.iterdir()
        if (
            (path.name.startswith(IMX_PREFIX) and new_imx_name and path.name != new_imx_name)
            or (path.name.startswith(GPX_PREFIX) and new_gpx_name and path.name != new_gpx_name)
        )
    ]

    if redundant_paths:
        LOG("Found OLD firmware file(s) to remove:")
        for f in redundant_paths:
            LOG(f"  - {f.name}")

        try:
            # Cleanup old FW files
            for f in redundant_paths:
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

    LOG("Change receiver version interactively:")
    detected_rcvr_version = fw_set.rcvr_version or "N/A"
    # current_rcvr_display = current_rcvr_version or "N/A"
    prompt_msg = (
        "Edit or press Enter to use current RCVR version "
        f"(Detected = {detected_rcvr_version}):"
    )
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

    git_stage_and_commit(OW_SW_PATH, f"Update firmware to version {fw_set.version}", stage_paths=[
                         rel_fw_dir, rel_rcvr_file], auto_confirm=NO_PROMPT, )


def run_fw_update(fpkg_fw_path: str, *, no_prompt: bool = False, base_branch: Optional[str] = None, fpkg_only: bool = False) -> None:
    global NO_PROMPT
    NO_PROMPT = no_prompt

    repo_path = OW_SW_PATH
    staged_files = git_get_staged_files(repo_path)
    if staged_files:
        LOG_EXCEPTION_STR(f"Staging area already contains files. Staged before add: {', '.join(staged_files)}")

    if not checkout_branch(repo_path, base_branch, branch_exist_requirement=BranchExistRequirement.BRANCH_MUST_EXIST, allow_empty=True, ):
        LOG_EXCEPTION_STR(f"❌ FATAL: Failed to checkout base branch '{base_branch}'")

    pair = get_fw_pair(fpkg_fw_path, fpkg_only=fpkg_only)
    if not pair:
        LOG_EXCEPTION_STR("❌ FATAL: Failed to build firmware set -> Aborting update.")
    if not fpkg_only and pair.imx_full_path is None:
        LOG_EXCEPTION_STR("❌ FATAL: No firmware pair available (no IMX) -> Aborting update.")

    version = pair.version or extract_version_from_fpkg(pair.gpx_full_path)
    if not version:
        LOG_EXCEPTION_STR(f"❌ FATAL: Could not extract version from firmware set: {pair} -> Aborting update.")
    if version != pair.version:
        pair = pair._replace(version=version)

    branch_prefix = f"update-fw-{str_to_slug(version)}"
    target_branch_name = f"{branch_prefix}-{str_to_slug(get_short_date_now())}"
    if git_is_local_branch_existing(repo_path, target_branch_name):
        LOG_EXCEPTION_STR(
            f"❌ FATAL: Already having target branch {target_branch_name} -> Aborting update, check again and delete the branch if you want to retry!!")

    LOG(f"🔀 Creating and switching to branch {target_branch_name}...")
    if not checkout_branch(repo_path, target_branch_name, branch_exist_requirement=BranchExistRequirement.BRANCH_MUST_NOT_EXIST, ):
        LOG("❌ FATAL: Could not switch/create branch -> Aborting update.")
        return

    update_firmwares(pair)
