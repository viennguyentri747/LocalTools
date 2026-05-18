#!/usr/local/bin/local_python
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional, Tuple

from available_tools.test_tools.test_upgrade_ut.bundle_api_helper import get_update_status
from available_tools.test_tools.test_upgrade_ut.common_utils import run_acu_cmd_via_ut
from dev.dev_common import LOG
from dev.dev_common.constants import ACU_IP, ACU_PASSWORD, ACU_USER, API_SYSTEM_REBOOT_ENDPOINT, SSM_PASSWORD, SSM_USER
from dev.dev_common.core_independent_utils import run_shell
from dev.dev_common.network_utils import ping_remote_host_via_jump_host


class EUpgradeComponent(str, Enum):
    CNX = "CNX"
    MDM = "MDM"
    AIM = "AIM"


class EIesaPrecheckResult(str, Enum):
    READY = "ready"
    FAIL = "fail"
    ABORT = "abort"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class IesaPrecheckState:
    bootpart_before: str
    expected_bootpart_after: str


def are_upgrade_components_final(base_url: str, components: List[EUpgradeComponent]) -> Tuple[bool, str]:
    update_status = get_update_status(base_url=base_url) or {}
    final_states = {"update_success", "update_fail"}
    normalized_status: dict[str, str] = {}
    for component in components:
        component_key = component.value
        component_state = str(update_status.get(component_key, "")).strip().lower()
        normalized_status[component_key] = component_state
    is_final = all(normalized_status[c.value] in final_states for c in components)
    status_msg = ", ".join(f"{c.value}={normalized_status[c.value] or 'N/A'}" for c in components)
    return is_final, status_msg


def _extract_partition(raw_text: str) -> Optional[str]:
    for pattern in [r"mmcblk1p([23])", r"\b([23])\b"]:
        match = re.search(pattern, raw_text)
        if match:
            return match.group(1)
    return None


def _read_current_bootpart(cmd_runner: Callable[[str], str], bootpart_file_path: str = "/run/media/boot/bootpart.txt") -> str:
    raw_output = cmd_runner(f"cat {bootpart_file_path}")
    parsed = _extract_partition(raw_output)
    if not parsed:
        raise RuntimeError(f"Cannot parse bootpart from output: '{raw_output}'")
    return parsed


def _read_current_root_partition(cmd_runner: Callable[[str], str]) -> str:
    command = "lsblk -no NAME,MOUNTPOINT | awk '/mmcblk1p[23]/ && $2 == \"/\" { n = $1; sub(/.*mmcblk1p/, \"\", n); print n }'"
    raw_output = cmd_runner(command)
    parsed = _extract_partition(raw_output)
    if not parsed:
        raise RuntimeError(f"Cannot parse current root partition from output: '{raw_output}'")
    return parsed


def run_iesa_upgrade_precheck(base_url: str, cmd_runner: Callable[[str], str], timeout_secs: int, bootpart_file_path: str = "/run/media/boot/bootpart.txt",
                              components: Optional[List[EUpgradeComponent]] = None) -> Tuple[EIesaPrecheckResult, str, Optional[IesaPrecheckState]]:
    if timeout_secs <= 0:
        return EIesaPrecheckResult.FAIL, f"invalid pre-upgrade timeout: {timeout_secs}s", None
    precheck_deadline = time.time() + timeout_secs
    check_components = components or [EUpgradeComponent.CNX, EUpgradeComponent.MDM, EUpgradeComponent.AIM]
    last_update_status_msg = ""
    while True:
        try:
            is_update_status_final, update_status_msg = are_upgrade_components_final(base_url=base_url, components=check_components)
            last_update_status_msg = update_status_msg
            if is_update_status_final:
                LOG(f"Pre-upgrade condition passed: update status is final before starting upgrade ({update_status_msg})")
                break
        except Exception as exc:
            last_update_status_msg = f"error: {exc}"
        remain_wait = precheck_deadline - time.time()
        if remain_wait <= 0:
            return EIesaPrecheckResult.TIMEOUT, f"update status did not become final within precheck timeout ({last_update_status_msg or 'N/A'})", None
        sleep_secs = min(2.0, remain_wait)
        LOG(f"Pre-upgrade wait: update status not final yet ({last_update_status_msg or 'N/A'}), retrying in {sleep_secs:.1f}s")
        time.sleep(sleep_secs)

    current_root_partition = _read_current_root_partition(cmd_runner=cmd_runner)
    current_bootpart = _read_current_bootpart(cmd_runner=cmd_runner, bootpart_file_path=bootpart_file_path)
    if current_bootpart != current_root_partition:
        return EIesaPrecheckResult.ABORT, f"bootpart mismatch before upgrade (bootpart={current_bootpart}, current_root={current_root_partition}). Please verify UT/ACU partition state first.", None
    LOG(f"Pre-upgrade condition passed: current_root_partition={current_root_partition}, bootpart={current_bootpart}")

    iesa_upgrade_state = ""
    while True:
        iesa_upgrade_state = cmd_runner("SYSTEMD_LOG_LEVEL=notice systemctl is-active iesa_upgrade")
        if iesa_upgrade_state.strip().lower() == "active":
            LOG("Pre-upgrade condition passed: iesa_upgrade service is active on ACU")
            break
        remain_wait = precheck_deadline - time.time()
        if remain_wait <= 0:
            return EIesaPrecheckResult.TIMEOUT, f"iesa_upgrade service did not become active within precheck timeout (last_state={iesa_upgrade_state or 'N/A'})", None
        sleep_secs = min(2.0, remain_wait)
        LOG(f"Pre-upgrade wait: iesa_upgrade service state={iesa_upgrade_state or 'N/A'}, retrying in {sleep_secs:.1f}s")
        time.sleep(sleep_secs)

    running_iesa = cmd_runner("ps | grep -E \"\\.iesa\" | grep -v grep")
    if running_iesa.strip():
        return EIesaPrecheckResult.FAIL, f"iesa process is still running on ACU: {running_iesa.strip()}", None
    LOG("Pre-upgrade condition passed: iesa process is not running on ACU")

    running_cltool = ""
    while True:
        running_cltool = cmd_runner("ps | grep -i insense_cltool | grep -v grep")
        if not running_cltool.strip():
            LOG("Pre-upgrade condition passed: insense_cltool process is not running on ACU")
            break
        remain_wait = precheck_deadline - time.time()
        if remain_wait <= 0:
            return EIesaPrecheckResult.TIMEOUT, f"insense_cltool process is still running on ACU: {running_cltool.strip()}", None
        sleep_secs = min(2.0, remain_wait)
        LOG(f"Pre-upgrade wait: insense_cltool process still running on ACU: {running_cltool.strip()} (retrying in {sleep_secs:.1f}s)")
        time.sleep(sleep_secs)
    state = IesaPrecheckState(bootpart_before=current_bootpart, expected_bootpart_after=("3" if current_bootpart == "2" else "2"))
    return EIesaPrecheckResult.READY, "ready", state


