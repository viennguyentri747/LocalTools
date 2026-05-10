#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from available_tools.iesa_tools.copy_to_ut_runner import ERequestCommand, _run_iesa_install_via_python
from available_tools.test_tools.test_upgrade_ut.common_utils import EUpgradeResult, check_target_support, run_acu_cmd_via_ut, run_acu_cmd_via_ut_with_retry
from dev.dev_common import *
from dev.dev_common.constants import ACU_IP, ACU_PASSWORD, ACU_USER, CHECKSUM_TYPE_MD5, SSM_PASSWORD, SSM_USER
from dev.dev_iesa.iesa_ut_install_utils import EUpgradeComponent, _read_current_bootpart, _read_current_root_partition, are_upgrade_components_final
from dev.dev_common.network_utils import copy_to_remote_via_jump_host, get_remote_file_checksum

REMOTE_DOWNLOAD_DIR = "/home/root/download"
BOOTPART_FILE_PATH = "/run/media/boot/bootpart.txt"
MIN_INSTALL_LOG_LINES = 10
MIN_SECS_AFTER_SUSCESS_LOG = 15
UPGRADE_SUCCESS_LOG_MARKER = "IESA ACU UPGRADE SUCCESS"
ARG_IESA_PATH = f"{ARGUMENT_LONG_PREFIX}path"
ARG_UT_IP = f"{ARGUMENT_LONG_PREFIX}ut_ip"
ARG_LOG_PATH = f"{ARGUMENT_LONG_PREFIX}log_path"
ARG_UT_USER = f"{ARGUMENT_LONG_PREFIX}ut_user"
ARG_UT_PASSWORD = f"{ARGUMENT_LONG_PREFIX}ut_password"
ARG_ACU_IP = f"{ARGUMENT_LONG_PREFIX}acu_ip"
ARG_ACU_USER = f"{ARGUMENT_LONG_PREFIX}acu_user"
ARG_ACU_PASSWORD = f"{ARGUMENT_LONG_PREFIX}acu_password"
ARG_REMOTE_DIR = f"{ARGUMENT_LONG_PREFIX}remote_dir"
ARG_TIMEOUT_SECS = f"{ARGUMENT_LONG_PREFIX}timeout_secs"
DEFAULT_UT_IP = f"{SSM_NORMAL_IP_PREFIX}.107"
DEFAULT_IESA_PATH = str(LOCAL_TOOL_REPO_PATH / "storage" / "in_iesa" / "ow_core_apps-release-master-1.0.0.196.iesa")


@dataclass(frozen=True)
class IesaRuntime:
    ut_ip: str
    ut_user: str = SSM_USER
    ut_password: str = SSM_PASSWORD
    acu_ip: str = ACU_IP
    acu_user: str = ACU_USER
    acu_password: str = ACU_PASSWORD
    remote_dir: str = REMOTE_DOWNLOAD_DIR


@dataclass
class UpgradeCheckState:
    install_line_count: int = 0
    bootpart_before: Optional[str] = None
    expected_bootpart_after: Optional[str] = None
    success_log_first_seen_at: Optional[float] = None


def _resolve_path(path: str, base_path: Optional[str] = None) -> str:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return str(candidate.resolve())
    if base_path:
        return str((Path(base_path).expanduser().resolve().parent / candidate).resolve())
    return str(candidate.resolve())


