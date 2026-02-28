"""Utilities for updating the Inertial Sense SDK repository."""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from dev.dev_common import *
from dev.dev_common.git_utils import BranchExistRequirement, checkout_branch, git_is_local_branch_existing, git_clone_shallow

# --- Configuration ---
INSENSE_SDK_UNPACK_DIR = INSENSE_SDK_REPO_PATH / "InsenseSDK"
LIBUSB_ZIP_SRC_PATH = Path.home() / "downloads" / "libusb-master-1-0.zip"
SDK_GITHUB_REPO = "inertialsense/inertial-sense-sdk"
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_BASE_URL = "https://github.com"
HTTP_USER_AGENT = "local-tools-sdk-updater"
NO_PROMPT: bool = False


# ─────────────────────────── Git helpers ──────────────────────────── #
# ─────────────────────────── Core SDK logic ────────────────────────── #


def extract_version_from_zip(zip_path: Path) -> Optional[str]:
    prefix = "inertial-sense-sdk-"
    # Ex: inertial-sense-sdk-2.7.0-rc.zip
    match = re.search(rf"{prefix}([\d\.]+[^\.]*?)\.zip", zip_path.name)
    if match:
        version = match.group(1)
        LOG(f"✅ Found SDK version: {version}")
        return version
    LOG(
        f"⚠️ WARNING: Could not extract version number from filename: {zip_path.name}, falling back to getting whole text after prefix: {prefix}"
    )
    match = re.search(rf"{prefix}(.+)\.zip", zip_path.name)
    if match:
        version = match.group(1)
        LOG(f"✅ Found SDK version: {version}")
        return version
    LOG(f"❌ FATAL: Could not extract version from filename: {zip_path.name}")
    return None


def extract_version_from_branch(branch_name: str) -> Optional[str]:
    match = re.search(r"(v?\d+(?:\.\d+)+[^/\\s]*)", branch_name)
    if match:
        version = match.group(1)
        if version.startswith("v") and len(version) > 1 and version[1].isdigit():
            version = version[1:]
        LOG(f"✅ Found SDK version from branch: {version}")
        return version
    LOG(f"⚠️ WARNING: Could not extract version from branch '{branch_name}', falling back to branch name.")
    return branch_name.strip() or None


def _normalize_branch_name(branch_name: str) -> str:
    safe_branch = sanitize_str_to_file_name(branch_name).replace("/", "-").replace("\\", "-").replace(" ", "-")
    safe_branch = re.sub(r"-{2,}", "-", safe_branch).strip("-")
    return safe_branch or str_to_slug(branch_name) or "sdk-branch"


def _github_ref_exists(repo: str, ref_namespace: str, ref_name: str) -> bool:
    check_url = f"{GITHUB_API_BASE_URL}/repos/{repo}/git/refs/{ref_namespace}/{ref_name}"
    LOG(f"Checking if ref '{ref_name}' exists via {check_url}")
    request = Request(check_url, headers={"Accept": "application/vnd.github+json", "User-Agent": HTTP_USER_AGENT})
    try:
        with urlopen(request, timeout=20) as response:
            return 200 <= response.status < 300
    except Exception as exc:
        LOG(f"❌ ERROR: Unexpected error while checking ref '{ref_name}': {exc}")
        return False


def _extract_filename_from_content_disposition(content_disposition: Optional[str]) -> Optional[str]:
    if not content_disposition:
        return None
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', content_disposition, re.IGNORECASE)
    if not match:
        return None
    file_name = match.group(1).strip().strip('"').strip("'")
    return file_name if file_name else None


def _download_github_archive_zip(repo: str, ref_namespace: str, ref_name: str) -> Optional[Path]:
    zip_url = f"{GITHUB_BASE_URL}/{repo}/archive/refs/{ref_namespace}/{ref_name}.zip"
    request = Request(zip_url, headers={"User-Agent": HTTP_USER_AGENT})
    download_dir = DOWNLOADS_PATH
    download_dir.mkdir(parents=True, exist_ok=True)
    fallback_name = f"inertial-sense-sdk-{_normalize_branch_name(ref_name)}.zip"
    output_path = download_dir / fallback_name
    tmp_path = output_path.with_suffix(".zip.part")
    try:
        LOG(f"⬇️ Downloading SDK archive from '{zip_url}' ...")
        with urlopen(request, timeout=120) as response:
            download_name = _extract_filename_from_content_disposition(response.headers.get("Content-Disposition"))
            if download_name:
                output_path = download_dir / download_name
                tmp_path = output_path.with_suffix(".zip.part")
            with tmp_path.open("wb") as fp:
                shutil.copyfileobj(response, fp)
        tmp_path.replace(output_path)
        LOG(f"✅ Downloaded SDK archive to '{output_path}'.")
        return output_path
    except Exception as exc:
        LOG(f"❌ ERROR: Unexpected error while downloading SDK archive: {exc}")
    if tmp_path.exists():
        tmp_path.unlink(missing_ok=True)
    return None


