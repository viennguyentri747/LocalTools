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
from utils import get_file_md5sum, LOG, is_diff_ignore_eol
from constants import GL_TISDK_TOKEN_KEY_NAME, LINE_SEPARATOR

# ─────────────────────────────  constants  ───────────────────────────── #
BUILD_TYPE_IESA = "iesa"
BUILD_TYPE_BINARY = "binary"
CORE_REPOS_PATH = Path.home() / "workspace" / "intellian_core_repos"
OW_SW_PATH = Path.home() / "ow_sw_tools"
# OW_SW_PATH = CORE_REPOS_PATH / "ow_sw_tools"
BUILD_FOLDER_PATH = OW_SW_PATH / "tmp_build"
SCRIPT_FOLDER_PATH = OW_SW_PATH / "v_test_folder" / "LocalBuild"
CREDENTIAL_FILE_PATH = SCRIPT_FOLDER_PATH / ".gitlab_credentials"
MANIFEST_FILE_NAME = "iesa_manifest_gitlab.xml"
MANIFEST_RELATIVE_PATH = f"tools/manifests/{MANIFEST_FILE_NAME}"
MANIFEST_FILE_PATH = OW_SW_PATH / MANIFEST_RELATIVE_PATH
BSP_ARTIFACT_DIR = SCRIPT_FOLDER_PATH / "bsp_artifacts"
BSP_ARTIFACT_PREFIX = "bsp-iesa-"
BSP_SYMLINK_PATH_FOR_BUILD = OW_SW_PATH / "packaging" / "bsp_current" / "bsp_current.tar.xz"

# ─────────────────────────────  top-level  ───────────────────────────── #


def main() -> None:
    parser = argparse.ArgumentParser(description="OneWeb SW-Tools local build helper.")
    parser.add_argument("--manifest_source", choices=["local", "remote"], default="local",
                        help="Source for the manifest repository URL (local or remote). Defaults to local.")
    parser.add_argument("--build_type", choices=[BUILD_TYPE_BINARY, BUILD_TYPE_IESA], type=str, default=BUILD_TYPE_BINARY,
                        help="Build type (binary or iesa). Defaults to binary.")
    parser.add_argument("-b", "--ow_manifest_branch", type=str,
                        help="Branch of oneweb_project_sw_tools for manifest. Ex: 'manpack_master'")
    parser.add_argument("--tisdk_branch", type=str, required=True, help="TISDK branch for BSP. Ex: 'manpack_master'")
    parser.add_argument("--overwrite_local", type=lambda x: x.lower() == 'true', default=False, help="Enable overwriting local repositories (true or false). Defaults to false.")
    parser.add_argument("--overwrite_repos", nargs='*', default=[], help="List of repository names to overwrite from local. If empty and --overwrite_local is true, prompts user.")
    parser.add_argument("-i", "--interactive", type=lambda x: x.lower() == 'true', default=False, help="Run in interactive mode (true or false). Defaults to false.")
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
    pre_build(build_type, args.manifest_source, args.ow_manifest_branch, args.tisdk_branch, args.overwrite_local, args.overwrite_repos)
    run_build(build_type, args.interactive)


# ───────────────────────────  helpers / actions  ─────────────────────── #
def run_shell(cmd: str, cwd: Optional[Path] = None, check_exit_code: bool = True) -> None:
    """Echo + run a shell command"""
    LOG(f"\n>>> {cmd} (cwd={cwd or Path.cwd()})")
    subprocess.run(cmd, shell=True, cwd=cwd, check=check_exit_code)


def prompt_branch() -> str:
    default = "master"
    branch = input(f"Branch of oneweb_project_sw_tools for manifest, default = {default}: ").strip()
    return branch or default


