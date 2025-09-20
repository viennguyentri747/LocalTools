#!/home/vien/local_tools/MyVenvFolder/bin/python
"""
OneWeb SW-Tools interactive local build helper (top-down, manifest-aware).
"""
import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
from typing import Dict, List, Optional, Union
import argparse
from dev_common import *
import yaml


GITLAB_CI_YML_PATH = OW_SW_PATH / ".gitlab-ci.yml"
# Need to put this here because we will go into docker environment from OW_SW_PATH
BSP_ARTIFACT_FOLDER_PATH = OW_SW_PATH / "custom_artifacts_bsp/"
BSP_ARTIFACT_PREFIX = "bsp-iesa-"
BSP_SYMLINK_PATH_FOR_BUILD = OW_SW_PATH / "packaging" / "bsp_current" / "bsp_current.tar.xz"
MAIN_STEP_LOG_PREFIX = f"{LINE_SEPARATOR}\n[MAIN_STEP]"


def main() -> None:
    parser = argparse.ArgumentParser(description="OneWeb SW-Tools local build helper.")
    parser.formatter_class = argparse.RawTextHelpFormatter
    # Fill help epilog from templates
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    parser.add_argument("--build_type", choices=[BUILD_TYPE_BINARY, BUILD_TYPE_IESA], type=str, default=BUILD_TYPE_BINARY,
                        help="Build type (binary or iesa). Defaults to binary.")
    parser.add_argument("--manifest_source", choices=[MANIFEST_SOURCE_LOCAL, MANIFEST_SOURCE_REMOTE], default="local",
                        help=F"Source for the manifest repository URL ({MANIFEST_SOURCE_LOCAL} or {MANIFEST_SOURCE_REMOTE}). Defaults to {MANIFEST_SOURCE_LOCAL}. Note that although it is local manifest, the source of sync is still remote so will need to push branch of dependent local repos specified in local manifest (not ow_sw_tools).")
    parser.add_argument(ARG_OW_MANIFEST_BRANCH_SHORT, ARG_OW_MANIFEST_BRANCH_LONG, type=Optional[str], default=None,
                        help="Branch of oneweb_project_sw_tools for manifest (either local or remote branch, depend on --manifest_source). Ex: 'manpack_master'")
    parser.add_argument("--tisdk_ref", type=str, default=None,
                        help="TISDK Ref for BSP (for creating .iesa). Ex: 'manpack_master'")
    parser.add_argument("--overwrite_repos", nargs='*', default=[],
                        help="List of repository names to overwrite from local")
    parser.add_argument("-i", "--interactive", type=lambda x: x.lower() == 'true', default=False,
                        help="Run in interactive mode (true or false). Defaults to false.")
    parser.add_argument("--force_reset_tmp_build", type=lambda x: x.lower() == 'true', default=False,
                        help="Force clearing tmp_build folder before sync (true or false). Defaults to false.")
    parser.add_argument("--sync", type=lambda x: x.lower() == 'true', default=True,
                        help="If true, perform tmp_build reset (true or false) and repo sync. Defaults to true.")
    parser.add_argument("--use_current_ow_branch", type=lambda x: x.lower() == 'true', default=True,
                        help="Use the current branch of ow_sw_tools repo (true or false). Defaults to true.")
    parser.add_argument("--make_clean", type=lambda x: x.lower() == 'true', default=True,
                        help="Run make clean before building (true or false). Defaults to true.")
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
    make_clean: bool = args.make_clean
    # Update overwrite repos no git suffix
    overwrite_repos = [get_path_no_suffix(r, GIT_SUFFIX) for r in overwrite_repos]
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
    run_build(build_type, args.interactive, make_clean)

    if build_type == BUILD_TYPE_IESA:
        LOG(f"{MAIN_STEP_LOG_PREFIX} IESA build finished. Renaming artifact...")
        if OW_OUTPUT_IESA_PATH.is_file():
            new_iesa_name = f"v_{manifest_branch}.iesa"
            new_iesa_path = OW_OUTPUT_IESA_PATH.parent / new_iesa_name
            # In linux, rename will overwrite.
            OW_OUTPUT_IESA_PATH.rename(new_iesa_path)
            new_iesa_output_abs_path = new_iesa_path.resolve()
            LOG(f"Renamed '{OW_OUTPUT_IESA_PATH.name}' to '{new_iesa_path.name}'")
            LOG(f"Find output IESA here (WSL path): {new_iesa_output_abs_path}")
            LOG(f"{LINE_SEPARATOR}")
            # run_shell(f"sudo chmod 644 {new_iesa_output_abs_path}")
            # original_md5 = md5sum(new_iesa_output_abs_path)
            LOG("Use this below command to copy to target IP:\n")
            LOG(
                f'output_path="{new_iesa_output_abs_path}" '
                '&& read -e -i "192.168.10" -p "Enter source IP address: " source_ip '
                # '&& rmh '
                '&& sudo chmod 644 "$output_path" '
                '&& scp -rJ root@$source_ip "$output_path" root@192.168.100.254:/home/root/download/ && { original_md5=$(md5sum "$output_path" | cut -d" " -f1); noti "SCP copy completed successfully"; echo -e "IESA copied completed. Install on target UT $source_ip with this below command:\\n"; } || { noti "SCP copy failed"; } '
                f'&& echo "original_md5=\\"$original_md5\\"; actual_md5=\\$(md5sum /home/root/download/{new_iesa_name} | cut -d\\\" \\\" -f1); echo \\\"original md5sum: \\$original_md5\\\"; echo \\\"actual md5sum: \\$actual_md5\\\"; if [ \\\"\\$original_md5\\\" = \\\"\\$actual_md5\\\" ]; then read -r -p \\\"MD5 match! Install (y/n)?: \\\" confirm; [ \\\"\\$confirm\\\" = \\\"y\\\" -o \\\"\\$confirm\\\" = \\\"Y\\\" ] && iesa_umcmd install pkg {new_iesa_name} && tail -F /var/log/upgrade_log; else echo \\\"MD5 MISMATCH! Not installing.\\\"; fi"', show_time=False
            )
        else:
            LOG(
                f"ERROR: Expected IESA artifact not found at '{OW_OUTPUT_IESA_PATH}' or it's not a file.", file=sys.stderr)
            sys.exit(1)
    else:
        LOG(f"{MAIN_STEP_LOG_PREFIX} Binary build finished.")
        LOG(f"Find output binary files in '{OW_BUILD_BINARY_OUTPUT_PATH}'")
        LOG(f"{LINE_SEPARATOR}")
        LOG("Use this below command to copy to target IP:")
        # LOG(f'sudo chmod -R 755 {OW_BUILD_BINARY_OUTPUT_PATH} && read -e -p "Enter target IP (192.168.10): " -i "192.168.10" TARGET_IP && read -e -p "Enter binary path: " -i "{OW_BUILD_BINARY_OUTPUT_PATH}/" BIN_PATH && scp -rJ root@$TARGET_IP $BIN_PATH root@192.168.100.254:/home/root/download/', show_time=False)
        LOG(f'sudo chmod -R 755 {OW_BUILD_BINARY_OUTPUT_PATH} && '
            f'while true; do '
            f'read -e -p "Enter binary path: " -i "{OW_BUILD_BINARY_OUTPUT_PATH}/" BIN_PATH && '
            f'if [ -f "$BIN_PATH" ]; then break; else echo "Error: File $BIN_PATH does not exist. Please try again."; fi; '
            f'done && '
            f'BIN_NAME=$(basename "$BIN_PATH") && '
            f'read -e -p "Enter destination name: " -i "$BIN_NAME" DEST_NAME && '
            f'original_md5=$(md5sum "$BIN_PATH" | cut -d" " -f1) && '
            f'read -e -p "Enter target IP: " -i "192.168.10" TARGET_IP && '
            f'scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -rJ root@$TARGET_IP "$BIN_PATH" root@192.168.100.254:/home/root/download/"$DEST_NAME" && '
            f'{{ echo "SCP copy completed successfully"; '
            f'echo -e "Binary copied completed. Setup symlink on target UT $TARGET_IP with this below command:\\n"; '
            f'echo "actual_md5=\\$(md5sum /home/root/download/$DEST_NAME | cut -d\\\" \\\" -f1) && if [ \\\"$original_md5\\\" = \"$actual_md5\\\" ]; then echo \\\"MD5 match! Proceeding...\\\" && cp /opt/bin/$BIN_NAME /home/root/download/backup_$BIN_NAME && ln -sf /home/root/download/$DEST_NAME /opt/bin/$BIN_NAME && echo \\\"Backup created and symlink updated: /opt/bin/$BIN_NAME -> /home/root/download/$DEST_NAME\\\"; else echo \\\"MD5 MISMATCH! Aborting.\\\"; fi"; '
            f'}} || {{ echo "SCP copy failed"; }}',
            show_time=False)

        # LOG(f'sudo chmod -R 755 {BUILD_BINARY_OUTPUT_PATH} && read -e -p "Enter target IP: " -i "192.168.10" TARGET_IP && scp -rJ root@$TARGET_IP {BUILD_BINARY_OUTPUT_PATH}/<bin> root@192.168.100.254:/home/root/download/', show_time=False)

