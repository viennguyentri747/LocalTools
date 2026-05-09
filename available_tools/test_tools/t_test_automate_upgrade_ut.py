#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import sys
import time
from pathlib import Path
from typing import List, Optional

from available_tools.test_tools.test_upgrade_ut import t_test_upgrade_bundle, t_test_upgrade_iesa
from available_tools.test_tools.test_upgrade_ut.common_utils import EUpgradeResult, run_acu_cmd_via_ut
from available_tools.test_tools.test_upgrade_ut.t_test_upgrade_iesa import EUpgradeComponent, are_upgrade_components_final
from available_tools.test_tools.test_upgrade_ut.upgrade_config import UPGRADE_TYPE_BUNDLE, UPGRADE_TYPE_IESA, UpgradeConfigError, UpgradeItemConfig, UpgradeTestConfig
from dev.dev_common import *
from dev.dev_common.constants import ACU_IP, ACU_PASSWORD, ACU_USER, SSM_PASSWORD, SSM_USER
from dev.dev_common.independent_network_utils import run_ssh_command
from dev.dev_common.network_utils import ping_remote_host_via_jump_host

ARG_CONFIG = f"{ARGUMENT_LONG_PREFIX}config"
ARG_IP = f"{ARGUMENT_LONG_PREFIX}ip"
ARG_OVERRIDE_CYCLES = f"{ARGUMENT_LONG_PREFIX}override_cycles"
ARG_OVERRIDE_MAX_RETRIES_PER_UPGRADE = f"{ARGUMENT_LONG_PREFIX}override_max_retries_per_upgrade"
ARG_CYCLES_LEGACY = f"{ARGUMENT_LONG_PREFIX}cycles"
ARG_MAX_RETRIES_PER_UPGRADE_LEGACY = f"{ARGUMENT_LONG_PREFIX}max_retries_per_upgrade"
DEFAULT_CONFIG_PATH = str(LOCAL_TOOL_REPO_PATH / "storage" / "automate_upgrade_ut_configs" / "sample_automate_upgrade_ut_config.json")
DEFAULT_UT_IP = f"{SSM_NORMAL_IP_PREFIX}.79"
def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Automate UT Upgrade Sequence",
            extra_description="Run upgrade_sequence items in order with cycle + retry handling.",
            args={
                ARG_CONFIG: DEFAULT_CONFIG_PATH,
                ARG_IP: DEFAULT_UT_IP,
                #ARG_OVERRIDE_CYCLES: 1,
                #ARG_OVERRIDE_MAX_RETRIES_PER_UPGRADE: 5,
            },
        ),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())

def _resolve_log_dir_path(log_dir_path: Optional[str], config_path: str) -> Optional[Path]:
    if not log_dir_path:
        return None
    resolved_path = Path(log_dir_path).expanduser()
    if not resolved_path.is_absolute():
        resolved_path = Path(config_path).expanduser().resolve().parent / resolved_path
    resolved_path = resolved_path.resolve()
    resolved_path.mkdir(parents=True, exist_ok=True)
    return resolved_path


def _build_upgrade_log_path(log_dir_path: Optional[Path], ssm_ip: str) -> Optional[Path]:
    if not log_dir_path:
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir_path / ssm_ip.strip() / f"upgrade_log_{timestamp}.txt"


@dataclass
class UpgradeCheckState:
    install_line_count: int = 0


class UpgradeLogHandler:
    def __init__(self, log_path: Optional[Path], ssm_ip: str) -> None:
        self._log_path = log_path
        self._ssm_ip = ssm_ip.strip()
        self._state = UpgradeCheckState()
        if self._log_path:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def _append_line(self, line: str) -> None:
        if not self._log_path:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self._log_path, "a", encoding="utf-8") as file_obj:
            file_obj.write(f"[{ts}] {line}\n")

    def log(self, msg: str) -> None:
        LOG(msg)
        self._append_line(msg)

    def on_install_line(self, line: str) -> None:
        if line.strip():
            self._state.install_line_count += 1
        self._append_line(line)


