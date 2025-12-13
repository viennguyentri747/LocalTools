
CURRENTLY, we using the gitingest tool internally to extract code context from specific filesystem paths. Let write our custom script to do this instead of call gitingest directly. Our ingest should be able to do this:
Input: List of filesystem paths (files or directories), we don't care about git repos or other inputs here, just make it simple
Output: For each path, extract code context including directory structure as well as file content and save all to 1 output file. Refer the open source project here: https://github.com/coderamp-labs/gitingest. Output file should be like below "//FILE CONTENT ....".

Example:
CLI output:

[main]vien:~/local_tools/$ /home/vien/local_tools/MyVenvFolder/bin/python /home/vien/local_tools/available_tools/code_tools/t_extract_code_context.py --extract-mode paths --include-paths-pattern '*' --exclude-paths-pattern .git .vscode --paths dev_common/ available_tools/code_tools/common_utils.py 
[2025-11-20 10:16:44] [INFO] Running mode 'paths': Extract context archives from explicit filesystem paths.
[2025-11-20 10:16:44] Include patterns: ['*'], Exclude patterns: ['.git', '.vscode']
[2025-11-20 10:16:44] Rotating folders: keeping 4 most recent for prefix 'context_paths_'
[2025-11-20 10:16:44] Removed old context folder: context_paths_20251119_232605
[2025-11-20 10:16:44] Log file created at: /home/vien/testing/.ai_context/context_paths_20251120_101644/log.txt
[2025-11-20 10:16:44] Output directory: /home/vien/testing/.ai_context/context_paths_20251120_101644
[2025-11-20 10:16:44] Starting gitingest for 'dev_common'.
[2025-11-20 10:16:44] >>> gitingest dev_common --output /home/vien/testing/.ai_context/context_paths_20251120_101644/folder_dev_common.txt --include-pattern '*' --exclude-pattern '.git' --exclude-pattern '.vscode' (cwd=/home/vien/workspace/other_projects/custom_tools/LocalTools)
[2025-11-20 10:16:44] Starting gitingest for 'available_tools/code_tools/common_utils.py'.
[2025-11-20 10:16:44] >>> gitingest available_tools/code_tools/common_utils.py --output /home/vien/testing/.ai_context/context_paths_20251120_101644/file_common_utils.py.txt --include-pattern '*' --exclude-pattern '.git' --exclude-pattern '.vscode' (cwd=/home/vien/workspace/other_projects/custom_tools/LocalTools)
[2025-11-20 10:16:46] [SUCCESS] Finished gitingest for 'available_tools/code_tools/common_utils.py'. Output saved to '/home/vien/testing/.ai_context/context_paths_20251120_101644/file_common_utils.py.txt'.
Analysis complete! Output written to: /home/vien/testing/.ai_context/context_paths_20251120_101644/file_common_utils.py.txt

Summary:
Directory: available_tools/code_tools/common_utils.py
File: common_utils.py
Lines: 122

Estimated tokens: 1.3k
[2025-11-20 10:16:46] [SUCCESS] Finished gitingest for 'dev_common'. Output saved to '/home/vien/testing/.ai_context/context_paths_20251120_101644/folder_dev_common.txt'.
Analysis complete! Output written to: /home/vien/testing/.ai_context/context_paths_20251120_101644/folder_dev_common.txt

Summary:
Directory: dev_common
Files analyzed: 18

Estimated tokens: 35.4k
[2025-11-20 10:16:46] 
==================== SUMMARY ====================
[2025-11-20 10:16:46] ✅ Successfully processed 2 paths: available_tools/code_tools/common_utils.py, dev_common/
[2025-11-20 10:16:46] Output files collected: [PosixPath('/home/vien/testing/.ai_context/context_paths_20251120_101644/file_common_utils.py.txt'), PosixPath('/home/vien/testing/.ai_context/context_paths_20251120_101644/folder_dev_common.txt')]
[2025-11-20 10:16:46]   - /home/vien/testing/.ai_context/context_paths_20251120_101644/file_common_utils.py.txt (exists: True)
[2025-11-20 10:16:46]   - /home/vien/testing/.ai_context/context_paths_20251120_101644/folder_dev_common.txt (exists: True)
[2025-11-20 10:16:46] Creating result file with 2 source(s): '/home/vien/testing/.ai_context/context_paths_20251120_101644/file_merged_context.txt'
[2025-11-20 10:16:46] Created result file from 2 file(s): '/home/vien/testing/.ai_context/context_paths_20251120_101644/file_merged_context.txt'
[2025-11-20 10:16:47] 
======================================================================

