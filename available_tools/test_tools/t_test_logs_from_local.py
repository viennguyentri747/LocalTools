#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Dict, Iterable, List, Tuple

from available_tools.test_tools.test_ut_log import t_get_acu_logs
from available_tools.test_tools.test_ut_log import t_test_pattern_in_logs_local
from available_tools.test_tools.test_ut_log import t_test_process_plog_local
from available_tools.test_tools.test_ut_log import t_test_time_sync_plog
from dev.dev_common import *

ARG_TEST_MODE = f"{ARGUMENT_LONG_PREFIX}mode"

MODE_GET_ACU_LOGS = "get_acu_logs"
MODE_ACU_PATTERN = "acu_log_pattern"
MODE_COMPACT_PLOG = "compact_plog"
MODE_TIME_SYNC_PLOG = "time_sync_plog"
AVAILABLE_TEST_MODES = (MODE_GET_ACU_LOGS, MODE_ACU_PATTERN, MODE_COMPACT_PLOG, MODE_TIME_SYNC_PLOG)

FORWARDED_TOOLS: Dict[str, ForwardedTool] = {
    MODE_GET_ACU_LOGS: ForwardedTool(
        mode=MODE_GET_ACU_LOGS,
        description="Fetch ACU logs from remote UTs into the local log directory.",
        main=t_get_acu_logs.main,
        get_templates=t_get_acu_logs.getToolData,
    ),
    MODE_ACU_PATTERN: ForwardedTool(
        mode=MODE_ACU_PATTERN,
        description="Fetch ACU logs locally and build a grep command for target patterns.",
        main=t_test_pattern_in_logs_local.main,
        get_templates=t_test_pattern_in_logs_local.getToolData,
    ),
    MODE_COMPACT_PLOG: ForwardedTool(
        mode=MODE_COMPACT_PLOG,
        description="Reduce downloaded P-logs to selected columns.",
        main=t_test_process_plog_local.main,
        get_templates=t_test_process_plog_local.getToolData,
    ),
    MODE_TIME_SYNC_PLOG: ForwardedTool(
        mode=MODE_TIME_SYNC_PLOG,
        description="Check LAST_TIME_SYNC drift from local P-logs.",
        main=t_test_time_sync_plog.main,
        get_templates=t_test_time_sync_plog.getToolData,
    ),
}


def get_tool_templates() -> List[ToolTemplate]:
    def clone_with_mode(mode: str, templates: Iterable[ToolTemplate]) -> List[ToolTemplate]:
        cloned: List[ToolTemplate] = []
        for template in templates:
            templated_args = dict(template.args or {})
            templated_args[ARG_TEST_MODE] = mode
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


def parse_args(argv: List[str]) -> Tuple[argparse.Namespace, List[str]]:
    parser = argparse.ArgumentParser(
        description="Run local ACU log helper tools from a single entry point.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        ARG_TEST_MODE,
        choices=AVAILABLE_TEST_MODES,
        required=True,
        help=(
            f"Which local log helper to run. "
            f"'{MODE_GET_ACU_LOGS}' forwards to t_get_acu_logs.py. "
            f"'{MODE_ACU_PATTERN}' forwards to t_test_pattern_in_logs_local.py. "
            f"'{MODE_COMPACT_PLOG}' forwards to t_test_process_plog_local.py. "
            f"'{MODE_TIME_SYNC_PLOG}' forwards to t_test_time_sync_plog.py."
        ),
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    return parser.parse_known_args(argv)


def _run_forwarded_tool(forwarded_tool: ForwardedTool, passthrough_args: List[str]) -> None:
    LOG(f"{LOG_PREFIX_MSG_INFO} Running mode '{forwarded_tool.mode}': {forwarded_tool.description}")
    original_argv = sys.argv
    clean_passthrough = [arg for arg in passthrough_args if arg != "--"]
    redirected_argv = [f"{Path(__file__).stem}:{forwarded_tool.mode}"] + clean_passthrough
    try:
        sys.argv = redirected_argv
        forwarded_tool.main()
    finally:
        sys.argv = original_argv


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


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
