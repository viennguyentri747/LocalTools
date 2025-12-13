#!/home/vien/local_tools/MyVenvFolder/bin/python
"""
Remote helper: Generate a ready-to-run `tail -F` command that follows ACU periodic logs
and prints only the selected column set (defaults to INS-focused columns).
"""

from __future__ import annotations

import argparse
from typing import Iterable, List, Sequence

from dev.dev_common import *
from dev.dev_iesa import *
from unit_tests.acu_log_tests.periodic_log_constants import *

DEFAULT_LOG_GLOB = "/var/log/P_*"
DEFAULT_LINES_PER_HEADER = 5

# CLI argument names
ARG_LOG_GLOB = f"{ARGUMENT_LONG_PREFIX}log_glob"
ARG_LINES_PER_HEADER = f"{ARGUMENT_LONG_PREFIX}lines_per_header"
ARG_COLUMN_LIST = f"{ARGUMENT_LONG_PREFIX}column_list"
ARG_LIST_COLUMNS = f"{ARGUMENT_LONG_PREFIX}list_columns"
ARG_RUN_NOW = f"{ARGUMENT_LONG_PREFIX}run_now"

TIME_COLUMN_NAME = TIME_COLUMN

# Authoritative order based on periodic log definitions
ALL_COLUMNS: List[str] = [ TIME_COLUMN, LAST_TIME_SYNC_COLUMN, LAST_IF_PATH_COLUMN, LAST_TRACK_ID_COLUMN, LAST_WARM_START_STATUS_COLUMN, LAST_AVG_SINR_COLUMN, LAST_SINR_SAMPLES_RX_COLUMN, LAST_VALID_SINRS_RX_COLUMN, LAST_NULL_SINRS_RX_COLUMN, LAST_ALARM_COLUMN, LAST_RCM_TX_FREQ_REQ_COLUMN, LAST_RCM_TX_FREQ_SET_COLUMN, LAST_RCM_RX_FREQ_REQ_COLUMN, LAST_RCM_RX_FREQ_SET_COLUMN, TOTAL_TRACK_ADV_RX_COLUMN, TOTAL_TRACK_ADV_RJ_COLUMN, TOTAL_TRACK_CANCEL_RX_COLUMN, TOTAL_TRACK_CANCEL_RJ_COLUMN, TOTAL_TRACKS_RX_COLUMN, TOTAL_TRACKS_RJ_COLUMN, TOTAL_RCM_TX_REQ_COLUMN, TOTAL_RCM_TX_SET_COLUMN, TOTAL_RCM_RX_REQ_COLUMN, TOTAL_RCM_RX_SET_COLUMN, LAST_IPA_STATUS_P_COLUMN, LAST_IPA_STATUS_S_COLUMN, LAST_TN_OFFSET_P_COLUMN, LAST_TN_OFFSET_S_COLUMN, LAST_TARGET_AZ_P_COLUMN, LAST_TARGET_AZ_S_COLUMN, LAST_ACTUAL_AZ_P_COLUMN, LAST_ACTUAL_AZ_S_COLUMN, LAST_TARGET_EL_P_COLUMN, LAST_TARGET_EL_S_COLUMN, LAST_ACTUAL_EL_P_COLUMN, LAST_ACTUAL_EL_S_COLUMN, LAST_TARGET_CL_P_COLUMN, LAST_TARGET_CL_S_COLUMN, LAST_ACTUAL_CL_P_COLUMN, LAST_ACTUAL_CL_S_COLUMN, PID_WS_COLUMN, TOTAL_ZOMBIES_COLUMN, ENABLE_GAIN_EVT_COLUMN, TOTAL_GAIN_EVTS_SENT_COLUMN, TOTAL_AIM_CRASHES_COLUMN, TOTAL_PCU_RESETS_P_COLUMN, TOTAL_PCU_RESETS_S_COLUMN, SINR_AVAILABLE_COLUMN, LAST_CANCELLED_TRACK_ID_COLUMN, TOTAL_ABNORMAL_TRACKS_COLUMN, TOTAL_TRANSIT_TRACKS_COLUMN, TOTAL_SEQUENTIAL_TRACKS_COLUMN, LAST_TID_RJ_COLUMN, TOTAL_PCU_CMDS_RTX_P_COLUMN, TOTAL_PCU_CMDS_RTX_S_COLUMN, TOTAL_PCU_CMDS_DROPPED_P_COLUMN, TOTAL_PCU_CMDS_DROPPED_S_COLUMN, TOTAL_INVALID_EL_TA_COLUMN, TOTAL_INVALID_EL_TR_COLUMN, TOTAL_SOFT_RESETS_COLUMN, HOMING_STATUS_P_COLUMN, HOMING_STATUS_S_COLUMN, LAST_EL_OFFSET_P_COLUMN, LAST_EL_OFFSET_S_COLUMN, LAST_BFS_AZ_OFFSET_P_COLUMN, LAST_BFS_EL_OFFSET_P_COLUMN, LAST_BFS_AZ_OFFSET_S_COLUMN, LAST_BFS_EL_OFFSET_S_COLUMN, TX_MUTED_P_COLUMN, TX_MUTED_S_COLUMN, BLOCKAGE_STATUS_P_COLUMN, LAST_BFS_CL_OFFSET_P_COLUMN, LAST_BFS_CL_OFFSET_S_COLUMN, LAST_ROLL_P_COLUMN, LAST_PITCH_P_COLUMN, LAST_YAW_P_COLUMN, LAST_INS_STATUS_COLUMN, LAST_RTK_COMPASS_STATUS_COLUMN, LAST_HEADING_STATUS_COLUMN, LAST_VELOCITY_COLUMN, LAST_MOTION_STATUS_COLUMN, LAST_TX_PANEL_TEMP_COLUMN, LAST_RX_PANEL_TEMP_COLUMN, LAST_KNOWN_ROLL_COLUMN, LAST_KNOWN_PITCH_COLUMN, LAST_KNOWN_YAW_COLUMN, LAST_PT_STATUS_COLUMN, LAST_GPS1_CNO_COLUMN, LAST_GPS2_CNO_COLUMN, LAST_KIM_HW_STATUS_COLUMN, ]

