from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable, Dict, List, Any
from dev_common import *
from dev_common.constants import *


class IesaLocalRepoInfo:
    def __init__(self, repo_name: str, repo_local_path: Path, gl_project_path: str, token_key_name: str):
        self._repo_name = repo_name
        self._token_key_name = token_key_name
        self._repo_local_path = repo_local_path
        self._gl_project_path = gl_project_path  # group/subgroup/repo/, expected to be unique

    @property
    def repo_name(self) -> str:
        return self._repo_name

    @property
    def gl_access_token(self) -> str:
        private_token = read_value_from_credential_file(CREDENTIALS_FILE_PATH, self._token_key_name)
        return private_token

    @property
    def repo_local_path(self) -> Path:
        return self._repo_local_path

    @property
    def gl_project_path(self) -> str:
        return self._gl_project_path


class LocalReposMapping:
    def __init__(self, *repos: IesaLocalRepoInfo):
        self._repos = {repo.repo_name: repo for repo in repos}

    def get_by_name(self, repo_name: str) -> IesaLocalRepoInfo | None:
        return self._repos.get(repo_name)

    def get_by_url(self, repo_url: str) -> IesaLocalRepoInfo | None:
        repo_name = re.search(r'/([^/]+?)(?:\.git)?$', repo_url)
        if repo_name:
            return self.get_by_name(repo_name.group(1))
        return None

    def get_by_gl_project_path(self, project_path: str) -> IesaLocalRepoInfo | None:
        for repo in self._repos.values():
            if repo.gl_project_path == project_path:
                return repo
        LOG(f"Error: Could not find a local repository mapping for the provided project path: {project_path}")
        return None

    def __iter__(self):
        return iter(self._repos.values())


LOCAL_REPO_MAPPING: LocalReposMapping = LocalReposMapping(
    IesaLocalRepoInfo(
        IESA_OW_SW_TOOLS_REPO_NAME,
        repo_local_path=OW_SW_PATH,
        gl_project_path=f"{INTELLIAN_ADC_GROUP}/{IESA_OW_SW_TOOLS_REPO_NAME}",
        token_key_name=GL_OW_SW_TOOLS_TOKEN_KEY_NAME
    ),

    IesaLocalRepoInfo(
        IESA_TISDK_TOOLS_REPO_NAME,
        repo_local_path=CORE_REPOS_PATH / IESA_TISDK_TOOLS_REPO_NAME,
        gl_project_path=f"{INTELLIAN_ADC_GROUP}/{IESA_TISDK_TOOLS_REPO_NAME}",
        token_key_name=GL_TISDK_TOKEN_KEY_NAME
    ),

    IesaLocalRepoInfo(
        IESA_INSENSE_SDK_REPO_NAME,
        repo_local_path=INSENSE_SDK_REPO_PATH,
        gl_project_path=f"{INTELLIAN_ADC_GROUP}/{PROTOTYPING_SUB_GROUP}/{IESA_INSENSE_SDK_REPO_NAME}",
        token_key_name=GL_INSENSE_SDK_TOKEN_KEY_NAME
    ),

    IesaLocalRepoInfo(
        IESA_INTELLIAN_PKG_REPO_NAME,
        repo_local_path=CORE_REPOS_PATH / IESA_INTELLIAN_PKG_REPO_NAME,
        gl_project_path=f"{INTELLIAN_ADC_GROUP}/{GERRIT_OW}/{IESA_INTELLIAN_PKG_REPO_NAME}",
        token_key_name=GL_INTELLIAN_PKG_TOKEN_KEY_NAME
    ),

    IesaLocalRepoInfo(
        IESA_ADC_LIB_REPO_NAME,
        repo_local_path=CORE_REPOS_PATH / IESA_ADC_LIB_REPO_NAME,
        gl_project_path=f"{INTELLIAN_ADC_GROUP}/{IESA_ADC_LIB_REPO_NAME}",
        token_key_name=GL_ADC_LIB_TOKEN_KEY_NAME
    ),

    IesaLocalRepoInfo(
        IESA_SPIBEAM_REPO_NAME,
        repo_local_path=CORE_REPOS_PATH / IESA_SPIBEAM_REPO_NAME,
        gl_project_path=f"{INTELLIAN_ADC_GROUP}/{IESA_SPIBEAM_REPO_NAME}",
        token_key_name=GL_SPIBEAM_TOKEN_KEY_NAME
    ),

    IesaLocalRepoInfo(
        IESA_UPGRADE_REPO_NAME,
        repo_local_path=CORE_REPOS_PATH / IESA_UPGRADE_REPO_NAME,
        gl_project_path=f"{INTELLIAN_ADC_GROUP}/{GERRIT_OW}/{IESA_UPGRADE_REPO_NAME}",
        token_key_name=GL_UPGRADE_TOKEN_KEY_NAME
    ),
)


class MatchInfo:
    def __init__(self, patterns_to_match, separator):
        self._patterns_to_match = patterns_to_match
        self._separator = separator
        self._match_map: Dict[str, List[str]] = {pattern: [] for pattern in patterns_to_match}

    def add_match(self, pattern, matched_line: str):
        if pattern in self._match_map:
            self._match_map[pattern].append(matched_line)

    def get_matched_lines(self, pattern: str) -> List[str]:
        return self._match_map.get(pattern, [])

    def get_patterns(self) -> List[str]:
        return self._patterns_to_match


@dataclass
class ToolTemplate:
    name: str
    extra_description: str
    args: Dict[str, Any]  # {arg_name: arg_value}
    search_root: Optional[Path]
    no_need_live_edit: bool
    usage_note: str = ""
    run_now_without_modify: bool = False
    should_hidden: bool = False
    is_use_win_python: bool = False

    def __init__(self, name: str, extra_description: str = "", args: Dict[str, Any] = {}, search_root: Optional[Path] = None, no_need_live_edit: bool = True, usage_note: str = "", should_run_now: bool = False, hidden: bool = False, is_use_win_python: bool = False):
        self.name = name
        self.extra_description = extra_description
        self.args = args
        self.search_root = search_root
        self.no_need_live_edit = no_need_live_edit
        self.usage_note = usage_note
        self.run_now_without_modify = should_run_now
        self.should_hidden = hidden
        self.is_use_win_python = is_use_win_python

@dataclass(frozen=True)
class ForwardedTool:
    """Represents a test tool that can be forwarded through this entry point."""

    mode: str
    description: str
    main: Callable[..., None]
    get_templates: Callable[[], List[ToolTemplate]]
