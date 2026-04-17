from pathlib import Path
import shlex
from typing import Optional, Union
from dev.dev_common.constants import *
from dev.dev_common.shell_utils import wrap_cmd_for_bash

def create_install_iesa_cmd(iesa_name: str, download_dir: str = ACU_DOWNLOAD_DIR, upgrade_log_path: str = "/var/log/upgrade_log") -> str:
    download_dir_norm = download_dir.rstrip("/")
    upgrade_log_out_path = f"{download_dir_norm}/upgrade_log.txt"
    return f"iesa_umcmd install pkg {shlex.quote(iesa_name)} && tail -F {shlex.quote(upgrade_log_path)} | tee {shlex.quote(upgrade_log_out_path)}"


def create_scp_ut_and_run_cmd(local_path: Union[str, Path], remote_host: str = f"{ACU_USER}@{ACU_IP}", remote_dir: str = ACU_DOWNLOAD_DIR, run_cmd_on_remote: Optional[str] = None, is_prompt_before_execute: bool = True) -> str:
    """
    Constructs a one-liner shell command that prompts for a source_ip (jump host), securely copies a local file to a remote host using scp -rJ, and prints a ready-to-paste UT-side command that verifies MD5 before executing a specified command.
    """
    lp = Path(local_path).expanduser().resolve()
    remote_dir_norm = remote_dir.rstrip("/")
    remote_filename = lp.name
    remote_abs_path = f"{remote_dir_norm}/{remote_filename}"
    from available_tools.iesa_tools.copy_to_ut_runner import build_md5_verified_post_copy_cmd

    # Default remote run command
    run_cmd_on_remote_expr = EMPTY_STR_VALUE if run_cmd_on_remote is None else f"&& {run_cmd_on_remote}"

    # Build the execution part with or without confirmation prompt
    if is_prompt_before_execute:
        execution_cmd = (
            f"read -r -p \"MD5 match! Install (y/n)?: \" confirm; "
            f"[ \"$confirm\" = \"y\" -o \"$confirm\" = \"Y\" ] {run_cmd_on_remote_expr}"
        )
    else:
        execution_cmd = f"echo \"MD5 match! Proceeding...\" {run_cmd_on_remote_expr}"

    original_md5_expr = "\"$original_md5\""
    exec_cmd_body = build_md5_verified_post_copy_cmd(original_md5=original_md5_expr, remote_abs_path=remote_abs_path, on_match_cmd=execution_cmd, quote_values=False, show_md5_details=True, original_md5_display="$original_md5", mismatch_message="MD5 MISMATCH! Not running.")
    exec_cmd = f"original_md5=\"%s\"; {exec_cmd_body}"
    
    cmd = (
        f"output_path=\"{lp}\" "
        f"&& sudo chmod -R 755 \"$output_path\" "
        f"&& rm -f ~/.ssh/known_hosts"
        f"&& read -e -i \"192.168.100.\" -p \"Enter source IP address: \" source_ip "
        f"&& ping_acu_ip \"$source_ip\" --mute "
        f"&& scp -rJ root@$source_ip \"$output_path\" {remote_host}:{remote_dir_norm}/ "
        f"&& {{ original_md5=$(md5sum \"$output_path\" | cut -d\" \" -f1); "
        f"noti \"SCP copy completed successfully\"; "
        f"echo -e \"File(s) copied completed. Run on target UT $source_ip with this below command:\\n\"; "
        f"printf '{exec_cmd}\\n' \"$original_md5\"; "
        f"echo; }} "
        f"|| {{ noti \"SCP copy failed\"; }} "
    )

    return wrap_cmd_for_bash(cmd)