# ───────────────────────────  helpers / actions  ─────────────────────── #


def prebuild_check(build_type: str, manifest_source: str, ow_manifest_branch: str, input_tisdk_ref: str, overwrite_repos: List[str], use_current_ow_branch: bool, current_branch: str):
    ow_sw_path_str = str(OW_SW_PATH)
    LOG(f"{MAIN_STEP_LOG_PREFIX} Pre-build check...")
    LOG(f"Check OW branch matches with manifest branch. This is because we use some OW folders from the build like ./external/, ... ")
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
        manifest: IesaManifest = parse_local_iesa_manifest()
        for repo_name in overwrite_repos:
            if repo_name not in manifest.get_all_repo_names():
                LOG(
                    f"ERROR: Invalid overwrite repo name: {repo_name}\nAvailable repo names in manifest: {manifest.get_all_repo_names()}")
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
    if sync:
        reset_or_create_tmp_build(force_reset_tmp_build)
        manifest_repo_url = get_manifest_repo_url(manifest_source)
        # Sync other repos from manifest of REMOTE OW_SW
        init_and_sync_from_remote(manifest_repo_url, ow_manifest_branch)
    else:
        LOG("Skipping tmp_build reset and repo sync due to --sync false flag.")

    # {repo → relative path from build folder}, use local as they should be the same
    manifest: IesaManifest = parse_local_iesa_manifest()

    if overwrite_repos:
        # Copy local code to overwrite code from remote before build
        repo_names = [get_path_no_suffix(r, GIT_SUFFIX) for r in overwrite_repos]
        for repo_name in repo_names:
            repo_rel_path_vs_tmp_build = manifest.get_repo_relative_path_vs_tmp_build(repo_name)
            if repo_name not in manifest.get_all_repo_names():
                LOG(f"ERROR: Specified repo \"{repo_name}\" not found in manifest.", file=sys.stderr)
                sys.exit(1)
            sync_local_code(repo_name, repo_rel_path_vs_tmp_build)

        any_changed: bool = any(show_changes(r, manifest.get_repo_relative_path_vs_tmp_build(r))
                                for r in repo_names if r in manifest.get_all_repo_names())
        if not any_changed:
            LOG("WARNING: No files changed in selected repos.")

    if build_type == BUILD_TYPE_IESA:
        prepare_iesa_bsp(tisdk_ref)


