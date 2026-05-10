#!/usr/local/bin/local_python
from __future__ import annotations

import re
import time
from enum import Enum
from typing import Callable, List, Optional, Tuple

from available_tools.test_tools.test_upgrade_ut.bundle_api_helper import get_update_status
from available_tools.test_tools.test_upgrade_ut.common_utils import run_acu_cmd_via_ut
from dev.dev_common import LOG
from dev.dev_common.constants import ACU_IP, ACU_PASSWORD, ACU_USER, SSM_PASSWORD, SSM_USER
from dev.dev_common.independent_network_utils import run_ssh_command
from dev.dev_common.network_utils import ping_remote_host_via_jump_host


class EUpgradeComponent(str, Enum):
    CNX = "CNX"
    MDM = "MDM"
    AIM = "AIM"


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


def check_safe_reboot_ut(ut_ip: str, timeout_before_reboot_secs: int = 240, should_ping_after_reboot: bool = False, ping_timeout_after_reboot_secs: int = 300, acu_ip: str = ACU_IP, acu_user: str = ACU_USER, acu_password: str = ACU_PASSWORD, ut_user: str = SSM_USER, ut_password: str = SSM_PASSWORD) -> bool:
    deadline_ts = time.time() + max(1, timeout_before_reboot_secs)
    while time.time() < deadline_ts:
        try:
            running_procs = run_acu_cmd_via_ut(ut_ip=ut_ip, command="ps | grep -E \"\\.iesa|insense_cltool\" | grep -v grep",
                                               timeout_secs=10, acu_ip=acu_ip, acu_user=acu_user, acu_password=acu_password, ut_user=ut_user, ut_password=ut_password)
            if running_procs.strip():
                LOG(f"Post-upgrade wait: iesa/cltool process is still running on ACU: {running_procs.strip()}")
                time.sleep(10)
                continue
            is_update_status_final, update_status_msg = are_upgrade_components_final(
                base_url=f"http://{ut_ip}", components=[EUpgradeComponent.CNX, EUpgradeComponent.MDM, EUpgradeComponent.AIM])
            if not is_update_status_final:
                LOG(f"Post-upgrade wait: update status is not final yet ({update_status_msg})")
                time.sleep(10)
                continue
            LOG(f"Post-upgrade condition passed: no iesa/cltool process and update status final ({update_status_msg})")
            break
        except Exception as exc:
            LOG(f"Post-upgrade wait: ACU check failed, retrying in 10s: {exc}")
            time.sleep(10)
    else:
        LOG(f"ERROR: timeout waiting post-upgrade conditions before reboot ({timeout_before_reboot_secs}s)")
        return False

    try:
        sleep_secs_before_reboot: int = 10
        run_ssh_command(host_ip=ut_ip, user=ut_user, password=ut_password, command=f"nohup sh -c 'sleep {sleep_secs_before_reboot}; reboot' >/dev/null 2>&1 &", timeout=10)
        LOG(f"Post-upgrade action: reboot command issued on UT {ut_ip}")
        sleep_secs_before_continue: int = sleep_secs_before_reboot + 5
        LOG(f"Post-upgrade action: sleeping {sleep_secs_before_continue}s before continuing")
        time.sleep(sleep_secs_before_continue)
        if should_ping_after_reboot:
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
