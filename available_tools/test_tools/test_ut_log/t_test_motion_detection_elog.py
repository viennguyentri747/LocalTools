#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from available_tools.test_tools.test_ut_log.common_test_functions import run_pattern_test_on_files
from available_tools.test_tools.test_ut_log.log_test_interface import EUtLogType, TestLogInterface, normalize_log_paths_map
from dev.dev_common import *

use_posix_paths()

TEST_NAME = "motion_detection_elog"
DEFAULT_MOTION_PATTERNS: List[str] = ["MOTION DETECT", "INS-READY"]
ARG_ELOG_PATHS = f"{ARGUMENT_LONG_PREFIX}elog_paths"
ARG_PATTERNS = f"{ARGUMENT_LONG_PREFIX}patterns"
WIN_CMD_INVOCATION = get_win_python_runner_cmd_invocation("available_tools.test_tools.test_ut_log.t_test_motion_detection_elog")


def get_tool_templates() -> List[ToolTemplate]:
    sample_log_path = ACU_LOG_PATH / "192.168.100.57" / "E_20260216_000000.txt"
    return [
        ToolTemplate(
            name="Check motion detection in E-log files",
            extra_description="Validate motion-detection related patterns in downloaded E-log files.",
            args={ARG_ELOG_PATHS: [str(sample_log_path)], ARG_PATTERNS: list(DEFAULT_MOTION_PATTERNS)},
            search_root=ACU_LOG_PATH,
            override_cmd_invocation=WIN_CMD_INVOCATION,
        ),
    ]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check required motion-detection patterns in local E-log files.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_ELOG_PATHS, nargs="+", type=Path, required=True, help="One or more local E-log files to scan.")
    parser.add_argument(ARG_PATTERNS, nargs="+", default=list(DEFAULT_MOTION_PATTERNS), help="Pattern(s) that must be present in the E-log files.")
    return parser.parse_args(argv)


def run_motion_detection_elog_test(elog_paths: Sequence[str | Path], patterns: Sequence[str]) -> Dict[str, List[str]]:
    resolved_paths = sorted({Path(path).expanduser().resolve() for path in elog_paths})
    missing_paths = [path for path in resolved_paths if not path.is_file()]
    if missing_paths:
        LOG_EXCEPTION(ValueError(f"Invalid E-log path(s): {', '.join(str(path) for path in missing_paths)}"), exit=True)
    return run_pattern_test_on_files(
        patterns=patterns,
        files=resolved_paths,
        test_name=TEST_NAME,
        require_all_patterns=True,
        max_matches_per_pattern=5,
    )


class MotionDetectionElogTest(TestLogInterface):
    TEST_NAME = "motion_detection_elog"

    @classmethod
    def get_target_log_types(cls) -> List[EUtLogType]:
        return [EUtLogType.ELOG]

    @classmethod
    def run_test(cls, log_paths_by_type: Dict[EUtLogType, List[Path]]) -> None:
        normalized_map = normalize_log_paths_map(log_paths_by_type)
        elog_paths = normalized_map.get(EUtLogType.ELOG, [])
        if not elog_paths:
            LOG_EXCEPTION(ValueError("No E-log files found for motion-detection test."), exit=True)
        run_motion_detection_elog_test(elog_paths=elog_paths, patterns=DEFAULT_MOTION_PATTERNS)


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    elog_paths = get_arg_value(args, ARG_ELOG_PATHS) or []
    patterns = get_arg_value(args, ARG_PATTERNS) or list(DEFAULT_MOTION_PATTERNS)
    run_motion_detection_elog_test(elog_paths=elog_paths, patterns=patterns)


if __name__ == "__main__":
    main()
