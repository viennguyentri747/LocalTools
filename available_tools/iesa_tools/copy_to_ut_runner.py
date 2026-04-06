#!/usr/local/bin/local_python
"""
Copy build artifacts to ACU via UT jump host, then print the UT-side command to validate and apply them.
Benefits of using this script vs bash
- Shorter command line (just run python)
- When rerun use latest python code here 
"""
import argparse
import os
from pathlib import Path
import shlex
import stat
import sys
from typing import Optional
from dev.dev_common import *
from dev.dev_iesa.acu_utils import create_install_iesa_cmd

MODE_BINARY_SHELL_CMD = "binary_shell_cmd"
MODE_IESA_SHELL_CMD = "iesa_shell_cmd"
MODE_IESA_AUTO = "iesa_auto"
MODE_NO_SETUP = "no_setup"
ARG_LOCAL_PATH = f"{ARGUMENT_LONG_PREFIX}local_path"
ARG_TARGET_IP = f"{ARGUMENT_LONG_PREFIX}target_ip"
ARG_DEST_NAME = f"{ARGUMENT_LONG_PREFIX}dest_name"
ARG_REMOTE_DIR = f"{ARGUMENT_LONG_PREFIX}remote_dir"
ARG_REMOTE_HOST_IP = f"{ARGUMENT_LONG_PREFIX}remote_host_ip"
ARG_REMOTE_USER = f"{ARGUMENT_LONG_PREFIX}remote_user"
ARG_PROMPT_BEFORE_EXECUTE = f"{ARGUMENT_LONG_PREFIX}prompt_before_execute"
DEFAULT_REMOTE_DIR = "/home/root/download"
DEFAULT_TARGET_IP_PREFIX = "192.168.100."
SSM_PASSWORD = read_value_from_credential_file(CREDENTIALS_FILE_PATH, UT_PWD_KEY_NAME)
ACU_PASSWORD = ""


def _prompt_non_empty(prompt_text: str, default_value: Optional[str] = None) -> str:
    while True:
        value = prompt_input(prompt_text + ":", default_value or "")
        if value is None:
            raise KeyboardInterrupt()
        final_value = (value or "").strip() or (default_value or "")
        if final_value:
            return final_value
        LOG(f"{LOG_PREFIX_MSG_WARNING} Value is required.")


def _resolve_local_file(local_path: Path) -> Path:
    if local_path.is_file():
        return local_path
    if not local_path.is_dir():
        raise FileNotFoundError(f"Local path '{local_path}' does not exist.")
    while True:
        default_path = str(local_path) + "/"
        selected_raw: Optional[str] = None
        if sys.stdin.isatty():
            selected_raw = prompt_input_with_path_completion("Enter binary path (Tab to autocomplete):", default_path)
            if selected_raw is None:
                raise KeyboardInterrupt()
        if not selected_raw:
            selected_raw = _prompt_non_empty("Enter binary path", default_path)
        selected = Path(selected_raw).expanduser()
        if selected.is_file():
            return selected.resolve()
        LOG(f"{LOG_PREFIX_MSG_WARNING} File '{selected}' does not exist. Please try again.")


def _get_target_ip(target_ip_arg: Optional[str]) -> str:
    target_ip = target_ip_arg.strip() if target_ip_arg else ""
    if not target_ip:
        target_ip = _prompt_non_empty("Enter target IP", DEFAULT_TARGET_IP_PREFIX)
    if not ping_host(target_ip, total_pings=2, time_out_per_ping=3, mute=True):
        raise ConnectionError(f"Target IP '{target_ip}' is not reachable.")
    return target_ip


def _ensure_local_file_accessible(local_file: Path) -> None:
    def _add_mode_bits(path: Path, extra_bits: int) -> None:
        current_mode = path.stat().st_mode
        desired_mode = current_mode | extra_bits
        if desired_mode != current_mode:
            os.chmod(path, desired_mode)

    try:
        for parent in reversed(local_file.parents):
            if str(parent) == "/":
                continue
            _add_mode_bits(parent, stat.S_IXUSR | stat.S_IRUSR)
        make_path_writable_recursively(local_file)
        _add_mode_bits(local_file, stat.S_IRUSR)
    except PermissionError:
        pass

    if not os.access(local_file, os.R_OK):
        raise PermissionError(
            f"Local file '{local_file}' is not readable. Try fixing it first, for example: "
            f"sudo chmod 644 {shlex.quote(str(local_file))}"
        )


