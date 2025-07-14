#!/usr/bin/env python3
"""
OneWeb SW-Tools interactive local build helper (top-down, manifest-aware).
"""
import os
from pathlib import Path
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
BUILD_TYPE_IESA = "iesa"
BUILD_TYPE_BINARY = "binary"
CORE_REPOS_PATH = Path.home() / "workspace" / "intellian_core_repos"
OW_SW_PATH = Path.home() / "ow_sw_tools"
# OW_SW_PATH = CORE_REPOS_PATH / "ow_sw_tools"
BUILD_FOLDER_PATH = OW_SW_PATH / "tmp_build"
SCRIPT_FOLDER_PATH = Path.home() / "local_tools"
CREDENTIAL_FILE_PATH = SCRIPT_FOLDER_PATH / ".gitlab_credentials"
GITLAB_CI_YML_PATH = OW_SW_PATH / ".gitlab-ci.yml"
MANIFEST_FILE_NAME = "iesa_manifest_gitlab.xml"
MANIFEST_RELATIVE_PATH = f"tools/manifests/{MANIFEST_FILE_NAME}"
MANIFEST_FILE_PATH = OW_SW_PATH / MANIFEST_RELATIVE_PATH
YML_PATH = OW_SW_PATH / "custom_artifacts"
# OW_LOCAL_BUILD_OUTPUT_DIR = SCRIPT_FOLDER_PATH / "local_build_output"
# Need to put this here because we will go into docker environment from OW_SW_PATH
BSP_ARTIFACT_DIR = OW_SW_PATH / "custom_artifacts_bsp"
BSP_ARTIFACT_PREFIX = "bsp-iesa-"
BSP_SYMLINK_PATH_FOR_BUILD = OW_SW_PATH / "packaging" / "bsp_current" / "bsp_current.tar.xz"
MAIN_STEP_LOG_PREFIX = f"{LINE_SEPARATOR}\n[MAIN_STEP]"
# ─────────────────────────────  top-level  ─────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="OneWeb SW-Tools local build helper.")
    parser.add_argument("--build_type", choices=[BUILD_TYPE_BINARY, BUILD_TYPE_IESA], type=str, default=BUILD_TYPE_BINARY,
                        help="Build type (binary or iesa). Defaults to binary.")
    parser.add_argument("--manifest_source", choices=[MANIFEST_SOURCE_LOCAL, MANIFEST_SOURCE_REMOTE], default="local",
                        help=F"Source for the manifest repository URL ({MANIFEST_SOURCE_LOCAL} or {MANIFEST_SOURCE_REMOTE}). Defaults to {MANIFEST_SOURCE_LOCAL}.")
    parser.add_argument("-b", "--ow_manifest_branch", type=str, required=True,
                        help="Branch of oneweb_project_sw_tools for manifest (either local or remote branch, depend on --manifest_source). Ex: 'manpack_master'")
    parser.add_argument("--check_manifest_branch", type=lambda x: x.lower() == 'true', default=True,
                        help="Check if OW_SW_PATH branch matches manifest branch (true or false). Defaults to true.")  # Only set this to FALSE if you know what you're doing
    parser.add_argument("--tisdk_ref", type=str, required=True,
                        help="TISDK Ref for BSP (for creating .iesa). Ex: 'manpack_master'")
    parser.add_argument("--is_overwrite_local_repos", type=lambda x: x.lower() == 'true', default=False,
                        help="Enable overwriting with local repositories code (true or false). Defaults to false.")
    parser.add_argument("--overwrite_repos", nargs='*', default=[],
                        help="List of repository names to overwrite from local. If empty and --is_overwrite_local_repos is true, prompts user.")
    parser.add_argument("-i", "--interactive", type=lambda x: x.lower() == 'true', default=False,
                        help="Run in interactive mode (true or false). Defaults to false.")
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
    is_overwrite_local_repos: bool = args.is_overwrite_local_repos
    manifest_source: str = args.manifest_source
    manifest_branch: str = args.ow_manifest_branch  # Can be local or remote
    tisdk_ref: str = args.tisdk_ref
    overwrite_repos: List[str] = args.overwrite_repos
    check_manifest_branch: bool = args.check_manifest_branch
    LOG(f"Parsed args: {args}")
    
    overwrite_repos = get_overwrite_repos(args.overwrite_repos, is_overwrite_local_repos)
    prebuild_check(build_type, manifest_source, manifest_branch, tisdk_ref,
                   is_overwrite_local_repos, overwrite_repos, check_manifest_branch)
    pre_build_setup(build_type, manifest_source, manifest_branch, tisdk_ref,
                    is_overwrite_local_repos, overwrite_repos, check_manifest_branch)
    run_build(build_type, args.interactive)


def get_overwrite_repos(orig_repos: List[str], is_overwrite_local_repos: bool) -> List[str]:
    overwrite_repos: List[str] = orig_repos
    if is_overwrite_local_repos:
        path_mapping: Dict[str, str] = parse_local_manifest()  # Mapping example: {"ow_sw_tools": "tools/ow_sw_tools"}
        if not orig_repos:
            repo_names = choose_repos(path_mapping)
            overwrite_repos = repo_names

    return overwrite_repos

