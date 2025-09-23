

from pathlib import Path
import re
from dev_common.constants import *


class IesaLocalRepoInfo:
    def __init__(self, repo_name: str, repo_local_path: Path, gl_project_path, token_key_name: str):
        self._repo_name = repo_name
        self._token_key_name = token_key_name
        self._repo_local_path = repo_local_path
        self._gl_project_path = gl_project_path  # group/subgroup/repo/

    @property
    def repo_name(self) -> str:
        return self._repo_name

    @property
    def token_key_name(self) -> str:
        return self._token_key_name

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

    def __iter__(self):
        return iter(self._repos.values())


LOCAL_REPO_MAPPING: LocalReposMapping = LocalReposMapping(
    IesaLocalRepoInfo(IESA_OW_SW_TOOLS_REPO_NAME, repo_local_path=CORE_REPOS_PATH/IESA_OW_SW_TOOLS_REPO_NAME,
                      gl_project_path=INTELLIAN_ADC_GROUP/IESA_OW_SW_TOOLS_REPO_NAME, token_key_name=GL_OW_SW_TOOLS_TOKEN_KEY_NAME),

    IesaLocalRepoInfo(IESA_TISDK_REPO_NAME, repo_local_path=CORE_REPOS_PATH/IESA_TISDK_REPO_NAME,
                      gl_project_path=INTELLIAN_ADC_GROUP/IESA_TISDK_REPO_NAME, token_key_name=GL_TISDK_TOKEN_KEY_NAME),

    IesaLocalRepoInfo(IESA_INSENSE_SDK_REPO_NAME, repo_local_path=CORE_REPOS_PATH/IESA_INSENSE_SDK_REPO_NAME,
                      gl_project_path=INTELLIAN_ADC_GROUP/PROTOTYPING_SUB_GROUP/IESA_INSENSE_SDK_REPO_NAME,  token_key_name=GL_INSENSE_SDK_TOKEN_KEY_NAME),

    IesaLocalRepoInfo(IESA_INTELLIAN_PKG_REPO_NAME, repo_local_path=CORE_REPOS_PATH/IESA_INTELLIAN_PKG_REPO_NAME,
                      gl_project_path=INTELLIAN_ADC_GROUP/GERRIT_OW/IESA_INTELLIAN_PKG_REPO_NAME, token_key_name=GL_INTELLIAN_PKG_TOKEN_KEY_NAME),

    IesaLocalRepoInfo(IESA_ADC_LIB_REPO_NAME, repo_local_path=CORE_REPOS_PATH/IESA_ADC_LIB_REPO_NAME,
                      gl_project_path=INTELLIAN_ADC_GROUP/IESA_ADC_LIB_REPO_NAME,  token_key_name=GL_ADC_LIB_TOKEN_KEY_NAME),

    IesaLocalRepoInfo(IESA_SPIBEAM_REPO_NAME, repo_local_path=CORE_REPOS_PATH/IESA_SPIBEAM_REPO_NAME,
                      gl_project_path=INTELLIAN_ADC_GROUP/IESA_SPIBEAM_REPO_NAME, token_key_name=GL_SPIBEAM_TOKEN_KEY_NAME)
)