# Columns that are most helpful when focusing on INS-related telemetry
INS_PRIORITY_COLUMNS: List[str] = [ TIME_COLUMN, LAST_TRACK_ID_COLUMN, LAST_TN_OFFSET_P_COLUMN, LAST_TN_OFFSET_S_COLUMN, LAST_INS_STATUS_COLUMN, LAST_RTK_COMPASS_STATUS_COLUMN, LAST_HEADING_STATUS_COLUMN, LAST_VELOCITY_COLUMN, LAST_MOTION_STATUS_COLUMN, LAST_ROLL_P_COLUMN, LAST_PITCH_P_COLUMN, LAST_YAW_P_COLUMN,  LAST_KNOWN_ROLL_COLUMN, LAST_KNOWN_PITCH_COLUMN, LAST_KNOWN_YAW_COLUMN, LAST_GPS1_CNO_COLUMN, LAST_GPS2_CNO_COLUMN, ]

DEFAULT_COLUMN_LIST: List[str] = list(INS_PRIORITY_COLUMNS)

AWK_PROGRAM = (
    'NR==FNR { if ($1 == "<TIME>") { for(i=1;i<=NF;i++) col_map[$i]=i; '
    'num_targets = split(cols, targets, " "); for(i=1; i<=num_targets; i++) { '
    'target_name=targets[i]; if(col_map[target_name]) { print_indices[++p]=col_map[target_name]; '
    'if (hdr == "") { hdr = target_name } else { hdr = hdr OFS target_name } } } } next } '
    '$1=="<TIME>" { print "\\n" hdr; c=0; next } '
    'NF>10 { if (c>0 && c%n==0) printf "\\n%s\\n", hdr; '
    'line=""; for(i=1;i<=p;i++) { idx=print_indices[i]; '
    'if (line == "") { line = $idx } else { line = line OFS $idx } } '
    'print line; c++ }'
).replace("<TIME>", TIME_COLUMN)


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Tail ACU P-log (INS columns)",
            args={ARG_COLUMN_LIST: DEFAULT_COLUMN_LIST},
            no_need_live_edit=True,
        ),
        ToolTemplate(
            name="Tail ACU P-log (all columns)",
            args={ARG_COLUMN_LIST: ALL_COLUMNS},
            no_need_live_edit=True,
            hidden=True,
        ),
    ]