def _build_upgrade_log_handler(log_path: Optional[Path], ssm_ip: str) -> UpgradeLogHandler:
    return UpgradeLogHandler(log_path=log_path, ssm_ip=ssm_ip)


def _log_msg(msg: str, log_handler: UpgradeLogHandler) -> None:
    log_handler.log(msg)


def _run_acu_cmd_via_ut(ut_ip: str, command: str, timeout: int = 20) -> str:
    return run_acu_cmd_via_ut(
        ut_ip=ut_ip, acu_ip=ACU_IP, acu_user=ACU_USER, acu_password=ACU_PASSWORD, ut_user=SSM_USER, ut_password=SSM_PASSWORD, command=command, timeout_secs=timeout
    )


def _run_upgrade_one_item(ssm_ip: str, item: UpgradeItemConfig, log_handler: UpgradeLogHandler, *, config_path: str) -> EUpgradeResult:
    try:
        if item.type == UPGRADE_TYPE_BUNDLE:
            runtime = t_test_upgrade_bundle.BundleRuntime(ssm_ip=ssm_ip)
            exit_code = t_test_upgrade_bundle.run_once_upgrade(runtime, item.path, base_path=config_path, supported_unit_types=item.supported_unit_types, supported_sub_parts=item.supported_sub_parts)
            if exit_code != 0:
                return EUpgradeResult.FAIL
            return EUpgradeResult.SUCCESS if handle_post_upgrade_bundle(ssm_ip) else EUpgradeResult.FAIL
        if item.type == UPGRADE_TYPE_IESA:
            if not handle_pre_upgrade_iesa(ssm_ip):
                LOG(f"ERROR: handle_pre_upgrade_iesa failed for {ssm_ip}")
                return EUpgradeResult.FAIL
            if not item.timeout_secs:
                LOG(f"ERROR: IESA item requires timeout_secs (>0). Missing for path: {item.path}")
                return EUpgradeResult.FAIL
            runtime = t_test_upgrade_iesa.IesaRuntime(
                ut_ip=ssm_ip,
                ut_user=SSM_USER,
                ut_password=SSM_PASSWORD,
                acu_ip=ACU_IP,
                acu_user=ACU_USER,
                acu_password=ACU_PASSWORD,
            )
            LOG(f"IESA item timeout_secs configured: {item.timeout_secs}s")
            run_result = t_test_upgrade_iesa.run_once_upgrade(runtime, item.path, item.timeout_secs, on_install_line_recv=log_handler.on_install_line, base_path=config_path, supported_unit_types=item.supported_unit_types, supported_sub_parts=item.supported_sub_parts)
            if run_result == EUpgradeResult.SHOULD_SKIP or run_result == EUpgradeResult.ABORT:
                LOG(f"Skipping post handle since result = {run_result}")
                return run_result

            is_success_upgrade = run_result == EUpgradeResult.SUCCESS
            LOG(f"IESA run result before post-handling: {'success' if is_success_upgrade else 'failed'}")
            if not handle_post_upgrade_iesa(is_success_upgrade=is_success_upgrade, ut_ip=ssm_ip):
                LOG(f"ERROR: post-upgrade handling failed (is_success_upgrade={is_success_upgrade})")
                return EUpgradeResult.FAIL
            return run_result
        LOG(f"ERROR: unsupported upgrade type '{item.type}' for path: {item.path}")
        log_handler.log(f"ERROR: unsupported upgrade type '{item.type}' for path: {item.path}")
        return EUpgradeResult.FAIL
    except Exception as exc:
        LOG(f"ERROR: exception while running upgrade item type={item.type}, path={item.path}: {exc}")
        log_handler.log(f"ERROR: exception while running upgrade item type={item.type}, path={item.path}: {exc}")
        return EUpgradeResult.FAIL

