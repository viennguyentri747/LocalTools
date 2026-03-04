#!/home/vien/workspace/intellian_core_repos/local_tools/MyVenvFolder/bin/python

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dev.dev_common import *

SYSTEM_PYTHON3_PATH = Path("/usr/bin/python3")


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Open Log Inspector",
            args={},
            extra_description="Launch the Inertial Sense Log Inspector GUI.",
        ),
        ToolTemplate(
            name="Open Log Inspector with log directory",
            args={ARG_PATH_LONG: f"{DOWNLOADS_PATH}/is_logs"},
            extra_description="Launch the GUI and preload a specific log directory.",
			hidden=True
        ),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def build_command(log_dir: str | None, passthrough_args: List[str]) -> List[str]:
    script_path = Path(INERTIAL_SENSE_LOG_INSPECTOR_PATH).expanduser()
    if not script_path.is_file():
        raise FileNotFoundError(f"Log Inspector script not found: {script_path}")
    python_cmd = str(SYSTEM_PYTHON3_PATH if SYSTEM_PYTHON3_PATH.is_file() else Path(sys.executable))
    cmd = [python_cmd, str(script_path)]
    if log_dir:
        cmd.append(str(Path(log_dir).expanduser()))
    return cmd + passthrough_args


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch the external Inertial Sense Log Inspector GUI.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_PATH_SHORT, ARG_PATH_LONG, type=str, default=None,
                        help="Optional log directory to open immediately in Log Inspector.", )
    args, passthrough_args = parser.parse_known_args()

    try:
        cmd = build_command(get_arg_value(args, ARG_PATH_LONG), passthrough_args)
    except Exception as exc:
        LOG_EXCEPTION(exc, msg="Failed to prepare Log Inspector command.", exit=False)
        raise SystemExit(1)

    LOG(f"Launching Log Inspector: {' '.join(cmd)}")
    raise SystemExit(subprocess.run(cmd, check=False).returncode)


if __name__ == "__main__":
    main()