def _calc_md5(file_path: str) -> str:
    digest = hashlib.md5()
    with open(file_path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def _resolve_log_path(log_path: Optional[str], iesa_path: str, base_path: Optional[str]) -> Optional[str]:
    if not log_path:
        return None
    normalized = _resolve_path(log_path, base_path=base_path)
    candidate = Path(normalized)
    if log_path.endswith("/") or candidate.is_dir() or not candidate.suffix:
        return str(candidate / f"{Path(iesa_path).stem}_iesa_install.log")
    return normalized


def _build_install_logger(log_path: Optional[str]) -> Callable[[str], None]:
    if not log_path:
        return lambda line: LOG(line)

    log_file = Path(log_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    def _on_line_recv(line: str) -> None:
        LOG(line)
        ts = datetime.now().isoformat(sep=" ", timespec="seconds")
        with open(log_file, "a", encoding="utf-8") as file_obj:
            file_obj.write(f"[{ts}] {line}\n")

    return _on_line_recv


def _copy_if_needed(runtime: IesaRuntime, local_iesa_path: str, remote_path: str) -> None:
    local_md5 = _calc_md5(local_iesa_path)
    remote_md5 = get_remote_file_checksum(
        remote_host_ip=runtime.acu_ip,
        remote_path=remote_path,
        remote_user=runtime.acu_user,
        password=runtime.acu_password,
        checksum_type=CHECKSUM_TYPE_MD5,
        jump_host_ip=runtime.ut_ip,
        jump_user=runtime.ut_user,
        jump_password=runtime.ut_password,
        timeout=20,
    )
    LOG(f"Local md5: {local_md5}")
    LOG(f"Remote md5 before copy: {remote_md5 or 'MISSING'}")
    if remote_md5 == local_md5:
        LOG(f"Remote IESA already matches local file, skipping copy: {remote_path}")
        return
    copy_to_remote_via_jump_host(
        local_path=local_iesa_path,
        remote_host_ip=runtime.acu_ip,
        remote_dest_path=remote_path,
        jump_host_ip=runtime.ut_ip,
        remote_user=runtime.acu_user,
        password=runtime.acu_password,
        jump_user=runtime.ut_user,
        jump_password=runtime.ut_password,
        recursive=False,
        timeout=300,
    )
    remote_md5_after = get_remote_file_checksum(
        remote_host_ip=runtime.acu_ip,
        remote_path=remote_path,
        remote_user=runtime.acu_user,
        password=runtime.acu_password,
        checksum_type=CHECKSUM_TYPE_MD5,
        jump_host_ip=runtime.ut_ip,
        jump_user=runtime.ut_user,
        jump_password=runtime.ut_password,
        timeout=20,
    )
    LOG(f"Remote md5 after copy: {remote_md5_after or 'MISSING'}")
    if remote_md5_after != local_md5:
        raise RuntimeError(f"Checksum mismatch after copy. local={local_md5}, remote={remote_md5_after or 'MISSING'}, path={remote_path}")


def _run_acu_cmd_via_ut(runtime: IesaRuntime, command: str, timeout_secs: int = 20) -> str:
    return run_acu_cmd_via_ut(
        ut_ip=runtime.ut_ip, acu_ip=runtime.acu_ip, acu_user=runtime.acu_user, acu_password=runtime.acu_password, ut_user=runtime.ut_user, ut_password=runtime.ut_password, command=command, timeout_secs=timeout_secs
    )


def _run_acu_cmd_via_ut_with_retry(runtime: IesaRuntime, command: str, timeout_secs: int, secs_between_each_retry: float = 2.0) -> str:
    return run_acu_cmd_via_ut_with_retry(
        ut_ip=runtime.ut_ip, acu_ip=runtime.acu_ip, acu_user=runtime.acu_user, acu_password=runtime.acu_password, ut_user=runtime.ut_user, ut_password=runtime.ut_password, command=command, timeout_secs=timeout_secs, secs_between_each_retry=secs_between_each_retry
    )


def can_start_upgrade(runtime: IesaRuntime, timeout: int, supported_unit_types: Optional[List[str]] = None, supported_sub_parts: Optional[List[str]] = None) -> Tuple[EUpgradeResult, str, Optional[UpgradeCheckState]]:
    if timeout <= 0:
        return EUpgradeResult.FAIL, f"invalid pre-upgrade timeout: {timeout}s", None
    precheck_deadline = time.time() + timeout

    def _run_precheck_cmd(command: str) -> str:
        remain_timeout = int(precheck_deadline - time.time())
        if remain_timeout <= 0:
            raise TimeoutError(f"pre-upgrade timeout exceeded while running '{command}'")
        return _run_acu_cmd_via_ut_with_retry(runtime, command, timeout_secs=remain_timeout, secs_between_each_retry=2.0)

    support_check = check_target_support(
        ut_ip=runtime.ut_ip,
        acu_ip=runtime.acu_ip,
        acu_user=runtime.acu_user,
        acu_password=runtime.acu_password,
        ut_user=runtime.ut_user,
        ut_password=runtime.ut_password,
        supported_unit_types=supported_unit_types,
        supported_sub_parts=supported_sub_parts,
        timeout_secs=timeout,
    )
    if support_check == EUpgradeResult.FAIL:
        return EUpgradeResult.FAIL, "target support check failed", None
    if support_check == EUpgradeResult.SHOULD_SKIP:
        return EUpgradeResult.SHOULD_SKIP, "target not supported for this item", None

    last_update_status_msg = ""
    while True:
        try:
            is_update_status_final, update_status_msg = are_upgrade_components_final(
                base_url=f"http://{runtime.ut_ip}",
                components=[EUpgradeComponent.CNX, EUpgradeComponent.MDM, EUpgradeComponent.AIM],
            )
            last_update_status_msg = update_status_msg
            if is_update_status_final:
                LOG(f"Pre-upgrade condition passed: update status is final before starting upgrade ({update_status_msg})")
                break
        except Exception as exc:
            last_update_status_msg = f"error: {exc}"
        remain_wait = precheck_deadline - time.time()
        if remain_wait <= 0:
            return EUpgradeResult.FAIL, f"update status did not become final within precheck timeout ({last_update_status_msg or 'N/A'})", None
        sleep_secs = min(2.0, remain_wait)
        LOG(f"Pre-upgrade wait: update status not final yet ({last_update_status_msg or 'N/A'}), retrying in {sleep_secs:.1f}s")
        time.sleep(sleep_secs)

    current_root_partition = _read_current_root_partition(cmd_runner=_run_precheck_cmd)
    current_bootpart = _read_current_bootpart(cmd_runner=_run_precheck_cmd, bootpart_file_path=BOOTPART_FILE_PATH)
    if current_bootpart != current_root_partition:
        return EUpgradeResult.ABORT, f"bootpart mismatch before upgrade (bootpart={current_bootpart}, current_root={current_root_partition}). Please verify UT/ACU partition state first.", None
    else:
        LOG(f"Pre-upgrade condition passed: current_root_partition={current_root_partition}, bootpart={current_bootpart}")

    iesa_upgrade_state = ""
    while True:
        iesa_upgrade_state = _run_precheck_cmd("SYSTEMD_LOG_LEVEL=notice systemctl is-active iesa_upgrade")
        if iesa_upgrade_state.strip().lower() == "active":
            LOG("Pre-upgrade condition passed: iesa_upgrade service is active on ACU")
            break
        remain_wait = precheck_deadline - time.time()
        if remain_wait <= 0:
            return EUpgradeResult.FAIL, f"iesa_upgrade service did not become active within precheck timeout (last_state={iesa_upgrade_state or 'N/A'})", None
        sleep_secs = min(2.0, remain_wait)
        LOG(f"Pre-upgrade wait: iesa_upgrade service state={iesa_upgrade_state or 'N/A'}, retrying in {sleep_secs:.1f}s")
        time.sleep(sleep_secs)
    running_iesa = _run_precheck_cmd("ps | grep -E \"\\.iesa\" | grep -v grep")
    if running_iesa.strip():
        return EUpgradeResult.FAIL, f"iesa process is still running on ACU: {running_iesa.strip()}", None
    else:
        LOG(f"Pre-upgrade condition passed: iesa process is not running on ACU")
    running_cltool = ""
    while True:
        running_cltool = _run_precheck_cmd("ps | grep -i insense_cltool | grep -v grep")
        if not running_cltool.strip():
            LOG("Pre-upgrade condition passed: insense_cltool process is not running on ACU")
            break
        remain_wait = precheck_deadline - time.time()
        if remain_wait <= 0:
            return EUpgradeResult.FAIL, f"insense_cltool process is still running on ACU: {running_cltool.strip()}", None
        sleep_secs = min(2.0, remain_wait)
        LOG(f"Pre-upgrade wait: insense_cltool process still running on ACU: {running_cltool.strip()} (retrying in {sleep_secs:.1f}s)")
        time.sleep(sleep_secs)
    state = UpgradeCheckState(bootpart_before=current_bootpart, expected_bootpart_after=("3" if current_bootpart == "2" else "2"))
    return EUpgradeResult.SUCCESS, "ready", state


def evaluate_iesa_upgrade_completion(runtime: IesaRuntime, state: UpgradeCheckState) -> Tuple[bool, str]:
    if state.success_log_first_seen_at is None:
        return False, f"missing success log marker '{UPGRADE_SUCCESS_LOG_MARKER}'"
    elapsed_sec_after_success_log = time.time() - state.success_log_first_seen_at
    if elapsed_sec_after_success_log < MIN_SECS_AFTER_SUSCESS_LOG:
        return False, f"success log marker seen but only {elapsed_sec_after_success_log:.1f}s elapsed (<{MIN_SECS_AFTER_SUSCESS_LOG}s)"
    if state.install_line_count < MIN_INSTALL_LOG_LINES:
        return False, f"install log lines check failed ({state.install_line_count}/{MIN_INSTALL_LOG_LINES})"
    bootpart_after = _read_current_bootpart(cmd_runner=lambda cmd: _run_acu_cmd_via_ut(runtime, cmd), bootpart_file_path=BOOTPART_FILE_PATH)
    is_bootpart_changed_ok = bool(state.expected_bootpart_after and bootpart_after == state.expected_bootpart_after)
    if not is_bootpart_changed_ok:
        return False, f"bootpart check failed (before={state.bootpart_before}, after={bootpart_after}, expected={state.expected_bootpart_after})"
    is_update_status_final, update_status_msg = are_upgrade_components_final(
        base_url=f"http://{runtime.ut_ip}",
        components=[EUpgradeComponent.CNX, EUpgradeComponent.MDM, EUpgradeComponent.AIM],
    )
    if not is_update_status_final:
        return False, f"component final-state check failed ({update_status_msg})"
    return True, f"all checks passed (bootpart={bootpart_after}, install_lines={state.install_line_count}, {update_status_msg}, success_elapsed={elapsed_sec_after_success_log:.1f}s)"


def run_once_upgrade(runtime: IesaRuntime, iesa_path: str, timeout_secs: int, log_path: Optional[str] = None, on_install_line_recv: Optional[Callable[[str], None]] = None, *, base_path: Optional[str] = None, start_timeout_secs: int = 180, supported_unit_types: Optional[List[str]] = None, supported_sub_parts: Optional[List[str]] = None) -> EUpgradeResult:
    LOG(f"Running upgrade IESA {iesa_path} on IP {runtime.ut_ip}")
    iesa_path = _resolve_path(iesa_path, base_path=base_path)
    if not os.path.isfile(iesa_path):
        LOG(f"ERROR: IESA file not found: {iesa_path}")
        return EUpgradeResult.FAIL
    if not runtime.ut_ip.strip():
        LOG("ERROR: missing ut_ip")
        return EUpgradeResult.FAIL
    package_name = os.path.basename(iesa_path)
    remote_path = f"{runtime.remote_dir.rstrip('/')}/{package_name}"
    resolved_log_path = _resolve_log_path(log_path, iesa_path, base_path=base_path)
    if resolved_log_path:
        LOG(f"IESA install log path: {resolved_log_path}")
    if timeout_secs <= start_timeout_secs:
        LOG(f"ERROR: timeout_secs ({timeout_secs}s) must be greater than start_timeout_secs ({start_timeout_secs}s)")
        return EUpgradeResult.FAIL
    try:
        precheck_result, can_start_msg, check_state = can_start_upgrade(runtime, timeout=start_timeout_secs, supported_unit_types=supported_unit_types, supported_sub_parts=supported_sub_parts)
    except Exception as exc:
        LOG(f"ERROR: pre-upgrade check failed with exception: {exc}")
        return EUpgradeResult.ABORT

    if precheck_result != EUpgradeResult.SUCCESS:
        LOG(f"ERROR: pre-upgrade check result = {precheck_result}: {can_start_msg}")
        return precheck_result
    elif not check_state:
        LOG("ERROR: pre-upgrade check state is missing")
        return EUpgradeResult.FAIL

    try:
        _copy_if_needed(runtime, iesa_path, remote_path)
        file_log_callback = _build_install_logger(resolved_log_path)

        def _combined_install_line_recv(line: str) -> None:
            file_log_callback(line)
            if line.strip():
                check_state.install_line_count += 1
            if check_state.success_log_first_seen_at is None and UPGRADE_SUCCESS_LOG_MARKER in line:
                check_state.success_log_first_seen_at = time.time()
            if on_install_line_recv:
                on_install_line_recv(line)

        completion: dict[str, Tuple[bool, str]] = {"result": (False, "not evaluated yet")}
        start_time = time.time()
        stop_requested = False

        def _on_request_next_command() -> ERequestCommand:
            nonlocal stop_requested
            if stop_requested:
                return ERequestCommand.RETURN
            elapsed = time.time() - start_time
            if elapsed > timeout_secs:
                completion["result"] = (False, f"upgrade timed out after {elapsed:.1f}s (limit={timeout_secs}s)")
                stop_requested = True
                LOG(f"ERROR: IESA upgrade timeout reached ({elapsed:.1f}s/{timeout_secs}s)")
                return ERequestCommand.RETURN
            is_done, reason = evaluate_iesa_upgrade_completion(runtime, check_state)
            completion["result"] = (is_done, reason)
            if is_done:
                stop_requested = True
                LOG(f"IESA completion conditions met: {reason}")
                return ERequestCommand.RETURN
            else:
                return ERequestCommand.CONTINUE

        _run_iesa_install_via_python(
            remote_name=package_name,
            remote_host_ip=runtime.acu_ip,
            remote_user=runtime.acu_user,
            jump_host_ip=runtime.ut_ip,
            should_prompt=False,
            on_install_line_recv=_combined_install_line_recv,
            on_request_next_command=_on_request_next_command,
            remote_password=runtime.acu_password,
            jump_user=runtime.ut_user,
            jump_password=runtime.ut_password,
        )
        final_ok, final_reason = completion["result"]
        if not final_ok:
            LOG(f"ERROR: IESA completion check failed: {final_reason}")
            return EUpgradeResult.FAIL
        show_noti(title="Upgrade Complete", message=f"Upgrade complete on {runtime.ut_ip}", no_log_on_success=True)
        LOG(f"IESA package installed successfully: {package_name}")
        return EUpgradeResult.SUCCESS
    except Exception as exc:
        LOG(f"ERROR: IESA install failed for {iesa_path}: {exc}")
        return EUpgradeResult.FAIL


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one .iesa sideload upgrade via UT jump host.",
        usage=f"{Path(__file__).name} {ARG_IESA_PATH} <iesa_path> {ARG_UT_IP} <ssm_ip> {ARG_TIMEOUT_SECS} <seconds> [{ARG_LOG_PATH} <log_file_or_dir>]",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_IESA_PATH, required=True, help="IESA path to install once")
    parser.add_argument(ARG_UT_IP, required=True, help="UT/SSM jump-host IP")
    parser.add_argument(ARG_LOG_PATH, required=False, help="Install log output path (file or directory)")
    parser.add_argument(ARG_UT_USER, default=SSM_USER, help=f"UT/SSM jump-host user (default: {SSM_USER})")
    parser.add_argument(ARG_UT_PASSWORD, default=SSM_PASSWORD, help="UT/SSM jump-host password")
    parser.add_argument(ARG_ACU_IP, default=ACU_IP, help=f"ACU IP (default: {ACU_IP})")
    parser.add_argument(ARG_ACU_USER, default=ACU_USER, help=f"ACU user (default: {ACU_USER})")
    parser.add_argument(ARG_ACU_PASSWORD, default=ACU_PASSWORD, help="ACU password")
    parser.add_argument(ARG_REMOTE_DIR, default=REMOTE_DOWNLOAD_DIR, help=f"ACU remote directory (default: {REMOTE_DOWNLOAD_DIR})")
    parser.add_argument(ARG_TIMEOUT_SECS, required=True, type=int, help="Mandatory total timeout in seconds (must be > start_timeout_secs)")
    return parser.parse_args(argv)


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Upgrade One IESA",
            extra_description="Copy one .iesa package via UT jump host and run install with live callback logs.",
            args={
                ARG_IESA_PATH: DEFAULT_IESA_PATH,
                ARG_UT_IP: DEFAULT_UT_IP,
                ARG_LOG_PATH: str(LOCAL_TOOL_REPO_PATH / "logs" / "upgrade_install"),
                ARG_UT_USER: SSM_USER,
                ARG_UT_PASSWORD: SSM_PASSWORD,
                ARG_ACU_IP: ACU_IP,
                ARG_ACU_USER: ACU_USER,
                ARG_ACU_PASSWORD: ACU_PASSWORD,
                ARG_REMOTE_DIR: REMOTE_DOWNLOAD_DIR,
                ARG_TIMEOUT_SECS: 1800,
            },
        ),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    runtime = IesaRuntime(
        ut_ip=get_arg_value(args, ARG_UT_IP),
        ut_user=get_arg_value(args, ARG_UT_USER),
        ut_password=get_arg_value(args, ARG_UT_PASSWORD),
        acu_ip=get_arg_value(args, ARG_ACU_IP),
        acu_user=get_arg_value(args, ARG_ACU_USER),
        acu_password=get_arg_value(args, ARG_ACU_PASSWORD),
        remote_dir=get_arg_value(args, ARG_REMOTE_DIR),
    )
    result = run_once_upgrade(runtime, get_arg_value(args, ARG_IESA_PATH), int(get_arg_value(args, ARG_TIMEOUT_SECS)), get_arg_value(args, ARG_LOG_PATH))
    raise SystemExit(0 if result == EUpgradeResult.SUCCESS else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