def _build_binary_post_copy_cmd(original_md5: str, remote_dir: str, remote_name: str, binary_name: str) -> str:
    remote_abs_path = f"{remote_dir.rstrip('/')}/{remote_name}"
    backup_name = f"backup_{binary_name}"
    return (
        f"actual_md5=$(md5sum {shlex.quote(remote_abs_path)} | cut -d\" \" -f1) && "
        f"if [ {shlex.quote(original_md5)} = \"$actual_md5\" ]; then "
        f"echo \"MD5 match! Proceeding...\" && "
        f"cp /opt/bin/{shlex.quote(binary_name)} {shlex.quote(remote_dir.rstrip('/') + '/' + backup_name)} && "
        f"ln -sf {shlex.quote(remote_abs_path)} /opt/bin/{shlex.quote(binary_name)} && "
        f"echo \"Backup created and symlink updated: /opt/bin/{binary_name} -> {remote_abs_path}\"; "
        f"else echo \"MD5 MISMATCH! Aborting.\"; fi"
    )


def _build_iesa_post_copy_cmd(original_md5: str, remote_dir: str, remote_name: str, prompt_before_execute: bool) -> str:
    remote_abs_path = f"{remote_dir.rstrip('/')}/{remote_name}"
    install_cmd = create_install_iesa_cmd(remote_name, download_dir=remote_dir)
    if prompt_before_execute:
        proceed_cmd = f"read -r -p \"MD5 match! Install (y/n)?: \" confirm; [ \"$confirm\" = \"y\" -o \"$confirm\" = \"Y\" ] && {install_cmd}"
    else:
        proceed_cmd = f"echo \"MD5 match! Proceeding...\" && {install_cmd}"
    return (
        f"actual_md5=$(md5sum {shlex.quote(remote_abs_path)} | cut -d\" \" -f1) && "
        f"echo \"original md5sum: {original_md5}\"; echo \"actual md5sum: $actual_md5\"; "
        f"if [ {shlex.quote(original_md5)} = \"$actual_md5\" ]; then {proceed_cmd}; "
        f"else echo \"MD5 MISMATCH! Not running.\"; fi"
    )


