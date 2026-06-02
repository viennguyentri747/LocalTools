from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple, Union
from dev.dev_common.constants import *
from dev.dev_common.core_independent_utils import *
from dev.dev_common.format_utils import get_path_no_suffix
import xml.etree.ElementTree as ElementTree
from dev.dev_common.gitlab_utils import *
from concurrent.futures import ThreadPoolExecutor, as_completed


class IesaManifest:
    """A class to represent the manifest data and provide helper functions."""

    def __init__(self, mapping: Dict[str, Tuple[str, str, str]], remotes: Dict[str, str]):
        # project mapping: repo_name -> (path, revision, remote_alias)
        self._mapping = mapping
        # remote mapping: remote_alias -> fetch_url from <remote name="..." fetch="..."/>
        self._remotes: Dict[str, str] = remotes

    def get_repo_relative_path_vs_tmp_build(self, repo_name: str) -> Optional[str]:
        """Returns the relative path of a repository vs the tmp_build folder."""
        if repo_name in self._mapping:
            return self._mapping[repo_name][0]
        else:
            LOG(f"Repo'{repo_name}' not found in manifest")
            return None

    def get_repo_path(self, repo_name: str) -> Optional[str]:
        """Alias for manifest project path."""
        return self.get_repo_relative_path_vs_tmp_build(repo_name)

    def get_repo_revision(self, repo_name: str) -> Optional[str]:
        """Returns the revision of a repository."""
        if repo_name in self._mapping:
            return self._mapping[repo_name][1]
        else:
            LOG(f"Repo'{repo_name}' not found in manifest")
            return None

    def _get_repo_remote_alias(self, repo_name: str) -> Optional[str]:
        """Returns the remote of a repository. Not useful for outer usage since they are aliases"""
        if repo_name in self._mapping:
            return self._mapping[repo_name][2]
        else:
            LOG(f"Repo'{repo_name}' not found in manifest")
            return None

    def get_repo_remote_alias(self, repo_name: str) -> Optional[str]:
        """Returns remote alias of a repository."""
        return self._get_repo_remote_alias(repo_name)

    def _get_remote_fetch_url_by_repo_name(self, repo_name: str) -> Optional[str]:
        """Returns fetch URL by repository name via project's remote alias."""
        remote_alias = self._get_repo_remote_alias(repo_name)
        if not remote_alias:
            return None
        fetch_url = self._remotes.get(remote_alias)
        if not fetch_url:
            LOG(f"Remote alias '{remote_alias}' of repo '{repo_name}' not found in manifest remotes")
            return None
        return fetch_url

    def get_full_repo_url_by_repo_name(self, repo_name: str) -> Optional[str]:
        """Returns full repo URL (fetch base URL + repo name)."""
        fetch_url = self._get_remote_fetch_url_by_repo_name(repo_name)
        if not fetch_url:
            return None
        return fetch_url.rstrip("/") + "/" + repo_name

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


def parse_iesa_manifest(root: ElementTree.Element, ignored_project_names: Optional[List[str]] = None) -> IesaManifest:
    """Parse manifest XML root and return IesaManifest."""
    ignored_name_set = set(ignored_project_names or [])
    remotes: Dict[str, str] = {}
    for remote_elem in root.iterfind("remote"):
        remote_name = remote_elem.attrib.get("name")
        fetch_url = remote_elem.attrib.get("fetch")
        if not remote_name or not fetch_url:
            continue
        remotes[remote_name] = fetch_url

    mapping: Dict[str, Tuple[str, str, str]] = {}
    for proj in root.iterfind("project"):
        name = proj.attrib.get("name")
        if not name:
            continue
        name = get_path_no_suffix(name, GIT_SUFFIX)
        path = proj.attrib.get("path")
        revision = proj.attrib.get("revision")
        remote = proj.attrib.get("remote")

        if name and path and revision and remote:
            if name in mapping:
                LOG(f"ERROR: duplicate project name \"{name}\" in manifest", file=sys.stderr)
                sys.exit(1)
            if name in ignored_name_set:
                LOG(f"Skipping ignored project \"{name}\" in manifest")
                continue
            mapping[name] = (path, revision, remote)

    return IesaManifest(mapping=mapping, remotes=remotes)


def parse_local_gl_iesa_manifest(manifest_path_or_str: Union[Path, str] = IESA_MANIFEST_FILE_PATH_LOCAL_PATH, ignored_project_names: Optional[List[str]] = None) -> IesaManifest:
    """Return a Manifest object from the manifest XML."""
    if ignored_project_names is None:
        ignored_project_names = []
    manifest_path = Path(manifest_path_or_str)
    if not manifest_path.is_file():
        LOG(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    tree = ElementTree.parse(manifest_path)
    return parse_iesa_manifest(tree.getroot(), ignored_project_names)


def parse_remote_gl_iesa_manifest(manifest_content: str, ignored_project_names: Optional[List[str]] = None) -> IesaManifest:
    """Return a Manifest object from the manifest XML string content."""
    if ignored_project_names is None:
        ignored_project_names = []
    root = ElementTree.fromstring(manifest_content)
    return parse_iesa_manifest(root, ignored_project_names)


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