def pre_build(build_type: str, manifest_source: str, ow_manifest_branch: str, tisdk_branch: str, overwrite_local: bool, overwrite_repos: List[str]) -> None:
    reset_or_create_tmp_build()
    manifest_repo_url = get_manifest_repo_url(manifest_source)
    init_and_sync(manifest_repo_url, ow_manifest_branch)

    # {repo → relative path from build folder}, use local as they should be the same
    path_mapping: Dict[str, str] = parse_local_manifest()

    repo_names: List[str] = []
    if overwrite_local:
        if not overwrite_repos:
            repo_names = choose_repos(path_mapping)
        else:
            repo_names = overwrite_repos
            LOG(f"\nOverwriting local code for specified repos: {repo_names}")

        # Copy local code to overwrite code from remote before build
        if repo_names:
            for repo in repo_names:
                if repo not in path_mapping:
                    LOG(f"Warning: Specified repo \"{repo}\" not found in manifest. Skipping.", file=sys.stderr)
                    continue
                sync_code(path_mapping[repo])

            changed_any: bool = any(show_changes(r, path_mapping[r]) for r in repo_names if r in path_mapping)
            if not changed_any:
                LOG("\nNo files changed in selected repos.")

    if build_type == BUILD_TYPE_IESA:
        prepare_iesa_bsp(BSP_ARTIFACT_DIR, tisdk_branch)


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
        LOG(LINE_SEPARATOR)
        LOG(f"Entering interactive mode.")
        LOG(f"Run 'make {make_target}' to start {build_type} building.")
        LOG(f"Type 'exit' or press Ctrl+D to leave interactive mode.")
        run_shell(docker_cmd + "bash", check_exit_code=False)
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


def init_and_sync(manifest_repo_url: str, manifest_repo_branch: str) -> None:
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
        path = proj.attrib.get("path")
        if name and path:
            if name in mapping:
                LOG(f"ERROR: duplicate project name \"{name}\" in manifest", file=sys.stderr)
                sys.exit(1)

            mapping[name] = path
    return mapping


def choose_repos(mapping: Dict[str, str]) -> List[str]:
    LOG("\nAvailable repositories from manifest (<repo name> -> <relative path>):")
    for name, path in sorted(mapping.items()):
        LOG(f"  {name:<20} → {path}")

    picked: List[str] = []
    while True:
        repo = input(f"[Optional] Repo name to copy from local in {CORE_REPOS_PATH} (enter blank to stop): ").strip()
        if not repo:
            break
        if repo not in mapping:
            LOG(f"Repo \"{repo}\" not listed in manifest. Try again.")
            continue
        LOG(f"Selected: \"{repo}\"")
        picked.append(repo)

    return picked

def sync_code(repo_folder_rel_path: str) -> None:
    repo_folder_name = Path(repo_folder_rel_path).name
    src_path = CORE_REPOS_PATH / repo_folder_name
    dest_root_path = BUILD_FOLDER_PATH / repo_folder_rel_path

    if not src_path.is_dir() or not dest_root_path.is_dir():
        LOG(f"ERROR: Source or destination not found at {src_path} or {dest_root_path}", file=sys.stderr)
        sys.exit(1)
        return

    LOG("Copying from", src_path, "to", dest_root_path)

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
    res = subprocess.run(
        ["git", "status", "--porcelain"],
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


def get_manifest_repo_url(source: str) -> str:
    if source == "remote":
        return "https://gitlab.com/intellian_adc/oneweb_project_sw_tools"
    elif source == "local":
        return f"file://{OW_SW_PATH}"
    else:
        raise ValueError(f"Unknown source: {source}, expected 'remote' or 'local'")


def prepare_iesa_bsp(artifacts_dir: str, tisdk_branch: str):
    # Logic to read token from file if not in env
    private_token = read_token_from_file(CREDENTIAL_FILE_PATH, GL_TISDK_TOKEN_KEY_NAME)
    if not private_token:
        LOG("Error: GitLab private token not found in credentials file.")
        sys.exit(1)

    # Details of the target project and job
    target_project_path = "intellian_adc/tisdk_tools"
    target_job_name = "sdk_create_tarball_release"
    target_ref = tisdk_branch

    # Get the target project using the new function
    target_project = get_gl_project(private_token, target_project_path)

    # For robust fetching of branch names, consider get_all=True here too if you're not sure the default is sufficient.
    LOG(f"Target project: {target_project_path}, instance: {target_project.branches.list(get_all=True)[0].name}")

    pipeline_id = get_latest_successful_pipeline_id(target_project, target_job_name, target_ref)
    if not pipeline_id:
        LOG(f"No successful pipeline found for job '{target_job_name}' on ref '{target_ref}'.")
        sys.exit(1)

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