def _log_checksums(local_md5: str, remote_md5: Optional[str], remote_abs_path: str, stage: str) -> None:
    LOG(f"{LOG_PREFIX_MSG_INFO} Local md5 ({stage}): {local_md5}")
    LOG(f"{LOG_PREFIX_MSG_INFO} Remote md5 ({stage}) {remote_abs_path}: {remote_md5 or 'MISSING'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy binary or IESA artifact to ACU through a UT jump host.")
    parser.add_argument(ARG_MODE, choices=[MODE_BINARY_SHELL_CMD, MODE_IESA_SHELL_CMD, MODE_NO_SETUP], required=True, help="Copy mode.")
    parser.add_argument(ARG_LOCAL_PATH, required=True, help="Local file path or binary output directory.")
    parser.add_argument(ARG_TARGET_IP, default=EMPTY_STR_VALUE, help="Target UT IP used as the SSH jump host.")
    parser.add_argument(ARG_DEST_NAME, default=EMPTY_STR_VALUE, help="Optional destination filename on ACU.")
    parser.add_argument(ARG_REMOTE_DIR, default=DEFAULT_REMOTE_DIR,
                        help=f"Remote ACU directory. Defaults to {DEFAULT_REMOTE_DIR}.")
    parser.add_argument(ARG_REMOTE_HOST_IP, default=ACU_IP, help=f"Remote ACU IP. Defaults to {ACU_IP}.")
    parser.add_argument(ARG_REMOTE_USER, default=ACU_USER, help=f"Remote ACU user. Defaults to {ACU_USER}.")
    add_arg_bool(parser, ARG_PROMPT_BEFORE_EXECUTE, default=True,
                 help_text="Prompt before executing the IESA install command")
    args = parser.parse_args()

    mode = get_arg_value(args, ARG_MODE)
    local_path = Path(get_arg_value(args, ARG_LOCAL_PATH)).expanduser().resolve()
    local_file = _resolve_local_file(local_path)
    remote_dir = get_arg_value(args, ARG_REMOTE_DIR).rstrip("/")
    remote_host_ip = get_arg_value(args, ARG_REMOTE_HOST_IP)
    remote_user = get_arg_value(args, ARG_REMOTE_USER)
    target_ip = _get_target_ip(get_arg_value(args, ARG_TARGET_IP))
    dest_name = get_arg_value(args, ARG_DEST_NAME) or local_file.name
    remote_abs_path = f"{remote_dir}/{dest_name}"

    _ensure_local_file_accessible(local_file)
    original_md5 = get_file_md5sum(str(local_file)).lower()
    remote_md5_before = get_remote_file_checksum(remote_host_ip=remote_host_ip, remote_path=remote_abs_path, remote_user=remote_user,
                                                 password=ACU_PASSWORD, checksum_type=CHECKSUM_TYPE_MD5, jump_host_ip=target_ip,
                                                 jump_user=SSM_USER, jump_password=SSM_PASSWORD)
    _log_checksums(local_md5=original_md5, remote_md5=remote_md5_before, remote_abs_path=remote_abs_path, stage="before copy")

    is_copied = False
    if remote_md5_before == original_md5:
        LOG(f"{LOG_PREFIX_MSG_INFO} Remote file already matches local file. Skipping copy: {remote_abs_path}")
    else:
        copy_to_remote_via_jump_host(local_path=local_file, remote_host_ip=remote_host_ip, remote_dest_path=remote_abs_path,
                                     jump_host_ip=target_ip, remote_user=remote_user, password=ACU_PASSWORD,
                                     jump_user=SSM_USER, jump_password=SSM_PASSWORD, recursive=False)
        time.sleep(1)
        remote_md5_after = get_remote_file_checksum(remote_host_ip=remote_host_ip, remote_path=remote_abs_path, remote_user=remote_user,
                                                    password=ACU_PASSWORD, checksum_type=CHECKSUM_TYPE_MD5, jump_host_ip=target_ip,
                                                    jump_user=SSM_USER, jump_password=SSM_PASSWORD)
        _log_checksums(local_md5=original_md5, remote_md5=remote_md5_after, remote_abs_path=remote_abs_path, stage="after copy")
        if remote_md5_after != original_md5:
            raise RuntimeError(f"Checksum mismatch after copy. local={original_md5}, remote={remote_md5_after or 'MISSING'}, path={remote_abs_path}")
        is_copied = True
        LOG_LINE_SEPARATOR()
        LOG("SCP copy completed successfully")
        show_noti(title="Copy Complete", message=f"File copied to {target_ip}", no_log_on_success=True)

    ut_command: Optional[str] = None
    purpose: str = ""
    if mode == MODE_BINARY_SHELL_CMD:
        purpose = f"Setup binary on target IP {target_ip}"
        ut_command = _build_binary_post_copy_cmd(
            original_md5=original_md5, remote_dir=remote_dir, remote_name=dest_name, binary_name=local_file.name)
        LOG_LINE_SEPARATOR()
    elif mode == MODE_IESA_SHELL_CMD:
        purpose = f"Setup IESA on target IP {target_ip}"
        ut_command = _build_iesa_post_copy_cmd(original_md5=original_md5, remote_dir=remote_dir, remote_name=dest_name,
                                               prompt_before_execute=get_arg_value(args, ARG_PROMPT_BEFORE_EXECUTE))
    else:
        action = "copied" if is_copied else "already up to date (copy skipped)"
        LOG(f"File {action}. Run on target UT {target_ip}!!")

    if ut_command:
        LOG_LINE_SEPARATOR()
        display_content_to_copy(ut_command, purpose=purpose, is_copy_to_clipboard=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Interrupted by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_ERROR} {exc}", file=sys.stderr)
        sys.exit(1)
