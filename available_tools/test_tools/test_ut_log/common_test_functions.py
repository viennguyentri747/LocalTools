#!/usr/local/bin/local_python
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from available_tools.test_tools.common import AcuLogInfo
from available_tools.test_tools.test_ut_log import t_get_acu_logs
from dev.dev_common import *

DEFAULT_DATE_VALUES: List[str] = list(t_get_acu_logs.DEFAULT_DATE_VALUES)
DEFAULT_MAX_THREAD_COUNT = t_get_acu_logs.DEFAULT_MAX_THREAD_COUNT


def batch_fetch_acu_logs(ips: List[str], log_types: List[str], date_filters: Optional[List[str]], log_output_dir: Path, max_thread_count: int, should_has_var_logs: bool = False) -> List[AcuLogInfo]:
    return t_get_acu_logs.batch_fetch_acu_logs(
        ips=ips,
        log_types=log_types,
        date_filters=date_filters,
        log_output_dir=log_output_dir,
        max_thread_count=max_thread_count,
        should_has_var_logs=should_has_var_logs,
    )


def sanitize_patterns(patterns: Sequence[str]) -> List[str]:
    sanitized = [strip_quotes(pattern).strip() for pattern in patterns if pattern]
    return [pattern for pattern in sanitized if pattern]


def build_search_prefixes(log_types: Sequence[str], date_filters: Optional[Sequence[str]]) -> List[str]:
    if not log_types:
        return [""]
    if not date_filters:
        return [str(log_type) for log_type in log_types]
    return [f"{log_type}_{date_filter}" for log_type in log_types for date_filter in date_filters] or [""]


def collect_candidate_files(base_dir: Path, ips: Sequence[str], prefixes: Sequence[str]) -> List[Path]:
    file_paths: Set[Path] = set()
    normalized_prefixes = list(prefixes)
    search_roots = [base_dir / ip for ip in ips] if ips else [base_dir]
    for root in search_roots:
        if not root.exists():
            LOG(f"{LOG_PREFIX_MSG_WARNING} Log directory does not exist: {root}")
            continue
        if not normalized_prefixes or normalized_prefixes == [""]:
            for path in root.rglob("*"):
                if path.is_file():
                    file_paths.add(path.resolve())
            continue
        for prefix in normalized_prefixes:
            for path in root.rglob(f"{prefix}*"):
                if path.is_file():
                    file_paths.add(path.resolve())
    return sorted(file_paths)


def build_grep_command(patterns: Sequence[str], files: Sequence[Path]) -> str:
    sanitized_patterns = sanitize_patterns(patterns)
    if not sanitized_patterns or not files:
        return ""
    combined_pattern = "|".join(sanitized_patterns)
    file_arguments = " ".join(quote(str(path)) for path in files)
    return f"grep -aE --color=always {quote(combined_pattern)} {file_arguments}; ec=$?; if [ $ec -eq 1 ]; then printf '\\nNo matches found!\\n'; elif [ $ec -eq 2 ]; then printf '\\nError: File not found or cannot be read!\\n'; fi"


def scan_patterns_in_files(patterns: Sequence[str], files: Sequence[Path], max_matches_per_pattern: int = 10) -> Dict[str, List[str]]:
    sanitized_patterns = sanitize_patterns(patterns)
    if not sanitized_patterns:
        return {}
    resolved_files = sorted({Path(file_path).expanduser().resolve() for file_path in files})
    compiled_patterns: Dict[str, re.Pattern[str]] = {}
    for pattern in sanitized_patterns:
        try:
            compiled_patterns[pattern] = re.compile(pattern)
        except re.error:
            compiled_patterns[pattern] = re.compile(re.escape(pattern))

    matches_by_pattern: Dict[str, List[str]] = {pattern: [] for pattern in sanitized_patterns}
    for file_path in resolved_files:
        if not file_path.is_file():
            continue
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as handle:
                for line_no, line in enumerate(handle, start=1):
                    line_text = line.rstrip("\r\n")
                    for pattern, compiled in compiled_patterns.items():
                        if len(matches_by_pattern[pattern]) >= max_matches_per_pattern:
                            continue
                        if compiled.search(line_text):
                            matches_by_pattern[pattern].append(f"{file_path}:{line_no}: {line_text}")
        except Exception as exc:
            LOG(f"{LOG_PREFIX_MSG_WARNING} Failed to scan log file '{file_path}': {exc}")
    return matches_by_pattern


def run_pattern_test_on_files(patterns: Sequence[str], files: Sequence[Path], test_name: str = "pattern_scan", require_all_patterns: bool = False, max_matches_per_pattern: int = 5) -> Dict[str, List[str]]:
    normalized_patterns = sanitize_patterns(patterns)
    resolved_files = sorted({Path(file_path).expanduser().resolve() for file_path in files})
    if not resolved_files:
        LOG_EXCEPTION(ValueError(f"No candidate files provided for test '{test_name}'."), exit=True)
    if not normalized_patterns:
        LOG_EXCEPTION(ValueError(f"No search patterns provided for test '{test_name}'."), exit=True)

    matches_by_pattern = scan_patterns_in_files(
        patterns=normalized_patterns,
        files=resolved_files,
        max_matches_per_pattern=max_matches_per_pattern,
    )
    matched_patterns = [pattern for pattern in normalized_patterns if matches_by_pattern.get(pattern)]
    missing_patterns = [pattern for pattern in normalized_patterns if pattern not in matched_patterns]
    if require_all_patterns and missing_patterns:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Test '{test_name}' failed. Missing pattern(s): {', '.join(missing_patterns)}")
        raise SystemExit(1)
    if not matched_patterns:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Test '{test_name}' failed. No patterns matched in {len(resolved_files)} file(s).")
        raise SystemExit(1)

    LOG(f"{LOG_PREFIX_MSG_SUCCESS} Test '{test_name}' matched {len(matched_patterns)}/{len(normalized_patterns)} pattern(s) across {len(resolved_files)} file(s).")
    for pattern in matched_patterns:
        pattern_matches = matches_by_pattern.get(pattern, [])
        if not pattern_matches:
            continue
        LOG(f"{LOG_PREFIX_MSG_INFO} Pattern '{pattern}' sample matches ({len(pattern_matches)}):")
        for sample_line in pattern_matches:
            LOG(f"  - {sample_line}", show_time=False)
    return matches_by_pattern
