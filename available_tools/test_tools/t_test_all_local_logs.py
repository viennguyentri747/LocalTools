#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Type

from available_tools.test_tools.common import ARG_LIST_IPS, ARG_LOG_OUTPUT_DIR_PATH
from available_tools.test_tools.test_ut_log import t_get_acu_logs
from available_tools.test_tools.test_ut_log.log_test_interface import EUtLogType, TestLogInterface
from available_tools.test_tools.test_ut_log.t_test_invalid_time_sync_elog import InvalidTimeSyncElogTest
from available_tools.test_tools.test_ut_log.t_test_motion_detection_elog import MotionDetectionElogTest
from available_tools.test_tools.test_ut_log.t_test_invalid_time_sync_plog import TimeSyncPlogTest
from dev.dev_common import *

use_posix_paths()

ARG_TESTS = f"{ARGUMENT_LONG_PREFIX}tests"
ARG_DATE_FILTERS = f"{ARGUMENT_LONG_PREFIX}date"
ARG_SHOULD_GET_LOG = f"{ARGUMENT_LONG_PREFIX}should_get_log"
WIN_CMD_INVOCATION = get_win_python_runner_cmd_invocation("available_tools.test_tools.t_test_all_local_logs")

TEST_REGISTRY: Dict[str, Type[TestLogInterface]] = {
    InvalidTimeSyncElogTest.get_test_name(): InvalidTimeSyncElogTest,
    MotionDetectionElogTest.get_test_name(): MotionDetectionElogTest,
    TimeSyncPlogTest.get_test_name(): TimeSyncPlogTest,
}
DEFAULT_TESTS: List[str] = sorted(TEST_REGISTRY.keys())


def _log_banner(title: str) -> None:
    LOG("", show_time=True)
    LOG(f"{LINE_SEPARATOR_NO_ENDLINE}\n{title}\n{LINE_SEPARATOR_NO_ENDLINE}", highlight=True, show_time=False)


def _normalize_runtime_path(path_like: Path, *, label: str) -> Path:
    normalized = Path(path_like).expanduser()
    if not is_platform_windows():
        return normalized
    normalized_str = str(normalized)
    # Already-converted UNC input from \\wsl.localhost\Ubuntu\home\... may stringify as //wsl.localhost/Ubuntu/home/....
    # Passing that to wslpath again creates \\wsl.localhost\Ubuntu\...; -> Need to check for both // and \\\\
    if normalized_str.startswith(("//", "\\\\")) or ":" in normalized_str:
        return normalized
    if normalized_str.startswith("/"):
        converted = Path(convert_wsl_to_win_path(Path(normalized_str)))
        LOG(f"{LOG_PREFIX_MSG_INFO} Converted POSIX {label} for Windows runtime: {normalized} -> {converted}")
        return converted
    return normalized


def get_tool_templates() -> List[ToolTemplate]:
    args = {
        ARG_LOG_OUTPUT_DIR_PATH: str(t_get_acu_logs.ACU_LOG_PATH),
        ARG_LIST_IPS: [UT_77, UT_56],
        ARG_DATE_FILTERS: t_get_acu_logs.DEFAULT_DATE_VALUES,
        ARG_SHOULD_GET_LOG: True,
        ARG_TESTS: list(DEFAULT_TESTS),
    }
    return [
        ToolTemplate(
            name="Run selected local log tests",
            extra_description="Collect required logs by type and run selected tests in one command.",
            args=args,
            search_root=t_get_acu_logs.ACU_LOG_PATH,
            override_cmd_invocation=WIN_CMD_INVOCATION,
        ),
    ]


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run selected local-log tests after collecting all required log files by log type.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))

    parser.add_argument(ARG_TESTS, nargs="+", default=list(DEFAULT_TESTS),
                        choices=sorted(TEST_REGISTRY.keys()), help="Which local log tests to run.")
    parser.add_argument(ARG_LOG_OUTPUT_DIR_PATH, type=Path, default=Path(
        t_get_acu_logs.ACU_LOG_PATH), help="Base directory where local ACU logs are stored.")
    parser.add_argument(ARG_LIST_IPS, nargs="+", default=list(LIST_MP_IPS),
                        help="UT IP folder(s) under log output path to scan.")
    parser.add_argument(ARG_DATE_FILTERS, nargs="+", default=None,
                        help="Optional date filter(s) (YYYYMMDD). If omitted, all matching files are used.")
    add_arg_bool(parser, ARG_SHOULD_GET_LOG, default=None,
                 help_text="Fetch required ACU logs from UTs before running local log tests.")
    return parser.parse_args(argv)


