#!/usr/bin/env python3
"""
OneWeb SW-Tools interactive local build helper (top-down, manifest-aware).
"""
import datetime
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Union
import argparse
from gitlab_helper import get_latest_successful_pipeline_id, download_job_artifacts, get_gl_project, read_token_from_file
from utils import get_file_md5sum, LOG, is_diff_ignore_eol, run_shell
from constants import *
import yaml
# ─────────────────────────────  constants  ───────────────────────────── #

CORE_REPOS_FOLDER_PATH = Path.home() / "workspace" / "intellian_core_repos/"
OW_SW_PATH = Path.home() / "ow_sw_tools/"
OUTPUT_IESA_PATH = OW_SW_PATH / "install_iesa_tarball.iesa"
# OW_SW_PATH = CORE_REPOS_PATH / "ow_sw_tools"
BUILD_FOLDER_PATH = OW_SW_PATH / "tmp_build/"
SCRIPT_FOLDER_PATH = Path.home() / "local_tools/"
CREDENTIAL_FILE_PATH = SCRIPT_FOLDER_PATH / ".gitlab_credentials"
GITLAB_CI_YML_PATH = OW_SW_PATH / ".gitlab-ci.yml"
MANIFEST_FILE_NAME = "iesa_manifest_gitlab.xml"
MANIFEST_RELATIVE_PATH = f"tools/manifests/{MANIFEST_FILE_NAME}"
MANIFEST_FILE_PATH = OW_SW_PATH / MANIFEST_RELATIVE_PATH
# OW_LOCAL_BUILD_OUTPUT_DIR = SCRIPT_FOLDER_PATH / "local_build_output"
# Need to put this here because we will go into docker environment from OW_SW_PATH
BSP_ARTIFACT_FOLDER_PATH = OW_SW_PATH / "custom_artifacts_bsp/"
BSP_ARTIFACT_PREFIX = "bsp-iesa-"
BSP_SYMLINK_PATH_FOR_BUILD = OW_SW_PATH / "packaging" / "bsp_current" / "bsp_current.tar.xz"
MAIN_STEP_LOG_PREFIX = f"{LINE_SEPARATOR}\n[MAIN_STEP]"
# ─────────────────────────────  top-level  ───────────────────────────── #


