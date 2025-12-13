#!/home/vien/local_tools/MyVenvFolder/bin/python
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from typing import List, Optional, Sequence, Set
from available_tools.test_tools.common import *
from available_tools.test_tools.t_get_acu_logs import DEFAULT_DATE_VALUES, batch_fetch_acu_logs
from dev.dev_common import *

DEFAULT_LOG_TYPE_PREFIXES = [P_LOG_PREFIX, T_LOG_PREFIX, E_LOG_PREFIX]
DEFAULT_LOG_OUTPUT_PATH = ACU_LOG_PATH
DEFAULT_PATTERNS = ["MOTION DETECT", "INS-READY"]

ARG_LOG_TYPES = f"{ARGUMENT_LONG_PREFIX}type"
ARG_DATE_FILTERS = f"{ARGUMENT_LONG_PREFIX}date"
ARG_PATTERNS = f"{ARGUMENT_LONG_PREFIX}patterns"
ARG_MAX_THREAD_COUNT = f"{ARGUMENT_LONG_PREFIX}max_threads"
DEFAULT_MAX_THREAD_COUNT = 20
ARG_SHOULD_HAS_VAR_LOG = f"{ARGUMENT_LONG_PREFIX}has_var_log"

def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Get ACU Logs + Find motion detection in ACU logs",
            extra_description="Generate a grep command against fetched ACU logs.",
            args={
                ARG_LOG_OUTPUT_PATH: str(DEFAULT_LOG_OUTPUT_PATH),
                ARG_LOG_TYPES: [E_LOG_PREFIX],
                ARG_LIST_IPS: LIST_MP_IPS,
                ARG_DATE_FILTERS: DEFAULT_DATE_VALUES,
                ARG_PATTERNS: [quote(pattern) for pattern in DEFAULT_PATTERNS],
                ARG_MAX_THREAD_COUNT: DEFAULT_MAX_THREAD_COUNT,
                ARG_SHOULD_HAS_VAR_LOG: True,
            },
        ),
    ]

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a grep command to search ACU logs for specific patterns.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))

    parser.add_argument(ARG_LOG_OUTPUT_PATH, type=Path, default=Path(DEFAULT_LOG_OUTPUT_PATH),
                        help="Base directory where ACU logs are stored locally.", )
    parser.add_argument(ARG_LIST_IPS, nargs="+", default=list(LIST_MP_IPS),
                        help="UT IP address(es) used as subdirectories within the log output path.", )
    parser.add_argument(ARG_LOG_TYPES, nargs="+", choices=DEFAULT_LOG_TYPE_PREFIXES,
                        default=list(DEFAULT_LOG_TYPE_PREFIXES), help="Log filename prefix(es) to include (P, T, or E).", )
    parser.add_argument(ARG_DATE_FILTERS, nargs="+", default=None,
                        help="Date(s) to filter logs (YYYYMMDD). Only files matching these dates are included.", )
    parser.add_argument(ARG_PATTERNS, nargs="+", default=list(DEFAULT_PATTERNS),
                        help="Patterns to search for within the ACU logs.", )
    parser.add_argument(ARG_MAX_THREAD_COUNT, type=int, default=DEFAULT_MAX_THREAD_COUNT,
                        help="Maximum concurrent fetch operations (must be >= 1).", )
    parser.add_argument(ARG_SHOULD_HAS_VAR_LOG, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="Indicates whether the ACU logs contain /var/log directory.", )

    return parser.parse_args(argv)


def _build_search_prefixes(log_types: List[str], date_filters: Optional[List[str]]) -> List[str]:
    if not log_types:
        return [""]

    prefixes: List[str] = []
    if date_filters:
        for log_type in log_types:
            for date_filter in date_filters:
                prefixes.append(f"{log_type}_{date_filter}")
    else:
        prefixes.extend(log_types)

    return prefixes or [""]


def _collect_candidate_files(base_dir: Path, ips: List[str], prefixes: List[str]) -> List[Path]:
    """
    Collect candidate log files matching the provided prefixes under the given base directory.
    """
    file_paths: Set[Path] = set()

    if ips:
        search_roots = [base_dir / ip for ip in ips]
    else:
        search_roots = [base_dir]

    for root in search_roots:
        if not root.exists():
            LOG(f"{LOG_PREFIX_MSG_WARNING} Log directory does not exist: {root}")
            continue

        if not prefixes or prefixes == [""]:
            for path in root.rglob("*"):
                if path.is_file():
                    file_paths.add(path.resolve())
            continue

        for prefix in prefixes:
            for path in root.rglob(f"{prefix}*"):
                if path.is_file():
                    file_paths.add(path.resolve())

    return sorted(file_paths)


def _build_grep_command(patterns: List[str], files: List[Path]) -> str:
    sanitized_patterns = [strip_quotes(p) for p in patterns if p]
    sanitized_patterns = [p for p in sanitized_patterns if p]
    if not sanitized_patterns or not files:
        return ""

    combined_pattern = "|".join(sanitized_patterns)
    file_arguments = " ".join(quote(str(path)) for path in files)
    return f"grep -aE --color=always {quote(combined_pattern)} {file_arguments}; ec=$?; if [ $ec -eq 1 ]; then echo 'No matches found!'; elif [ $ec -eq 2 ]; then echo 'Error: File not found or cannot be read!'; fi"

def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    log_output_dir = Path(get_arg_value(args, ARG_LOG_OUTPUT_PATH)).expanduser()
    ips: List[str] = get_arg_value(args, ARG_LIST_IPS)
    log_types: List[str] = get_arg_value(args, ARG_LOG_TYPES)
    date_filters: Optional[List[str]] = get_arg_value(args, ARG_DATE_FILTERS)
    patterns: List[str] = get_arg_value(args, ARG_PATTERNS)
    max_thread_count: int = get_arg_value(args, ARG_MAX_THREAD_COUNT)
    should_has_var_log: bool = get_arg_value(args, ARG_SHOULD_HAS_VAR_LOG)
    log_output_dir.mkdir(parents=True, exist_ok=True)

    LOG(f"{LOG_PREFIX_MSG_INFO} Fetching latest ACU logs prior to pattern scan...")
    fetch_results = batch_fetch_acu_logs(ips=ips, log_types=log_types, date_filters=date_filters,
                                         log_output_dir=log_output_dir, max_thread_count=max_thread_count, should_has_var_logs=should_has_var_log)

    if not any(fetch_info.is_valid for fetch_info in fetch_results):
        LOG_EXCEPTION(f" Failed to fetch any ACU logs; aborting pattern scan.")

    prefixes = _build_search_prefixes(log_types, date_filters)
    candidate_files = _collect_candidate_files(log_output_dir, ips, prefixes)

    if not candidate_files:
        LOG(f"{LOG_PREFIX_MSG_WARNING} No log files found under {log_output_dir} matching the provided criteria.")
        raise SystemExit(1)

    LOG(f"{LOG_PREFIX_MSG_INFO} Found {len(candidate_files)} log file(s) to scan.")
    command = _build_grep_command(patterns, candidate_files)
    if not command:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Unable to build grep command (missing patterns or files).", file=sys.stderr)
        raise SystemExit(1)

    display_content_to_copy(command, purpose=f"search patterns ({', '.join(patterns)}) in ACU logs", is_copy_to_clipboard=True, post_actions={ PostActionType.RUN_CONTENT_IN_SHELL}, )


if __name__ == "__main__":
    main()