def run_build(build_type: str, interactive: bool, make_clean: bool = True) -> None:
    if build_type == BUILD_TYPE_BINARY:
        make_target = "arm"
    elif build_type == BUILD_TYPE_IESA:
        make_target = "package"
    else:
        throw_exception(f"Unknown build type: {build_type}, expected {BUILD_TYPE_BINARY} or {BUILD_TYPE_IESA}")

    docker_cmd_base = (
        f"docker run -it --rm -v {OW_SW_PATH}:{OW_SW_PATH} -w {OW_SW_PATH} oneweb_sw "
    )

    # Command to find and convert script files to Unix format
    dos2unix_cmd = (
        f"apt-get install -y dos2unix && "
        f"find {OW_SW_PATH.absolute()}/packaging \\( -name tmp_build -o -name .git -o -name __pycache__ \\) "
        "-prune -o -type f \\( -name '*.py' -o -name '*.sh' \\) -exec dos2unix {} +"
    )

    chmod_cmd = f"chmod -R +x {OW_SW_PATH.absolute()}/"

    time_start = datetime.now()
    make_clean_cmd = "make clean"
    if interactive:
        show_noti(title="Interactive Mode", message="Starting interactive mode...")
        LOG(f"{LINE_SEPARATOR}Entering interactive mode.")

        # Build the command sequence based on make_clean flag
        if make_clean:
            bash_setup = f"""/bin/bash -c "echo 'Cleaning build' && {make_clean_cmd} && echo 'Running dos2unix on script files...' && {dos2unix_cmd} && echo 'Granting execute permissions to script files...' && {chmod_cmd} && echo -e '\\nRun make {make_target} to start {build_type} building.\\n\\nType exit or press Ctrl+D to leave interactive mode.' && exec bash" """
        else:
            bash_setup = f"""/bin/bash -c "echo 'Running dos2unix on script files...' && {dos2unix_cmd} && echo 'Granting execute permissions to script files...' && {chmod_cmd} && echo -e '\\nRun make {make_target} to start {build_type} building.\\n\\nType exit or press Ctrl+D to leave interactive mode.' && exec bash" """

        run_shell(docker_cmd_base + bash_setup, check_throw_exception_on_exit_code=False)
        LOG(f"Exiting interactive mode...")
    else:
        LOG("Running dos2unix on script files and build command...")

        # Build the command sequence based on make_clean flag
        if make_clean:
            combined_cmd = f"{make_clean_cmd} && {dos2unix_cmd} && {chmod_cmd} && make {make_target}"
        else:
            combined_cmd = f"{dos2unix_cmd} && {chmod_cmd} && make {make_target}"

        run_shell(docker_cmd_base + f"bash -c '{combined_cmd}'")
        elapsed_time = (datetime.now() - time_start).total_seconds()
        LOG(f"Build finished in {elapsed_time} seconds", show_time=True)
        show_noti(title="Build finished", message=f"Build finished in {elapsed_time} seconds")


