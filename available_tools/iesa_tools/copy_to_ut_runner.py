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
MODE_IESA_PYTHON = "iesa_python"
MODE_NO_SETUP = "no_setup"
ARG_LOCAL_PATH = f"{ARGUMENT_LONG_PREFIX}local_path"
ARG_TARGET_IP = f"{ARGUMENT_LONG_PREFIX}target_ip"
ARG_DEST_NAME = f"{ARGUMENT_LONG_PREFIX}dest_name"
ARG_REMOTE_DIR = f"{ARGUMENT_LONG_PREFIX}remote_dir"
ARG_REMOTE_HOST_IP = f"{ARGUMENT_LONG_PREFIX}remote_host_ip"
ARG_PROMPT_BEFORE_EXECUTE = f"{ARGUMENT_LONG_PREFIX}prompt_before_execute"
DEFAULT_REMOTE_DIR = "/home/root/download"
DEFAULT_TARGET_IP_PREFIX = "192.168.100."


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
    if not ping_host(target_ip, total_pings=2, time_out_per_ping=5, mute=True):
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


def _shell_value(value: str, quote_values: bool) -> str:
    return shlex.quote(value) if quote_values else value


def build_md5_verified_post_copy_cmd(original_md5: str, remote_abs_path: str, on_match_cmd: str, quote_values: bool = True, show_md5_details: bool = False, original_md5_display: Optional[str] = None, mismatch_message: str = "MD5 MISMATCH! Not running.") -> str:
    quoted_remote_abs_path = _shell_value(remote_abs_path, quote_values)
    quoted_original_md5 = _shell_value(original_md5, quote_values)
    md5_details_cmd = EMPTY_STR_VALUE
    if show_md5_details:
        md5_value_to_show = original_md5 if original_md5_display is None else original_md5_display
        md5_details_cmd = f"echo \"original md5sum: {md5_value_to_show}\"; echo \"actual md5sum: $actual_md5\"; "
    return (
        f"actual_md5=$(md5sum {quoted_remote_abs_path} | cut -d\" \" -f1) && "
        f"{md5_details_cmd}if [ {quoted_original_md5} = \"$actual_md5\" ]; then {on_match_cmd}; "
        f"else echo \"{mismatch_message}\"; fi"
    )


def build_binary_post_copy_cmd(original_md5: str, remote_dir: str, remote_name: str, binary_name: str, quote_values: bool = True) -> str:
    remote_dir_norm = remote_dir.rstrip("/")
    remote_abs_path = f"{remote_dir_norm}/{remote_name}"
    backup_path = f"{remote_dir_norm}/backup_{binary_name}"
    quoted_remote_abs_path = _shell_value(remote_abs_path, quote_values)
    quoted_backup_path = _shell_value(backup_path, quote_values)
    quoted_binary_name = _shell_value(binary_name, quote_values)
    proceed_cmd = (
        f"echo \"MD5 match! Proceeding...\" && "
        f"chmod +x {quoted_remote_abs_path} && "
        f"cp $(realpath /opt/bin/{quoted_binary_name}) {quoted_backup_path} && "
        f"ln -sf {quoted_remote_abs_path} /opt/bin/{quoted_binary_name} && "
        f"echo \"Backup created and symlink updated: /opt/bin/{binary_name} -> {remote_abs_path}\""
    )
    return build_md5_verified_post_copy_cmd(original_md5=original_md5, remote_abs_path=remote_abs_path, on_match_cmd=proceed_cmd, quote_values=quote_values, mismatch_message="MD5 MISMATCH! Aborting.")


def build_binary_post_copy_cmd_for_shell_echo(remote_dir: str = DEFAULT_REMOTE_DIR) -> str:
    escaped_cmd = build_binary_post_copy_cmd(original_md5="\"$original_md5\"", remote_dir=remote_dir, remote_name="$DEST_NAME", binary_name="$BIN_NAME", quote_values=False).replace("\\", "\\\\").replace("\"", "\\\"")
    return escaped_cmd.replace("$(", "\\$(").replace("$actual_md5", "\\$actual_md5")


def _build_binary_post_copy_cmd(original_md5: str, remote_dir: str, remote_name: str, binary_name: str) -> str:
    return build_binary_post_copy_cmd(original_md5=original_md5, remote_dir=remote_dir, remote_name=remote_name, binary_name=binary_name)