def _get_required_log_types(test_names: Sequence[str]) -> List[EUtLogType]:
    required_types = {
        log_type for test_name in test_names for log_type in TEST_REGISTRY[test_name].get_target_log_types()}
    return sorted(required_types, key=lambda log_type: log_type.to_log_prefix())


def _collect_log_files_for_type(log_output_dir: Path, ips: Sequence[str], log_type: EUtLogType, date_filters: Optional[Sequence[str]]) -> List[Path]:
    log_prefix = log_type.to_log_prefix()
    prefixes = [f"{log_prefix}_{date_filter}" for date_filter in date_filters] if date_filters else [f"{log_prefix}_"]
    search_roots = [log_output_dir / ip for ip in ips] if ips else [log_output_dir]
    LOG(
        f"{LOG_PREFIX_MSG_INFO} Collecting log type '{log_prefix}': base_dir={log_output_dir}, ips={list(ips) if ips else ['<all>']}, date_filters={list(date_filters) if date_filters else ['<any>']}")
    collected: set[Path] = set()
    for search_root in search_roots:
        if not search_root.exists():
            LOG(
                f"{LOG_PREFIX_MSG_WARNING} Skip missing log directory: {search_root} (expected patterns: {[f'{prefix}*' for prefix in prefixes]})")
            continue
        root_total = 0
        for prefix in prefixes:
            pattern = f"{prefix}*"
            pattern_count = 0
            for candidate in search_root.rglob(pattern):
                if candidate.is_file():
                    collected.add(candidate.resolve())
                    pattern_count += 1
            root_total += pattern_count
            LOG(f"{LOG_PREFIX_MSG_INFO} Search files result: root={search_root}, pattern={pattern}, matched_files={pattern_count}")
        LOG(f"{LOG_PREFIX_MSG_INFO} Search summary for root={search_root}: total_matched_files={root_total}")
    sample_paths = sorted(collected)[:5]
    if sample_paths:
        LOG(f"{LOG_PREFIX_MSG_INFO} Sample collected files for '{log_prefix}' (max 5): {', '.join(str(path) for path in sample_paths)}")
    else:
        LOG(
            f"{LOG_PREFIX_MSG_WARNING} No files collected for log type '{log_prefix}'. Checked roots={', '.join(str(root) for root in search_roots)} with patterns={[f'{prefix}*' for prefix in prefixes]}")
    return sorted(collected)


def _collect_logs_by_type(log_output_dir: Path, ips: Sequence[str], required_types: Sequence[EUtLogType], date_filters: Optional[Sequence[str]]) -> Dict[EUtLogType, List[Path]]:
    log_paths_by_type: Dict[EUtLogType, List[Path]] = {}
    for log_type in required_types:
        log_paths = _collect_log_files_for_type(log_output_dir, ips, log_type, date_filters)
        log_paths_by_type[log_type] = log_paths
        LOG(f"{LOG_PREFIX_MSG_INFO} Collected {len(log_paths)} file(s) for log type {log_type.to_log_prefix()}.")
    return log_paths_by_type