# ───────────────────────────  helpers / actions  ─────────────────────── #


def prebuild_check(build_type: str, manifest_source: str, ow_manifest_branch: str, tisdk_ref: str, is_overwrite_local_repos: bool, overwrite_repos: List[str], check_manifest_branch: bool):
    ow_sw_path_str = str(OW_SW_PATH)
    LOG(f"{MAIN_STEP_LOG_PREFIX} Pre-build check...")
    LOG(f"Check OW branch matches with manifest branch. This is because we use some OW folders from the build like ./external/, ... ")
    if check_manifest_branch:
        try:
            current_branch = run_shell("git branch --show-current", cwd=ow_sw_path_str,
                                       capture_output=True, text=True).stdout.strip()
            if current_branch != ow_manifest_branch:
                is_branch_ok: bool = False
                if manifest_source == MANIFEST_SOURCE_LOCAL:
                    # Check if local branch is ahead (descendant) of manifest branch
                    is_ancestor = run_shell(
                        f"git merge-base --is-ancestor origin/{ow_manifest_branch} {current_branch}", cwd=ow_sw_path_str, check_exception_on_exit_code=False
                    )

                    if is_ancestor.returncode == 0:
                        is_branch_ok = True
                    else:
                        LOG(f"ERROR: Local branch '{current_branch}' is not ahead of or equal to 'origin/{ow_manifest_branch}'", file=sys.stderr)
                        is_branch_ok = False
                else:
                    LOG(f"ERROR: OW_SW_PATH ({ow_sw_path_str}) is on branch '{current_branch}', but manifest branch is '{ow_manifest_branch}'. Checkout correct OW_SW_PATH branch or update manifest branch. Ex: cd {ow_sw_path_str} && git checkout {ow_manifest_branch}", file=sys.stderr)
                if not is_branch_ok:
                    sys.exit(1)
        except Exception as e:
            LOG(f"ERROR: Error while checking OW_SW_PATH branch: {e}", file=sys.stderr)
            sys.exit(1)

    if build_type == BUILD_TYPE_IESA:
        LOG(f"Check TISDK ref {tisdk_ref} matches with {GITLAB_CI_YML_PATH}'s tisdk branch to avoid using wrong BSP")
        tisdk_branch = get_tisdk_branch_from_ci_yml(GITLAB_CI_YML_PATH)
        if tisdk_ref != tisdk_branch:
            # Maybe we should check if tisdk_ref is ahead of tisdk_branch in the future if need change tisdk ref separately
            LOG(f"ERROR: TISDK ref '{tisdk_ref}' does not match with {GITLAB_CI_YML_PATH}'s tisdk branch '{tisdk_branch}'.", file=sys.stderr)
            sys.exit(1)
        else:
            LOG(f"TISDK ref '{tisdk_ref}' matches with {GITLAB_CI_YML_PATH}'s tisdk branch '{tisdk_branch}'.")

    # Verify overwrite_repos
    if is_overwrite_local_repos:
        if not overwrite_repos:
            LOG(f"ERROR: Please specify overwrite_repos when --is_overwrite_local_repos is true.", file=sys.stderr)
            sys.exit(1)

        path_mapping: Dict[str, str] = parse_local_manifest()  # Mapping example: {"ow_sw_tools": "tools/ow_sw_tools"}
        for repo_name in overwrite_repos:
            if repo_name not in path_mapping:
                LOG(f"ERROR: Invalid overwrite repo name: {repo_name}\nCurrent overwrite_repos: {overwrite_repos}, Available repo names in manifest: {list(path_mapping.keys())}")
                sys.exit(1)


def pre_build_setup(build_type: str, manifest_source: str, ow_manifest_branch: str, tisdk_ref: str, is_overwrite_local_repos: bool, overwrite_repos: List[str], check_manifest_branch: bool) -> None:
    LOG(f"{MAIN_STEP_LOG_PREFIX} Pre-build setup...")
    reset_or_create_tmp_build()
    manifest_repo_url = get_manifest_repo_url(manifest_source)
    init_and_sync(manifest_repo_url, ow_manifest_branch)

    # {repo → relative path from build folder}, use local as they should be the same
    path_mapping: Dict[str, str] = parse_local_manifest()  # Mapping example: {"ow_sw_tools": "tools/ow_sw_tools"}

    if is_overwrite_local_repos and overwrite_repos:
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
            LOG("\nNo files changed in selected repos.")

    if build_type == BUILD_TYPE_IESA:
        prepare_iesa_bsp(tisdk_ref)


