#!/usr/local/bin/local_python
from __future__ import annotations

import enum
import os
import time
from typing import Any, Dict, Optional

import requests
from requests_toolbelt import MultipartEncoder

from dev.dev_common import LOG

STATUS_KEY = "status"
OK_VALUE = "ok"
YES_VALUE = "yes"
API = "api"
INSTALL = "install"


class InstallRole(str, enum.Enum):
    STANDALONE = "standalone"
    PRIMARY = "primary"
    SECONDARY = "secondary"

    def __str__(self) -> str:
        return self.value


class UtComponent(str, enum.Enum):
    AIM = "aim"
    CNX = "cnx"
    EGR = "egr"
    MDM = "mdm"
    MIM = "mim"

    def __str__(self) -> str:
        return self.value


def get_basic_sw_info(base_url: str) -> Optional[Dict[str, Any]]:
    try:
        response = requests.get(f"{base_url}/{API}/system/swinfo", timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        LOG(f"Error getting software info: {exc}")
        return None


def get_sw_details(base_url: str) -> Optional[Dict[str, Any]]:
    try:
        response = requests.get(f"{base_url}/{API}/system/swdetails", timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        LOG(f"Error getting software details: {exc}")
        return None


def start_over_installation(base_url: str) -> bool:
    try:
        response = requests.get(f"{base_url}/{API}/{INSTALL}/start_over", timeout=60)
        return response.status_code == 200 and response.json().get(STATUS_KEY) == OK_VALUE
    except Exception as exc:
        LOG(f"Error running start_over_installation: {exc}")
        return False


def set_install_role(base_url: str, role: InstallRole) -> bool:
    try:
        response = requests.post(f"{base_url}/{API}/{INSTALL}/cuc_role", json={"installation_role": role.value}, timeout=60)
        response.raise_for_status()
        return response.json().get(STATUS_KEY) == OK_VALUE
    except Exception as exc:
        LOG(f"Error setting install role to {role}: {exc}")
        return False


def get_managed_components(base_url: str) -> Optional[Dict[UtComponent, bool]]:
    try:
        response = requests.get(f"{base_url}/{API}/sdl/managed_components", timeout=10)
        response.raise_for_status()
        raw_data: Dict[str, bool] = response.json()
        valid_keys = {member.value for member in UtComponent}
        converted_data: Dict[UtComponent, bool] = {}
        for key, value in raw_data.items():
            if key in valid_keys:
                converted_data[UtComponent(key)] = value
            else:
                LOG(f"Warning: Received unexpected component key '{key}' from API.")
        return converted_data
    except Exception as exc:
        LOG(f"Error fetching managed components: {exc}")
        return None


def get_sdl_stats(base_url: str) -> Optional[Dict[str, Any]]:
    try:
        response = requests.get(f"{base_url}/{API}/sdl/sdlstats", timeout=15)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        LOG(f"ERROR: Unexpected error in get_sdl_stats: {exc}")
        return None


def is_all_ut_components_up(base_url: str) -> bool:
    try:
        response = requests.get(f"{base_url}/{API}/{INSTALL}/check_component", timeout=10)
        return response.status_code == 200 and response.json().get(STATUS_KEY) == YES_VALUE
    except Exception as exc:
        LOG(f"Error checking component readiness: {exc}")
        return False


def wait_util_awaiting_next(base_url: str, name: Optional[str] = None, progress: Optional[int] = None, timeout: int = 300) -> bool:
    sanity_wait_secs = 5
    LOG(f"Sanity wait {sanity_wait_secs}s before waiting for 'awaiting_next' (name={name}, progress={progress})")
    time.sleep(sanity_wait_secs)
    start_time = time.time()
    min_check_count = 10
    check_count = 0
    while time.time() - start_time < timeout or check_count < min_check_count:
        check_count += 1
        state_info = get_current_state(base_url)
        if check_count % 5 == 0:
            LOG(f"Current state: {state_info}")
        if isinstance(state_info, dict) and state_info.get(STATUS_KEY) == "awaiting_next":
            if (name is None or state_info.get("name") == name) and (progress is None or state_info.get("progress") == progress):
                return True
        time.sleep(1)
    LOG(f"Timeout after {timeout}s waiting for awaiting_next")
    return False


def get_current_state(base_url: str) -> Dict[Any, Any]:
    try:
        response = requests.get(f"{base_url}/{API}/{INSTALL}/current_state", timeout=10)
        return response.json() if response.status_code == 200 else {}
    except Exception as exc:
        LOG(f"Error getting current state: {exc}")
        return {}


def upload_bundle(base_url: str, bundle_path: str) -> Optional[Dict[str, str]]:
    try:
        with open(bundle_path, "rb") as file_obj:
            form = MultipartEncoder(fields={"file": (os.path.basename(bundle_path), file_obj, "application/octet-stream")})
            headers = {"Content-Type": form.content_type}
            file_size_mb = round(os.path.getsize(bundle_path) / (1024 * 1024), 1)
            timeout_upload = max(60, int(file_size_mb * 1.0))
            LOG(f"Uploading bundle size={file_size_mb}MB timeout={timeout_upload}s")
            response = requests.post(f"{base_url}/{API}/{INSTALL}/upload_sw_bundle", headers=headers, data=form, timeout=timeout_upload)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else None
    except Exception as exc:
        LOG(f"Error uploading bundle: {exc}")
        return None


def proceed_to_next_install_step(base_url: str) -> bool:
    try:
        response = requests.get(f"{base_url}/{API}/{INSTALL}/next", timeout=10)
        if response.status_code != 200 or response.json().get(STATUS_KEY) != OK_VALUE:
            LOG("Failed to proceed to next install step.")
            return False
        LOG("Proceeded to next install step.")
        return True
    except requests.RequestException as exc:
        LOG(f"Error proceeding to next install step: {exc}")
        return False


def get_component_upgrade_status(base_url: str) -> Dict[str, Any]:
    try:
        response = requests.get(f"{base_url}/{API}/sdl/component_upgrade_status", timeout=10)
        return response.json() if response.status_code == 200 else {}
    except requests.RequestException:
        return {}


def apply_bundle(base_url: str, flag: bool = True) -> bool:
    LOG("Applying software bundle...")
    try:
        response = requests.get(f"{base_url}/{API}/{INSTALL}/update_sw_bundle/{str(flag).lower()}", timeout=60)
        if response.status_code != 200:
            LOG(f"ERROR: Bundle apply request failed: HTTP {response.status_code}")
            return False
        result = response.json()
        if result.get(STATUS_KEY) == OK_VALUE:
            LOG("Bundle apply initiated successfully.")
            return True
        LOG(f"ERROR: Bundle apply failed: {result}")
        return False
    except Exception as exc:
        LOG(f"ERROR: Error applying bundle: {exc}")
        return False


def get_update_status(base_url: str) -> Optional[Dict[str, Any]]:
    try:
        response = requests.get(f"{base_url}/{API}/{INSTALL}/check_update_status", timeout=60)
        if response.status_code == 200:
            data = response.json()
            return data if isinstance(data, dict) else None
        LOG(f"ERROR: Failed to get update status: {response.status_code}")
        return None
    except Exception as exc:
        LOG(f"ERROR: Error checking update status: {exc}")
        return None
