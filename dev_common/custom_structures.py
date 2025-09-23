

from pathlib import Path
import re
import sys
from dev_common.constants import *
from dev_common.core_utils import LOG


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
)