def unzip_to_dest(zip_path: Path, dest_dir: Path) -> bool:
    LOG(f"📦 Unzipping '{zip_path.name}' to '{dest_dir}'...")
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(dest_dir)
        LOG("   -> Unzip complete.")
        return True
    except Exception as exc:
        LOG(f"❌ ERROR: Failed to unzip '{zip_path.name}': {exc}")
        return False


def integrate_libusb(new_sdk_path: Path) -> None:
    LOG("⚙️ Integrating libusb...")
    libusb_src_dir = new_sdk_path / "src" / "libusb"
    libusb_temp_dir = libusb_src_dir / "libusb-master"

    if not LIBUSB_ZIP_SRC_PATH.exists():
        LOG(f"⚠️ WARNING: libusb zip not found at '{LIBUSB_ZIP_SRC_PATH}'. Skipping integration.")
        return

    if not unzip_to_dest(LIBUSB_ZIP_SRC_PATH, libusb_src_dir):
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
    git_stage_and_commit(INSENSE_SDK_REPO_PATH, "Integrate libusb", suppress_output=True)


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
    except Exception as exc:
        LOG(f"❌ ERROR: Failed to update top-level CMakeLists.txt: {exc}")

    git_stage_and_commit(INSENSE_SDK_REPO_PATH, "Update CMakeLists.txt files", show_diff=True, suppress_output=True)


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
    git_stage_and_commit(INSENSE_SDK_REPO_PATH, "Cleanup old SDKs", suppress_output=True)


