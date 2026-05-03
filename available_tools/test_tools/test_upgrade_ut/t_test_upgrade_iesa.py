#!/usr/local/bin/local_python
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from available_tools.iesa_tools.copy_to_ut_runner import _run_iesa_install_via_python
from dev.dev_common import *
from dev.dev_common.constants import ACU_IP, ACU_PASSWORD, ACU_USER, CHECKSUM_TYPE_MD5, SSM_PASSWORD, SSM_USER
from dev.dev_common.network_utils import copy_to_remote_via_jump_host, get_remote_file_checksum

REMOTE_DOWNLOAD_DIR = "/home/root/download"
ARG_IESA_PATH = f"{ARGUMENT_LONG_PREFIX}path"
ARG_UT_IP = f"{ARGUMENT_LONG_PREFIX}ut_ip"
ARG_LOG_PATH = f"{ARGUMENT_LONG_PREFIX}log_path"
ARG_UT_USER = f"{ARGUMENT_LONG_PREFIX}ut_user"
ARG_UT_PASSWORD = f"{ARGUMENT_LONG_PREFIX}ut_password"
ARG_ACU_IP = f"{ARGUMENT_LONG_PREFIX}acu_ip"
ARG_ACU_USER = f"{ARGUMENT_LONG_PREFIX}acu_user"
ARG_ACU_PASSWORD = f"{ARGUMENT_LONG_PREFIX}acu_password"
ARG_REMOTE_DIR = f"{ARGUMENT_LONG_PREFIX}remote_dir"
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
        return lambda _line: None
    log_file = Path(log_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    def _on_line_recv(line: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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


def run_once_upgrade(runtime: IesaRuntime, iesa_path: str, log_path: Optional[str] = None, on_install_line_recv: Optional[Callable[[str], None]] = None, *, base_path: Optional[str] = None) -> int:
    LOG(f"Running upgrade IESA {iesa_path} on IP {runtime.ut_ip}")
    iesa_path = _resolve_path(iesa_path, base_path=base_path)
    if not os.path.isfile(iesa_path):
        LOG(f"ERROR: IESA file not found: {iesa_path}")
        return 1
    if not runtime.ut_ip.strip():
        LOG("ERROR: missing ut_ip")
        return 1
    package_name = os.path.basename(iesa_path)
    remote_path = f"{runtime.remote_dir.rstrip('/')}/{package_name}"
    resolved_log_path = _resolve_log_path(log_path, iesa_path, base_path=base_path)
    if resolved_log_path:
        LOG(f"IESA install log path: {resolved_log_path}")
    try:
        _copy_if_needed(runtime, iesa_path, remote_path)
        file_log_cb = _build_install_logger(resolved_log_path)
        def _combined_install_line_recv(line: str) -> None:
            file_log_cb(line)
            if on_install_line_recv:
                on_install_line_recv(line)
        _run_iesa_install_via_python(
            remote_name=package_name,
            remote_dir=runtime.remote_dir,
            remote_host_ip=runtime.acu_ip,
            remote_user=runtime.acu_user,
            jump_host_ip=runtime.ut_ip,
            should_prompt=False,
            on_install_line_recv=_combined_install_line_recv,
            remote_password=runtime.acu_password,
            jump_user=runtime.ut_user,
            jump_password=runtime.ut_password,
        )
        LOG(f"IESA package installed successfully: {package_name}")
        return 0
    except Exception as exc:
        LOG(f"ERROR: IESA install failed for {iesa_path}: {exc}")
        return 1


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one .iesa sideload upgrade via UT jump host.",
        usage=f"{Path(__file__).name} {ARG_IESA_PATH} <iesa_path> {ARG_UT_IP} <ssm_ip> [{ARG_LOG_PATH} <log_file_or_dir>]",
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
    exit_code = run_once_upgrade(runtime, get_arg_value(args, ARG_IESA_PATH), get_arg_value(args, ARG_LOG_PATH))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main(sys.argv[1:])
