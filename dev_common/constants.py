from pathlib import Path

# FORMATS
LINE_SEPARATOR = f"\n{'=' * 70}\n"
LINE_SEPARATOR_NO_ENDLINE = f"{'=' * 70}"

# GL
INTELLIAN_ADC_GROUP = "intellian_adc"
PROTOTYPING_SUB_GROUP = "prototyping"
GERRIT_OW = "gerrit_mirror/oneweb"

# IESA REPO_NAMES
IESA_OW_SW_TOOLS_REPO_NAME = "oneweb_project_sw_tools"
IESA_TISDK_REPO_NAME = "tisdk"
IESA_INTELLIAN_PKG_REPO_NAME = "intellian_pkg"
IESA_INSENSE_SDK_REPO_NAME = "insensesdk"
IESA_ADC_LIB_REPO_NAME = "adc_lib"
IESA_SPIBEAM_REPO_NAME = "submodule_spibeam"
# IESA GL TOKEN KEYS
GL_OW_SW_TOOLS_TOKEN_KEY_NAME = "GITLAB_OW_SW_TOOLS_TOKEN"
GL_TISDK_TOKEN_KEY_NAME = "GITLAB_TISDK_TOKEN"
GL_INSENSE_SDK_TOKEN_KEY_NAME = "GITLAB_INSENSE_SDK_TOKEN"
GL_ADC_LIB_TOKEN_KEY_NAME = "GITLAB_ADC_LIB_TOKEN"
GL_INTELLIAN_PKG_TOKEN_KEY_NAME = "GITLAB_INTELLIAN_PKG_TOKEN"
GL_SPIBEAM_TOKEN_KEY_NAME = "GITLAB_SPIBEAM_TOKEN"

# PATHS
DOWNLOAD_FOLDER_PATH = Path.home() / "downloads"
REPO_PATH = Path.home() / "local_tools/"
AVAILABLE_TOOLS_PATH = REPO_PATH / "available_tools"
CREDENTIALS_FILE_PATH = REPO_PATH / ".my_credentials.env"
OW_SW_PATH = Path.home() / "ow_sw_tools"
CORE_REPOS_PATH = Path.home() / "workspace" / "intellian_core_repos/"


INSENSE_SDK_REPO_PATH = CORE_REPOS_PATH / IESA_INSENSE_SDK_REPO_NAME
DOWNLOADS_PATH = Path.home() / "downloads"

OW_OUTPUT_IESA_PATH = OW_SW_PATH / "install_iesa_tarball.iesa"
OW_BUILD_FOLDER_PATH = OW_SW_PATH / "tmp_build/"
OW_KIM_FTM_FW_PATH = OW_SW_PATH / "packaging/opt_etc/kim_ftm_fw/"
OW_KIM_RCVR_VERSION_FILE_PATH = OW_KIM_FTM_FW_PATH / "kim_rcvr_version.txt"
OW_BUILD_OUTPUT_FOLDER_PATH = OW_BUILD_FOLDER_PATH / "out"
OW_BUILD_BINARY_OUTPUT_PATH = OW_BUILD_OUTPUT_FOLDER_PATH / "bin"
IESA_MANIFEST_RELATIVE_PATH = f"tools/manifests/iesa_manifest_gitlab.xml"
IESA_MANIFEST_FILE_PATH = OW_SW_PATH / IESA_MANIFEST_RELATIVE_PATH
OW_MAIN_BRANCHES = ["manpack_master", "master"]

# WSL COMMANDS
CMD_WSLPATH = 'wslpath'
CMD_EXPLORER = 'explorer.exe'
CMD_GITINGEST = 'gitingest'
CMD_GIT = 'git'
WSL_SELECT_FLAG = '/select,'

# SYMBOLS
UNDERSCORE = '_'
HYPHEN = '-'


JIRA_API_TOKEN_KEY_NAME = "JIRA_API_TOKEN"
JIRA_COMPANY_URL_KEY_NAME = "JIRA_COMPANY_URL"
JIRA_USERNAME_KEY_NAME = "JIRA_USERNAME"

MANIFEST_SOURCE_LOCAL = "local"
MANIFEST_SOURCE_REMOTE = "remote"
BUILD_TYPE_IESA = "iesa"
BUILD_TYPE_BINARY = "binary"

# File extensions and suffixes
FILE_PREFIX = 'file_'
GIT_SUFFIX = ".git"
TXT_EXTENSION = '.txt'

# Argument name constants
ARGUMENT_LONG_PREFIX = "--"
ARGUMENT_SHORT_PREFIX = "-"
ARG_VERSION_OR_FW_PATH = f"{ARGUMENT_LONG_PREFIX}version_or_fw_path"
ARG_OW_MANIFEST_BRANCH_LONG = f"{ARGUMENT_LONG_PREFIX}ow_manifest_branch"
ARG_OW_MANIFEST_BRANCH_SHORT = f"{ARGUMENT_SHORT_PREFIX}b"
ARG_TOOL_PREFIX = f"{ARGUMENT_LONG_PREFIX}prefix"
ARG_TOOL_FOLDER_PATTERN = f"{ARGUMENT_LONG_PREFIX}folder_pattern"
# ARG_TOOL_ROOT_PATH = f"{ARGUMENT_LONG_PREFIX}root_path"
ARG_PATH_LONG = f"{ARGUMENT_LONG_PREFIX}path"
ARG_PATHS_LONG = f"{ARGUMENT_LONG_PREFIX}paths"
ARG_PATH_SHORT = f"{ARGUMENT_SHORT_PREFIX}p"
ARG_PATHS_SHORT = f"{ARGUMENT_SHORT_PREFIX}p"
ARG_TICKET_URL_LONG = f"{ARGUMENT_LONG_PREFIX}jira_url"
ARG_OUTPUT_DIR_LONG = '--output_dir'
ARG_OUTPUT_DIR_SHORT = '-o'
ARG_NO_OPEN_EXPLORER = '--no-open-explorer'
ARG_MAX_FOLDERS = '--max-folders'

# New common argument names for Inertial Sense tools
ARG_UPDATE_FW = f"{ARGUMENT_LONG_PREFIX}update_fw"
ARG_UPDATE_SDK = f"{ARGUMENT_LONG_PREFIX}update_sdk"
ARG_NO_PROMPT = f"{ARGUMENT_LONG_PREFIX}no_prompt"
ARG_SDK_PATH = f"{ARGUMENT_LONG_PREFIX}sdk_path"

# Emojis
SUCCESS_EMOJI = "✅"
FAILURE_EMOJI = "❌"
CELEBRATION_EMOJI = "🎉"

# Messages
LOG_PREFIX_MSG_INFO = '[INFO]'
LOG_PREFIX_MSG_SUCCESS = '[SUCCESS]'
LOG_PREFIX_MSG_ERROR = '[ERROR]'
LOG_PREFIX_MSG_WARNING = '[WARNING]'
LOG_PREFIX_MSG_FATAL = '[FATAL]'


class IesaLocalRepoInfo:
    __slots__ = ['_repo_name', '_token_key_name']

    def __init__(self, repo_name: str, repo_local_path: Path, gl_project_path: Path, token_key_name: str):
        self._repo_name = repo_name
        self._token_key_name = token_key_name
        self._repo_local_path = repo_local_path
        self._gl_project_path = gl_project_path

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
    def gl_project_path(self) -> Path:
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