def reset_or_create_tmp_build(force_reset_tmp_build: bool) -> None:
    repo_dir = OW_BUILD_FOLDER_PATH / '.repo'
    manifest_file = repo_dir / 'manifest.xml'
    manifests_git_head = repo_dir / 'manifests' / '.git' / 'HEAD'

    def should_reset_instead_clearing(force_reset: bool) -> bool:
        return not force_reset and repo_dir.is_dir() and manifest_file.is_file() and manifests_git_head.is_file()

    if OW_BUILD_FOLDER_PATH.exists():
        should_reset: bool = False
        if should_reset_instead_clearing(force_reset_tmp_build):
            LOG(f"Resetting existing repo in {OW_BUILD_FOLDER_PATH}...")
            try:
                run_shell("repo forall -c 'git reset --hard' && repo forall -c 'git clean -fdx'", cwd=OW_BUILD_FOLDER_PATH)
            except subprocess.CalledProcessError:
                LOG(f"Warning: 'repo forall' failed in {OW_BUILD_FOLDER_PATH}. Assuming broken repo and clearing...")
                should_reset = True
        else:
            LOG(f"Force clearing tmp_build folder at {OW_BUILD_FOLDER_PATH}...")
            should_reset = True
        if should_reset:
            run_shell("sudo rm -rf " + str(OW_BUILD_FOLDER_PATH))
            OW_BUILD_FOLDER_PATH.mkdir(parents=True)
    else:
        OW_BUILD_FOLDER_PATH.mkdir(parents=True)


def get_tisdk_ref_from_ci_yml(file_path: str) -> Optional[str]:
    tisdk_ref = None
    sdk_release_ref = None

    with open(file_path, 'r') as f:
        ci_config = yaml.safe_load(f)

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


def init_and_sync_from_remote(manifest_repo_url: str, manifest_repo_branch: str) -> None:
    LOG(f"{MAIN_STEP_LOG_PREFIX} Init and Sync repo at {OW_BUILD_FOLDER_PATH}...")
    run_shell(f"repo init {manifest_repo_url} -b {manifest_repo_branch} -m {IESA_MANIFEST_RELATIVE_PATH}",
              cwd=OW_BUILD_FOLDER_PATH,)

    # Construct the full path to the manifest file
    manifest_full_path = os.path.join(OW_BUILD_FOLDER_PATH, ".repo", "manifests", IESA_MANIFEST_RELATIVE_PATH)
    # Check if the manifest file exists before trying to read it
    LOG("\n--------------------- MANIFEST ---------------------")
    if os.path.exists(manifest_full_path):
        LOG(f"--- Manifest Content ({manifest_full_path}) ---")
        with open(manifest_full_path, 'r') as f:
            LOG(f.read())
        LOG("--- End Manifest Content ---")
    else:
        throw_exception(
            f"Manifest file not found at: {manifest_full_path}")
    run_shell("repo sync", cwd=OW_BUILD_FOLDER_PATH)


def choose_repos(manifest: IesaManifest) -> List[str]:
    LOG("\nAvailable repositories from manifest (<repo name> -> <relative path>):")
    for name in sorted(manifest.get_all_repo_names()):
        LOG(f"  {name:<20} → {manifest.get_repo_relative_path_vs_tmp_build(name)}")

    picked: List[str] = []
    while True:
        repo_name = input(
            f"[Optional] Repo name to copy from local in {CORE_REPOS_FOLDER_PATH} (enter blank to stop): ").strip()
        if not repo_name:
            break
        if repo_name not in manifest.get_all_repo_names():
            LOG(f"Repo \"{repo_name}\" not listed in manifest. Try again.")
            continue
        LOG(f"Selected: \"{repo_name}\"")
        picked.append(repo_name)

    return picked


