from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple, Union
from dev_common.constants import *
from dev_common.core_utils import *
from dev_common.format_utils import get_path_no_suffix
import xml.etree.ElementTree as ElementTree
from dev_common.gitlab_utils import *
from concurrent.futures import ThreadPoolExecutor, as_completed


class IesaManifest:
    """A class to represent the manifest data and provide helper functions."""

    def __init__(self, mapping: Dict[str, Tuple[str, str, str]]):
        self._mapping = mapping

    def get_repo_relative_path_vs_tmp_build(self, repo_name: str) -> Optional[str]:
        """Returns the relative path of a repository vs the tmp_build folder."""
        if repo_name in self._mapping:
            return self._mapping[repo_name][0]
        else:
            LOG(f"Repo'{repo_name}' not found in manifest")
            return None

    def get_repo_revision(self, repo_name: str) -> Optional[str]:
        """Returns the revision of a repository."""
        if repo_name in self._mapping:
            return self._mapping[repo_name][1]
        else:
            LOG(f"Repo'{repo_name}' not found in manifest")
            return None

    def get_repo_remote(self, repo_name: str) -> Optional[str]:
        """Returns the remote of a repository."""
        if repo_name in self._mapping:
            return self._mapping[repo_name][2]
        else:
            LOG(f"Repo'{repo_name}' not found in manifest")
            return None

    def get_all_repo_names(self, include_ow_sw_repos: bool = False) -> List[str]:
        """Returns a list of all repository names."""
        base_list = list(self._mapping.keys())
        if include_ow_sw_repos:
            base_list.insert(0, IESA_OW_SW_TOOLS_REPO_NAME)
        return base_list

    def to_serializable_dict(self) -> Dict[str, Dict[str, str]]:
        """Return manifest data as a JSON-friendly dict."""
        return {
            repo_name: {
                "relative_path_vs_tmp_build": path,
                "revision": revision,
                "remote": remote,
            }
            for repo_name, (path, revision, remote) in self._mapping.items()
        }


def _parse_iesa_projects(root: ElementTree.Element, ignored_project_names: List[str] = []) -> Dict[str, Tuple[str, str, str]]:
    """Parse project elements from manifest XML root and return mapping."""
    mapping: Dict[str, Tuple[str, str, str]] = {}
    for proj in root.iterfind("project"):
        name = proj.attrib.get("name")
        name = get_path_no_suffix(name, GIT_SUFFIX)
        path = proj.attrib.get("path")
        revision = proj.attrib.get("revision")
        remote = proj.attrib.get("remote")
        
        if name and path and revision and remote:
            if name in mapping:
                LOG(f"ERROR: duplicate project name \"{name}\" in manifest", file=sys.stderr)
                sys.exit(1)
            if name in ignored_project_names:
                LOG(f"Skipping ignored project \"{name}\" in manifest")
                continue
            mapping[name] = (path, revision, remote)

    return mapping


def parse_local_gl_iesa_manifest(manifest_path_or_str: Union[Path, str] = IESA_MANIFEST_FILE_PATH_LOCAL, ignored_project_names: List[str] = [ "third_party_apps" ]) -> IesaManifest:
    """Return a Manifest object from the manifest XML."""
    manifest_path = Path(manifest_path_or_str)
    if not manifest_path.is_file():
        LOG(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    tree = ElementTree.parse(manifest_path)
    mapping = _parse_iesa_projects(tree.getroot(), ignored_project_names)
    return IesaManifest(mapping)


def parse_remote_gl_iesa_manifest(manifest_content: str, ignored_project_names: List[str] = [ "third_party_apps" ]) -> IesaManifest:
    """Return a Manifest object from the manifest XML string content."""
    root = ElementTree.fromstring(manifest_content)
    mapping = _parse_iesa_projects(root, ignored_project_names)
    return IesaManifest(mapping)


def is_manifest_valid(manifest: IesaManifest):
    LOG("Verifying manifest refs exist on remote...")
    missing_refs: list[str] = []

    for repo_name in manifest.get_all_repo_names():
        revision = manifest.get_repo_revision(repo_name)
        repo_info = get_repo_info_by_name(repo_name)

        if not repo_info:
            LOG(f"Warning: Could not find local configuration for '{repo_name}'. Skipping remote branch check.")
            continue

        gl_project = get_gl_project(repo_info)
        LOG(f" -> Verifying branch '{revision}' for repo '{repo_info.gl_project_path}'...")

        if is_gl_ref_exists(gl_project, revision):
            LOG(f"    Ref '{revision}' exists on remote.")
        else:
            LOG(f"    Ref '{revision}' does NOT exist on remote!")
            missing_refs.append(
                f" - Repo: {repo_info.gl_project_path}\n"
                f"   Branch: '{revision}'"
            )

    if missing_refs:
        LOG_EXCEPTION_STR(
            "One or more branches in the manifest could not be found on the remote server. "
            "Please ensure the following branches are pushed to their respective repositories:\n"
            + "\n".join(missing_refs)
        )
    else:
        LOG("All manifest branches successfully verified on their remotes. 👍")
        return True