def build_iesa_post_copy_cmd(original_md5: str, remote_dir: str, remote_name: str, prompt_before_execute: bool, quote_values: bool = True, original_md5_display: Optional[str] = None) -> str:
    remote_abs_path = f"{remote_dir.rstrip('/')}/{remote_name}"
    install_cmd = create_install_iesa_cmd(remote_name, download_dir=remote_dir)
    proceed_cmd = f"read -r -p \"MD5 match! Install (y/n)?: \" confirm; [ \"$confirm\" = \"y\" -o \"$confirm\" = \"Y\" ] && {install_cmd}" if prompt_before_execute else f"echo \"MD5 match! Proceeding...\" && {install_cmd}"
    return build_md5_verified_post_copy_cmd(original_md5=original_md5, remote_abs_path=remote_abs_path, on_match_cmd=proceed_cmd, quote_values=quote_values, show_md5_details=True, original_md5_display=original_md5_display, mismatch_message="MD5 MISMATCH! Not running.")


def _build_iesa_post_copy_cmd(original_md5: str, remote_dir: str, remote_name: str, prompt_before_execute: bool) -> str:
    return build_iesa_post_copy_cmd(original_md5=original_md5, remote_dir=remote_dir, remote_name=remote_name, prompt_before_execute=prompt_before_execute)

def _log_checksums(local_md5: str, remote_md5: Optional[str], remote_abs_path: str, stage: str) -> None:
    LOG(f"{LOG_PREFIX_MSG_INFO} Local md5 ({stage}): {local_md5}")
    LOG(f"{LOG_PREFIX_MSG_INFO} Remote md5 ({stage}) {remote_abs_path}: {remote_md5 or 'MISSING'}")


def _wrap_command_with_remote_env(command: str) -> str:
    # Paramiko exec_command runs non-login shells by default; source /etc/profile explicitly.
    wrapped_body = f"[ -f /etc/profile ] && . /etc/profile >/dev/null 2>&1 || true; {command}"
    return f"sh -lc {shlex.quote(wrapped_body)}"


def _run_remote_command_with_live_output(remote_host_ip: str, remote_user: str, jump_host_ip: str, command: str) -> int:
    target_client = jump_client = jump_channel = None
    stdout = stderr = None
    stdout_pending = EMPTY_STR_VALUE
    stderr_pending = EMPTY_STR_VALUE
    try:
        target_client, jump_client, jump_channel = open_ssh_client(host_ip=remote_host_ip, user=remote_user, password=ACU_PASSWORD or EMPTY_STR_VALUE, timeout=10, jump_host_ip=jump_host_ip, jump_user=SSM_USER, jump_password=SSM_PASSWORD)
        LOG(f"{LOG_PREFIX_MSG_INFO} Running remote command on ACU via UT {jump_host_ip}. Command: {command}")
        _, stdout, stderr = target_client.exec_command(command, get_pty=True)
        LOG(f"{LOG_PREFIX_MSG_INFO} Live install log started. Press Ctrl+C to stop tailing.")
        while True:
            if stdout.channel.recv_ready():
                stdout_pending += stdout.channel.recv(4096).decode('utf-8', errors='replace')
                while "\n" in stdout_pending:
                    line, stdout_pending = stdout_pending.split("\n", 1)
                    LOG(line.rstrip("\r"))
            if stderr.channel.recv_stderr_ready():
                stderr_pending += stderr.channel.recv_stderr(4096).decode('utf-8', errors='replace')
                while "\n" in stderr_pending:
                    line, stderr_pending = stderr_pending.split("\n", 1)
                    LOG(f"{LOG_PREFIX_MSG_WARNING} {line.rstrip(chr(13))}")
            if stdout.channel.exit_status_ready() and not stdout.channel.recv_ready() and not stderr.channel.recv_stderr_ready():
                break
            time.sleep(0.1)
        if stdout_pending.strip():
            LOG(stdout_pending.rstrip("\r"))
        if stderr_pending.strip():
            LOG(f"{LOG_PREFIX_MSG_WARNING} {stderr_pending.rstrip(chr(13))}")
        return int(stdout.channel.recv_exit_status())
    except KeyboardInterrupt:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Log tail stopped by user.")
        if stdout and stdout.channel:
            stdout.channel.close()
        if stderr and stderr.channel:
            stderr.channel.close()
        return 0
    finally:
        if stdout:
            stdout.close()
        if stderr:
            stderr.close()
        close_ssh_client(target_client, jump_client, jump_channel)