def _normalize_columns(columns: Sequence[str]) -> List[str]:
    """Remove blanks/duplicates, enforce the time column first, and fail on unknown entries."""
    cleaned: List[str] = []
    seen = set()
    available = set(ALL_COLUMNS)
    missing: List[str] = []

    for col in columns:
        candidate = col.strip()
        if not candidate:
            continue
        if candidate not in available:
            missing.append(candidate)
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        cleaned.append(candidate)

    if missing:
        LOG_EXCEPTION(ValueError(f"Unknown column(s): {', '.join(missing)}"), exit=True)

    if not cleaned:
        raise ValueError("At least one valid column name is required.")

    if cleaned[0] != TIME_COLUMN_NAME:
        cleaned = [TIME_COLUMN_NAME] + [col for col in cleaned if col != TIME_COLUMN_NAME]

    return cleaned


def _print_available_columns(columns: Iterable[str]) -> None:
    LOG("Available periodic log columns:", show_time=False)
    for col in columns:
        LOG(f"  - {col}", show_time=False)


def _quote_double(value: str) -> str:
    escaped = value.replace('"', r'\"')
    return f'"{escaped}"'


def build_tail_command(log_glob: str, lines_per_header: int, columns: Sequence[str]) -> str:
    columns_str = " ".join(columns)
    log_assignment = _quote_double(log_glob)
    columns_assignment = _quote_double(columns_str)
    return (
        f"total_line_per_header={lines_per_header}; "
        f"logfile={log_assignment}; "
        f"target_cols={columns_assignment}; "
        f"tail -F $logfile | awk -v n=\"$total_line_per_header\" -v cols=\"$target_cols\" "
        f"-F'\\t' '{AWK_PROGRAM}' $logfile -"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show (and optionally run) a tail+awk command that streams selected P-log columns on a UT.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))

    parser.add_argument(
        ARG_COLUMN_LIST,
        nargs="+",
        default=None,
        help="Space-separated list of column names to include (defaults to INS-focused set).",
    )
    parser.add_argument(
        ARG_LOG_GLOB,
        type=str,
        default=DEFAULT_LOG_GLOB,
        help=f"Path/glob of the periodic log on the UT (default: {DEFAULT_LOG_GLOB}).",
    )
    parser.add_argument(
        ARG_LINES_PER_HEADER,
        type=int,
        default=DEFAULT_LINES_PER_HEADER,
        help=f"How many printed rows before repeating the header (default: {DEFAULT_LINES_PER_HEADER}).",
    )
    parser.add_argument(
        ARG_LIST_COLUMNS,
        action="store_true",
        help="Print the available columns and exit.",
    )
    parser.add_argument(
        ARG_RUN_NOW,
        type=lambda x: x.lower() == TRUE_STR_VALUE,
        default=False,
        help=f"Run the generated command locally (true/false). Defaults to false.",
    )

    args = parser.parse_args()

    if get_arg_value(args, ARG_LIST_COLUMNS):
        _print_available_columns(ALL_COLUMNS)
        return

    requested_columns = get_arg_value(args, ARG_COLUMN_LIST) or DEFAULT_COLUMN_LIST
    columns = _normalize_columns(requested_columns)
    lines_per_header = int(get_arg_value(args, ARG_LINES_PER_HEADER))
    log_glob = str(get_arg_value(args, ARG_LOG_GLOB))

    command = build_tail_command(log_glob, lines_per_header, columns)
    run_now: bool = get_arg_value(args, ARG_RUN_NOW)

    if run_now:
        LOG("Running tail command locally...", highlight=True)
        run_shell(command, want_shell=True, executable='/bin/bash')
    else:
        display_content_to_copy(
            command,
            purpose="tail ACU periodic log with filtered columns",
            is_copy_to_clipboard=True,
        )


if __name__ == "__main__":
    main()