def main() -> None:
    parser = argparse.ArgumentParser(description="OneWeb SW-Tools local build helper.")
    parser.add_argument("--build_type", choices=[BUILD_TYPE_BINARY, BUILD_TYPE_IESA], type=str, default=BUILD_TYPE_BINARY,
                        help="Build type (binary or iesa). Defaults to binary.")
    parser.add_argument("--manifest_source", choices=[MANIFEST_SOURCE_LOCAL, MANIFEST_SOURCE_REMOTE], default="local",
                        help=F"Source for the manifest repository URL ({MANIFEST_SOURCE_LOCAL} or {MANIFEST_SOURCE_REMOTE}). Defaults to {MANIFEST_SOURCE_LOCAL}. Note that although it is local manifest, the source of sync is still remote so will need to push branch of dependent local repos specified in local manifest (not ow_sw_tools).")
    parser.add_argument("-b", "--ow_manifest_branch", type=Optional[str], default=None,
                        help="Branch of oneweb_project_sw_tools for manifest (either local or remote branch, depend on --manifest_source). Ex: 'manpack_master'")
    # parser.add_argument("--check_manifest_branch", type=lambda x: x.lower() == 'true', default=True,
    #                     help="Check if OW_SW_PATH branch matches manifest branch (true or false). Defaults to true.")  # Only set this to FALSE if you know what you're doing
    parser.add_argument("--tisdk_ref", type=str, default=None,
                        help="TISDK Ref for BSP (for creating .iesa). Ex: 'manpack_master'")
    parser.add_argument("--overwrite_repos", nargs='*', default=[],
                        help="List of repository names to overwrite from local")
    parser.add_argument("-i", "--interactive", type=lambda x: x.lower() == 'true', default=False,
                        help="Run in interactive mode (true or false). Defaults to false.")
    parser.add_argument("--force_reset_tmp_build", type=lambda x: x.lower() == 'true', default=False,
                        help="Force clearing tmp_build folder (true or false). Defaults to false.")
    parser.add_argument("--sync", type=lambda x: x.lower() == 'true', default=True,
                        help="If true, perform tmp_build reset (true or false) and repo sync. Defaults to true.")
    parser.add_argument("--use_current_ow_branch", type=lambda x: x.lower() == 'true', default=False,
                        help="Use the current branch of ow_sw_tools repo. Defaults to false.")
    args = parser.parse_args()
    LOG(
        textwrap.dedent(
            """\
            -------------------------------
            OneWeb local build orchestrator
            -------------------------------"""
        )
    )
    build_type: str = args.build_type
    # is_overwrite_local_repos: bool = args.is_overwrite_local_repos
    manifest_source: str = args.manifest_source
    tisdk_ref: Optional[str] = args.tisdk_ref
    overwrite_repos: List[str] = args.overwrite_repos
    force_reset_tmp_build: bool = args.force_reset_tmp_build
    sync: bool = args.sync
    use_current_ow_branch: bool = args.use_current_ow_branch
    # Update overwrite repos no git suffix
    overwrite_repos = [get_path_no_git_suffix(r) for r in overwrite_repos]
    LOG(f"Parsed args: {args}")

    # LOG(f"CD to {OW_SW_PATH}")
    # os.chdir(OW_SW_PATH)
    ow_sw_path_str = str(OW_SW_PATH)
    current_branch = run_shell("git branch --show-current", cwd=ow_sw_path_str,
                               capture_output=True, text=True).stdout.strip()

    manifest_branch: Optional[str] = None  # Can be local or remote
    if use_current_ow_branch:
        if manifest_source == MANIFEST_SOURCE_LOCAL:
            LOG(f"Using current branch '{current_branch}' as manifest branch.")
            manifest_branch = current_branch
        else:
            LOG(f"ERROR: --use_current_ow_branch is only valid when --manifest_source is local.", file=sys.stderr)
            sys.exit(1)
    else:
        manifest_branch = args.ow_manifest_branch
        if args.ow_manifest_branch is None:
            LOG(f"ERROR: --ow_manifest_branch is required when not using --use_current_ow_branch.", file=sys.stderr)
            sys.exit(1)

    prebuild_check(build_type, manifest_source, manifest_branch, tisdk_ref,
                   overwrite_repos, use_current_ow_branch, current_branch)
    pre_build_setup(build_type, manifest_source, manifest_branch,
                    tisdk_ref, overwrite_repos, force_reset_tmp_build, sync)
    run_build(build_type, args.interactive)

    if build_type == BUILD_TYPE_IESA:
        LOG(f"{MAIN_STEP_LOG_PREFIX} IESA build finished. Renaming artifact...")
        if OUTPUT_IESA_PATH.is_file():
            new_iesa_name = f"v_{manifest_branch}.iesa"
            new_iesa_path = OUTPUT_IESA_PATH.parent / new_iesa_name
            try:
                # In linux, rename will overwrite.
                OUTPUT_IESA_PATH.rename(new_iesa_path)
                LOG(f"Renamed '{OUTPUT_IESA_PATH.name}' to '{new_iesa_path.name}'")
                LOG(f"Find output IESA here (WSL path): {new_iesa_path.resolve()}")

                LOG("\nUse this below command to copy to target IP:\n")
                output_path = new_iesa_path.resolve()
                LOG(f'output_path="{output_path}" && read -p "Enter source IP address: " source_ip && rmh && sudo chmod 644 "$output_path" && scp -rJ root@$source_ip "$output_path" root@192.168.100.254:/home/root/download/')
            except OSError as e:
                LOG(f"Error renaming file: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            LOG(f"ERROR: Expected IESA artifact not found at '{OUTPUT_IESA_PATH}' or it's not a file.", file=sys.stderr)
            sys.exit(1)


# ───────────────────────────  helpers / actions  ─────────────────────── #
def prebuild_check(build_type: str, manifest_source: str, ow_manifest_branch: str, input_tisdk_ref: str, overwrite_repos: List[str], use_current_ow_branch: bool, current_branch: str):
    ow_sw_path_str = str(OW_SW_PATH)
    LOG(f"{MAIN_STEP_LOG_PREFIX} Pre-build check...")
    LOG(f"Check OW branch matches with manifest branch. This is because we use some OW folders from the build like ./external/, ... ")
    try:
        if not use_current_ow_branch:
            base_manifest_branch = ow_manifest_branch
            LOG(f"Checking if manifest branch '{base_manifest_branch}' exists in '{ow_sw_path_str}'...")
            branch_exists_result = run_shell(
                f"git rev-parse --verify {base_manifest_branch}", cwd=ow_sw_path_str, capture_output=True, text=True, check_throw_exception_on_exit_code=False)
            if branch_exists_result.returncode != 0:
                LOG(f"ERROR: Manifest branch '{base_manifest_branch}' does not exist in '{ow_sw_path_str}'. Please ensure the branch is available.", file=sys.stderr)
                sys.exit(1)
            LOG(f"Manifest branch '{base_manifest_branch}' exists.")

            if current_branch != base_manifest_branch:
                is_branch_ok: bool = False
                if manifest_source == MANIFEST_SOURCE_LOCAL:
                    if is_ancestor(f"{base_manifest_branch}", current_branch, cwd=ow_sw_path_str):
                        is_branch_ok = True
                    else:
                        LOG(f"ERROR: Local branch '{current_branch}' is not a descendant of '{base_manifest_branch}' (or its remote tracking branch if applicable).", file=sys.stderr)
                        is_branch_ok = False
                else:
                    LOG(f"ERROR: OW_SW_PATH ({ow_sw_path_str}) is on branch '{current_branch}', but manifest branch is '{base_manifest_branch}'. Checkout correct OW_SW_PATH branch or update manifest branch. Ex: cd {ow_sw_path_str} && git checkout {base_manifest_branch}", file=sys.stderr)
                    LOG(f"This is kinda wierd but because we run docker")
                if not is_branch_ok:
                    sys.exit(1)
    except Exception as e:
        LOG(f"ERROR: Error while checking OW_SW_PATH branch: {e}", file=sys.stderr)
        sys.exit(1)

    if build_type == BUILD_TYPE_IESA:
        if not input_tisdk_ref:
            LOG(f"ERROR: TISDK ref is not provided.", file=sys.stderr)
            sys.exit(1)

        LOG(f"Check TISDK ref {input_tisdk_ref} matches with {GITLAB_CI_YML_PATH}'s tisdk branch to avoid using wrong BSP")
        tisdk_ref_from_ci_yml: Optional[str] = get_tisdk_ref_from_ci_yml(GITLAB_CI_YML_PATH)
        if input_tisdk_ref != tisdk_ref_from_ci_yml:
            # Maybe we should check if tisdk_ref is ahead of tisdk_branch in the future if need change tisdk ref separately
            LOG(f"ERROR: TISDK ref '{input_tisdk_ref}' does not match with {GITLAB_CI_YML_PATH}'s tisdk branch '{tisdk_ref_from_ci_yml}'.", file=sys.stderr)
            sys.exit(1)
        else:
            LOG(f"TISDK ref '{input_tisdk_ref}' matches with {GITLAB_CI_YML_PATH}'s tisdk branch '{tisdk_ref_from_ci_yml}'.")

    # Verify overwrite_repos
    if overwrite_repos:
        path_mapping: Dict[str, str] = parse_local_manifest()  # Mapping example: {"ow_sw_tools": "tools/ow_sw_tools"}
        for repo_name in overwrite_repos:
            if repo_name not in path_mapping:
                LOG(
                    f"ERROR: Invalid overwrite repo name: {repo_name}\nAvailable repo names in manifest: {list(path_mapping.keys())}")
                sys.exit(1)


def is_ancestor(ancestor_ref: str, descentdant_ref: str, cwd: Union[str, Path]) -> bool:
    """
    Checks the ancestry relationship between two Git references.

    Args:
        ref1: The first Git reference (commit hash, branch, tag).
        ref2: The second Git reference.
        cwd: The working directory for the Git command.

    Returns:
        True if the ancestry condition is met, False otherwise.
    """
    cmd = f"git merge-base --is-ancestor {ancestor_ref} {descentdant_ref}"
    result = run_shell(cmd, cwd=cwd, check_throw_exception_on_exit_code=False)
    return result.returncode == 0


def pre_build_setup(build_type: str, manifest_source: str, ow_manifest_branch: str, tisdk_ref: str, overwrite_repos: List[str], force_reset_tmp_build: bool, sync: bool) -> None:
    LOG(f"{MAIN_STEP_LOG_PREFIX} Pre-build setup...")
    setup_executable_files(OW_SW_PATH)  # It will use LOCAL OW_SW to run build (docker run -it ...)

    if sync:
        reset_or_create_tmp_build(force_reset_tmp_build)
        manifest_repo_url = get_manifest_repo_url(manifest_source)
        init_and_sync(manifest_repo_url, ow_manifest_branch)  # Sync other repos from manifest of REMOTE OW_SW
    else:
        LOG("Skipping tmp_build reset and repo sync due to --sync false flag.")

    # {repo → relative path from build folder}, use local as they should be the same
    path_mapping: Dict[str, str] = parse_local_manifest()  # Mapping example: {"ow_sw_tools": "tools/ow_sw_tools"}

    if overwrite_repos:
        # Copy local code to overwrite code from remote before build
        repo_names = [get_path_no_git_suffix(r) for r in overwrite_repos]
        for repo_name in repo_names:
            if repo_name not in path_mapping:
                LOG(f"ERROR: Specified repo \"{repo_name}\" not found in manifest.", file=sys.stderr)
                sys.exit(1)
            repo_rel_path_vs_tmp_build = path_mapping[repo_name]
            sync_code(repo_name, repo_rel_path_vs_tmp_build)

        any_changed: bool = any(show_changes(r, path_mapping[r]) for r in repo_names if r in path_mapping)
        if not any_changed:
            LOG("WARNING: No files changed in selected repos.")

    if build_type == BUILD_TYPE_IESA:
        prepare_iesa_bsp(tisdk_ref)


def setup_executable_files(folder_path: Path, postfixes: Optional[List[str]] = None) -> None:
    # Define the set of script extensions that should be made executable.
    supported_script_postfixes = {".sh", ".py", ".pl", ".awk", ".sed"}

    # Default to .py and .sh if no postfixes are specified.
    if postfixes is None:
        postfixes = [".py", ".sh"]

    try:
        if not folder_path.exists():
            LOG(f"Path does not exist, cannot proceed: {folder_path}")
            return

        if not folder_path.is_dir():
            LOG(f"Path is not a directory. This function only accepts directory paths. Path: {folder_path}")
            return

        LOG(f"Processing a directory: {folder_path}")

        # Filter the user-provided postfixes to only include supported script types.
        valid_postfixes = [p for p in postfixes if p in supported_script_postfixes]
        unsupported = set(postfixes) - set(valid_postfixes)
        for p in unsupported:
            LOG(f"Ignoring unsupported file extension for directory scan: {p}")

        if not valid_postfixes:
            LOG("No supported file types to process in the directory. Exiting.")
            return

        # Common setup for the 'find' command to exclude certain folders.
        path_to_use = shlex.quote(str(folder_path))
        ignore_folders = ["tmp_build", ".git", "__pycache__", "node_modules"]
        prune_parts = [f"-name {shlex.quote(d)} -type d" for d in ignore_folders]
        prune_clause = f"\\( {' -o '.join(prune_parts)} \\) -prune -o" if prune_parts else ""

        # Build the name-matching part of the find command.
        name_patterns = [f"-name '*{ext}'" for ext in valid_postfixes]
        name_clause = " -o ".join(name_patterns)

        # Command to convert all matching files to Unix line endings.
        # Using -print0 and xargs -0 handles filenames with spaces or special characters.
        LOG(f"Converting {', '.join(valid_postfixes)} files to Unix line endings...")
        dos2unix_cmd = (
            f"find {path_to_use} {prune_clause} "
            f"-type f \\( {name_clause} \\) "
            "-print0 | xargs -0 dos2unix"
        )
        run_shell(dos2unix_cmd, check_throw_exception_on_exit_code=False)

        # Command to grant execute permissions to the same set of files.
        LOG(f"Granting execute permissions to {', '.join(valid_postfixes)} files...")
        chmod_cmd = (
            f"find {path_to_use} {prune_clause} "
            f"-type f \\( {name_clause} \\) "
            "-print0 | xargs -0 chmod +x"
        )
        run_shell(chmod_cmd, check_throw_exception_on_exit_code=False)
        LOG("Directory processing complete.")

    except Exception as e:
        LOG(f"A critical error occurred in setup_executable_files for path '{folder_path}': {e}", exc_info=True)


def run_build(build_type: str, interactive: bool = False) -> None:
    if build_type == BUILD_TYPE_BINARY:
        make_target = "arm"
    elif build_type == BUILD_TYPE_IESA:
        make_target = "package"
    else:
        raise ValueError(f"Unknown build type: {build_type}, expected {BUILD_TYPE_BINARY} or {BUILD_TYPE_IESA}")

    docker_cmd_base = (
        f"docker run -it --rm -v {OW_SW_PATH}:{OW_SW_PATH} -w {OW_SW_PATH} oneweb_sw "
    )

    # Command to find and convert script files to Unix format (similar to setup_executable_files logic)
    # This targets the same file types that setup_executable_files processes
    dos2unix_cmd = (
        "find . \\( -name tmp_build -o -name .git -o -name __pycache__ -o -name node_modules \\) -prune -o "
        "-type f \\( -name '*.py' -o -name '*.sh' -o -name '*.pl' -o -name '*.awk' -o -name '*.sed' \\) "
        "-print0 | xargs -0 dos2unix"
    )

    time_now = datetime.datetime.now()
    if interactive:
        LOG(f"{LINE_SEPARATOR}Entering interactive mode.")
        LOG("Note: dos2unix will be run automatically when you execute make commands.")
        LOG(f"Run 'dos2unix_and_make() {{ {dos2unix_cmd} && make {make_target}; }}' to start {build_type} building with dos2unix.", highlight=True)
        LOG(f"Or run individual commands: first '{dos2unix_cmd.replace('xargs -0 dos2unix', 'xargs -0 dos2unix')}', then 'make {make_target}'")
        LOG(f"Type 'exit' or press Ctrl+D to leave interactive mode.")

        # Create a bash function for convenience and enter interactive mode
        bash_setup = f"""
        dos2unix_and_make() {{
            echo "Running dos2unix on script files..."
            {dos2unix_cmd}
            echo "Running make {make_target}..."
            make {make_target}
        }}
        """
        run_shell(docker_cmd_base + f"bash -c '{bash_setup}; bash'", check_throw_exception_on_exit_code=False)
        LOG(f"Exiting interactive mode...")
    else:
        LOG("Running dos2unix on script files and build command...")
        # Chain dos2unix and make commands
        run_shell(docker_cmd_base + f"bash -c {dos2unix_cmd} && make {make_target}")
        elapsed_time = (datetime.datetime.now() - time_now).total_seconds()
        LOG(f"Build finished in {elapsed_time} seconds")


def reset_or_create_tmp_build(force_reset_tmp_build: bool) -> None:
    repo_dir = BUILD_FOLDER_PATH / '.repo'
    manifest_file = repo_dir / 'manifest.xml'
    manifests_git_head = repo_dir / 'manifests' / '.git' / 'HEAD'

    def should_reset_instead_clearing(force_reset: bool) -> bool:
        return not force_reset and repo_dir.is_dir() and manifest_file.is_file() and manifests_git_head.is_file()

    if BUILD_FOLDER_PATH.exists():
        if should_reset_instead_clearing(force_reset_tmp_build):
            LOG(f"Resetting existing repo in {BUILD_FOLDER_PATH}...")
            try:
                run_shell("repo forall -c 'git reset --hard' && repo forall -c 'git clean -fdx'", cwd=BUILD_FOLDER_PATH)
            except subprocess.CalledProcessError:
                LOG(f"Warning: 'repo forall' failed in {BUILD_FOLDER_PATH}. Assuming broken repo and clearing...")
                run_shell("sudo rm -rf " + str(BUILD_FOLDER_PATH))
                BUILD_FOLDER_PATH.mkdir(parents=True)
        else:
            LOG(f"Force clearing tmp_build folder at {BUILD_FOLDER_PATH}...")
            run_shell("sudo rm -rf " + str(BUILD_FOLDER_PATH))
            BUILD_FOLDER_PATH.mkdir(parents=True)
    else:
        BUILD_FOLDER_PATH.mkdir(parents=True)


def get_tisdk_ref_from_ci_yml(file_path: str) -> Optional[str]:
    tisdk_ref = None
    sdk_release_ref = None

    try:
        with open(file_path, 'r') as f:
            ci_config = yaml.safe_load(f)
    except Exception as e:
        LOG(f"Error reading {file_path}: {e}", file=sys.stderr)
        return None

    # Search through all items in the YAML file to find job definitions
    for job_details in ci_config.values():
        if not isinstance(job_details, dict) or 'needs' not in job_details or not isinstance(job_details.get('needs'), list):
            continue

        # Iterate over the dependencies in the 'needs' list
        for need in job_details['needs']:
            # We are looking for a dictionary entry from the correct project
            if isinstance(need, dict) and need.get('project') == 'intellian_adc/tisdk_tools':
                job = need.get('job')
                ref = need.get('ref')
                if job == 'sdk_create_tarball':
                    tisdk_ref = ref
                elif job == 'sdk_create_tarball_release':
                    sdk_release_ref = ref

    if (tisdk_ref is None or sdk_release_ref is None) or (tisdk_ref != sdk_release_ref):
        LOG(
            f"ERROR: TISDK ref mismatch in CI config. 'sdk_create_tarball' ref is '{tisdk_ref}' while 'sdk_create_tarball_release' is '{sdk_release_ref}'.", file=sys.stderr)
        return None

    return tisdk_ref


def init_and_sync(manifest_repo_url: str, manifest_repo_branch: str) -> None:
    LOG(f"{MAIN_STEP_LOG_PREFIX} Init and Sync repo at {BUILD_FOLDER_PATH}...")
    run_shell(f"repo init {manifest_repo_url} -b {manifest_repo_branch} -m {MANIFEST_RELATIVE_PATH}",
              cwd=BUILD_FOLDER_PATH,)

    # Construct the full path to the manifest file
    manifest_full_path = os.path.join(BUILD_FOLDER_PATH, ".repo", "manifests", MANIFEST_RELATIVE_PATH)
    # Check if the manifest file exists before trying to read it
    LOG("\n--------------------- MANIFEST ---------------------")
    if os.path.exists(manifest_full_path):
        LOG(f"--- Manifest Content ({manifest_full_path}) ---")
        try:
            with open(manifest_full_path, 'r') as f:
                LOG(f.read())
        except Exception as e:
            LOG(f"Error reading manifest file: {e}")
        LOG("--- End Manifest Content ---")
    else:
        LOG(
            f"Manifest file not found at: {manifest_full_path}. This might happen if {MANIFEST_FILE_NAME} was not found in the manifest repository.")
    LOG("\n")

    run_shell("repo sync", cwd=BUILD_FOLDER_PATH)


def parse_local_manifest(manifest_file: Path = MANIFEST_FILE_PATH) -> Dict[str, str]:
    """Return {project-name → path} from the manifest XML."""
    if not manifest_file.is_file():
        LOG(f"ERROR: manifest not found at {manifest_file}", file=sys.stderr)
        sys.exit(1)

    tree = ET.parse(manifest_file)
    mapping: Dict[str, str] = {}
    for proj in tree.getroot().iterfind("project"):
        name = proj.attrib.get("name")
        name = get_path_no_git_suffix(name)
        path = proj.attrib.get("path")
        if name and path:
            if name in mapping:
                LOG(f"ERROR: duplicate project name \"{name}\" in manifest", file=sys.stderr)
                sys.exit(1)

            mapping[name] = path
    return mapping


def get_path_no_git_suffix(path: str) -> str:
    suffix = ".git"
    if path.endswith(suffix):
        path = path[:-len(suffix)]
    return path


def choose_repos(mapping: Dict[str, str]) -> List[str]:
    LOG("\nAvailable repositories from manifest (<repo name> -> <relative path>):")
    for name, path in sorted(mapping.items()):
        LOG(f"  {name:<20} → {path}")

    picked: List[str] = []
    while True:
        repo_name = input(
            f"[Optional] Repo name to copy from local in {CORE_REPOS_FOLDER_PATH} (enter blank to stop): ").strip()
        if not repo_name:
            break
        if repo_name not in mapping:
            LOG(f"Repo \"{repo_name}\" not listed in manifest. Try again.")
            continue
        LOG(f"Selected: \"{repo_name}\"")
        picked.append(repo_name)

    return picked


def sync_code(repo_name: str, repo_rel_path_vs_tmp_build: str) -> None:
    src_path = CORE_REPOS_FOLDER_PATH / repo_name
    dest_root_path = BUILD_FOLDER_PATH / repo_rel_path_vs_tmp_build

    if not src_path.is_dir() or not dest_root_path.is_dir():
        LOG(f"ERROR: Source or destination not found at {src_path} or {dest_root_path}", file=sys.stderr)
        sys.exit(1)

    LOG(f"Verifying git history for '{repo_name}'...")
    try:
        src_overwrite_commit = run_shell("git rev-parse HEAD", cwd=src_path,
                                         capture_output=True, text=True).stdout.strip()
        dest_orig_commit = run_shell("git rev-parse HEAD", cwd=dest_root_path,
                                     capture_output=True, text=True).stdout.strip()  # Fetch remotely via repo sync

        if src_overwrite_commit == dest_orig_commit:
            LOG("Source and destination are at the same commit. No history check needed.")
        elif not is_ancestor(dest_orig_commit, src_overwrite_commit, cwd=src_path):
            LOG(f"ERROR: Source (override) commit ({str(src_path)}: {src_overwrite_commit}) is not a descendant of destination ({str(dest_root_path)}: {dest_orig_commit}).\nMake sure check out correct branch +  force push local branch to remote (as it fetched dest remotely via repo sync)!", file=sys.stderr)
            sys.exit(1)
        else:
            LOG(f"Common ancestor for '{repo_name}' found. Proceeding with sync.")
    except Exception as e:
        LOG(f"ERROR: Failed to verify git history for '{repo_name}'. Reason: {e}", file=sys.stderr)
        sys.exit(1)

    LOG(f"Copying from \"{src_path}\" to \"{dest_root_path}\"")

    EXCLUDE_DIRS = {".git", ".vscode"}
    for file_or_dir in src_path.rglob("*"):
        if any(part in EXCLUDE_DIRS for part in file_or_dir.parts):
            continue

        file_rel_path = file_or_dir.relative_to(src_path)
        dest_path = dest_root_path / file_rel_path
        if file_or_dir.is_file():
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if not dest_path.exists() or is_diff_ignore_eol(file_or_dir, dest_path):
                shutil.copy2(file_or_dir, dest_path)
        elif file_or_dir.is_dir():
            # Create directories if they don't exist
            dest_path.mkdir(parents=True, exist_ok=True)


def show_changes(repo_name: str, rel_path: str) -> bool:
    repo_path = BUILD_FOLDER_PATH / rel_path
    exclude_pattern = ":(exclude)tmp_local_gitlab_ci/"
    res = subprocess.run(
        # Need . to apply pathspecs (with exclude) to current directory
        ["git", "status", "--porcelain", ".", exclude_pattern],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    changes: List[str] = [line for line in res.stdout.splitlines() if line.strip()]
    if changes:
        LOG(f"\nChanges in {repo_name} ({rel_path}):")
        for line in changes:
            LOG(" ", line)
    else:
        LOG(f"\nNo changes detected in {repo_name}.")
    return bool(changes)


def get_manifest_repo_url(manifest_source: str) -> Optional[str]:
    LOG(f"{MAIN_STEP_LOG_PREFIX} Getting manifest repo URL...")
    manifest_url: Optional[str] = None
    if manifest_source == MANIFEST_SOURCE_REMOTE:
        manifest_url = "https://gitlab.com/intellian_adc/oneweb_project_sw_tools"
    elif manifest_source == MANIFEST_SOURCE_LOCAL:
        manifest_url = f"file://{OW_SW_PATH}"
    else:
        raise ValueError(f"Unknown source: {manifest_source}, expected 'remote' or 'local'")

    LOG(f"Using manifest source: {manifest_source} ({manifest_url})")
    return manifest_url


def prepare_iesa_bsp(tisdk_ref: str):
    LOG(f"{MAIN_STEP_LOG_PREFIX} Preparing IESA BSP for release, TISDK ref: {tisdk_ref}...")
    # Logic to read token from file if not in env
    private_token = read_token_from_file(CREDENTIAL_FILE_PATH, GL_TISDK_TOKEN_KEY_NAME)
    if not private_token:
        LOG("Error: GitLab private token not found in credentials file.")
        sys.exit(1)

    # Details of the target project and job
    target_project_path = "intellian_adc/tisdk_tools"
    target_job_name = "sdk_create_tarball_release"
    target_ref = tisdk_ref

    # Get the target project using the new function
    target_project = get_gl_project(private_token, target_project_path)

    # For robust fetching of branch names, consider get_all=True here too if you're not sure the default is sufficient.
    LOG(f"Target project: {target_project_path}, instance: {target_project.branches.list(get_all=True)[0].name}")

    pipeline_id = get_latest_successful_pipeline_id(target_project, target_job_name, target_ref)
    if not pipeline_id:
        LOG(f"No successful pipeline found for job '{target_job_name}' on ref '{target_ref}'.")
        sys.exit(1)

    artifacts_dir = BSP_ARTIFACT_FOLDER_PATH
    # Clean artifacts directory contents
    if os.path.exists(artifacts_dir):
        LOG(f"Cleaning artifacts directory: {artifacts_dir}")
        shutil.rmtree(artifacts_dir)

    paths: List[str] = download_job_artifacts(target_project, artifacts_dir, pipeline_id, target_job_name)
    if paths:
        bsp_path = None
        LOG(f"Artifacts extracted to: {artifacts_dir}")
        for path in paths:
            LOG(f"  {path}")
            file_name = os.path.basename(path)
            if file_name.startswith(BSP_ARTIFACT_PREFIX):
                if bsp_path:
                    LOG(f"Overwriting previous BSP path {bsp_path} with {path}")
                    LOG("Setting permissions for BSP file to 644...")
                    os.chmod(bsp_path, 0o644)  # 644: rw-r--r--
                bsp_path = path
        if bsp_path:
            LOG(f"Final BSP: {bsp_path}. md5sum: {get_file_md5sum(bsp_path)}")
            LOG(f"Creating symbolic link {BSP_SYMLINK_PATH_FOR_BUILD} -> {bsp_path}")
            subprocess.run(["ln", "-sf", bsp_path, BSP_SYMLINK_PATH_FOR_BUILD])
            subprocess.run(["ls", "-la", BSP_SYMLINK_PATH_FOR_BUILD])


# ───────────────────────  module entry-point  ────────────────────────── #
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        LOG(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        LOG("\nAborted by user.", file=sys.stderr)
        sys.exit(1)