def _path_contains_any_files(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    for item in path.rglob("*"):
        if item.is_file() or item.is_symlink():
            LOG(f"   -> Found file: {item}")
            return True
    return False


def _remove_empty_dirs(path: Path) -> bool:
    if not path.exists():
        return True
    if not path.is_dir():
        return False
    dirs = sorted((item for item in path.rglob("*") if item.is_dir()), key=lambda p: len(p.parts), reverse=True)
    for dir_path in dirs:
        try:
            dir_path.rmdir()
        except OSError:
            return False
    try:
        path.rmdir()
    except OSError:
        return False
    return True


def sdk_update_pre_setup(*, base_branch: Optional[str], sdk_dir_suffix: str,
                         target_branch_suffix: str) -> Optional[tuple[Path, str, Path, str]]:
    repo_path = INSENSE_SDK_REPO_PATH
    if not checkout_branch(repo_path, base_branch, branch_exist_requirement=BranchExistRequirement.BRANCH_MUST_EXIST, allow_empty=True, ):
        LOG(f"❌ FATAL: Failed to checkout base branch '{base_branch}'")
        return None
    INSENSE_SDK_UNPACK_DIR.mkdir(parents=True, exist_ok=True)
    new_sdk_dir_name = f"inertial-sense-sdk-{sdk_dir_suffix}"
    new_sdk_path = INSENSE_SDK_UNPACK_DIR / new_sdk_dir_name
    if new_sdk_path.exists():
        if not new_sdk_path.is_dir() or _path_contains_any_files(new_sdk_path):
            LOG(
                f"❌ FATAL: Target SDK path already exists at '{new_sdk_path}' and contains files. "
            )
            display_content_to_copy(
                f"rm -rf {new_sdk_path}", purpose="Content to clean up SDK directory before retrying",
            )
            return None
        LOG(f"⚠️ WARNING: Target SDK path already exists at '{new_sdk_path}' but contains only empty directories. Cleaning it up...")
        if not _remove_empty_dirs(new_sdk_path):
            LOG(
                f"❌ FATAL: Could not remove empty directories under '{new_sdk_path}'. "
                f"Check and delete it with command 'rm -rf {new_sdk_path}'."
            )
            return None
        LOG(f"   -> Removed empty SDK path: '{new_sdk_path}'")
    target_branch_prefix = f"update-sdk-{str_to_slug(target_branch_suffix)}"
    target_branch_name = f"{target_branch_prefix}-{str_to_slug(get_short_date_now())}"
    if git_is_local_branch_existing(repo_path, target_branch_name):
        LOG(
            f"❌ FATAL: Already having target branch {target_branch_name} -> Aborting update, check again and delete the branch if you want to retry!!")
        return None
    if not checkout_branch(repo_path, target_branch_name, branch_exist_requirement=BranchExistRequirement.BRANCH_MUST_NOT_EXIST, ):
        LOG("❌ FATAL: Could not switch/create branch -> Aborting update.")
        return None
    return repo_path, new_sdk_dir_name, new_sdk_path, target_branch_name


def _finalize_sdk_update_from_zip(*, sdk_zip_path: Path, version: str,
                                  pre_setup_result: tuple[Path, str, Path, str]) -> None:
    repo_path, new_sdk_dir_name, new_sdk_path, _ = pre_setup_result
    if not unzip_to_dest(sdk_zip_path, INSENSE_SDK_UNPACK_DIR):
        return
    git_stage_and_commit(repo_path, f"Unzip new SDK {version}", suppress_output=True)
    integrate_libusb(new_sdk_path)
    modify_sdk_cmake_files(version, new_sdk_path)
    cleanup_old_sdks(INSENSE_SDK_UNPACK_DIR, new_sdk_dir_name)
    LOG("\n🎉 SDK update process finished successfully!")
    signal_handler_stash_ref = "bca3b5c"
    apply_signal_handler(signal_handler_stash_ref, new_sdk_path)


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


def confirm_branch_action(prompt: str) -> bool:
    if NO_PROMPT:
        LOG(f"{prompt} (auto-confirmed due to --no-prompt)")
        return True
    while True:
        current_branch = get_current_git_branch()
        branch_info = f" (on branch: {current_branch})" if current_branch else ""
        is_confirmed: bool = prompt_confirmation(f"{prompt}{branch_info}")
        return is_confirmed


def _sdk_rel_path(new_sdk_path: Optional[Path]) -> Optional[str]:
    if not new_sdk_path:
        return None
    try:
        return new_sdk_path.relative_to(INSENSE_SDK_REPO_PATH).as_posix()
    except ValueError:
        LOG(
            f"⚠️ WARNING: SDK path '{new_sdk_path}' is not within repo '{INSENSE_SDK_REPO_PATH}'. Skipping path rewrite."
        )
        return None


def _build_stash_replaced_path_map(old_stash_files: list[str], new_sdk_rel_path: str) -> dict[str, str]:
    LOG(
        f"Building path replacement map for stash application. New SDK relative path: '{new_sdk_rel_path}', Target files: {old_stash_files}")
    path_map: dict[str, str] = {}
    sdk_dir_pattern = re.compile(r"(?:^|/)(inertial-sense-sdk-[^/]+)(/.*)?$")
    for old_file_path in old_stash_files:
        match = sdk_dir_pattern.search(old_file_path)
        if not match:
            continue
        suffix = match.group(2) or ""
        new_path = f"{new_sdk_rel_path}{suffix}"
        if old_file_path != new_path:
            path_map[old_file_path] = new_path
    return path_map


# replaced_path_map: dict[old_path: str, new_path: str]
def _get_rewrited_stash_patch(patch_text: str, replaced_path_map: dict[str, str]) -> str:
    # update stash patch to replace previous path with "old_path" and new path with "new_path"
    if not replaced_path_map:
        return patch_text
    rewrite_prefixes = ("diff --git ", "--- ", "+++ ", "rename from ", "rename to ", "copy from ", "copy to ")
    lines = patch_text.splitlines()
    for idx, line in enumerate(lines):
        if not line.startswith(rewrite_prefixes):
            continue
        for old_path, new_path in replaced_path_map.items():
            line = line.replace(f"a/{old_path}", f"a/{new_path}")
            line = line.replace(f"b/{old_path}", f"b/{new_path}")
            if line.startswith(("rename from ", "rename to ", "copy from ", "copy to ")):
                line = line.replace(old_path, new_path)
        lines[idx] = line
    patched = "\n".join(lines)
    if patch_text.endswith("\n"):
        patched += "\n"
    return patched


def _extract_patch_paths(patch_text: str) -> list[str]:
    paths: set[str] = set()
    for line in patch_text.splitlines():
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        for part in parts[2:4]:
            path = part[2:] if part.startswith(("a/", "b/")) else part
            if path and path != "/dev/null":
                paths.add(path)
    return sorted(paths)


def apply_signal_handler(stash_ref: str, new_sdk_path: Optional[Path] = None) -> None:
    try:
        patch_path = Path(__file__).resolve().parent / "sdk_signal_handler.patch"
        if not patch_path.exists():
            LOG(f"❌ ERROR: Patch file not found at '{patch_path}'.")
            return

        patch_text = patch_path.read_text()
        old_patch_rel_paths = _extract_patch_paths(patch_text)
        new_sdk_rel_path = _sdk_rel_path(new_sdk_path)
        path_map: dict[str, str] = {}
        rewritten_patch_rel_paths = list(old_patch_rel_paths)
        if new_sdk_rel_path and old_patch_rel_paths:
            path_map = _build_stash_replaced_path_map(old_patch_rel_paths, new_sdk_rel_path)
            if path_map:
                LOG(f"Paths to rewrite in patch: {path_map}")
                patch_text = _get_rewrited_stash_patch(patch_text, path_map)
                rewritten_patch_rel_paths = [path_map.get(path, path) for path in old_patch_rel_paths]
            else:
                LOG("⚠️ WARNING: No paths to rewrite in patch; applying as-is.")
        elif not old_patch_rel_paths:
            LOG("⚠️ WARNING: No file paths found in patch; applying as-is.")
        else:
            LOG("⚠️ WARNING: No new SDK path provided; applying patch without path rewrite.")

        LOG(f"Applying signal handler patch from '{patch_path}'...")
        res_apply = subprocess.run([CMD_GIT, "apply", "--index", "-"], input=patch_text,
                                   text=True, capture_output=True, cwd=INSENSE_SDK_REPO_PATH, )
        if res_apply.returncode != 0:
            LOG(f"Patch file: '{patch_path}'")
            rewritten_insense_patch_abs_paths = [str(INSENSE_SDK_REPO_PATH / path)
                                                 for path in rewritten_patch_rel_paths]
            LOG(
                f"❌ ERROR: Failed to automatically apply patch to 1 or more file(s): ")
            LOG(f"Patch is at: {patch_path}")
            LOG(f"File paths to apply patch: {', '.join(rewritten_insense_patch_abs_paths)}")
            return

        if not git_has_staged_changes(INSENSE_SDK_REPO_PATH):
            LOG("⚠️ WARNING: No staged changes after applying patch; skipping commit.")
            return

        subject = f"Apply signal handler patch {stash_ref}".strip()
        LOG(f"Committing with subject: {subject}")
        run_shell([CMD_GIT, "commit", "-m", subject], check_throw_exception_on_exit_code=True,
                  cwd=INSENSE_SDK_REPO_PATH)
        LOG("✅ Applied signal handler patch and committed successfully.")
    except Exception as exc:
        LOG_EXCEPTION(exc, msg=f"Failed while applying patch '{stash_ref}'", exit=False)


# ─────────────────────────── Public entry point ─────────────────────── #


def run_sdk_update_with_zip(sdk_zip_path: Path, *, no_prompt: bool = False, base_branch: Optional[str] = None) -> None:
    global NO_PROMPT
    sdk_zip_path = Path(sdk_zip_path).expanduser()
    NO_PROMPT = no_prompt

    if not sdk_zip_path.exists():
        LOG(f"❌ FATAL: SDK zip file not found at '{sdk_zip_path}'")
        return

    version = extract_version_from_zip(sdk_zip_path)
    if not version:
        return
    LOG(f"   -> Extracted version: {version}")

    pre_setup_result = sdk_update_pre_setup(base_branch=base_branch, sdk_dir_suffix=version, target_branch_suffix=version)
    if not pre_setup_result:
        return
    _finalize_sdk_update_from_zip(sdk_zip_path=sdk_zip_path, version=version, pre_setup_result=pre_setup_result)


def run_sdk_update_with_ref_or_path(branch_or_tag_name: Optional[str] = None, *, sdk_zip_path: Optional[Path] = None,
                                      no_prompt: bool = False, base_branch: Optional[str] = None) -> None:
    global NO_PROMPT
    NO_PROMPT = no_prompt
    normalized_name = (branch_or_tag_name or "").strip()
    resolved_zip_path = Path(sdk_zip_path).expanduser() if sdk_zip_path else None

    if resolved_zip_path:
        if normalized_name:
            LOG("⚠️ WARNING: Both sdk_zip_path and branch_or_tag_name provided. Prioritizing sdk_zip_path.")
        if not resolved_zip_path.exists():
            LOG(f"❌ FATAL: SDK zip file not found at '{resolved_zip_path}'")
            return
        version = extract_version_from_zip(resolved_zip_path)
        if not version:
            return
        LOG(f"   -> Extracted version: {version}")
        pre_setup_result = sdk_update_pre_setup(base_branch=base_branch, sdk_dir_suffix=version, target_branch_suffix=version)
        if not pre_setup_result:
            return
        _finalize_sdk_update_from_zip(sdk_zip_path=resolved_zip_path, version=version, pre_setup_result=pre_setup_result)
        return

    if not normalized_name:
        LOG("❌ FATAL: Missing SDK source. Provide either sdk_zip_path or branch_or_tag_name.")
        return
    LOG(f"🔎 Checking '{normalized_name}' in '{SDK_GITHUB_REPO}' (tag first, then branch)...")
    ref_namespace: Optional[str] = None
    sdk_dir_suffix = _normalize_branch_name(normalized_name)
    if _github_ref_exists(SDK_GITHUB_REPO, "tags", normalized_name):
        ref_namespace = "tags"
        LOG(f"✅ Found tag '{normalized_name}'.")
    elif _github_ref_exists(SDK_GITHUB_REPO, "heads", normalized_name):
        ref_namespace = "heads"
        LOG(f"✅ Tag not found; found branch '{normalized_name}'.")
    else:
        LOG(f"❌ FATAL: Neither tag nor branch '{normalized_name}' was found in '{SDK_GITHUB_REPO}'.")
        return

    version = extract_version_from_branch(normalized_name)
    if not version:
        return
    LOG(f"   -> Extracted version: {version}")
    pre_setup_result = sdk_update_pre_setup(base_branch=base_branch, sdk_dir_suffix=sdk_dir_suffix, target_branch_suffix=version)
    if not pre_setup_result:
        return

    downloaded_zip_path = _download_github_archive_zip(SDK_GITHUB_REPO, ref_namespace, normalized_name)
    if not downloaded_zip_path:
        return
    _finalize_sdk_update_from_zip(sdk_zip_path=downloaded_zip_path, version=version, pre_setup_result=pre_setup_result)

def run_sdk_update_with_branch_checkout(branch_name: str, *, base_branch: str, no_prompt: bool = False,
                               repo_url: str = "https://github.com/inertialsense/inertial-sense-sdk.git", ) -> None:
    global NO_PROMPT
    NO_PROMPT = no_prompt
    normalized_branch = (branch_name or "").strip()
    if not normalized_branch:
        LOG("❌ FATAL: Branch name is empty.")
        return

    version = extract_version_from_branch(normalized_branch)
    if not version:
        return
    LOG(f"   -> Extracted version: {version}")

    pre_setup_result = sdk_update_pre_setup(
        base_branch=base_branch,
        sdk_dir_suffix=_normalize_branch_name(normalized_branch),
        target_branch_suffix=version,
    )
    if not pre_setup_result:
        return
    repo_path, new_sdk_dir_name, new_sdk_path, _ = pre_setup_result

    if not git_clone_shallow(repo_url, new_sdk_path, branch_name=normalized_branch, depth=1):
        return

    # Remove .git directory from the cloned SDK to avoid nest repos
    git_dir = new_sdk_path / DOT_GIT
    if git_dir.exists():
        LOG(f"Removing {DOT_GIT} directory from {new_sdk_path}")
        shutil.rmtree(git_dir)
    git_stage_and_commit(repo_path, f"Clone new SDK {normalized_branch}", suppress_output=True)

    integrate_libusb(new_sdk_path)
    modify_sdk_cmake_files(version, new_sdk_path)
    cleanup_old_sdks(INSENSE_SDK_UNPACK_DIR, new_sdk_dir_name)

    LOG("\n🎉 SDK update process finished successfully!")
    signal_handler_stash_ref = "bca3b5c"
    apply_signal_handler(signal_handler_stash_ref, new_sdk_path)
