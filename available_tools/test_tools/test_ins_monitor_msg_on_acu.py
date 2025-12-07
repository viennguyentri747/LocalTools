#!/home/vien/local_tools/MyVenvFolder/bin/python
"""
Remote tool: Generate SCP + run command to copy and execute test_ins_monitor_messages.py on a target device.
- Builds a one-liner to SCP to /home/root/download/ on the target via jump host
- Service control options are constants in this tool (no CLI flags): service name, restart flag, restart delay
"""

import argparse
from pathlib import Path
from typing import List
from available_tools.test_tools.common import ACU_SCRIPT_DIR
from dev_common import *
from dev_iesa import *

DEFAULT_LOCAL_FILE = ACU_SCRIPT_DIR / "test_ins_monitor_messages.py"

# Argument name constants (local to this tool)
ARG_CFG_OVERRIDE_MESSAGES_LONG = f"{ARGUMENT_LONG_PREFIX}cfg_override_messages"
ARG_DURATION_LONG = f"{ARGUMENT_LONG_PREFIX}duration"
ARG_DURATION_SHORT = f"{ARGUMENT_SHORT_PREFIX}d"
ARG_INS_CONFIG_PATH_LONG = f"{ARGUMENT_LONG_PREFIX}ins_config_path"
ARG_LOG_FILE_LONG = f"{ARGUMENT_LONG_PREFIX}log_file"
ARG_RUN_NOW = f"{ARGUMENT_LONG_PREFIX}run_now"
ARG_IS_RESTART_INS_LONG = f"{ARGUMENT_LONG_PREFIX}is_restart_ins"

