from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple
from dev_common.constants import GIT_SUFFIX, IESA_MANIFEST_FILE_PATH
from dev_common.core_utils import LOG
from dev_common.format_utils import get_path_no_suffix
import xml.etree.ElementTree as ElementTree

class IesaManifest:
    """A class to represent the manifest data and provide helper functions."""

    def __init__(self, mapping: Dict[str, Tuple[str, str, str]]):
        self._mapping = mapping
    def get_repo_relative_path_vs_tmp_build(self, repo_name: str) -> Optional[str]:

        """Returns the relative path of a repository vs the tmp_build folder."""
        if repo_name in self._mapping:
            return self._mapping[repo_name][0]
        return None

    def get_repo_revision(self, repo_name: str) -> Optional[str]:
        """Returns the revision of a repository."""
        if repo_name in self._mapping:
            return self._mapping[repo_name][1]
        return None

    def get_repo_remote(self, repo_name: str) -> Optional[str]:
        """Returns the remote of a repository."""
        if repo_name in self._mapping:
            return self._mapping[repo_name][2]
        return None

    def get_all_repo_names(self) -> List[str]:
        """Returns a list of all repository names."""
        return list(self._mapping.keys())


def parse_local_iesa_manifest(manifest_file: Path = IESA_MANIFEST_FILE_PATH) -> IesaManifest:
    """Return a Manifest object from the manifest XML."""
    if not manifest_file.is_file():
        LOG(f"ERROR: manifest not found at {manifest_file}", file=sys.stderr)
        sys.exit(1)

    tree = ElementTree.parse(manifest_file)
    mapping: Dict[str, Tuple[str, str, str]] = {}
    for proj in tree.getroot().iterfind("project"):
        name = proj.attrib.get("name")
        name = get_path_no_suffix(name, GIT_SUFFIX)
        path = proj.attrib.get("path")
        revision = proj.attrib.get("revision")
        remote = proj.attrib.get("remote")

        if name and path and revision and remote:
            if name in mapping:
                LOG(f"ERROR: duplicate project name \"{name}\" in manifest", file=sys.stderr)
                sys.exit(1)

            mapping[name] = (path, revision, remote)
    return IesaManifest(mapping)