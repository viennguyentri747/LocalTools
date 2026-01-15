from pathlib import Path
from typing import Optional, Union
from dev.dev_common.constants import *
from dev.dev_common.shell_utils import wrap_cmd_for_bash


def create_scp_ut_and_run_cmd(local_path: Union[str, Path], exec_output_path: Optional[Union[str, Path]] = None, remote_host: str = f"{ACU_USER}@{ACU_IP}", remote_dir: str = "/home/root/download/", run_cmd_on_remote: Optional[str] = None, is_prompt_before_execute: bool = True) -> str:
    """
    Constructs a one-liner shell command that prompts for a source_ip (jump host), securely copies a local file to a remote host using scp -rJ, prints a ready-to-paste UT-side command that verifies MD5 before executing a specified command, and optionally saves that exec command to a local file.
    """
    lp = Path(local_path).expanduser().resolve()
    remote_dir_norm = remote_dir.rstrip("/")
    remote_filename = lp.name
    remote_abs_path = f"{remote_dir_norm}/{remote_filename}"

    # Default remote run command
    run_cmd_on_remote_expr = f"" if run_cmd_on_remote is None else f"&& {run_cmd_on_remote}"

    # Build the execution part with or without confirmation prompt
    if is_prompt_before_execute:
        execution_cmd = (
            f"read -r -p \"MD5 match! Install (y/n)?: \" confirm; "
            f"[ \"$confirm\" = \"y\" -o \"$confirm\" = \"Y\" ] {run_cmd_on_remote_expr}"
        )
    else:
        execution_cmd = f"echo \"MD5 match! Proceeding...\" {run_cmd_on_remote_expr}"

    exec_cmd = (
        f"original_md5=\"%s\"; actual_md5=$(md5sum {remote_abs_path} | cut -d\" \" -f1); "
        f"echo \"original md5sum: %s\"; echo \"actual md5sum: $actual_md5\"; "
        f"if [ \"%s\" = \"$actual_md5\" ]; then {execution_cmd}; else echo \"MD5 MISMATCH! Not running.\"; fi"
    )
    
    exec_output_path_str = "" if exec_output_path is None else str(Path(exec_output_path).expanduser().resolve())
    cmd = (
        f"output_path=\"{lp}\" "
        f"&& sudo chmod -R 755 \"$output_path\" "
        f"&& read -e -i \"192.168.100.\" -p \"Enter source IP address: \" source_ip "
        f"&& ping_acu_ip \"$source_ip\" --mute "
        f"&& scp -rJ root@$source_ip \"$output_path\" {remote_host}:{remote_dir_norm}/ "
        f"&& {{ original_md5=$(md5sum \"$output_path\" | cut -d\" \" -f1); "
        f"noti \"SCP copy completed successfully\"; "
        f"echo -e \"File(s) copied completed. Run on target UT $source_ip with this below command:\\n\"; "
        f"exec_output_path=\"{exec_output_path_str}\"; "
        f"if [ -n \"$exec_output_path\" ]; then "
        f"mkdir -p \"$(dirname \"$exec_output_path\")\" && "
        f"printf '{exec_cmd}\\n' \"$original_md5\" \"$original_md5\" \"$original_md5\" | tee \"$exec_output_path\"; "
        f"else printf '{exec_cmd}\\n' \"$original_md5\" \"$original_md5\" \"$original_md5\"; fi; "
        f"echo; }} "
        f"|| {{ noti \"SCP copy failed\"; }} "
    )

    return wrap_cmd_for_bash(cmd)