def handle_pre_upgrade_iesa(ut_ip: str, timeout_secs_acu_reachable: int = 300) -> bool:
    is_reachable = ping_remote_host_via_jump_host( remote_host_ip=ACU_IP, jump_host_ip=ut_ip, jump_user=SSM_USER, jump_password=SSM_PASSWORD, max_wait_sec=timeout_secs_acu_reachable, retry_interval_sec=5.0, ping_count=1, ping_timeout_sec=2, ssh_timeout_sec=10, check_jump_host_reachable=True, mute=False, )
    if is_reachable:
        LOG(f"Pre-upgrade condition passed: ACU is reachable via UT {ut_ip}")
        return True
    LOG(f"ERROR: ACU is not reachable via UT {ut_ip} within {timeout_secs_acu_reachable}s.")
    return False

def handle_post_upgrade_iesa(is_success_upgrade: bool, ut_ip: str, timeout_before_reboot_secs: int = 240, ping_timeout_after_reboot_secs: int = 300) -> bool:
    LOG(f"Post-upgrade handling started (upgrade_result={'success' if is_success_upgrade else 'failed'})")
    deadline_ts = time.time() + max(1, timeout_before_reboot_secs)
    while time.time() < deadline_ts:
        try:
            running_procs = _run_acu_cmd_via_ut(ut_ip, "ps | grep -E \"\\.iesa|insense_cltool\" | grep -v grep", timeout=10)
            if running_procs.strip():
                LOG(f"Post-upgrade wait: iesa/cltool process is still running on ACU: {running_procs.strip()}")
                time.sleep(10)
                continue
            is_update_status_final, update_status_msg = are_upgrade_components_final(
                base_url=f"http://{ut_ip}",
                components=[EUpgradeComponent.CNX, EUpgradeComponent.MDM, EUpgradeComponent.AIM],
            )
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
        run_ssh_command(
            host_ip=ut_ip,
            user=SSM_USER,
            password=SSM_PASSWORD,
            command="nohup sh -c 'sleep 10; reboot' >/dev/null 2>&1 &",
            timeout=10,
        )
        LOG(f"Post-upgrade action: reboot command issued on UT {ut_ip}")
        sleep_secs_before_ping = 5
        LOG(f"Post-upgrade action: sleeping {sleep_secs_before_ping}s before ACU reachability check after reboot")
        time.sleep(sleep_secs_before_ping)
        is_reachable_after_reboot = ping_remote_host_via_jump_host( remote_host_ip=ACU_IP, jump_host_ip=ut_ip, jump_user=SSM_USER, jump_password=SSM_PASSWORD, max_wait_sec=ping_timeout_after_reboot_secs, retry_interval_sec=5.0, ping_count=1, ping_timeout_sec=2, ssh_timeout_sec=10, check_jump_host_reachable=True, mute=False, )
        if not is_reachable_after_reboot:
            LOG(f"ERROR: ACU is not reachable via UT {ut_ip} after reboot within {ping_timeout_after_reboot_secs}s")
            return False
        LOG(f"Post-upgrade validation passed: ACU is reachable via UT {ut_ip} after reboot")
        return True
    except Exception as exc:
        LOG(f"ERROR: failed to issue reboot command on UT {ut_ip}: {exc}")
        return False

def handle_post_upgrade_bundle(ut_ip: str) -> bool:
    # Do nothing!!
    return True