def _run_iesa_install_via_python(remote_name: str, remote_dir: str, remote_host_ip: str, remote_user: str, jump_host_ip: str, should_prompt: bool) -> None:
    if should_prompt and not prompt_confirmation("MD5 match! Install (y/n)?"):
        LOG(f"{LOG_PREFIX_MSG_WARNING} Install skipped by user.")
        return
    install_and_tail_cmd = _wrap_command_with_remote_env(create_install_iesa_cmd(remote_name, download_dir=remote_dir))
    LOG(f"{LOG_PREFIX_MSG_INFO} Running remote install + tail command on ACU via UT {jump_host_ip}...")
    install_rc = _run_remote_command_with_live_output(remote_host_ip=remote_host_ip, remote_user=remote_user, jump_host_ip=jump_host_ip, command=install_and_tail_cmd)
    if install_rc != 0:
        raise RuntimeError(f"Remote install command failed with exit code {install_rc}.")
    LOG(f"{LOG_PREFIX_MSG_SUCCESS} IESA install command started successfully on remote host {jump_host_ip}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy binary or IESA artifact to ACU through a UT jump host.")
    parser.add_argument(ARG_MODE, choices=[MODE_BINARY_SHELL_CMD, MODE_IESA_SHELL_CMD, MODE_IESA_PYTHON, MODE_NO_SETUP], required=True, help="Copy mode.")
    parser.add_argument(ARG_LOCAL_PATH, required=True, help="Local file path or binary output directory.")
    parser.add_argument(ARG_TARGET_IP, default=EMPTY_STR_VALUE, help="Target UT IP used as the SSH jump host.")
    parser.add_argument(ARG_DEST_NAME, default=EMPTY_STR_VALUE, help="Optional destination filename on ACU.")
    parser.add_argument(ARG_REMOTE_DIR, default=DEFAULT_REMOTE_DIR,
                        help=f"Remote ACU directory. Defaults to {DEFAULT_REMOTE_DIR}.")
    parser.add_argument(ARG_REMOTE_HOST_IP, default=ACU_IP, help=f"Remote ACU IP. Defaults to {ACU_IP}.")
    add_arg_bool(parser, ARG_PROMPT_BEFORE_EXECUTE, default=True,
                 help_text="Prompt before executing the IESA install command")
    args = parser.parse_args()

    mode = get_arg_value(args, ARG_MODE)
    local_path = Path(get_arg_value(args, ARG_LOCAL_PATH)).expanduser().resolve()
    local_file = _resolve_local_file(local_path)
    remote_dir = get_arg_value(args, ARG_REMOTE_DIR).rstrip("/")
    remote_host_ip = get_arg_value(args, ARG_REMOTE_HOST_IP)
    target_ip = _get_target_ip(get_arg_value(args, ARG_TARGET_IP))
    dest_name = get_arg_value(args, ARG_DEST_NAME) or local_file.name
    remote_abs_path = f"{remote_dir}/{dest_name}"

    _ensure_local_file_accessible(local_file)
    original_md5 = get_file_md5sum(str(local_file)).lower()
    remote_md5_before = get_remote_file_checksum(remote_host_ip=remote_host_ip, remote_path=remote_abs_path, remote_user=ACU_USER,
                                                 password=ACU_PASSWORD, checksum_type=CHECKSUM_TYPE_MD5, jump_host_ip=target_ip,
                                                 jump_user=SSM_USER, jump_password=SSM_PASSWORD)
    _log_checksums(local_md5=original_md5, remote_md5=remote_md5_before, remote_abs_path=remote_abs_path, stage="before copy")

    is_copied = False
    if remote_md5_before == original_md5:
        LOG(f"{LOG_PREFIX_MSG_INFO} Remote file already matches local file. Skipping copy: {remote_abs_path}")
    else:
        copy_to_remote_via_jump_host(local_path=local_file, remote_host_ip=remote_host_ip, remote_dest_path=remote_abs_path,
                                     jump_host_ip=target_ip, remote_user=ACU_USER, password=ACU_PASSWORD,
                                     jump_user=SSM_USER, jump_password=SSM_PASSWORD, recursive=False)
        time.sleep(1)
        remote_md5_after = get_remote_file_checksum(remote_host_ip=remote_host_ip, remote_path=remote_abs_path, remote_user=ACU_USER,
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
    elif mode == MODE_IESA_PYTHON:
        _run_iesa_install_via_python(remote_name=dest_name, remote_dir=remote_dir, remote_host_ip=remote_host_ip, remote_user=remote_user,
                                     jump_host_ip=target_ip, should_prompt=get_arg_value(args, ARG_PROMPT_BEFORE_EXECUTE))
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