# Defaults derived from context and ins_monitor logging
DEFAULT_MESSAGES = "DID_GPS2_RTK_CMP_REL_MESSAGE"
DEFAULT_DURATION = 15
DEFAULT_INS_CONFIG_PATH = "/usr/local/config/system_config/ins_config.json"
DEFAULT_LOG_FILE = "/var/log/ins_monitor_log"
# Service-related constants (not user-overridable via CLI)
SERVICE_NAME = "ins_monitor"
RESTART_DELAY = 2.0


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Check RTK REL message (default)",
            args={
                ARG_RUN_NOW: True,
                ARG_IS_RESTART_INS_LONG: False,
                ARG_PATH_LONG: str(DEFAULT_LOCAL_FILE),
                ARG_DURATION_LONG: DEFAULT_DURATION,
                ARG_INS_CONFIG_PATH_LONG: DEFAULT_INS_CONFIG_PATH,
                ARG_LOG_FILE_LONG: DEFAULT_LOG_FILE,
            },
            no_need_live_edit=True,
        ),
        ToolTemplate(
            name="Check GPS1/GPS2/RTK messages (multi)",
            args={
                ARG_RUN_NOW: True,
                ARG_IS_RESTART_INS_LONG: False,
                ARG_PATH_LONG: str(DEFAULT_LOCAL_FILE),
                ARG_DURATION_LONG: 20,
                ARG_INS_CONFIG_PATH_LONG: DEFAULT_INS_CONFIG_PATH,
                ARG_LOG_FILE_LONG: DEFAULT_LOG_FILE,
                ARG_CFG_OVERRIDE_MESSAGES_LONG: "DID_GPS1_POS_MESSAGE,DID_GPS2_POS_MESSAGE,DID_GPS2_RTK_CMP_REL_MESSAGE",
            },
            no_need_live_edit=True,
        ),
        ToolTemplate(
            name="Check RTK REL (longer timeout)",
            args={
                ARG_RUN_NOW: True,
                ARG_IS_RESTART_INS_LONG: False,
                ARG_PATH_LONG: str(DEFAULT_LOCAL_FILE),
                ARG_DURATION_LONG: 20,
                ARG_INS_CONFIG_PATH_LONG: DEFAULT_INS_CONFIG_PATH,
                ARG_LOG_FILE_LONG: DEFAULT_LOG_FILE,
                ARG_CFG_OVERRIDE_MESSAGES_LONG: DEFAULT_MESSAGES,
            },
            no_need_live_edit=True,
        ),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show SCP+run command to copy and execute test_ins_monitor_messages.py on target UT.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))

    parser.add_argument(ARG_PATH_LONG, ARG_PATH_SHORT, type=Path, default=DEFAULT_LOCAL_FILE,
                        help="Local path to the remote script to copy (default: remote_tools/src/test_ins_monitor_messages.py)", )
    parser.add_argument(ARG_IS_RESTART_INS_LONG, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="Restart the service before monitoring (true or false). Defaults to false.", )
    parser.add_argument(ARG_CFG_OVERRIDE_MESSAGES_LONG, type=str, default=None,
                        help="Optional: Comma-separated message names to detect, overriding ins_config.json", )
    parser.add_argument(ARG_DURATION_LONG, ARG_DURATION_SHORT, type=int, default=DEFAULT_DURATION,
                        help=f"Duration in seconds to monitor for messages (default: {DEFAULT_DURATION})", )
    parser.add_argument(ARG_INS_CONFIG_PATH_LONG, type=str, default=DEFAULT_INS_CONFIG_PATH,
                        help=f"Path to ins_config.json on target (default: {DEFAULT_INS_CONFIG_PATH})", )
    parser.add_argument(ARG_LOG_FILE_LONG, type=str, default=DEFAULT_LOG_FILE,
                        help=f"Path to ins_monitor log on target (default: {DEFAULT_LOG_FILE})", )
    parser.add_argument(ARG_RUN_NOW, type=lambda x: x.lower() == TRUE_STR_VALUE, default=False,
                        help="Run the generated command now (true or false). Defaults to false.", )
    args = parser.parse_args()
    local_script_path: Path = get_arg_value(args, ARG_PATH_LONG)

    # 1) Validate local script file
    if not local_script_path.exists():
        LOG(f"❌ Local script not found: {local_script_path}")
        return
    LOG(f"Using local script: {local_script_path}")

    # 2) Build the remote python command with quoted args
    remote_script_path = f"/home/root/download/{local_script_path.name}"
    parts: List[str] = ["python3", quote(remote_script_path),
                        ARG_DURATION_LONG, str(int(get_arg_value(args, ARG_DURATION_LONG))),
                        "--service", quote_arg_value_if_need(SERVICE_NAME),
                        "--restart_delay", str(float(RESTART_DELAY)),
                        ARG_INS_CONFIG_PATH_LONG, quote_arg_value_if_need(
                            get_arg_value(args, ARG_INS_CONFIG_PATH_LONG)),
                        ARG_LOG_FILE_LONG, quote_arg_value_if_need(get_arg_value(args, ARG_LOG_FILE_LONG)),
                        ]
    if (override_messages := get_arg_value(args, ARG_CFG_OVERRIDE_MESSAGES_LONG)) is not None:
        parts.extend([ARG_CFG_OVERRIDE_MESSAGES_LONG, quote_arg_value_if_need(override_messages)])

    is_restart_service: bool = get_arg_value(args, ARG_IS_RESTART_INS_LONG)
    if is_restart_service:
        parts.append("--restart")

    remote_run = " ".join(parts)

    # 3) Build the SCP + remote-run one-liner
    one_liner = create_scp_ut_and_run_cmd(local_path=local_script_path, run_cmd_on_remote=remote_run)

    run_now: bool = get_arg_value(args, ARG_RUN_NOW)
    if run_now:
        LOG("Running command now...", highlight=True)
        run_shell(one_liner, want_shell=True, executable='/bin/bash')
    else:
        display_content_to_copy(one_liner, is_copy_to_clipboard=True, purpose="Copy and run INS message test")


if __name__ == "__main__":
    main()
