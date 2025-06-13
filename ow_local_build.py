#!/usr/bin/env python3
"""
OneWeb SW-Tools interactive local build helper (top-down, manifest-aware).
"""

# Example usage:
# python3 ~/ow_sw_tools/v_test_folder/LocalBuild/ow_local_build.py --manifest_source local --make_target arm --branch test_ins_shm_rgnss

import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Union
import argparse

# ─────────────────────────────  constants  ───────────────────────────── #
OW_PATH = Path.home() / "ow_sw_tools"
BUILD_FOLDER = OW_PATH / "tmp_build"
CORE_REPOS = Path.home() / "workspace" / "intellian_core_repos"
MANIFEST_FILE_NAME = "iesa_manifest_gitlab.xml"
MANIFEST_RELATIVE_PATH = f"tools/manifests/{MANIFEST_FILE_NAME}"
MANIFEST_FILE = OW_PATH / MANIFEST_RELATIVE_PATH

# ─────────────────────────────  top-level  ───────────────────────────── #


def main() -> None:
    parser = argparse.ArgumentParser(description="OneWeb SW-Tools local build helper.")
    parser.add_argument("--manifest_source", choices=["local", "remote"], default="local",
                        help="Source for the manifest repository URL (local or remote). Defaults to local.")
    parser.add_argument("--make_target", type=str, default="arm",
                        help="The make target to run in the docker container. Defaults to 'arm'.")
    parser.add_argument("-b", "--branch", type=str, default="master",
                        help="Branch of oneweb_project_sw_tools for manifest. Defaults to 'master'.")

    args = parser.parse_args()
    print(
        textwrap.dedent(
            """\
            -------------------------------
            OneWeb local build orchestrator
            -------------------------------"""
        )
    )

    reset_or_create_tmp_build()
    manifest_repo_url = get_manifest_repo_url(args.manifest_source)
    init_and_sync(manifest_repo_url, args.branch)

    # {repo → relative path from build folder}, use local as they should be the same
    path_mapping: Dict[str, str] = parse_local_manifest()
    repo_names: List[str] = choose_repos(path_mapping)

    if repo_names:
        for repo in repo_names:
            sync_code(path_mapping[repo])

        changed_any: bool = any(show_changes(r, path_mapping[r]) for r in repo_names)
        if not changed_any:
            print("\nNo files changed in selected repos.")

    run_build(args.make_target)


# ───────────────────────────  helpers / actions  ─────────────────────── #
def run(cmd: Union[str, List[str]], cwd: Optional[Path] = None, check: bool = True) -> None:
    """Run a shell command, echoing it."""
    print(f"\n>>> {cmd} (cwd={cwd or Path.cwd()})")
    subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd, check=check)


def prompt_branch() -> str:
    default = "master"
    branch = input(f"Branch of oneweb_project_sw_tools for manifest, default = {default}: ").strip()
    return branch or default


def reset_or_create_tmp_build() -> None:
    repo_dir = BUILD_FOLDER / '.repo'
    manifest_file = repo_dir / 'manifest.xml'  # .repo/manifest.xml stored the manifest you get from the repo

    if BUILD_FOLDER.exists():
        # Check if it's a valid repo: both .repo folder AND manifest.xml must exist
        if repo_dir.is_dir() and manifest_file.is_file():
            print(f"Reseting existing repo in {BUILD_FOLDER}...")
            try:
                run("repo forall -c 'git reset --hard' && repo forall -c 'git clean -fdx'", cwd=BUILD_FOLDER)
            except subprocess.CalledProcessError:
                # If 'repo forall' fails (e.g., due to a broken manifest, launcher issues, etc.)
                # Treat it as a broken repo and clear it.
                print(f"Warning: 'repo forall' failed in {BUILD_FOLDER}. Assuming broken repo and clearing...")
                run("sudo rm -rf " + str(BUILD_FOLDER))
                BUILD_FOLDER.mkdir(parents=True)
        else:
            # If BUILD_FOLDER exists, but it's not a fully functional repo (missing .repo or manifest)
            print(f"\nClearing broken or non-repo folder {BUILD_FOLDER} (missing .repo or manifest.xml)...")
            run("sudo rm -rf " + str(BUILD_FOLDER))
            BUILD_FOLDER.mkdir(parents=True)
    else:
        # If the folder doesn't exist at all, create it
        BUILD_FOLDER.mkdir(parents=True)


