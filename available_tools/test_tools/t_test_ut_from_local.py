#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Dict, List, Tuple

from available_tools.test_tools import test_pattern_in_acu_logs_local as pattern_tool
from available_tools.test_tools.test_ut_since_startup import t_test_ut_acquisition_status_via_bash_tools as bash_status_tool
from available_tools.test_tools.test_ut_since_startup import t_test_ut_acquisition_status_tools as python_status_tool
from available_tools.test_tools.plog_test_tools import t_test_process_plog_local
from dev.dev_common import *


ARG_TEST_MODE = f"{ARGUMENT_LONG_PREFIX}mode"

MODE_STATUS = "status_since_startup"
MODE_STATUS_NATIVE = "status_since_startup_python"
MODE_ACU_PATTERN = "acu_log_pattern"
MODE_COMPACT_PLOG = "compact_plog"
AVAILABLE_TEST_MODES = (MODE_STATUS, MODE_STATUS_NATIVE, MODE_ACU_PATTERN, MODE_COMPACT_PLOG)

FORWARDED_TOOLS: Dict[str, ForwardedTool] = {
    MODE_STATUS: ForwardedTool(
        mode=MODE_STATUS,
        description="Reboot UT and check status endpoints after startup.",
        main=bash_status_tool.main,
        get_templates=bash_status_tool.get_tool_templates,
    ),
    MODE_STATUS_NATIVE: ForwardedTool(
        mode=MODE_STATUS_NATIVE,
        description="Reboot UT and check status endpoints via native Python client.",
        main=python_status_tool.main,
        get_templates=python_status_tool.get_tool_templates,
    ),
    MODE_ACU_PATTERN: ForwardedTool(
        mode=MODE_ACU_PATTERN,
        description="Generate grep commands to search downloaded ACU logs.",
        main=pattern_tool.main,
        get_templates=pattern_tool.get_tool_templates,
    ),
    MODE_COMPACT_PLOG: ForwardedTool(
        mode=MODE_COMPACT_PLOG,
        description="Trim downloaded P-logs down to specific columns.",
        main=t_test_process_plog_local.main,
        get_templates=t_test_process_plog_local.get_tool_templates,
    ),
}

def get_tool_templates() -> List[ToolTemplate]:
    """Provide ready-to-run templates for the combined tool."""
    aggregated_templates: List[ToolTemplate] = []
    for mode, tool in FORWARDED_TOOLS.items():
        templates = tool.get_templates()
        # Insert the mode argument at the beginning to each template
        for template in templates:
            template.args = {ARG_TEST_MODE: mode, **template.args}
        aggregated_templates.extend(templates)
    return aggregated_templates


def parse_args(argv: List[str]) -> Tuple[argparse.Namespace, List[str]]:
    """Parse known arguments while preserving the remaining args for the selected tool."""

    parser = argparse.ArgumentParser(
        description="Run UT helper tools from a single entry point.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        ARG_TEST_MODE,
        choices=AVAILABLE_TEST_MODES,
        required=True,
        help=(
            f"Which UT helper to run. "
            f"'{MODE_STATUS}' forwards to test_ut_acquisition_status_via_bash.py. "
            f"'{MODE_STATUS_NATIVE}' forwards to test_ut_acquisition_status.py. "
            f"'{MODE_ACU_PATTERN}' forwards to test_pattern_in_acu_logs.py. "
            f"'{MODE_COMPACT_PLOG}' forwards to test_gen_compact_log_from_plog.py."
        ),
    )

    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))
    return parser.parse_known_args(argv)


def _run_forwarded_tool(forwarded_tool: ForwardedTool, passthrough_args: List[str]) -> None:
    """Invoke the forwarded tool with the provided passthrough arguments."""

    LOG(f"{LOG_PREFIX_MSG_INFO} Running mode '{forwarded_tool.mode}': {forwarded_tool.description}")
    original_argv = sys.argv

    clean_passthrough = [arg for arg in passthrough_args if arg != "--"]
    redirected_argv = [f"{Path(__file__).stem}:{forwarded_tool.mode}"] + clean_passthrough

    try:
        sys.argv = redirected_argv
        forwarded_tool.main()
    finally:
        sys.argv = original_argv


def main(argv: List[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]

    parsed_args, passthrough_args = parse_args(argv)
    mode = get_arg_value(parsed_args, ARG_TEST_MODE)
    forwarded_tool = FORWARDED_TOOLS.get(mode)

    if not forwarded_tool:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Unsupported mode: {mode}", file=sys.stderr)
        raise SystemExit(1)

    _run_forwarded_tool(forwarded_tool, passthrough_args)


if __name__ == "__main__":
    main()
