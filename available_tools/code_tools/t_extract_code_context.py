#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Dict, Iterable, List
from available_tools.code_tools.common_utils import *
from available_tools.code_tools.context_from_git_diff import get_diff_tool_templates, main_git_diff
from available_tools.code_tools.context_from_git_lab_mr import ( ARG_SHOULD_INCLUDE_FILE_CONTENT, get_mr_tool_templates, main_git_mr, )
from available_tools.code_tools.context_from_paths import DEFAULT_MAX_WORKERS, get_paths_tool_templates, main_paths
from dev.dev_common import *

FORWARDED_TOOLS: Dict[str, ForwardedTool] = {
    EXTRACT_MODE_PATHS: ForwardedTool(
        mode=EXTRACT_MODE_PATHS,
        description="Extract context archives from explicit filesystem paths.",
        main=main_paths,
        get_templates=lambda: ToolData(tool_template=get_paths_tool_templates()),
    ),
    EXTRACT_MODE_GIT_DIFF: ForwardedTool(
        mode=EXTRACT_MODE_GIT_DIFF,
        description="Generate context from a git diff between two refs.",
        main=main_git_diff,
        get_templates=lambda: ToolData(tool_template=get_diff_tool_templates()),
    ),
    EXTRACT_MODE_GIT_MR: ForwardedTool(
        mode=EXTRACT_MODE_GIT_MR,
        description="Fetch merge-request metadata and context from GitLab.",
        main=main_git_mr,
        get_templates=lambda: ToolData(tool_template=get_mr_tool_templates()),
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
        aggregated_templates.extend(clone_with_mode(mode, tool.get_templates_list()))

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

    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))

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



def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())

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
