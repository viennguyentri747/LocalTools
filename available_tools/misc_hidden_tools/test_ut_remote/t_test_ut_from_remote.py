#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Dict, List, Tuple

from misc_hidden_tools.test_ut_remote import test_ins_monitor_msg_on_acu as ins_monitor_tool
from misc_hidden_tools.test_ut_remote import test_tail_p_log_on_acu as tail_p_log_tool
from dev.dev_common import *
from dev.dev_common.custom_structures import ForwardedTool

ARG_TEST_MODE = f"{ARGUMENT_LONG_PREFIX}mode"

MODE_INS_MONITOR = "ins_monitor"
MODE_TAIL_P_LOG = "tail_p_log"
AVAILABLE_TEST_MODES = (MODE_INS_MONITOR, MODE_TAIL_P_LOG)

FORWARDED_TOOLS: Dict[str, ForwardedTool] = {
    MODE_INS_MONITOR: ForwardedTool(
        mode=MODE_INS_MONITOR,
        description="Copy and run INS monitor message checks on a UT.",
        main=ins_monitor_tool.main,
        get_templates=ins_monitor_tool.getToolData,
    ),
    MODE_TAIL_P_LOG: ForwardedTool(
        mode=MODE_TAIL_P_LOG,
        description="Generate ACU periodic log tail command snippets.",
        main=tail_p_log_tool.main,
        get_templates=tail_p_log_tool.getToolData,
    ),
}


def get_tool_templates() -> List[ToolTemplate]:
    """Provide ready-to-run templates for remote UT helpers."""
    aggregated_templates: List[ToolTemplate] = []
    for mode, tool in FORWARDED_TOOLS.items():
        aggregated_templates.extend([template.clone_with_args({ARG_TEST_MODE: mode}) for template in tool.get_templates_list()])

    return aggregated_templates


def parse_args(argv: List[str]) -> Tuple[argparse.Namespace, List[str]]:
    parser = argparse.ArgumentParser(
        description="Run UT remote helper tools from a single entry point.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        ARG_TEST_MODE,
        choices=AVAILABLE_TEST_MODES,
        required=True,
        help="Which UT remote helper to run (e.g. ins_monitor, tail_p_log).",
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
