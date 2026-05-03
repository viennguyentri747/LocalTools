#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from available_tools.test_tools.test_upgrade_ut.bundle_api_helper import apply_bundle, get_component_upgrade_status, get_current_state, get_sdl_stats, proceed_to_next_install_step, start_over_installation, upload_bundle, wait_util_awaiting_next
from dev.dev_common import *

DEFAULT_MONITOR_INTERVAL_SECS = 2
DEFAULT_MONITOR_TIMEOUT_SECS = 6000
DEFAULT_NO_STATE_CHANGE_TIMEOUT_SECS = 600
ARG_BUNDLE_PATH = f"{ARGUMENT_LONG_PREFIX}path"
ARG_SSM_IP = f"{ARGUMENT_LONG_PREFIX}ssm_ip"
DEFAULT_SSM_IP = f"{SSM_NORMAL_IP_PREFIX}.107"
DEFAULT_BUNDLE_PATH = str(LOCAL_TOOL_REPO_PATH / "storage" / "in_bundle" / "OW-IESA_2.0.0.9T_FTM_1.22_AIM_1.0.0.196_CNX_420.204.1.022_MDM_4.0.1.305RP_MIM_0.0.0_SSM_5.0.70_SSM_BSP_4.0.24.tar.gz")


class InstallBundleReturnCode(Enum):
    SUCCESS = 1
    FAIL_UPLOAD = 10
    FAIL_TIMEOUT = 11
    FAIL_AIM = 12
    FAIL_PREPARE = 13
    FAIL_APPLY = 14
    FAIL_FILE_NOT_FOUND = 15
    FAIL_UNKNOWN = 99


@dataclass(frozen=True)
class BundleRuntime:
    ssm_ip: str


def _resolve_path(path: str, base_path: Optional[str] = None) -> str:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return str(candidate.resolve())
    if base_path:
        return str((Path(base_path).expanduser().resolve().parent / candidate).resolve())
    return str(candidate.resolve())


def _prepare_install(base_url: str) -> bool:
    if not start_over_installation(base_url):
        LOG("ERROR: start_over_installation failed")
        return False
    if not wait_util_awaiting_next(base_url, name="install_initial", progress=100, timeout=300):
        LOG("ERROR: timeout waiting for install_initial")
        return False
    if not proceed_to_next_install_step(base_url):
        LOG("ERROR: failed to proceed to select_installation_role")
        return False
    if not wait_util_awaiting_next(base_url, name="select_installation_role", progress=None, timeout=300):
        LOG("ERROR: timeout waiting for select_installation_role")
        return False
    if not proceed_to_next_install_step(base_url):
        LOG("ERROR: failed to proceed to upload_sw_bundle")
        return False
    if not wait_util_awaiting_next(base_url, name="upload_sw_bundle", progress=100, timeout=300):
        LOG("ERROR: timeout waiting for upload_sw_bundle")
        return False
    return True


def _monitor_installation(base_url: str, interval_secs: int = DEFAULT_MONITOR_INTERVAL_SECS, max_timeout_secs: int = DEFAULT_MONITOR_TIMEOUT_SECS, no_state_change_timeout_secs: int = DEFAULT_NO_STATE_CHANGE_TIMEOUT_SECS) -> InstallBundleReturnCode:
    start_time = time.time()
    last_change_ts = start_time
    last_state_name = ""
    last_state_progress = -1
    last_state_status = ""
    component_statuses: Dict[str, str] = {}
    while time.time() - start_time < max_timeout_secs:
        try:
            sdl_stats = get_sdl_stats(base_url)
            if sdl_stats:
                LOG(f"SDL busy={sdl_stats.get('sdl_is_busy')} status={sdl_stats.get('sdl_status')} status_advanced={sdl_stats.get('sdl_status_advanced')} progress={sdl_stats.get('sw_update_percent')}%")
            state_info = get_current_state(base_url)
            component_status = get_component_upgrade_status(base_url)
            state_name = str(state_info.get("name", "Unknown")) if state_info else "Unknown"
            state_progress = int(state_info.get("progress", 0)) if state_info else 0
            state_status = str(state_info.get("status", "Unknown")) if state_info else "Unknown"
            if state_name != last_state_name or state_progress != last_state_progress or state_status != last_state_status:
                LOG(f"State: {state_name} | Progress: {state_progress}% | Status: {state_status}")
                last_state_name, last_state_progress, last_state_status = state_name, state_progress, state_status
                last_change_ts = time.time()
            for component, status in component_status.items():
                if component_statuses.get(component) != status:
                    LOG(f"Component {component}: {status}")
                    component_statuses[component] = status
                    last_change_ts = time.time()
                if component == "aim" and status == "failed":
                    LOG("ERROR: AIM installation failed")
                    return InstallBundleReturnCode.FAIL_AIM
            if state_progress == 100 and state_status == "awaiting_next":
                LOG("Installation completed")
                return InstallBundleReturnCode.SUCCESS
            if time.time() - last_change_ts > no_state_change_timeout_secs:
                LOG(f"ERROR: No state/component change in {no_state_change_timeout_secs}s")
                return InstallBundleReturnCode.FAIL_TIMEOUT
            time.sleep(interval_secs)
        except Exception as exc:
            LOG(f"ERROR: monitoring error: {exc}")
            time.sleep(interval_secs)
    LOG("ERROR: installation monitor timeout")
    return InstallBundleReturnCode.FAIL_TIMEOUT


def run_once_upgrade(runtime: BundleRuntime, bundle_path: str, *, base_path: Optional[str] = None) -> int:
    bundle_path = _resolve_path(bundle_path, base_path=base_path)
    if not os.path.isfile(bundle_path):
        LOG(f"ERROR: bundle file not found: {bundle_path}")
        return 1
    if not runtime.ssm_ip.strip():
        LOG("ERROR: missing ssm_ip")
        return 1
    base_url = f"http://{runtime.ssm_ip.strip()}"
    LOG(f"Installing bundle once: {os.path.basename(bundle_path)}")
    try:
        if not _prepare_install(base_url):
            return 1
        if not upload_bundle(base_url, bundle_path):
            return 1
        if not apply_bundle(base_url):
            return 1
        return 0 if _monitor_installation(base_url) == InstallBundleReturnCode.SUCCESS else 1
    except Exception as exc:
        LOG(f"ERROR: Unexpected exception while installing bundle {bundle_path}: {exc}")
        return 1


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one .tar.gz bundle upgrade using the SSM install API.",
        usage=f"{Path(__file__).name} {ARG_BUNDLE_PATH} <bundle_path> {ARG_SSM_IP} <ssm_ip>",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.epilog = build_examples_epilog(getToolData().tool_template, Path(__file__))
    parser.add_argument(ARG_BUNDLE_PATH, required=True, help="Bundle path to install once")
    parser.add_argument(ARG_SSM_IP, required=True, help="SSM IP for bundle install API")
    return parser.parse_args(argv)


def get_tool_templates() -> List[ToolTemplate]:
    return [
        ToolTemplate(
            name="Upgrade One Bundle",
            extra_description="Upload and apply one .tar.gz bundle to a UT SSM endpoint.",
            args={ARG_BUNDLE_PATH: DEFAULT_BUNDLE_PATH, ARG_SSM_IP: DEFAULT_SSM_IP},
        ),
    ]


def getToolData() -> ToolData:
    return ToolData(tool_template=get_tool_templates())


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    runtime = BundleRuntime(ssm_ip=get_arg_value(args, ARG_SSM_IP))
    exit_code = run_once_upgrade(runtime, get_arg_value(args, ARG_BUNDLE_PATH))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main(sys.argv[1:])
