from pathlib import Path
import shlex
from typing import Callable
from dev.dev_common import *
from dev.dev_common.network_utils import ECopyType
from dev.dev_common.file_utils import dump_sqlite_db, remove_file


def _resolve_events_db_path_from_cfg(target_ip: str) -> str:
    cfg_url = f"http://{target_ip}/api/cm/cfg_all"
    cmd = f"curl -s {shlex.quote(cfg_url)} | jq -r '.[] | select(.name == \"events_db_location\") | .value'"
    result = run_shell(cmd, want_shell=True, capture_output=True, text=True, timeout=20)
    stdout, stderr = result.stdout or "", result.stderr or ""
    if stderr.strip():
        LOG(f"{LOG_PREFIX_MSG_WARNING} events_db_location query stderr: {stderr.strip()}")
    for line in stdout.splitlines():
        value = line.strip()
        if value and value != "null":
            return value
    raise RuntimeError(f"Unable to resolve events_db_location from {cfg_url}. stdout='{stdout.strip()}' stderr='{stderr.strip()}'")


def copy_events_db_before_reboot(cycle: int, attempt: int, target_ip: str, cycle_base: Path, program_log_path: Path, append_program_log_fn: Callable[[Path, str], None], event_stage: str) -> None:
    events_db_remote_path = _resolve_events_db_path_from_cfg(target_ip=target_ip)
    dest_dir = cycle_base
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        copied_files = copy_to_local(remote_src_paths=events_db_remote_path, remote_host_ip=target_ip, remote_user=SSM_USER, password=SSM_PASSWORD, local_dest_path=dest_dir, timeout=30, copy_type=ECopyType.SCP)
        copied_text = ", ".join(copied_files) if copied_files else "none"
        sqlite_files = [Path(p) for p in copied_files if Path(p).suffix in (".sqlite3", ".db", ".sqlite")] or [Path(p) for p in copied_files]
        if not sqlite_files:
            raise RuntimeError("No downloaded sqlite file found to dump.")
        sqlite_file = sqlite_files[0]
        dump_path = cycle_base / "custom_events_log.txt"
        dump_sqlite_db(sqlite_db_path=sqlite_file, output_dump_path=dump_path, timeout=60)
        remove_file(str(sqlite_file))
        msg = f"Cycle {cycle} attempt {attempt}: copied+dumped events DB {event_stage}. remote={events_db_remote_path}, local={copied_text}, dump={dump_path}"
        LOG(f"{LOG_PREFIX_MSG_INFO} {msg}")
        append_program_log_fn(program_log_path, msg)
    except Exception as exc:
        msg = f"Cycle {cycle} attempt {attempt}: failed to copy events DB {event_stage}: {type(exc).__name__}: {exc}"
        LOG(f"{LOG_PREFIX_MSG_WARNING} {msg}")
        append_program_log_fn(program_log_path, msg)
