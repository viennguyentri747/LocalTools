#!/home/vien/local_tools/MyVenvFolder/bin/python
"""
Remote tool: Generate SCP + run command to copy and execute test_check_message.py on a target device.
- Builds a one-liner to SCP to /home/root/download/ on the target via jump host
- Runs the script with args: --messages, --timeout, --ins_config_path, --log_file
- Service control options are constants in this tool (no CLI flags): service name, restart flag, restart delay
"""

import argparse
from pathlib import Path
from typing import List
import shlex

from dev_common import *
from dev_common.remote_utils import create_scp_and_run_cmd

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LOCAL_FILE = SCRIPT_DIR / "src" / "test_check_message.py"

# Argument name constants (local to this tool)
ARG_MESSAGES_LONG = f"{ARGUMENT_LONG_PREFIX}messages"
ARG_MESSAGES_SHORT = f"{ARGUMENT_SHORT_PREFIX}m"
ARG_TIMEOUT_LONG = f"{ARGUMENT_LONG_PREFIX}timeout"
ARG_TIMEOUT_SHORT = f"{ARGUMENT_SHORT_PREFIX}t"
ARG_INS_CONFIG_PATH_LONG = f"{ARGUMENT_LONG_PREFIX}ins_config_path"
ARG_LOG_FILE_LONG = f"{ARGUMENT_LONG_PREFIX}log_file"

# Defaults derived from context and ins_monitor logging
DEFAULT_MESSAGES = "DID_GPS2_RTK_CMP_REL_MESSAGE"
DEFAULT_TIMEOUT = 15
DEFAULT_INS_CONFIG_PATH = "/usr/local/config/system_config/ins_config.json"
DEFAULT_LOG_FILE = "/var/log/ins_monitor_log"
# Service-related constants (not user-overridable via CLI)
SERVICE_NAME = "ins_monitor"
RESTART_SERVICE = True
RESTART_DELAY = 2.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show SCP+run command to copy and execute test_check_message.py on target UT.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))

    parser.add_argument(ARG_PATH_LONG, ARG_PATH_SHORT, type=Path, default=DEFAULT_LOCAL_FILE,
                        help="Local path to the remote script to copy (default: remote_tools/src/test_check_message.py)", )
    parser.add_argument(ARG_MESSAGES_LONG, ARG_MESSAGES_SHORT, type=str, default=DEFAULT_MESSAGES,
                        help=f"Comma-separated message names to detect (default: {DEFAULT_MESSAGES})", )
    parser.add_argument(ARG_TIMEOUT_LONG, ARG_TIMEOUT_SHORT, type=int, default=DEFAULT_TIMEOUT,
                        help=f"Timeout in seconds to wait for messages (default: {DEFAULT_TIMEOUT})", )
    parser.add_argument(ARG_INS_CONFIG_PATH_LONG, type=str, default=DEFAULT_INS_CONFIG_PATH,
                        help=f"Path to ins_config.json on target (default: {DEFAULT_INS_CONFIG_PATH})", )
    parser.add_argument(ARG_LOG_FILE_LONG, type=str, default=DEFAULT_LOG_FILE,
                        help=f"Path to ins_monitor log on target (default: {DEFAULT_LOG_FILE})", )

    args = parser.parse_args()
    out_path: Path = args.path

    # 1) Validate local script file
    if not out_path.exists():
        LOG(f"❌ Local script not found: {out_path}")
        return
    LOG(f"Using local script: {out_path}")

    # 2) Build the remote python command with quoted args
    remote_script_path = f"/home/root/download/{out_path.name}"
    parts: List[str] = ["python3", quote(remote_script_path),
                        ARG_MESSAGES_LONG, quote(args.messages),
                        ARG_TIMEOUT_LONG, str(int(args.timeout)),
                        "--service", quote(SERVICE_NAME),
                        "--restart_delay", str(float(RESTART_DELAY)),
                        ARG_INS_CONFIG_PATH_LONG, args.ins_config_path,
                        ARG_LOG_FILE_LONG, args.log_file,
                        ]
    if RESTART_SERVICE:
        parts.append("--restart")

    remote_run = " ".join(parts)

    # 3) Build the SCP + remote-run one-liner
    one_liner = create_scp_and_run_cmd(local_path=out_path, run_cmd_on_remote=remote_run)

    LOG(LINE_SEPARATOR, show_time=False)
    LOG("Paste and run this one-liner in your local shell:", highlight=True)
    LOG(one_liner, show_time=False)
    LOG(LINE_SEPARATOR, show_time=False)


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Check RTK REL message (default)",
            args={
                ARG_PATH_LONG: str(DEFAULT_LOCAL_FILE),
                ARG_MESSAGES_LONG: DEFAULT_MESSAGES,
                ARG_TIMEOUT_LONG: DEFAULT_TIMEOUT,
                ARG_INS_CONFIG_PATH_LONG: DEFAULT_INS_CONFIG_PATH,
                ARG_LOG_FILE_LONG: DEFAULT_LOG_FILE,
            },
            no_need_live_edit=True,
        ),
        ToolTemplate(
            name="Check GPS1/GPS2/RTK messages (multi)",
            args={
                ARG_PATH_LONG: str(DEFAULT_LOCAL_FILE),
                ARG_MESSAGES_LONG: "DID_GPS1_POS_MESSAGE,DID_GPS2_POS_MESSAGE,DID_GPS2_RTK_CMP_REL_MESSAGE",
                ARG_TIMEOUT_LONG: 20,
                ARG_INS_CONFIG_PATH_LONG: DEFAULT_INS_CONFIG_PATH,
                ARG_LOG_FILE_LONG: DEFAULT_LOG_FILE,
            },
            no_need_live_edit=True,
        ),
        ToolTemplate(
            name="Check RTK REL (longer timeout)",
            args={
                ARG_PATH_LONG: str(DEFAULT_LOCAL_FILE),
                ARG_MESSAGES_LONG: DEFAULT_MESSAGES,
                ARG_TIMEOUT_LONG: 20,
                ARG_INS_CONFIG_PATH_LONG: DEFAULT_INS_CONFIG_PATH,
                ARG_LOG_FILE_LONG: DEFAULT_LOG_FILE,
            },
            no_need_live_edit=True,
        ),
    ]


if __name__ == "__main__":
    main()
