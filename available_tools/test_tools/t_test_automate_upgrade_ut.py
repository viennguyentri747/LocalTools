#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import re
import sys
from pathlib import Path
from typing import List, Optional

from available_tools.test_tools.test_upgrade_ut import t_test_upgrade_bundle, t_test_upgrade_iesa
from available_tools.test_tools.test_upgrade_ut.bundle_api_helper import get_update_status
from available_tools.test_tools.test_upgrade_ut.upgrade_config import UPGRADE_TYPE_BUNDLE, UPGRADE_TYPE_IESA, UpgradeConfigError, UpgradeItemConfig, UpgradeTestConfig
from dev.dev_common import *
from dev.dev_common.constants import ACU_IP, ACU_PASSWORD, ACU_USER, SSM_PASSWORD, SSM_USER
from dev.dev_common.independent_network_utils import run_ssh_command

ARG_CONFIG = f"{ARGUMENT_LONG_PREFIX}config"
ARG_IP = f"{ARGUMENT_LONG_PREFIX}ip"
ARG_CYCLES = f"{ARGUMENT_LONG_PREFIX}cycles"
ARG_MAX_REBOOT_RETRIES = f"{ARGUMENT_LONG_PREFIX}max_reboot_retries"
DEFAULT_CONFIG_PATH = str(LOCAL_TOOL_REPO_PATH / "storage" / "automate_upgrade_ut_configs" / "sample_upgrade_sequence.json")
DEFAULT_UT_IP = f"{SSM_NORMAL_IP_PREFIX}.79"
BOOTPART_FILE_PATH = "/run/media/boot/bootpart.txt"
MIN_INSTALL_LOG_LINES = 10

