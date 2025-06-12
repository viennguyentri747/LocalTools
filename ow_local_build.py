#!/usr/bin/env python3
"""
OneWeb SW-Tools interactive local build helper (top-down, manifest-aware).

High-level flow
---------------
main()
 ├─ prompt_branch()                 → ask branch name
 ├─ reset_or_create_tmp_build()     → clean / create tmp_build
 ├─ init_and_sync()                 → repo init + repo sync
 ├─ parse_manifest()                → build {project-name: path} map
 ├─ choose_repos()                  → let user pick repo names
 ├─ sync_code()                     → rsync from core → manifest path
 ├─ show_changes()                  → git status for each selected repo
 ├─ confirm_build()                 → y/N prompt
 └─ run_build()                     → docker run make arm
"""

from pathlib import Path
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Union

# ─────────────────────────────  constants  ───────────────────────────── #
OW_PATH = Path.home() / "ow_sw_tools"
BUILD_FOLDER = OW_PATH / "tmp_build"
CORE_REPOS = Path.home() / "workspace" / "intellian_core_repos"
MANIFEST_RELATIVE_PATH = "tools/manifests/iesa_manifest_gitlab.xml"
MANIFEST_FILE = OW_PATH / MANIFEST_RELATIVE_PATH

# ─────────────────────────────  top-level  ───────────────────────────── #


def main() -> None:
    print(
        textwrap.dedent(
            """\
            -------------------------------
            OneWeb local build orchestrator
            -------------------------------"""
        )
    )

    branch: str = prompt_branch()
    reset_or_create_tmp_build()
    manifest_repo_url = get_manifest_repo_url()
    init_and_sync(manifest_repo_url, branch)

    path_mapping: Dict[str, str] = parse_manifest()  # {repo → relative path from build folder}
    repo_names: List[str] = choose_repos(path_mapping)

    if repo_names:
        for repo in repo_names:
            sync_code(path_mapping[repo])

        changed_any: bool = any(show_changes(r, path_mapping[r]) for r in repo_names)
        if not changed_any:
            print("\nNo files changed in selected repos.")

    if confirm_build():
        run_build()
    else:
        print("Build skipped.")


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
    if BUILD_FOLDER.exists():
        print(f"\nFound existing {BUILD_FOLDER}. -> Cleaning...")
        run(
            "repo forall -c 'git reset --hard' && repo forall -c 'git clean -fdx'",
            cwd=BUILD_FOLDER,
        )
    else:
        BUILD_FOLDER.mkdir(parents=True)


def init_and_sync(manifest_repo_url: str, branch: str) -> None:
    run(f"repo init {manifest_repo_url} -b {branch} -m {MANIFEST_RELATIVE_PATH}",cwd=BUILD_FOLDER,)
    run("repo sync", cwd=BUILD_FOLDER)


def parse_manifest(manifest_file: Path = MANIFEST_FILE) -> Dict[str, str]:
    """Return {project-name → path} from the manifest XML."""
    if not manifest_file.is_file():
        print(f"ERROR: manifest not found at {manifest_file}")
        sys.exit(1)

    tree = ET.parse(manifest_file)
    mapping: Dict[str, str] = {}
    for proj in tree.getroot().iterfind("project"):
        name = proj.attrib.get("name")
        path = proj.attrib.get("path")
        if name and path:
            if name in mapping:
                print(f"ERROR: duplicate project name \"{name}\" in manifest")
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
        print(f"ERROR: Source or destination not found at {src} or {dst}")
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

def get_manifest_repo_url() -> str:
    if(input("Use remote url instead local? [y/N]: ").lower() == "y"):
        return "https://gitlab.com/intellian_adc/oneweb_project_sw_tools"
    else:
        return f"file://{OW_PATH}"

def run_build() -> None:
    run(
        f"docker run -it --rm -v {OW_PATH}:{OW_PATH} -w {OW_PATH} "
        "oneweb_sw bash -c 'make arm'"
    )


# ───────────────────────  module entry-point  ────────────────────────── #
if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"\nCommand failed with exit code {exc.returncode}", file=sys.stderr)
        sys.exit(exc.returncode)