[2025-11-20 10:16:47] Estimated token count for file_merged_context.txt: 36.52k
[2025-11-20 10:16:48] Opened Explorer to highlight '/home/vien/testing/.ai_context/context_paths_20251120_101644/file_merged_context.txt'

// My current code:

#!/home/vien/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Dict, Iterable, List

from available_tools.code_tools.common_utils import *
from available_tools.code_tools.context_from_git_diff import get_diff_tool_templates, main_git_diff
from available_tools.code_tools.context_from_git_lab_mr import (
    ARG_SHOULD_INCLUDE_FILE_CONTENT,
    get_mr_tool_templates,
    main_git_mr,
)
from available_tools.code_tools.context_from_paths import DEFAULT_MAX_WORKERS, get_paths_tool_templates, main_paths
from dev.dev_common import *
from dev.dev_common.custom_structures import ForwardedTool

FORWARDED_TOOLS: Dict[str, ForwardedTool] = {
    EXTRACT_MODE_PATHS: ForwardedTool(
        mode=EXTRACT_MODE_PATHS,
        description="Extract context archives from explicit filesystem paths.",
        main=main_paths,
        get_templates=get_paths_tool_templates,
    ),
    EXTRACT_MODE_GIT_DIFF: ForwardedTool(
        mode=EXTRACT_MODE_GIT_DIFF,
        description="Generate context from a git diff between two refs.",
        main=main_git_diff,
        get_templates=get_diff_tool_templates,
    ),
    EXTRACT_MODE_GIT_MR: ForwardedTool(
        mode=EXTRACT_MODE_GIT_MR,
        description="Fetch merge-request metadata and context from GitLab.",
        main=main_git_mr,
        get_templates=get_mr_tool_templates,
    ),
}


