#!/home/vien/local_tools/MyVenvFolder/bin/python
"""
Remote tool: Print a single-line command to SCP a static script to a remote device (via jump host),
plus the command to run it on the target after MD5 verification.
"""
import argparse
from pathlib import Path
from typing import List
from dev_common import *
from dev_common.remote_utils import create_scp_and_run_cmd
from dev_common.tools_utils import display_command_to_use
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LOCAL_FILE = SCRIPT_DIR / "src" / "helloworld.py"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show SCP+run command for a static hello world script.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(get_tool_templates(), Path(__file__))

    parser.add_argument(
        ARG_PATH_LONG, ARG_PATH_SHORT,
        type=Path,
        default=DEFAULT_LOCAL_FILE,
        help="Local path to the hello world script to copy (default: remote_tools/src/helloworld.py)",
    )

    args = parser.parse_args()
    out_path: Path = args.path

    # 1) Validate local script file
    if not out_path.exists():
        LOG(f"❌ Local script not found: {out_path}")
        return
    LOG(f"Using local script: {out_path}")

    # 2) Build the SCP + remote-run one-liner
    remote_run = f"python3 /home/root/download/{out_path.name}"
    one_liner = create_scp_and_run_cmd(local_path=out_path, run_cmd_on_remote=remote_run)

    display_command_to_use(one_liner, is_copy_to_clipboard=True, purpose="Paste the following command in your local shell")


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Copy helloworld.py (default)",
            extra_description="Copy remote_tools/src/helloworld.py to remote and show how to run it",
            args={
                ARG_PATH_LONG: str(DEFAULT_LOCAL_FILE),
            },
            no_need_live_edit=True,
        ),
    ]


if __name__ == "__main__":
    main()