def sync_local_code(repo_name: str, repo_rel_path_vs_tmp_build: str) -> None:
    src_path = CORE_REPOS_FOLDER_PATH / repo_name
    dest_root_path = OW_BUILD_FOLDER_PATH / repo_rel_path_vs_tmp_build

    if not src_path.is_dir() or not dest_root_path.is_dir():
        LOG(f"ERROR: Source or destination not found at {src_path} or {dest_root_path}", file=sys.stderr)
        throw_exception(f"Source or destination not found at {src_path} or {dest_root_path}")

    LOG(f"Verifying git history for '{repo_name}'...")
    src_overwrite_commit = run_shell("git rev-parse HEAD", cwd=src_path,
                                     capture_output=True, text=True).stdout.strip()
    dest_orig_commit = run_shell("git rev-parse HEAD", cwd=dest_root_path,
                                 capture_output=True, text=True).stdout.strip()  # Fetch remotely via repo sync

    if src_overwrite_commit == dest_orig_commit:
        LOG("Source and destination are at the same commit. No history check needed.")
    elif not is_ancestor(dest_orig_commit, src_overwrite_commit, cwd=src_path):
        LOG(f"ERROR: Source (override) commit ({str(src_path)}: {src_overwrite_commit}) is not a descendant of destination ({str(dest_root_path)}: {dest_orig_commit}).\nMake sure check out correct branch +  force push local branch to remote (as it fetched dest remotely via repo sync)!", file=sys.stderr)
        throw_exception(
            f"Source commit {src_overwrite_commit} is not a descendant of destination commit {dest_orig_commit}.")
    else:
        LOG(f"Common ancestor for '{repo_name}' found. Proceeding with sync.")

    LOG(f"Copying from \"{src_path}\" to \"{dest_root_path}\"")

    EXCLUDE_DIRS = {".git", ".vscode"}
    for file_or_dir in src_path.rglob("*"):
        # parts = [part1, part2, part3] if path is "part1/part2/part3"
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
    repo_path = OW_BUILD_FOLDER_PATH / rel_path
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
        throw_exception(
            f"Unknown manifest source: {manifest_source}, expected {MANIFEST_SOURCE_LOCAL} or {MANIFEST_SOURCE_REMOTE}")

    LOG(f"Using manifest source: {manifest_source} ({manifest_url})")
    return manifest_url


def prepare_iesa_bsp(tisdk_ref: str):
    LOG(f"{MAIN_STEP_LOG_PREFIX} Preparing IESA BSP for release, TISDK ref: {tisdk_ref}...")
    # Logic to read token from file if not in env
    private_token = read_value_from_credential_file(CREDENTIALS_FILE_PATH, GL_TISDK_TOKEN_KEY_NAME)
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


def throw_exception(message: str):
    """
    Helper function to throw an error with a message.
    """
    raise Exception(message)


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="IESA Build Local",
            description="Build IESA with local manifest and current branch",
            args={
                "--build_type": "iesa",
                "--manifest_source": "local",
                "--use_current_ow_branch": True,
                "--tisdk_ref": "manpack_master",
                "--interactive": False,
                "--make_clean": True,
                "--force_reset_tmp_build": True,
                "--overwrite_repos": ["intellian_pkg", "insensesdk", "adc_lib"],  # "upgrade", "submodule_spibeam"
            }
        ),
        ToolTemplate(
            name="Binary Build",
            description="Build binary with default settings",
            args={
                "--build_type": "binary",
                "--manifest_source": "local",
                "--use_current_ow_branch": True,
                "--interactive": False,
                "--force_reset_tmp_build": False,
                "--make_clean": False,
                "--overwrite_repos": ["intellian_pkg", "insensesdk", "adc_lib"],  # "upgrade", "submodule_spibeam",
            }
        ),
    ]


# ───────────────────────  module entry-point  ────────────────────────── #

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        exception_trace = traceback.format_exc()
        LOG(f"ERROR: {exception_trace}", file=sys.stderr)
        show_noti(title="Error", message=f"An error occurred: {e}")
    except KeyboardInterrupt:
        LOG("\nAborted by user.", file=sys.stderr)
        sys.exit(1)