def init_and_sync(manifest_repo_url: str, branch: str) -> None:
    # TODO: BUG - seem like repo init still use wrong manifest.xml in case of local file://
    run(f"repo init {manifest_repo_url} -b {branch} -m {MANIFEST_RELATIVE_PATH}", cwd=BUILD_FOLDER,)

    # Get manifest repository info
    print("\n--- Manifest Repository Info ---")
    try:
        run("git remote -v", cwd=os.path.join(BUILD_FOLDER, ".repo", "manifests"))
        run("git branch --show-current", cwd=os.path.join(BUILD_FOLDER, ".repo", "manifests"))
    except Exception as e:
        print(f"Error getting manifest repo info: {e}")
    print("--- End Manifest Repository Info ---\n")

    # Construct the full path to the manifest file
    manifest_full_path = os.path.join(BUILD_FOLDER, ".repo", "manifests", MANIFEST_RELATIVE_PATH)
    # Check if the manifest file exists before trying to read it
    if os.path.exists(manifest_full_path):
        print(f"--- Manifest Content ({manifest_full_path}) ---")
        try:
            with open(manifest_full_path, 'r') as f:
                print(f.read())
        except Exception as e:
            print(f"Error reading manifest file: {e}")
        print("--- End Manifest Content ---")
    else:
        print(
            f"Manifest file not found at: {manifest_full_path}. This might happen if {MANIFEST_FILE_NAME} was not found in the manifest repository.")

    run("repo sync", cwd=BUILD_FOLDER)


def parse_local_manifest(manifest_file: Path = MANIFEST_FILE) -> Dict[str, str]:
    """Return {project-name → path} from the manifest XML."""
    if not manifest_file.is_file():
        print(f"ERROR: manifest not found at {manifest_file}", file=sys.stderr)
        sys.exit(1)

    tree = ET.parse(manifest_file)
    mapping: Dict[str, str] = {}
    for proj in tree.getroot().iterfind("project"):
        name = proj.attrib.get("name")
        path = proj.attrib.get("path")
        if name and path:
            if name in mapping:
                print(f"ERROR: duplicate project name \"{name}\" in manifest", file=sys.stderr)
                sys.exit(1)

            mapping[name] = path
    return mapping


def choose_repos(mapping: Dict[str, str]) -> List[str]:
    print("\nAvailable repositories from manifest (<repo name> -> <relative path>):")
    for name, path in sorted(mapping.items()):
        print(f"  {name:<20} → {path}")

    picked: List[str] = []
    while True:
        repo = input(f"[Optional] Repo name to copy from local in {CORE_REPOS} (enter blank to stop): ").strip()
        if not repo:
            break
        if repo not in mapping:
            print(f"Repo \"{repo}\" not listed in manifest. Try again.")
            continue
        print(f"Selected: \"{repo}\"")
        picked.append(repo)

    return picked


def sync_code(repo_folder_rel_path: str) -> None:
    repo_folder_name = Path(repo_folder_rel_path).name
    src = CORE_REPOS / repo_folder_name
    dst = BUILD_FOLDER / repo_folder_rel_path
    if not src.is_dir() or not dst.is_dir():
        print(f"ERROR: Source or destination not found at {src} or {dst}", file=sys.stderr)
        sys.exit(1)
        return
    print("Copying from", src, "to", dst)
    rsync_command = [
        "rsync",
        "-avc",  # -a: archive mode, -v: verbose, -c: --checksum (for content comparison)
        # "--delete", # IMPORTANT: If you want to remove files in destination that are not in source
        "--exclude=.git/",
        "--exclude=.vscode/",
        str(src) + "/",  # Source with trailing slash to copy contents, not the folder itself
        str(dst)        # Destination without trailing slash
    ]

    run(rsync_command)


def show_changes(repo_name: str, rel_path: str) -> bool:
    repo_path = BUILD_FOLDER / rel_path
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    changes: List[str] = [line for line in res.stdout.splitlines() if line.strip()]
    if changes:
        print(f"\nChanges in {repo_name} ({rel_path}):")
        for line in changes:
            print(" ", line)
    else:
        print(f"\nNo changes detected in {repo_name}.")
    return bool(changes)


def confirm_build() -> bool:
    return input("\nProceed with docker build (make arm)? [y/N]: ").lower() == "y"


def get_manifest_repo_url(source: str) -> str:
    if source == "remote":
        return "https://gitlab.com/intellian_adc/oneweb_project_sw_tools"
    else:  # source == "local"
        return f"file://{OW_PATH}"


def run_build(make_target: str) -> None:
    run(
        f"docker run -it --rm -v {OW_PATH}:{OW_PATH} -w {OW_PATH} "
        f"oneweb_sw bash -c 'make {make_target}'"
    )


# ───────────────────────  module entry-point  ────────────────────────── #
if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"\nCommand failed with exit code {exc.returncode}", file=sys.stderr)
        sys.exit(exc.returncode)
    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        sys.exit(1)