def get_tool_templates() -> List[ToolTemplate]:
    """Aggregate templates from each forwarded extraction mode."""

    def clone_with_mode(mode: str, templates: Iterable[ToolTemplate]) -> List[ToolTemplate]:
        cloned: List[ToolTemplate] = []
        for template in templates:
            templated_args = dict(template.args or {})
            templated_args[ARG_EXTRACT_MODE] = mode
            cloned.append(
                ToolTemplate(
                    name=template.name,
                    extra_description=template.extra_description,
                    args=templated_args,
                    search_root=template.search_root,
                    no_need_live_edit=template.no_need_live_edit,
                    usage_note=template.usage_note,
                    should_run_now=getattr(template, "run_now_without_modify", False),
                    hidden=getattr(template, "should_hidden", False),
                )
            )
        return cloned

    aggregated_templates: List[ToolTemplate] = []
    for mode, tool in FORWARDED_TOOLS.items():
        aggregated_templates.extend(clone_with_mode(mode, tool.get_templates()))

    return aggregated_templates


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for all supported extract modes."""
    parser = argparse.ArgumentParser(
        description="Extract code context from file paths, git diffs, or GitLab merge requests.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        ARG_EXTRACT_MODE,
        choices=sorted(FORWARDED_TOOLS.keys()),
        required=True,
        help="Which extraction helper to run.",
    )

    parser.add_argument(
        ARG_OUTPUT_DIR_SHORT,
        ARG_OUTPUT_DIR,
        type=Path,
        default=Path.home() / DEFAULT_OUTPUT_BASE_DIR / DEFAULT_OUTPUT_SUBDIR,
        help=f"The directory where the output will be saved. (default: ~/{DEFAULT_OUTPUT_BASE_DIR}/{DEFAULT_OUTPUT_SUBDIR})",
    )
    parser.add_argument(
        ARG_NO_OPEN_EXPLORER,
        action="store_true",
        help="Do not open Windows Explorer to highlight the output file(s) after completion.",
    )
    parser.add_argument(
        ARG_MAX_FOLDERS,
        type=int,
        default=DEFAULT_MAX_FOLDERS,
        help=f"Maximum number of context folders to keep (default: {DEFAULT_MAX_FOLDERS}).",
    )

    # paths mode options
    parser.add_argument(
        ARG_PATHS_SHORT,
        ARG_PATHS_LONG,
        nargs="+",
        help="[paths mode] One or more filesystem paths to ingest.",
    )
    parser.add_argument(
        ARG_MAX_WORKERS,
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="[paths mode] Maximum number of parallel threads to run.",
    )
    parser.add_argument(
        ARG_INCLUDE_PATHS_PATTERN,
        nargs="*",
        default=[],
        help='[paths mode] Additional patterns to include (e.g., "*.py" "*.md").',
    )
    parser.add_argument(
        ARG_EXCLUDE_PATHS_PATTERN,
        nargs="*",
        default=[],
        help='[paths mode] Additional patterns to exclude (e.g., "build" "*.log").',
    )

    # git diff mode options
    parser.add_argument(
        ARG_PATH_LONG,
        type=Path,
        help="[git_diff mode] The path to the local git repository.",
    )
    parser.add_argument(
        ARG_BASE_REF_LONG,
        help="[git_diff mode] The base git ref. (Ex: origin/master)",
    )
    parser.add_argument(
        ARG_TARGET_REF_LONG,
        help="[git_diff mode] The target git ref to compare against the base (Ex: origin/feat_branch).",
    )

    # gitlab MR mode options
    parser.add_argument(
        ARG_GITLAB_MR_URL_LONG,
        help="[gitlab_mr mode] The URL of the GitLab Merge Request.",
    )
    parser.add_argument(
        ARG_SHOULD_INCLUDE_FILE_CONTENT,
        type=lambda x: x.lower() == TRUE_STR_VALUE,
        default=True,
        help="Include changed file contents in the output (true or false). Defaults to true.",
    )

    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))

    return parser.parse_args(argv)


def _validate_required_args(mode: str, args: argparse.Namespace) -> None:
    """Guard against missing arguments before dispatching to the forwarded tool."""
    if mode == EXTRACT_MODE_PATHS:
        if not get_arg_value(args, ARG_PATHS_LONG):
            LOG(f"Error: --paths argument is required for '{EXTRACT_MODE_PATHS}' mode.", file=sys.stderr)
            sys.exit(1)
    elif mode == EXTRACT_MODE_GIT_DIFF:
        if not (
            get_arg_value(args, ARG_PATH_LONG)
            and get_arg_value(args, ARG_BASE_REF_LONG)
            and get_arg_value(args, ARG_TARGET_REF_LONG)
        ):
            LOG(
                f"Error: --path, --base, and --target arguments are required for '{EXTRACT_MODE_GIT_DIFF}' mode.",
                file=sys.stderr,
            )
            sys.exit(1)
    elif mode == EXTRACT_MODE_GIT_MR:
        if not get_arg_value(args, ARG_GITLAB_MR_URL_LONG):
            LOG(f"Error: --mr-url argument is required for '{EXTRACT_MODE_GIT_MR}' mode.", file=sys.stderr)
            sys.exit(1)


def _run_forwarded_tool(forwarded_tool: ForwardedTool, args: argparse.Namespace) -> None:
    LOG(f"{LOG_PREFIX_MSG_INFO} Running mode '{forwarded_tool.mode}': {forwarded_tool.description}")
    forwarded_tool.main(args)


def main(argv: List[str] | None = None) -> None:
    args = parse_args(argv)
    mode = get_arg_value(args, ARG_EXTRACT_MODE)

    forwarded_tool = FORWARDED_TOOLS.get(mode)
    if not forwarded_tool:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Unsupported extract mode: {mode}", file=sys.stderr)
        sys.exit(1)

    _validate_required_args(mode, args)
    _run_forwarded_tool(forwarded_tool, args)


if __name__ == "__main__":
    main()



//FILE CONTENT


FILE(S) CONTEXT BELOW...

======================================================================

======================================================================
INPUT 1/2 (FILE): /home/vien/workspace/other_projects/custom_tools/LocalTools/available_tools/code_tools/common_utils.py
======================================================================
Directory structure:
└── common_utils.py

================================================
FILE: .
================================================
import argparse
from dev.dev_common import *

# Default paths
DEFAULT_OUTPUT_BASE_DIR = 'testing'
....<remain file content>

======================================================================
INPUT 2/2 (FOLDER): /home/vien/workspace/other_projects/custom_tools/LocalTools/dev_common
======================================================================
Directory structure:
└── dev_common/
    ├── __init__.py
    ├── algo_utils.py
    ├── constants.py
    ├── core_utils.py
    ├── custom_structures.py
    ├── file_utils.py
    ├── format_utils.py
    ├── git_utils.py
    ├── gitlab_utils.py
    ├── gui_utils.py
    ├── input_utils.py
    ├── jira_utils.py
    ├── md_utils.py
    ├── network_utils.py
    ├── noti_utils.py
    ├── obisidan_utils.py
    ├── python_misc_utils.py
    └── tools_utils.py

================================================
FILE: __init__.py
================================================
from .core_utils import *
from .constants import *
from .custom_structures import *
from .git_utils import *
from .noti_utils import *
....<remain file content>

================================================
FILE: algo_utils.py
================================================
# Import thefuzz library for fuzzy string matching
from dataclasses import dataclass
import os
from thefuzz import fuzz
from pathlib import Path
....<remain file content>

================================================
FILE: constants.py
================================================
from pathlib import Path
from typing import List


# FORMATS
LINE_SEPARATOR = f"\n{'=' * 70}\n"
....<remain file content>

================================================
FILE: core_utils.py
================================================
import hashlib
import os
from pathlib import Path
import shlex
import subprocess
....<remain file content>

================================================
FILE: custom_structures.py
================================================
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable, Dict, List, Any
from dev.dev_common import *
....<remain file content>

================================================
FILE: file_utils.py
================================================
from enum import Enum
import hashlib
import os
from pathlib import Path
import shutil
....<remain file content>

================================================
FILE: format_utils.py
================================================
import re
from datetime import datetime
import shlex
from typing import List, Union
from readable_number import ReadableNumber
....<remain file content>

================================================
FILE: git_utils.py
================================================
#!/home/vien/local_tools/MyVenvFolder/bin/python

import subprocess
import re
import sys
....<remain file content>

================================================
FILE: gitlab_utils.py
================================================
import time
import gitlab
import os
import base64
import sys
....<remain file content>

================================================
FILE: gui_utils.py
================================================
from __future__ import annotations

import curses
import shutil
import sys
....<remain file content>

================================================
FILE: input_utils.py
================================================
import shlex
from typing import Optional, List, Tuple, Callable

from pathlib import Path
from prompt_toolkit import prompt
....<remain file content>

================================================
FILE: jira_utils.py
================================================
from enum import Enum
import re
import requests
from collections import defaultdict
from typing import List, Dict, Optional, Any
....<remain file content>

================================================
FILE: md_utils.py
================================================


from dev.dev_common.constants import *


def get_md_todo_checkbox(is_done: bool) -> str:
....<remain file content>

================================================
FILE: network_utils.py
================================================
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
import shlex
import subprocess
....<remain file content>

================================================
FILE: noti_utils.py
================================================
#!/home/vien/local_tools/MyVenvFolder/bin/python
import os
import subprocess
import re
import time
....<remain file content>

================================================
FILE: obisidan_utils.py
================================================
#!/home/vien/local_tools/MyVenvFolder/bin/python
"""
Obsidian integration for Jira using the Obsidian Advanced URI plugin.
This script creates a new note in Obsidian by populating a local template
file and then calling a specially crafted obsidian://adv-uri URL.
....<remain file content>

================================================
FILE: python_misc_utils.py
================================================
from pathlib import Path
from dev.dev_common.constants import *
from dev.dev_common.format_utils import quote


def get_arg_value(args, arg_name: str, for_shell: bool = False):
....<remain file content>

================================================
FILE: tools_utils.py
================================================
from dataclasses import dataclass
import fcntl
import importlib.util
import os
from pathlib import Path
....<remain file content>