def check_safe_reboot_ut(ut_ip: str, timeout_before_reboot_secs: int = 240, should_ping_after_reboot: bool = False, ping_timeout_after_reboot_secs: int = 300, acu_ip: str = ACU_IP, acu_user: str = ACU_USER, acu_password: str = ACU_PASSWORD, ut_user: str = SSM_USER, ut_password: str = SSM_PASSWORD) -> bool:
    deadline_ts = time.time() + max(1, timeout_before_reboot_secs)
    while time.time() < deadline_ts:
        try:
            running_procs = run_acu_cmd_via_ut(ut_ip=ut_ip, command="ps | grep -E \"\\.iesa|insense_cltool\" | grep -v grep",
                                               timeout_secs=10, acu_ip=acu_ip, acu_user=acu_user, acu_password=acu_password, ut_user=ut_user, ut_password=ut_password)
            if running_procs.strip():
                LOG(f"Safe reboot wait: iesa/cltool process is still running on ACU: {running_procs.strip()}")
                time.sleep(10)
                continue
            is_update_status_final, update_status_msg = are_upgrade_components_final(
                base_url=f"http://{ut_ip}", components=[EUpgradeComponent.CNX, EUpgradeComponent.MDM, EUpgradeComponent.AIM])
            if not is_update_status_final:
                LOG(f"Safe reboot wait: update status is not final yet ({update_status_msg})")
                time.sleep(10)
                continue
            LOG(f"Post-upgrade condition passed: no iesa/cltool process and update status final ({update_status_msg})")
            break
        except Exception as exc:
            sleep_secs = 30 if time.time() + 30 < deadline_ts else 0
            if sleep_secs <= 0:
                LOG(f"Safe reboot wait: ACU check failed: {exc}")
                return False
            LOG(f"Safe reboot wait: ACU check failed, retrying in {sleep_secs:.1f}s: {exc}")
            time.sleep(sleep_secs)
    else:
        LOG(f"ERROR: timeout waiting post-upgrade conditions before reboot ({timeout_before_reboot_secs}s)")
        return False

    try:
        reboot_url = f"http://{ut_ip}{API_SYSTEM_REBOOT_ENDPOINT}"
        run_shell(["curl", "-X", "GET", reboot_url], capture_output=True, text=True, check_throw_exception_on_exit_code=True, timeout=10)
        LOG(f"Post-upgrade action: reboot API issued to UT {ut_ip} ({reboot_url})")
        if should_ping_after_reboot:
            secs_sleep_before_ping = 5
            LOG(f"Post-upgrade action: waiting for {secs_sleep_before_ping} seconds before checking ACU reachability after reboot")
            time.sleep(secs_sleep_before_ping)
            is_reachable_after_reboot = ping_remote_host_via_jump_host(remote_host_ip=acu_ip, jump_host_ip=ut_ip, jump_user=ut_user, jump_password=ut_password,
                                                                    max_wait_sec=ping_timeout_after_reboot_secs, retry_interval_sec=5.0, ping_count=1, ping_timeout_sec=2, ssh_timeout_sec=10, check_jump_host_reachable=True, mute=False)
            if not is_reachable_after_reboot:
                LOG(f"ERROR: ACU is not reachable via UT {ut_ip} after reboot within {ping_timeout_after_reboot_secs}s")
                return False
            LOG(f"Post-upgrade validation passed: ACU is reachable via UT {ut_ip} after reboot")
        else:
            LOG(f"Post-upgrade action: skipping ACU reachability check after reboot (should_ping_after_reboot={should_ping_after_reboot})")

        return True
    except Exception as exc:
        LOG(f"ERROR: failed to issue reboot command on UT {ut_ip}: {exc}")
        return False