def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Automate UT Upgrade Sequence",
            extra_description="Run upgrade_sequence items in order with cycle + retry handling.",
            args={
                ARG_CONFIG: DEFAULT_CONFIG_PATH,
                ARG_IP: DEFAULT_UT_IP,
                ARG_CYCLES: 1,
                ARG_MAX_REBOOT_RETRIES: 1,
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
    bootpart_before: Optional[str] = None
    expected_bootpart_after: Optional[str] = None


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

    def _run_acu_cmd_via_ut(self, command: str) -> str:
        stdout, stderr = run_ssh_command(
            host_ip=ACU_IP,
            user=ACU_USER,
            password=ACU_PASSWORD,
            command=command,
            timeout=20,
            jump_host_ip=self._ssm_ip,
            jump_user=SSM_USER,
            jump_password=SSM_PASSWORD,
        )
        if stderr.strip():
            self.log(f"WARNING: ACU command stderr: {stderr.strip()}")
        return stdout.strip()

    def _extract_partition(self, raw_text: str) -> Optional[str]:
        for pattern in [r"mmcblk1p([23])", r"\b([23])\b"]:
            match = re.search(pattern, raw_text)
            if match:
                return match.group(1)
        return None

    def _read_bootpart(self) -> str:
        raw_output = self._run_acu_cmd_via_ut(f"cat {BOOTPART_FILE_PATH}")
        parsed = self._extract_partition(raw_output)
        if not parsed:
            raise RuntimeError(f"Cannot parse bootpart from output: '{raw_output}'")
        return parsed

    def _read_current_root_partition(self) -> str:
        command = "lsblk -no NAME,MOUNTPOINT | awk '/mmcblk1p[23]/ && $2 == \"/\" { n = $1; sub(/.*mmcblk1p/, \"\", n); print n }'"
        raw_output = self._run_acu_cmd_via_ut(command)
        parsed = self._extract_partition(raw_output)
        if not parsed:
            raise RuntimeError(f"Cannot parse current root partition from output: '{raw_output}'")
        return parsed

    def prepare_for_upgrade_attempt(self) -> None:
        self._state = UpgradeCheckState()
        current_root_partition = self._read_current_root_partition()
        current_bootpart = self._read_bootpart()
        if current_bootpart != current_root_partition:
            raise RuntimeError(
                f"bootpart mismatch before upgrade (bootpart={current_bootpart}, current_root={current_root_partition}). "
                f"Please verify UT/ACU partition state first."
            )
        self._state.bootpart_before = current_bootpart
        self._state.expected_bootpart_after = "3" if current_bootpart == "2" else "2"
        self.log(f"Pre-upgrade check: current_root_partition={current_root_partition}, bootpart={current_bootpart}, expected_after_upgrade={self._state.expected_bootpart_after}")

    def evaluate_upgrade_completion(self) -> bool:
        bootpart_after = self._read_bootpart()
        condition_1_ok = bool(self._state.expected_bootpart_after and bootpart_after == self._state.expected_bootpart_after)
        condition_2_ok = self._state.install_line_count >= MIN_INSTALL_LOG_LINES
        update_status = get_update_status(base_url=f"http://{self._ssm_ip}") or {}
        cnx_status = str(update_status.get("CNX", "")).strip().lower()
        mdm_status = str(update_status.get("MDM", "")).strip().lower()
        final_states = {"update_success", "update_fail"}
        condition_3_ok = cnx_status in final_states and mdm_status in final_states
        self.log(
            f"Upgrade completion check: "
            f"condition1_bootpart_changed={condition_1_ok} (before={self._state.bootpart_before}, after={bootpart_after}, expected={self._state.expected_bootpart_after}); "
            f"condition2_install_log_lines={self._state.install_line_count}/{MIN_INSTALL_LOG_LINES}; "
            f"condition3_component_final={condition_3_ok} (CNX={cnx_status or 'N/A'}, MDM={mdm_status or 'N/A'})"
        )
        if condition_1_ok and condition_2_ok and condition_3_ok:
            show_noti(title="Upgrade Complete", message=f"Upgrade complete on {self._ssm_ip}", no_log_on_success=True)
            self.log("Upgrade completion conditions met.")
            return True


        self.log("Upgrade completion conditions not met.")
        return False


def _build_upgrade_log_handler(log_path: Optional[Path], ssm_ip: str) -> UpgradeLogHandler:
    return UpgradeLogHandler(log_path=log_path, ssm_ip=ssm_ip)


def _log_msg(msg: str, log_handler: UpgradeLogHandler) -> None:
    log_handler.log(msg)


def _run_one_item(config: UpgradeTestConfig, ssm_ip: str, item: UpgradeItemConfig, log_handler: UpgradeLogHandler, *, config_path: str) -> int:
    if item.type == UPGRADE_TYPE_BUNDLE:
        runtime = t_test_upgrade_bundle.BundleRuntime(ssm_ip=ssm_ip)
        return t_test_upgrade_bundle.run_once_upgrade(runtime, item.path, base_path=config_path)
    if item.type == UPGRADE_TYPE_IESA:
        runtime = t_test_upgrade_iesa.IesaRuntime(
            ut_ip=ssm_ip,
            ut_user=SSM_USER,
            ut_password=SSM_PASSWORD,
            acu_ip=ACU_IP,
            acu_user=ACU_USER,
            acu_password=ACU_PASSWORD,
        )
        return t_test_upgrade_iesa.run_once_upgrade(runtime, item.path, on_install_line_recv=log_handler.on_install_line, base_path=config_path)
    LOG(f"ERROR: unsupported upgrade type '{item.type}' for path: {item.path}")
    log_handler.log(f"ERROR: unsupported upgrade type '{item.type}' for path: {item.path}")
    return 1


def run_automate(config: UpgradeTestConfig, ssm_ip: str, *, config_path: str) -> int:
    if not config.upgrade_sequence:
        LOG("ERROR: empty upgrade_sequence in config")
        return 1
    if not ssm_ip.strip():
        LOG("ERROR: missing SSM/UT IP. Set --ip.")
        return 1

    total_cycles = max(1, int(config.cycles))
    retry_count = max(0, int(config.retry.max_reboot_retries))
    global_log_dir_path = _resolve_log_dir_path(config.upgrade_log_dir_path, config_path=config_path)
    global_log_path = _build_upgrade_log_path(global_log_dir_path, ssm_ip=ssm_ip)
    upgrade_log_handler = _build_upgrade_log_handler(global_log_path, ssm_ip=ssm_ip)
    _log_msg(f"Starting automated upgrade: cycles={total_cycles}, max_retries={retry_count}, items={len(config.upgrade_sequence)}", upgrade_log_handler)
    if global_log_path:
        _log_msg(f"Upgrade log path: {global_log_path}", upgrade_log_handler)

    for cycle_idx in range(1, total_cycles + 1):
        _log_msg(f"=== Cycle {cycle_idx}/{total_cycles} ===", upgrade_log_handler)
        for item_idx, item in enumerate(config.upgrade_sequence, start=1):
            _log_msg(f"[{item_idx}/{len(config.upgrade_sequence)}] Upgrade item: type={item.type}, path={item.path}", upgrade_log_handler)
            attempt = 0
            while True:
                attempt += 1
                _log_msg(f"Attempt {attempt}/{retry_count + 1}", upgrade_log_handler)
                if item.type == UPGRADE_TYPE_IESA:
                    try:
                        upgrade_log_handler.prepare_for_upgrade_attempt()
                    except Exception as exc:
                        _log_msg(f"ERROR: pre-upgrade partition validation failed: {exc}", upgrade_log_handler)
                        return 1
                exit_code = _run_one_item(config, ssm_ip, item, upgrade_log_handler, config_path=config_path)
                if exit_code == 0 and item.type == UPGRADE_TYPE_IESA:
                    try:
                        if not upgrade_log_handler.evaluate_upgrade_completion():
                            _log_msg("ERROR: upgrade completion conditions not met.", upgrade_log_handler)
                            exit_code = 1
                    except Exception as exc:
                        _log_msg(f"ERROR: failed to evaluate upgrade completion: {exc}", upgrade_log_handler)
                        exit_code = 1
                if exit_code == 0:
                    _log_msg(f"Item success: type={item.type}, path={item.path}", upgrade_log_handler)
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
        usage=f"{Path(__file__).name} {ARG_CONFIG} <json_config> {ARG_IP} <ssm_ip> [{ARG_CYCLES} <n>] [{ARG_MAX_REBOOT_RETRIES} <n>]",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_CONFIG, required=True, help="Path to JSON configuration file")
    parser.add_argument(ARG_IP, required=True, help="SSM/UT IP (required)")
    parser.add_argument(ARG_CYCLES, type=int, help="Override cycle count")
    parser.add_argument(ARG_MAX_REBOOT_RETRIES, type=int, help="Override retry.max_reboot_retries")
    return parser.parse_args(argv)



def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    try:
        config = UpgradeTestConfig.load_from_file(get_arg_value(args, ARG_CONFIG)).with_overrides(cycles=get_arg_value(args, ARG_CYCLES), max_reboot_retries=get_arg_value(args, ARG_MAX_REBOOT_RETRIES))
    except UpgradeConfigError as exc:
        LOG(f"ERROR: {exc}")
        raise SystemExit(1)
    exit_code = run_automate(config, ssm_ip=get_arg_value(args, ARG_IP), config_path=get_arg_value(args, ARG_CONFIG))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main(sys.argv[1:])