def run_automate(config: UpgradeTestConfig, ssm_ip: str, *, config_path: str) -> int:
    if not config.upgrade_sequence:
        LOG("ERROR: empty upgrade_sequence in config")
        return 1
    if not ssm_ip.strip():
        LOG("ERROR: missing SSM/UT IP. Set --ip.")
        return 1

    total_cycles = max(1, int(config.cycles))
    retry_count = max(0, int(config.max_retries_per_upgrade))
    wait_secs_before_next_upgrade = max(0, int(config.wait_secs_before_next_upgrade))
    global_log_dir_path = _resolve_log_dir_path(config.upgrade_log_dir_path, config_path=config_path)
    global_log_path = _build_upgrade_log_path(global_log_dir_path, ssm_ip=ssm_ip)
    upgrade_log_handler = _build_upgrade_log_handler(global_log_path, ssm_ip=ssm_ip)
    _log_msg(f"Starting automated upgrade: cycles={total_cycles}, max_retries={retry_count}, wait_secs_before_next_upgrade={wait_secs_before_next_upgrade}, items={len(config.upgrade_sequence)}", upgrade_log_handler)
    if global_log_path:
        _log_msg(f"Upgrade log path: {global_log_path}", upgrade_log_handler)

    for cycle_idx in range(1, total_cycles + 1):
        _log_msg(f"=== Cycle {cycle_idx}/{total_cycles} ===", upgrade_log_handler)
        for item_idx, item in enumerate(config.upgrade_sequence, start=1):
            timeout_part = f", timeout_secs={item.timeout_secs}s" if item.timeout_secs else ""
            _log_msg(f"[{item_idx}/{len(config.upgrade_sequence)}] Upgrade item: type={item.type}, path={item.path}{timeout_part}", upgrade_log_handler)
            attempt = 0
            while True:
                attempt += 1
                _log_msg(f"Attempt {attempt}/{retry_count + 1}", upgrade_log_handler)
                run_result = _run_upgrade_one_item(ssm_ip, item, upgrade_log_handler, config_path=config_path)
                if run_result == EUpgradeResult.SHOULD_SKIP:
                    _log_msg(f"Item skipped: type={item.type}, path={item.path}", upgrade_log_handler)
                    break
                if run_result == EUpgradeResult.ABORT:
                    LOG_EXCEPTION_STR(f"ERROR: item ABORT: type={item.type}, path={item.path}. Check manually fix the issue.", exit=True)
                    exit(1)
                if run_result == EUpgradeResult.SUCCESS:
                    _log_msg(f"Item success: type={item.type}, path={item.path}", upgrade_log_handler)
                    _log_msg(f"Sleeping {wait_secs_before_next_upgrade}s before next item", upgrade_log_handler)
                    time.sleep(wait_secs_before_next_upgrade)
                    break
                if attempt > retry_count:
                    _log_msg(f"ERROR: item failed after retries: type={item.type}, path={item.path}", upgrade_log_handler)
                    return 1
                _log_msg("Item failed; retrying...", upgrade_log_handler)

    _log_msg("All upgrade cycles completed successfully", upgrade_log_handler)
    return 0


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automate ordered UT software upgrades from config.upgrade_sequence.",
        usage=f"{Path(__file__).name} {ARG_CONFIG} <json_config> {ARG_IP} <ssm_ip> [{ARG_OVERRIDE_CYCLES} <n>] [{ARG_OVERRIDE_MAX_RETRIES_PER_UPGRADE} <n>]",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_CONFIG, required=True, help="Path to JSON configuration file")
    parser.add_argument(ARG_IP, required=True, help="SSM/UT IP (required)")
    parser.add_argument(ARG_OVERRIDE_CYCLES, ARG_CYCLES_LEGACY, dest="override_cycles", type=int, help="Override cycle count")
    parser.add_argument(ARG_OVERRIDE_MAX_RETRIES_PER_UPGRADE, ARG_MAX_RETRIES_PER_UPGRADE_LEGACY, dest="override_max_retries_per_upgrade", type=int, help="Override max retries per upgrade item")
    return parser.parse_args(argv)



def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    try:
        config = UpgradeTestConfig.load_from_file(get_arg_value(args, ARG_CONFIG)).with_overrides(cycles=getattr(args, "override_cycles", None), max_retries_per_upgrade=getattr(args, "override_max_retries_per_upgrade", None))
    except UpgradeConfigError as exc:
        LOG(f"ERROR: {exc}")
        raise SystemExit(1)
    exit_code = run_automate(config, ssm_ip=get_arg_value(args, ARG_IP), config_path=get_arg_value(args, ARG_CONFIG))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main(sys.argv[1:])