def _fetch_logs_if_requested(should_get_log: bool, ips: List[str], required_types: Sequence[EUtLogType], date_filters: Optional[List[str]], log_output_dir: Path) -> None:
    if not should_get_log:
        return
    log_types = [log_type.to_log_prefix() for log_type in required_types]
    LOG(f"{LOG_PREFIX_MSG_INFO} Fetching ACU logs first (--should_get_log=true). log_types={','.join(log_types)}, ips={','.join(ips)}")
    fetch_results = t_get_acu_logs.batch_fetch_acu_logs(
        ut_ips=ips,
        log_types=log_types,
        date_filters=date_filters,
        log_output_dir=log_output_dir,
        max_thread_count=t_get_acu_logs.DEFAULT_MAX_THREAD_COUNT,
    )
    if not any(fetch_info.is_valid for fetch_info in fetch_results):
        LOG_EXCEPTION(ValueError("Failed to fetch any ACU logs before running local log tests."), exit=True)


def _run_selected_tests(test_names: Sequence[str], log_paths_by_type: Dict[EUtLogType, List[Path]]) -> None:
    failed_tests: List[str] = []
    total_tests = len(test_names)
    for i, test_name in enumerate(test_names, 1):
        test_impl = TEST_REGISTRY[test_name]
        _log_banner(f"[TEST {i}/{total_tests}] {test_name}")
        LOG(f"{LOG_PREFIX_MSG_INFO} Running test: {test_name} on paths: {log_paths_by_type.values()}")
        try:
            test_impl.run_test(log_paths_by_type)
            LOG(f"{LOG_PREFIX_MSG_SUCCESS} Test '{test_name}' passed.")
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else (0 if exc.code in (None, 0) else 1)
            if code != 0:
                LOG(f"{LOG_PREFIX_MSG_ERROR} Test '{test_name}' failed (exit code: {code}).")
                failed_tests.append(test_name)
        except Exception as exc:
            LOG(f"{LOG_PREFIX_MSG_ERROR} Test '{test_name}' failed with unexpected error: {exc}")
            failed_tests.append(test_name)

    if failed_tests:
        _log_banner("[TEST SUMMARY] FAIL")
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed tests: {', '.join(sorted(set(failed_tests)))}")
        raise SystemExit(1)
    _log_banner("[TEST SUMMARY] PASS")


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    selected_tests: List[str] = get_arg_value(args, ARG_TESTS) or list(DEFAULT_TESTS)
    log_output_dir = _normalize_runtime_path(
        Path(get_arg_value(args, ARG_LOG_OUTPUT_DIR_PATH)), label="log output path")
    ips: List[str] = get_arg_value(args, ARG_LIST_IPS) or []
    date_filters: Optional[List[str]] = get_arg_value(args, ARG_DATE_FILTERS)
    should_get_log: bool = bool(get_arg_value(args, ARG_SHOULD_GET_LOG))

    if not selected_tests:
        LOG_EXCEPTION(ValueError("No tests were selected. Provide at least one value for --tests."), exit=True)

    required_types = _get_required_log_types(selected_tests)
    if not required_types:
        LOG_EXCEPTION(ValueError("Selected tests did not request any log types."), exit=True)

    log_output_dir.mkdir(parents=True, exist_ok=True)
    _log_banner("RUN LOCAL LOG TESTS")
    LOG(f"{LOG_PREFIX_MSG_INFO} Selected tests: {', '.join(selected_tests)}")
    LOG(f"{LOG_PREFIX_MSG_INFO} Required log types: {', '.join(log_type.to_log_prefix() for log_type in required_types)}")
    _fetch_logs_if_requested(should_get_log=should_get_log, ips=ips, required_types=required_types,
                             date_filters=date_filters, log_output_dir=log_output_dir)
    log_paths_by_type = _collect_logs_by_type(log_output_dir, ips, required_types, date_filters)

    missing_types = [log_type.to_log_prefix() for log_type, paths in log_paths_by_type.items() if not paths]
    if missing_types:
        LOG_EXCEPTION(ValueError(
            f"Missing required log files for type(s): {', '.join(missing_types)} under {log_output_dir}"), exit=True)

    _run_selected_tests(selected_tests, log_paths_by_type)
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Completed all requested local log tests: {', '.join(selected_tests)}")
    LOG(LINE_SEPARATOR)


if __name__ == "__main__":
    main()
