#!/usr/local/bin/local_python
from __future__ import annotations

import time
from enum import Enum
from typing import List, Optional

from dev.dev_common import LOG
from dev.dev_common.constants import ACU_IP, ACU_PASSWORD, ACU_USER, SSM_PASSWORD, SSM_USER
from dev.dev_common.independent_network_utils import run_ssh_command


class EUpgradeResult(str, Enum):
    SUCCESS = "success"
    SHOULD_SKIP = "should_skip"
    FAIL = "fail"
    ABORT = "abort"


def run_acu_cmd_via_ut(ut_ip: str, command: str, timeout_secs: int = 20, acu_ip: str = ACU_IP, acu_user: str = ACU_USER, acu_password: str = ACU_PASSWORD, ut_user: str = SSM_USER, ut_password: str = SSM_PASSWORD) -> str:
    stdout, stderr = run_ssh_command(
        host_ip=acu_ip,
        user=acu_user,
        password=acu_password,
        command=command,
        timeout=max(1, int(timeout_secs)),
        jump_host_ip=ut_ip,
        jump_user=ut_user,
        jump_password=ut_password,
    )
    if stderr.strip():
        LOG(f"WARNING: ACU command stderr: {stderr.strip()}")
    return stdout.strip()


def run_acu_cmd_via_ut_with_retry(ut_ip: str, command: str, timeout_secs: int, secs_between_each_retry: float = 2.0, acu_ip: str = ACU_IP, acu_user: str = ACU_USER, acu_password: str = ACU_PASSWORD, ut_user: str = SSM_USER, ut_password: str = SSM_PASSWORD) -> str:
    max_wait = max(1, int(timeout_secs))
    deadline = time.time() + max_wait
    last_exc: Optional[Exception] = None
    while True:
        remain = int(deadline - time.time())
        if remain <= 0:
            break
        try:
            return run_acu_cmd_via_ut(ut_ip=ut_ip, command=command, timeout_secs=min(20, remain), acu_ip=acu_ip, acu_user=acu_user, acu_password=acu_password, ut_user=ut_user, ut_password=ut_password)
        except Exception as exc:
            last_exc = exc
            sleep_secs = min(max(0.0, secs_between_each_retry), max(0.0, deadline - time.time()))
            if sleep_secs <= 0:
                break
            LOG(f"ACU cmd retry failed for '{command}': {exc} (retry in {sleep_secs:.1f}s)")
            time.sleep(sleep_secs)
    raise RuntimeError(f"ACU command failed within {max_wait}s for '{command}': {last_exc}")


def check_target_support(ut_ip: str, acu_ip: str, acu_user: str, acu_password: str, ut_user: str, ut_password: str, supported_unit_types: Optional[List[str]] = None, supported_sub_parts: Optional[List[str]] = None, timeout_secs: int = 180) -> EUpgradeResult:
    deadline = time.time() + max(1, int(timeout_secs))
    normalized_supported_unit_types = [x.strip().lower() for x in (supported_unit_types or []) if str(x).strip()]
    normalized_supported_sub_parts = [x.strip().upper() for x in (supported_sub_parts or []) if str(x).strip()]

    def _run_precheck_cmd(command: str) -> str:
        remain = int(deadline - time.time())
        if remain <= 0:
            raise TimeoutError(f"pre-upgrade timeout exceeded while running '{command}'")
        return run_acu_cmd_via_ut_with_retry(ut_ip=ut_ip, acu_ip=acu_ip, acu_user=acu_user, acu_password=acu_password, ut_user=ut_user, ut_password=ut_password, command=command, timeout_secs=remain, secs_between_each_retry=2.0)

    try:
        if normalized_supported_unit_types:
            unit_type = ""
            while True:
                unit_type = _run_precheck_cmd("cat /var/volatile/unit_type 2>/dev/null").strip().lower()
                if unit_type:
                    break
                remain_wait = deadline - time.time()
                if remain_wait <= 0:
                    LOG("ERROR: unit_type is empty or unavailable within precheck timeout")
                    return EUpgradeResult.FAIL
                time.sleep(min(2.0, remain_wait))
            if unit_type not in normalized_supported_unit_types:
                LOG(f"Skipping item: unit_type={unit_type} not in supported_unit_types={normalized_supported_unit_types}")
                return EUpgradeResult.SHOULD_SKIP
            LOG(f"Target support check passed: Found unit_type={unit_type} is supported")

        if normalized_supported_sub_parts:
            sub_part = ""
            while True:
                sub_part = _run_precheck_cmd("LD_LIBRARY_PATH=/opt/lib /opt/bin/product_config | grep -oE '[A-Z]+-[A-Z0-9]+' | head -1 | cut -d'-' -f1").strip().upper()
                if sub_part:
                    break
                remain_wait = deadline - time.time()
                if remain_wait <= 0:
                    LOG("ERROR: sub_part is empty or unavailable within precheck timeout")
                    return EUpgradeResult.FAIL
                time.sleep(min(2.0, remain_wait))
            if sub_part not in normalized_supported_sub_parts:
                LOG(f"Skipping item: sub_part={sub_part} not in supported_sub_parts={normalized_supported_sub_parts}")
                return EUpgradeResult.SHOULD_SKIP
            LOG(f"Target support check passed: Found sub_part={sub_part} is supported")
        return EUpgradeResult.SUCCESS
    except Exception as exc:
        LOG(f"ERROR: target support check failed: {exc}")
        return EUpgradeResult.FAIL