def run_build(build_type: str, interactive: bool = False) -> None:
    if build_type == BUILD_TYPE_BINARY:
        make_target = "arm"
    elif build_type == BUILD_TYPE_IESA:
        make_target = "package"
    else:
        raise ValueError(f"Unknown build type: {build_type}, expected {BUILD_TYPE_BINARY} or {BUILD_TYPE_IESA}")

    docker_cmd = (
        f"docker run -it --rm -v {OW_SW_PATH}:{OW_SW_PATH} -w {OW_SW_PATH} oneweb_sw "
    )

    if interactive:
        LOG(f"{LINE_SEPARATOR}Entering interactive mode.")
        LOG(f"Run 'make {make_target}' to start {build_type} building.", highlight=True)
        LOG(f"Type 'exit' or press Ctrl+D to leave interactive mode.")
        run_shell(docker_cmd + "bash", check_exception_on_exit_code=False)
        # For now, we pass the control to bash process -> Code will not reach unless we exit interactive mode (run_shell will block)
        LOG(f"Exiting interactive mode...")
    else:
        run_shell(docker_cmd + f"bash -c 'make {make_target}'")


def reset_or_create_tmp_build() -> None:
    repo_dir = BUILD_FOLDER_PATH / '.repo'
    manifest_file = repo_dir / 'manifest.xml'  # .repo/manifest.xml stored the manifest you get from the repo

    if BUILD_FOLDER_PATH.exists():
        # Check if it's a valid repo: both .repo folder AND manifest.xml must exist
        if repo_dir.is_dir() and manifest_file.is_file():
            LOG(f"Reseting existing repo in {BUILD_FOLDER_PATH}...")
            try:
                run_shell("repo forall -c 'git reset --hard' && repo forall -c 'git clean -fdx'", cwd=BUILD_FOLDER_PATH)
            except subprocess.CalledProcessError:
                # If 'repo forall' fails (e.g., due to a broken manifest, launcher issues, etc.)
                # Treat it as a broken repo and clear it.
                LOG(f"Warning: 'repo forall' failed in {BUILD_FOLDER_PATH}. Assuming broken repo and clearing...")
                run_shell("sudo rm -rf " + str(BUILD_FOLDER_PATH))
                BUILD_FOLDER_PATH.mkdir(parents=True)
        else:
            # If BUILD_FOLDER exists, but it's not a fully functional repo (missing .repo or manifest)
            LOG(f"\nClearing broken or non-repo folder {BUILD_FOLDER_PATH} (missing .repo or manifest.xml)...")
            run_shell("sudo rm -rf " + str(BUILD_FOLDER_PATH))
            BUILD_FOLDER_PATH.mkdir(parents=True)
    else:
        # If the folder doesn't exist at all, create it
        BUILD_FOLDER_PATH.mkdir(parents=True)


def get_tisdk_branch_from_ci_yml(file_path: str) -> Optional[str]:
    sdk_ref = None
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
                    sdk_ref = ref
                elif job == 'sdk_create_tarball_release':
                    sdk_release_ref = ref

    if (sdk_ref is None or sdk_release_ref is None) or (sdk_ref != sdk_release_ref):
        LOG(
            f"ERROR: TISDK ref mismatch in CI config. 'sdk_create_tarball' ref is '{sdk_ref}' while 'sdk_create_tarball_release' is '{sdk_release_ref}'.", file=sys.stderr)
        return None

    return sdk_ref


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
            f"[Optional] Repo name to copy from local in {CORE_REPOS_PATH} (enter blank to stop): ").strip()
        if not repo_name:
            break
        if repo_name not in mapping:
            LOG(f"Repo \"{repo_name}\" not listed in manifest. Try again.")
            continue
        LOG(f"Selected: \"{repo_name}\"")
        picked.append(repo_name)

    return picked


def sync_code(repo_name: str, repo_rel_path_vs_tmp_build: str) -> None:
    src_path = CORE_REPOS_PATH / repo_name
    dest_root_path = BUILD_FOLDER_PATH / repo_rel_path_vs_tmp_build

    if not src_path.is_dir() or not dest_root_path.is_dir():
        LOG(f"ERROR: Source or destination not found at {src_path} or {dest_root_path}", file=sys.stderr)
        sys.exit(1)
        return

    LOG(f"Copying from \"{src_path}\" to \"{dest_root_path}\"")

    EXCLUDE_DIRS = {".git", ".vscode"}
    for file in src_path.rglob("*"):
        if any(part in EXCLUDE_DIRS for part in file.parts):
            continue
        if file.is_file():
            file_rel_path = file.relative_to(src_path)
            dest_file_path = dest_root_path / file_rel_path
            dest_file_path.parent.mkdir(parents=True, exist_ok=True)

            if not dest_file_path.exists() or is_diff_ignore_eol(file, dest_file_path):
                shutil.copy2(file, dest_file_path)


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

    artifacts_dir = BSP_ARTIFACT_DIR
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
    except subprocess.CalledProcessError as exc:
        LOG(f"\nCommand failed with exit code {exc.returncode}", file=sys.stderr)
        sys.exit(exc.returncode)
    except KeyboardInterrupt:
        LOG("\nAborted by user.", file=sys.stderr)
        sys.exit(1)
