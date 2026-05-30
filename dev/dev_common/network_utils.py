from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
import random
from pathlib import Path, PurePosixPath
import paramiko
import posixpath
import re
import shlex
import stat
import time
import socket
import subprocess
import sys
import select
from typing import Callable, List, Optional, Tuple
from dev.dev_common.constants import *
from dev.dev_common.core_utils import *
from dev.dev_common.format_utils import format_bytes_human
from dev.dev_common.independent_network_utils import *

SSH_KEY_TYPE_RSA = 'rsa'
KEY_TYPE_ED25519 = 'ed25519'
LEGACY_SSH_RSA_OPTIONS = ['-o', 'HostKeyAlgorithms=+ssh-rsa', '-o', 'PubkeyAcceptedAlgorithms=+ssh-rsa']
LEGACY_SSH_RSA_OPTION_STR = "-o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa"
NON_INTERACTIVE_KNOWN_HOST_OPTIONS = ['-o', 'UserKnownHostsFile=/dev/null', '-o', 'GlobalKnownHostsFile=/dev/null']
NON_INTERACTIVE_KNOWN_HOST_OPTION_STR = "-o UserKnownHostsFile=/dev/null -o GlobalKnownHostsFile=/dev/null"


def build_non_interactive_proxy_command(jump_user: str, jump_host_ip: str) -> str:
    """Build a ProxyCommand that also suppresses host-key prompts for the jump host."""
    proxy_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", *NON_INTERACTIVE_KNOWN_HOST_OPTIONS, *LEGACY_SSH_RSA_OPTIONS, "-W", "%h:%p", f"{jump_user}@{jump_host_ip}"]
    return " ".join(shlex.quote(part) for part in proxy_cmd)


class ECopyType(Enum):
    SFTP = "sftp"
    SCP = "scp"


class ELineType(str, Enum):
    ProgramLog = "ProgramLog"
    LiveLog = "LiveLog"


class ERequestCommand(str, Enum):
    CONTINUE = "continue"
    RETURN = "return"


def get_remote_file_checksum(remote_host_ip: str, remote_path: str, remote_user: str = ACU_USER, password: Optional[str] = None,
                             checksum_type: str = CHECKSUM_TYPE_MD5, timeout: int = 10, jump_host_ip: Optional[str] = None,
                             jump_user: Optional[str] = None, jump_password: Optional[str] = None) -> Optional[str]:
    """Return remote file checksum string, or None when file is missing."""
    checksum_cmd = "md5sum" if checksum_type == CHECKSUM_TYPE_MD5 else "sha256sum" if checksum_type == CHECKSUM_TYPE_SHA256 else EMPTY_STR_VALUE
    if not checksum_cmd:
        raise ValueError(
            f"Unsupported checksum_type='{checksum_type}'. Use '{CHECKSUM_TYPE_MD5}' or '{CHECKSUM_TYPE_SHA256}'.")
    remote_path_quoted = shlex.quote(remote_path)
    remote_cmd = (
        f'if [ -f {remote_path_quoted} ]; then '
        f'{checksum_cmd} {remote_path_quoted} | cut -d" " -f1; '
        f'else echo {shlex.quote(REMOTE_CHECKSUM_FILE_MISSING)}; fi'
    )
    stdout, stderr = run_ssh_command(host_ip=remote_host_ip, user=remote_user, password=password or EMPTY_STR_VALUE, command=remote_cmd,
                                     timeout=timeout, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password)
    if stderr.strip():
        LOG(f"{LOG_PREFIX_MSG_WARNING} Remote checksum stderr from {remote_host_ip}: {stderr.strip()}")
    for line in reversed((stdout or EMPTY_STR_VALUE).splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        if candidate == REMOTE_CHECKSUM_FILE_MISSING:
            return None
        if re.fullmatch(r"[a-fA-F0-9]{32}", candidate) or re.fullmatch(r"[a-fA-F0-9]{64}", candidate):
            return candidate.lower()
        break
    raise RuntimeError(
        f"Could not parse remote checksum output for '{remote_path}' on {remote_host_ip}. Raw stdout='{stdout.strip()}' stderr='{stderr.strip()}'")


def copy_remote_file_if_needed(local_path: str | Path, remote_host_ip: str, remote_dest_path: str, remote_user: str = ACU_USER, password: Optional[str] = None,
                               jump_host_ip: Optional[str] = None, jump_user: Optional[str] = None, jump_password: Optional[str] = None, checksum_type: str = CHECKSUM_TYPE_MD5,
                               checksum_timeout: int = 20, copy_timeout: int = 300, sleep_after_copy_secs: float = 1.0, recursive: Optional[bool] = False) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """Copy local file to remote only when checksum differs. Returns (is_copied, local_checksum, remote_checksum_before, remote_checksum_after)."""
    if checksum_type != CHECKSUM_TYPE_MD5:
        raise ValueError(f"Unsupported checksum_type='{checksum_type}'. copy_remote_file_if_needed currently supports '{CHECKSUM_TYPE_MD5}' only.")
    local_abs_path: Path = Path(local_path).expanduser().resolve()
    local_checksum = get_file_md5sum(local_abs_path)
    remote_checksum_before = get_remote_file_checksum(remote_host_ip=remote_host_ip, remote_path=remote_dest_path, remote_user=remote_user, password=password,
                                                      checksum_type=checksum_type, timeout=checksum_timeout, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password)
    if remote_checksum_before == local_checksum:
        LOG(f"MD5 checksums local={local_checksum} == remote={remote_checksum_before}. Skipping copy of {local_abs_path} to {remote_host_ip}:{remote_dest_path}")
        return False, local_checksum, remote_checksum_before, remote_checksum_before
    if jump_host_ip:
        LOG(f"MD5 checksums local={local_checksum} != remote={remote_checksum_before}. Copying {local_abs_path} to {remote_host_ip}:{remote_dest_path} via jump host {jump_host_ip}")
        copy_to_remote_via_jump_host(local_path=local_abs_path, remote_host_ip=remote_host_ip, remote_dest_path=remote_dest_path, jump_host_ip=jump_host_ip, remote_user=remote_user,
                                     password=password, jump_user=jump_user, jump_password=jump_password, recursive=recursive, timeout=copy_timeout)
    else:
        copy_to_remote(local_path=local_abs_path, remote_host_ip=remote_host_ip, remote_dest_path=remote_dest_path, remote_user=remote_user, password=password, recursive=recursive, timeout=copy_timeout)
    if sleep_after_copy_secs > 0:
        time.sleep(sleep_after_copy_secs)
    remote_checksum_after = get_remote_file_checksum(remote_host_ip=remote_host_ip, remote_path=remote_dest_path, remote_user=remote_user, password=password,
                                                     checksum_type=checksum_type, timeout=checksum_timeout, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password)
    if remote_checksum_after != local_checksum:
        raise RuntimeError(f"Checksum mismatch after copy. local={local_checksum}, remote={remote_checksum_after or 'MISSING'}, path={remote_dest_path}")
    return True, local_checksum, remote_checksum_before, remote_checksum_after


def stream_live_remote_log(host_ip: str, user: str, password: str, remote_log_path: str, connect_timeout: int = 5,
                        jump_host_ip: Optional[str] = None, jump_user: Optional[str] = None,
                        jump_password: Optional[str] = None, tail_lines: int = 0, read_timeout: int = 900,
                        poll_interval: float = 0.1, stop_event=None, on_line: Optional[Callable[[str, ELineType], None]] = None,
                        retry_interval: float = 5.0, on_get_log_fail: Optional[Callable[[Exception], ERequestCommand]] = None) -> None:
    """Continuously tail a remote log file or read from a serial device until interrupted or stop_event is set.
    Automatically retries on connection loss or timeout unless on_get_log_fail asks to stop."""
    LOG(f"Getting live log at {remote_log_path} from {host_ip}" + f"via jump host {jump_host_ip}" if jump_host_ip else EMPTY_STR_VALUE)
    on_line = on_line or (lambda line, _line_type: print(line, flush=True))
    on_get_log_fail = on_get_log_fail or (lambda _exc: ERequestCommand.CONTINUE)
    def _should_return(command) -> bool:
        cmd_value = getattr(command, "value", command)
        return str(cmd_value).strip().lower() == ERequestCommand.RETURN.value
    is_device = remote_log_path.startswith("/dev/")
    if is_device:
        remote_cmd = f"cat {shlex.quote(remote_log_path)}"
    else:
        remote_cmd = f"tail -F -n {max(0, int(tail_lines))} {shlex.quote(remote_log_path)}"

    # Add first line starting
    on_line(f"[{get_log_timestamp()}] Getting live log at {remote_log_path} from {host_ip} via jump host {jump_host_ip}", ELineType.ProgramLog)
    def _emit_line(text: str, saw_first: bool) -> bool:
        clean = (text or "").rstrip("\r\n")
        if not clean:
            return saw_first
        if not saw_first:
            on_line(clean + f"\r\nGET_UT_LIVE_LOG START at {get_log_timestamp()}!!", ELineType.LiveLog)
            return True
        on_line(clean, ELineType.LiveLog)
        return saw_first
    # Some device logs occasionally emit non-UTF8 bytes; decode with replacement and keep streaming.
    def _emit_decoded_lines(decoded: str, saw_first: bool) -> bool:
        for raw_line in decoded.splitlines():
            saw_first = _emit_line(raw_line, saw_first)
        return saw_first
    def _sleep_with_stop(seconds: float) -> None:
        if seconds <= 0:
            return
        if not stop_event:
            time.sleep(seconds)
            return
        deadline = time.time() + seconds
        while not stop_event.is_set():
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            time.sleep(min(0.2, remaining))
    reconnect_attempt = 0
    while not (stop_event and stop_event.is_set()):
        target_client = None
        jump_client = None
        jump_channel = None
        stdout = stderr = None

        try:
            last_output_time = time.time()
            waiting_start_time = last_output_time
            waiting_last_second = -1
            waiting_last_text_len = 0
            saw_first_log = False

            target_client, jump_client, jump_channel = open_ssh_client(
                host_ip=host_ip, user=user, password=password, timeout=connect_timeout,
                jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password)
            _, stdout, stderr = target_client.exec_command(remote_cmd)
            channel = stdout.channel
            channel.settimeout(1.0)
           
            while not (stop_event and stop_event.is_set()):
                transport = target_client.get_transport()
                if transport is None or not transport.is_active():
                    raise ConnectionError(f"SSH connection lost for {host_ip}")
                if channel.closed or channel.eof_received:
                    raise ConnectionError(f"SSH channel closed while streaming '{remote_log_path}' from {host_ip}")
                if channel.recv_ready():
                    try:
                        raw = channel.recv(4096)
                    except (TimeoutError, socket.timeout):
                        raw = b""
                    if raw == b"":
                        raise ConnectionError(f"SSH channel returned EOF while streaming '{remote_log_path}' from {host_ip}")
                    saw_first_log = _emit_decoded_lines(raw.decode("utf-8", errors="replace"), saw_first_log)
                    last_output_time = time.time()
                    reconnect_attempt = 0
                    continue
                if channel.exit_status_ready():
                    stderr_text = stderr.read().decode('utf-8', errors='replace').strip() if stderr else ""
                    if stderr_text:
                        raise RuntimeError(stderr_text)
                    return  # Clean exit — remote process ended normally, no retry
                if not saw_first_log:
                    elapsed_seconds = int(time.time() - waiting_start_time)
                    if elapsed_seconds != waiting_last_second:
                        timeout_text = f"{read_timeout}s" if read_timeout > 0 else "infinite"
                        waiting_text = f"Waiting for log output from '{remote_log_path}'... Elapsed: {elapsed_seconds}/{timeout_text}"
                        waiting_last_text_len = max(waiting_last_text_len, len(waiting_text))
                        LOG(f"{waiting_text}{' ' * (waiting_last_text_len - len(waiting_text))}", same_line=True, show_time=True)
                        waiting_last_second = elapsed_seconds
                if not is_device and read_timeout > 0 and (time.time() - last_output_time) >= read_timeout:
                    raise TimeoutError(f"No data received from '{remote_log_path}' for {read_timeout} seconds")
                _sleep_with_stop(max(0.01, poll_interval))

        except Exception as e:
            if stop_event and stop_event.is_set():
                return
            next_command = ERequestCommand.CONTINUE
            try:
                next_command = on_get_log_fail(e)
            except Exception as cb_exc:
                LOG(f"{LOG_PREFIX_MSG_WARNING} on_get_log_fail callback failed ({type(cb_exc).__name__}: {cb_exc}); defaulting to retry.", show_time=True)
            if _should_return(next_command):
                LOG(f"[get_live_remote_log] Error ({type(e).__name__}: {e}) — callback requested stop retrying.", show_time=True)
                return
            reconnect_attempt += 1
            exp = min(6, reconnect_attempt - 1)
            backoff_secs = min(60.0, float(retry_interval) * (2 ** exp)) + random.uniform(0.0, 1.5)
            LOG(f"[get_live_remote_log] Error ({type(e).__name__}: {e}) — retrying in {backoff_secs:.1f}s (attempt {reconnect_attempt})...", show_time=True)
            _sleep_with_stop(backoff_secs)

        finally:
            if stdout:
                stdout.close()
            if stderr:
                stderr.close()
            close_ssh_client(target_client, jump_client, jump_channel)


#def get_live_remote_log(host_ip: str, user: str, password: str, remote_log_path: str, timeout: int = 5,
#                        jump_host_ip: Optional[str] = None, jump_user: Optional[str] = None,
#                        jump_password: Optional[str] = None, tail_lines: int = 0, read_timeout: int = 300,
#                        poll_interval: float = 0.1, stop_event=None, on_line: Optional[Callable[[str], None]] = None,
#                        retry_interval: float = 5.0) -> None:
#    """Continuously tail a remote log file or read from a serial device until interrupted or stop_event is set.
#    Automatically retries on connection loss or timeout. Uses select() to avoid readline() hanging."""
#    LOG(f"Getting live log from {host_ip} via jump host {jump_host_ip}")
#    on_line = on_line or (lambda line: print(line, flush=True))
#    is_device = remote_log_path.startswith("/dev/")
#    if is_device:
#        remote_cmd = f"cat {shlex.quote(remote_log_path)}"
#    else:
#        remote_cmd = f"tail -F -n {max(0, int(tail_lines))} {shlex.quote(remote_log_path)}"

#    while not (stop_event and stop_event.is_set()):
#        target_client = None
#        jump_client = None
#        jump_channel = None
#        stdout = stderr = None
#        line_buf = b""  # partial line buffer

#        try:
#            target_client, jump_client, jump_channel = open_ssh_client(
#                host_ip=host_ip, user=user, password=password, timeout=timeout,
#                jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password)
#            _, stdout, stderr = target_client.exec_command(remote_cmd)
#            stdout.channel.setblocking(False)  # non-blocking mode, select() controls timing
#            last_output_time = time.time()
#            waiting_start_time = last_output_time
#            waiting_last_second = -1
#            waiting_last_text_len = 0
#            saw_first_log = False

#            while not (stop_event and stop_event.is_set()):
#                if target_client.get_transport() is None or not target_client.get_transport().is_active():
#                    raise ConnectionError(f"SSH connection lost for {host_ip}")

#                if not saw_first_log:
#                    elapsed_seconds = int(time.time() - waiting_start_time)
#                    if elapsed_seconds != waiting_last_second:
#                        waiting_text = f"Waiting for log output from '{remote_log_path}'... Elapsed: {elapsed_seconds}/{read_timeout}s"
#                        waiting_last_text_len = max(waiting_last_text_len, len(waiting_text))
#                        LOG(f"{waiting_text}{' ' * (waiting_last_text_len - len(waiting_text))}", same_line=False, show_time=False)
#                        waiting_last_second = elapsed_seconds

#                # Wait up to poll_interval for data — never blocks indefinitely
#                ready, _, _ = select.select([stdout.channel], [], [], poll_interval)
#                if not ready:
#                    # No data in this poll window — check timeouts
#                    if is_device:
#                        last_output_time = time.time()  # serial devices can be silent, don't timeout
#                        continue
#                    if (time.time() - last_output_time) >= read_timeout:
#                        raise TimeoutError(f"No data received from '{remote_log_path}' for {read_timeout} seconds")
#                    continue

#                # Data is ready — recv raw bytes
#                try:
#                    data = stdout.channel.recv(4096)
#                except Exception as e:
#                    raise ConnectionError(f"Channel recv error for {host_ip}: {e}")

#                if not data:
#                    # Empty recv = channel closed
#                    if stdout.channel.exit_status_ready():
#                        stderr_text = stderr.read().decode('utf-8', errors='replace').strip() if stderr else ""
#                        if stderr_text:
#                            raise RuntimeError(stderr_text)
#                        return  # Clean exit — remote process ended normally, no retry
#                    continue

#                # Accumulate into buffer and split on newlines
#                line_buf += data
#                lines = line_buf.split(b'\n')
#                line_buf = lines.pop()  # last element is incomplete line — keep for next recv

#                for raw_line in lines:
#                    line = raw_line.decode('utf-8', errors='replace').rstrip('\r')
#                    LOG(line)
#                    if not saw_first_log:
#                        on_line(line + f"\r\nGET_UT_LIVE_LOG START at {time.strftime('%Y-%m-%d %H:%M:%S')}!!")
#                        saw_first_log = True
#                    else:
#                        on_line(line)
#                    last_output_time = time.time()

#        except Exception as e:
#            if stop_event and stop_event.is_set():
#                return
#            LOG(f"[get_live_remote_log] Error ({type(e).__name__}: {e}) — retrying in {retry_interval}s...", show_time=True)
#            time.sleep(retry_interval)

#        finally:
#            if stdout:
#                stdout.close()
#            if stderr:
#                stderr.close()
#            close_ssh_client(target_client, jump_client, jump_channel)

@dataclass
class SshPwlessStatuses:
    """Categorized results for SSH passwordless checks."""

    passwordless_ips: List[str] = field(default_factory=list)
    password_required_ips: List[str] = field(default_factory=list)
    unreachable_ips: List[str] = field(default_factory=list)


def ping_remote_host(host: str, total_pings: int = 3, time_out_per_ping: int = 5, mute: bool = False) -> bool:
    try:
        if not mute:
            LOG(f"[INFO] Pinging {host} {total_pings} times with a timeout of {time_out_per_ping} seconds...")
        cmd = ['ping', '-c', str(total_pings), '-W', str(time_out_per_ping), host]
        result = run_shell(
            cmd,
            capture_output=True,
            text=True,
            timeout=time_out_per_ping * total_pings + 2  # Total timeout
        )

        if not mute:
            LOG(f"Host {host} is {'reachable' if result.returncode == 0 else 'not reachable'}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        if not mute:
            LOG(f"[WARNING] Ping to {host} timed out")
        return False
    except Exception as e:
        if not mute:
            LOG(f"[WARNING] Ping to {host} failed: {e}")
        return False


def ping_remote_host_via_jump_host(remote_host_ip: str, jump_host_ip: Optional[str] = None, jump_user: str = SSM_USER, jump_password: Optional[str] = None, *,
                                   max_wait_sec: int = 120, retry_interval_sec: float = 1.0, ping_count: int = 1,
                                   ping_timeout_sec: int = 1, ssh_timeout_sec: int = 10, check_jump_host_reachable: bool = True,
                                   mute: bool = False) -> bool:
    start_time = time.time()
    deadline = start_time + max(1, int(max_wait_sec))
    interval = max(0.1, float(retry_interval_sec))
    ping_count = max(1, int(ping_count))
    ping_timeout = max(1, int(ping_timeout_sec))
    ssh_timeout = max(1, int(ssh_timeout_sec))
    last_reason = EMPTY_STR_VALUE
    ping_ok_marker = "__PING_OK__"
    ping_fail_marker = "__PING_FAIL__"
    remote_ping_cmd = f"ping -c {ping_count} -W {ping_timeout} {shlex.quote(remote_host_ip)} >/dev/null 2>&1 && echo {ping_ok_marker} || echo {ping_fail_marker}"

    while time.time() < deadline:
        elapsed = int(time.time() - start_time)
        try:
            if not jump_host_ip:
                if ping_remote_host(remote_host_ip, total_pings=ping_count, time_out_per_ping=ping_timeout, mute=True):
                    if not mute:
                        LOG(f"{LOG_PREFIX_MSG_INFO} {remote_host_ip} is reachable after {elapsed}s.")
                    return True
                last_reason = f"{remote_host_ip} not reachable"
            elif check_jump_host_reachable and not ping_remote_host(jump_host_ip, total_pings=ping_count, time_out_per_ping=ping_timeout, mute=True):
                last_reason = f"jump host {jump_host_ip} is not reachable"
            else:
                stdout, stderr = run_ssh_command(
                    host_ip=jump_host_ip,
                    user=jump_user,
                    password=jump_password or EMPTY_STR_VALUE,
                    command=remote_ping_cmd,
                    timeout=ssh_timeout,
                )
                if stderr.strip():
                    last_reason = stderr.strip()
                marker = (stdout or EMPTY_STR_VALUE).strip().splitlines()
                last_line = marker[-1].strip() if marker else EMPTY_STR_VALUE
                if last_line == ping_ok_marker:
                    if not mute:
                        LOG(f"{LOG_PREFIX_MSG_INFO} {remote_host_ip} is reachable from jump host {jump_host_ip} after {elapsed}s.")
                    return True
                last_reason = f"{remote_host_ip} not reachable from jump host {jump_host_ip}"
        except Exception as exc:
            last_reason = str(exc)
        if not mute:
            via_text = f" via {jump_host_ip}" if jump_host_ip else EMPTY_STR_VALUE
            LOG(f"{LOG_PREFIX_MSG_INFO} Waiting for {remote_host_ip}{via_text} [{elapsed}/{int(max_wait_sec)}s]: {last_reason or 'retrying'}")
        time.sleep(interval)

    if not mute:
        elapsed = int(time.time() - start_time)
        via_text = f" via {jump_host_ip}" if jump_host_ip else EMPTY_STR_VALUE
        LOG(f"{LOG_PREFIX_MSG_WARNING} Timeout waiting for {remote_host_ip}{via_text} after {elapsed}s. Last reason: {last_reason or 'unknown'}")
    return False


def _sftp_mkdir_p(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    remote_dir = remote_dir.strip()
    if not remote_dir or remote_dir == ".":
        return
    current = "/" if remote_dir.startswith("/") else ""
    for part in PurePosixPath(remote_dir).parts:
        if part in ("", "/"):
            continue
        current = posixpath.join(current, part) if current not in (
            "", "/") else (f"/{part}" if current == "/" else part)
        try:
            sftp.stat(current)
        except IOError:
            sftp.mkdir(current)


def _sftp_put_file(sftp: paramiko.SFTPClient, local_file: Path, remote_file_path: str) -> str:
    _sftp_mkdir_p(sftp, posixpath.dirname(remote_file_path))
    sftp.put(str(local_file), remote_file_path)
    return remote_file_path


class _TransferProgressReporter:
    def __init__(self, label: str, total_bytes: int, log_interval_sec: float = 1.0):
        self.label = label
        self.total_bytes = max(0, int(total_bytes))
        self.log_interval_sec = log_interval_sec
        self.start_time = time.time()
        self.last_log_time = 0.0
        self.last_logged_percent = -1
        self.use_same_line = bool(getattr(sys.stdout, "isatty", lambda: False)())
        self.has_rendered = False

    def report(self, transferred_bytes: int, force: bool = False) -> None:
        transferred_bytes = max(0, min(int(transferred_bytes), self.total_bytes))
        elapsed = max(time.time() - self.start_time, 1e-6)
        percent = 100 if self.total_bytes == 0 else int((transferred_bytes * 100) / self.total_bytes)
        if not force and percent == self.last_logged_percent and (time.time() - self.last_log_time) < self.log_interval_sec:
            return
        rate_mib_s = (transferred_bytes / elapsed) / (1024 * 1024)
        transferred_h = format_bytes_human(transferred_bytes)
        total_h = format_bytes_human(self.total_bytes)
        LOG(f"{LOG_PREFIX_MSG_INFO} {self.label}: {percent}% ({transferred_h}/{total_h}), elapsed {elapsed:.1f}s, rate {rate_mib_s:.2f} MiB/s", same_line=self.use_same_line)
        self.last_logged_percent = percent
        self.last_log_time = time.time()
        self.has_rendered = True

    def finish_line(self) -> None:
        if self.use_same_line and self.has_rendered:
            LOG("", show_time=False)
            self.has_rendered = False


def _sftp_put_file_with_progress(sftp: paramiko.SFTPClient, local_file: Path, remote_file_path: str, base_offset: int = 0, total_bytes: Optional[int] = None, label: Optional[str] = None) -> str:
    file_size = local_file.stat().st_size
    file_uploaded = 0
    overall_total = file_size if total_bytes is None else max(file_size, int(total_bytes))
    LOG(f"{LOG_PREFIX_MSG_INFO} Uploading {local_file} to {remote_file_path} ({format_bytes_human(file_size)})")
    reporter = _TransferProgressReporter(label=label or f"Upload Progress", total_bytes=overall_total)

    def _on_progress(transferred: int, total: int) -> None:
        nonlocal file_uploaded
        file_uploaded = max(0, min(transferred, file_size if file_size >= 0 else total))
        reporter.report(base_offset + file_uploaded)

    _sftp_mkdir_p(sftp, posixpath.dirname(remote_file_path))
    reporter.report(0, force=True)
    try:
        sftp.put(str(local_file), remote_file_path, callback=_on_progress)
        reporter.report(base_offset + file_size, force=True)
    except Exception as exc:
        uploaded_h = format_bytes_human(file_uploaded)
        total_h = format_bytes_human(file_size)
        progress_pct = 100.0 if file_size <= 0 else (file_uploaded * 100.0 / file_size)
        if isinstance(exc, EOFError):
            raise RuntimeError(
                f"Failed to upload '{local_file}' to '{remote_file_path}': EOFError "
                f"(SFTP/SSH stream closed during transfer at {progress_pct:.1f}% [{uploaded_h}/{total_h}]). "
                f"Likely connection drop/reset via target or jump host, or remote-side SSH/service restart."
            ) from exc
        raise RuntimeError(
            f"Failed to upload '{local_file}' to '{remote_file_path}' at {progress_pct:.1f}% [{uploaded_h}/{total_h}]: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    finally:
        reporter.finish_line()
    return remote_file_path


def _sftp_put_directory(sftp: paramiko.SFTPClient, local_dir: Path, remote_dir_path: str) -> str:
    _sftp_mkdir_p(sftp, remote_dir_path)
    local_items = sorted(local_dir.rglob("*"))
    files = [item for item in local_items if item.is_file()]
    total_bytes = sum(item.stat().st_size for item in files)
    uploaded_bytes = 0
    for local_item in local_items:
        rel_path = local_item.relative_to(local_dir).as_posix()
        remote_item_path = posixpath.join(remote_dir_path, rel_path)
        if local_item.is_dir():
            _sftp_mkdir_p(sftp, remote_item_path)
        else:
            _sftp_put_file_with_progress(sftp, local_item, remote_item_path,
                                         base_offset=uploaded_bytes, total_bytes=total_bytes)
            uploaded_bytes += local_item.stat().st_size
    return remote_dir_path


def _expand_remote_sources(target_client: paramiko.SSHClient, remote_sources: List[str], timeout: int = 20) -> List[str]:
    if not remote_sources:
        return []
    joined_sources = " ".join(shlex.quote(source) for source in remote_sources)
    remote_cmd = f"set -- {joined_sources}; for pattern in \"$@\"; do for src in $pattern; do [ -e \"$src\" ] && printf '%s\\n' \"$src\"; done; done"
    _, stdout, stderr = target_client.exec_command(remote_cmd, timeout=timeout)
    stdout_text = stdout.read().decode("utf-8", errors="replace")
    stderr_text = stderr.read().decode("utf-8", errors="replace").strip()
    if stderr_text:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Remote source expansion stderr: {stderr_text}")
    stdout.channel.recv_exit_status()
    expanded_sources: List[str] = []
    seen_sources = set()
    for line in stdout_text.splitlines():
        source = line.strip()
        if source and source not in seen_sources:
            seen_sources.add(source)
            expanded_sources.append(source)
    return expanded_sources


def _sftp_is_dir(sftp: paramiko.SFTPClient, remote_path: str) -> bool:
    return stat.S_ISDIR(sftp.stat(remote_path).st_mode)


def _sftp_get_file_with_progress(sftp: paramiko.SFTPClient, remote_file_path: str, local_file: Path, base_offset: int = 0, total_bytes: Optional[int] = None, label: Optional[str] = None) -> str:
    remote_stat = sftp.stat(remote_file_path)
    file_size = int(remote_stat.st_size)
    local_file.parent.mkdir(parents=True, exist_ok=True)
    reporter = _TransferProgressReporter(label=label or "Download Progress:",
                                         total_bytes=file_size if total_bytes is None else max(file_size, int(total_bytes)))
    LOG(f"{LOG_PREFIX_MSG_INFO} Downloading {remote_file_path} to {local_file} ({format_bytes_human(file_size)})")

    def _on_progress(transferred: int, total: int) -> None:
        reporter.report(base_offset + max(0, min(transferred, file_size if file_size >= 0 else total)))

    reporter.report(base_offset, force=True)
    try:
        sftp.get(remote_file_path, str(local_file), callback=_on_progress)
        reporter.report(base_offset + file_size, force=True)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download '{remote_file_path}' to '{local_file}': {type(exc).__name__}: {exc}") from exc
    finally:
        reporter.finish_line()
    return str(local_file)


def _sftp_collect_dir_files(sftp: paramiko.SFTPClient, remote_dir_path: str) -> List[Tuple[str, int]]:
    remote_files: List[Tuple[str, int]] = []
    queue = [remote_dir_path]
    while queue:
        current_dir = queue.pop()
        for entry in sftp.listdir_attr(current_dir):
            remote_path = posixpath.join(current_dir, entry.filename)
            if stat.S_ISDIR(entry.st_mode):
                queue.append(remote_path)
            elif stat.S_ISREG(entry.st_mode):
                remote_files.append((remote_path, int(entry.st_size)))
    return remote_files


def _copy_to_local_sftp_impl(remote_src_paths: str | List[str], remote_host_ip: str, local_dest_path: str | Path, remote_user: str = ACU_USER,
                        password: Optional[str] = None, jump_host_ip: Optional[str] = None, jump_user: Optional[str] = None,
                        jump_password: Optional[str] = None, recursive: Optional[bool] = None, timeout: Optional[int] = None) -> List[str]:
    remote_sources = [remote_src_paths] if isinstance(remote_src_paths, str) else list(remote_src_paths or [])
    if not remote_sources:
        raise ValueError("remote_src_paths cannot be empty.")

    local_dest = Path(local_dest_path).expanduser().resolve()
    should_use_recursive = True if recursive is None else recursive
    copied_local_paths: List[str] = []
    target_client = jump_client = jump_channel = None
    sftp = None
    try:
        target_client, jump_client, jump_channel = open_ssh_client(
            host_ip=remote_host_ip, user=remote_user, password=password, timeout=timeout or 5, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password)
        transport = target_client.get_transport()
        if transport is None or not transport.is_active():
            raise RuntimeError(f"SSH transport unavailable for {remote_host_ip}")
        sftp = paramiko.SFTPClient.from_transport(transport)
        resolved_remote_paths = _expand_remote_sources(
            target_client=target_client, remote_sources=remote_sources, timeout=timeout or 20)
        if not resolved_remote_paths:
            LOG(f"{LOG_PREFIX_MSG_WARNING} No remote files matched sources: {remote_sources}")
            return copied_local_paths

        should_treat_dest_as_dir = len(resolved_remote_paths) > 1 or (local_dest.exists() and local_dest.is_dir())
        if should_treat_dest_as_dir:
            local_dest.mkdir(parents=True, exist_ok=True)

        transfer_errors = 0
        for remote_src in resolved_remote_paths:
            try:
                remote_is_dir = _sftp_is_dir(sftp, remote_src)
            except IOError as exc:
                transfer_errors += 1
                LOG(f"{LOG_PREFIX_MSG_WARNING} Skipping unreadable remote source '{remote_src}': {exc}")
                continue

            if remote_is_dir:
                if not should_use_recursive:
                    raise ValueError(f"Remote path '{remote_src}' is a directory. Set recursive=True to copy it.")
                local_base_dir = (
                    local_dest / PurePosixPath(remote_src).name) if should_treat_dest_as_dir else local_dest
                local_base_dir.mkdir(parents=True, exist_ok=True)
                remote_files = _sftp_collect_dir_files(sftp, remote_src)
                total_bytes = sum(file_size for _, file_size in remote_files)
                downloaded_bytes = 0
                for remote_file, file_size in remote_files:
                    relative = PurePosixPath(remote_file).relative_to(PurePosixPath(remote_src)).as_posix()
                    local_file = local_base_dir / relative
                    try:
                        _sftp_get_file_with_progress(sftp=sftp, remote_file_path=remote_file, local_file=local_file,
                                                     base_offset=downloaded_bytes, total_bytes=total_bytes, label=f"Download {PurePosixPath(remote_src).name}:")
                        copied_local_paths.append(str(local_file))
                        downloaded_bytes += file_size
                    except Exception as exc:
                        transfer_errors += 1
                        LOG(f"{LOG_PREFIX_MSG_WARNING} Failed to download '{remote_file}': {exc}")
            else:
                local_file = (local_dest / PurePosixPath(remote_src).name) if should_treat_dest_as_dir else local_dest
                try:
                    _sftp_get_file_with_progress(sftp=sftp, remote_file_path=remote_src, local_file=local_file)
                    copied_local_paths.append(str(local_file))
                except Exception as exc:
                    transfer_errors += 1
                    LOG(f"{LOG_PREFIX_MSG_WARNING} Failed to download '{remote_src}': {exc}")

        if transfer_errors:
            LOG(f"{LOG_PREFIX_MSG_WARNING} Completed download with {transfer_errors} transfer error(s).")
        return copied_local_paths
    finally:
        if sftp:
            sftp.close()
        close_ssh_client(target_client, jump_client, jump_channel)


def _copy_to_remote_impl(local_path: str | Path, remote_host_ip: str, remote_dest_path: str, remote_user: str = ACU_USER,
                         password: Optional[str] = None, jump_host_ip: Optional[str] = None, jump_user: Optional[str] = None,
                         jump_password: Optional[str] = None, recursive: Optional[bool] = None, timeout: Optional[int] = None) -> str:
    local_path_obj = Path(local_path).expanduser().resolve()
    should_use_recursive = local_path_obj.is_dir() if recursive is None else recursive
    if local_path_obj.is_dir() and not should_use_recursive:
        raise ValueError(f"Local path '{local_path_obj}' is a directory. Set recursive=True to copy it.")
    target_client = jump_client = jump_channel = None
    sftp = None
    try:
        target_client, jump_client, jump_channel = open_ssh_client(
            host_ip=remote_host_ip, user=remote_user, password=password, timeout=timeout or 5, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password)
        transport = target_client.get_transport()
        if transport is None or not transport.is_active():
            raise RuntimeError(f"SSH transport unavailable for {remote_host_ip}")
        sftp = paramiko.SFTPClient.from_transport(transport)
        if should_use_recursive and local_path_obj.is_dir():
            return _sftp_put_directory(sftp, local_path_obj, remote_dest_path)
        result = _sftp_put_file_with_progress(sftp, local_path_obj, remote_dest_path)
        return result
    finally:
        if sftp:
            sftp.close()
        close_ssh_client(target_client, jump_client, jump_channel)


def _copy_to_local_scp_impl(remote_src_paths: str | List[str], remote_host_ip: str, local_dest_path: str | Path, remote_user: str = ACU_USER,
                                jump_host_ip: Optional[str] = None, recursive: Optional[bool] = None, timeout: Optional[int] = None,
                                strict_host_key_checking: bool = False) -> List[str]:
    remote_sources = [remote_src_paths] if isinstance(remote_src_paths, str) else list(remote_src_paths or [])
    if not remote_sources:
        raise ValueError("remote_src_paths cannot be empty.")
    # We need two forms of the same destination:
    # - CURRENT for local Python file ops (mkdir/rglob in the current runtime)
    # - WSL_OR_LINUX for the scp command string executed via Linux shell (`wsl bash -lc ...` on Windows host)
    local_dest = get_normalized_path(local_dest_path, target_platform=ETargetPlatform.CURRENT, log_label="scp local destination").expanduser().resolve()
    local_dest_for_scp = get_normalized_path(local_dest_path, target_platform=ETargetPlatform.WSL_OR_LINUX)
    local_dest.mkdir(parents=True, exist_ok=True)
    before_files = set(str(p.resolve()) for p in local_dest.rglob("*") if p.is_file())
    cmd: List[str] = ["scp"]
    if recursive is not False:
        cmd.append("-r")
    if timeout and int(timeout) > 0:
        cmd.extend(["-o", f"ConnectTimeout={int(timeout)}"])
    if not strict_host_key_checking:
        cmd.extend(["-o", "StrictHostKeyChecking=no", *NON_INTERACTIVE_KNOWN_HOST_OPTIONS])
    cmd.extend(LEGACY_SSH_RSA_OPTIONS)
    if jump_host_ip:
        proxy_option = f"ProxyJump={remote_user}@{jump_host_ip}" if strict_host_key_checking else f"ProxyCommand={build_non_interactive_proxy_command(remote_user, jump_host_ip)}"
        cmd.extend(["-o", proxy_option])
    for src in remote_sources:
        cmd.append(f"{remote_user}@{remote_host_ip}:{src}")
    cmd.append(str(local_dest_for_scp))
    scp_cmd_str = " ".join(shlex.quote(str(arg)) for arg in cmd)
    # OpenSSH scp only renders the transfer meter when stderr is a TTY. `script`
    # gives scp a pseudo-terminal even when launched through Win Python/WSL.
    progress_cmd = ["script", "-qfec", scp_cmd_str, "/dev/null"]
    result = run_shell(progress_cmd, capture_output=False, timeout=timeout if timeout and timeout > 0 else None, check_throw_exception_on_exit_code=False)
    if result.returncode != 0:
        raise RuntimeError(f"SCP copy failed with exit_code={result.returncode}. See SCP output above.")
    after_files = [str(p.resolve()) for p in local_dest.rglob("*") if p.is_file()]
    return sorted(path for path in after_files if path not in before_files)


def copy_to_remote(local_path: str | Path, remote_host_ip: str, remote_dest_path: str, remote_user: str = ACU_USER,
                   password: Optional[str] = None, recursive: Optional[bool] = None, strict_host_key_checking: bool = False,
                   timeout: Optional[int] = None) -> str:
    """Copy a local file or directory to a remote host using Paramiko SFTP."""
    if strict_host_key_checking:
        LOG(f"{LOG_PREFIX_MSG_WARNING} strict_host_key_checking is ignored for Paramiko-based copy_to_remote().")
    LOG(f"{LOG_PREFIX_MSG_INFO} Copying '{Path(local_path).expanduser()}' to {remote_user}@{remote_host_ip}:{remote_dest_path} via Paramiko")
    return _copy_to_remote_impl(local_path=local_path, remote_host_ip=remote_host_ip, remote_dest_path=remote_dest_path, remote_user=remote_user,
                                password=password, recursive=recursive, timeout=timeout)


def copy_to_remote_via_jump_host(local_path: str | Path, remote_host_ip: str, remote_dest_path: str, jump_host_ip: str,
                                 remote_user: str = ACU_USER, password: Optional[str] = None, jump_user: Optional[str] = None,
                                 jump_password: Optional[str] = None, recursive: Optional[bool] = None, strict_host_key_checking: bool = False,
                                 timeout: Optional[int] = None) -> str:
    """Copy a local file or directory to a remote host through a jump host using Paramiko SFTP."""
    if strict_host_key_checking:
        LOG(f"{LOG_PREFIX_MSG_WARNING} strict_host_key_checking is ignored for Paramiko-based copy_to_remote_via_jump_host().")
    LOG(f"{LOG_PREFIX_MSG_INFO} Copying '{Path(local_path).expanduser()}' to {remote_user}@{remote_host_ip}:{remote_dest_path} via jump host {jump_user}@{jump_host_ip} using Paramiko")
    return _copy_to_remote_impl(local_path=local_path, remote_host_ip=remote_host_ip, remote_dest_path=remote_dest_path, remote_user=remote_user, password=password, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password,
                                recursive=recursive, timeout=timeout)


def copy_to_local(remote_src_paths: str | List[str], remote_host_ip: str, local_dest_path: str | Path, remote_user: str = ACU_USER,
                  password: Optional[str] = None, recursive: Optional[bool] = None, strict_host_key_checking: bool = False,
                  timeout: Optional[int] = None, copy_type: ECopyType = ECopyType.SFTP) -> List[str]:
    """Copy remote files/directories to local path via SFTP (Paramiko) or SCP."""
    remote_desc = remote_src_paths if isinstance(remote_src_paths, str) else f"{len(remote_src_paths)} source(s)"
    display_dest = format_path_for_display(Path(local_dest_path).expanduser())
    LOG(f"{LOG_PREFIX_MSG_INFO} Copying '{remote_desc}' from {remote_user}@{remote_host_ip} to '{display_dest}' using {copy_type.value.upper()}")
    if copy_type == ECopyType.SCP:
        if password:
            setup_passwordless_ssh(user=remote_user, remote_ip=remote_host_ip, remote_password=password)
        return _copy_to_local_scp_impl(remote_src_paths=remote_src_paths, remote_host_ip=remote_host_ip, local_dest_path=local_dest_path, remote_user=remote_user, recursive=recursive, timeout=timeout, strict_host_key_checking=strict_host_key_checking)
    if strict_host_key_checking:
        LOG(f"{LOG_PREFIX_MSG_WARNING} strict_host_key_checking is ignored for Paramiko-based copy_to_local().")
    return _copy_to_local_sftp_impl(remote_src_paths=remote_src_paths, remote_host_ip=remote_host_ip, local_dest_path=local_dest_path, remote_user=remote_user, password=password, recursive=recursive, timeout=timeout)


def copy_to_local_via_jump_host(remote_src_paths: str | List[str], remote_host_ip: str, local_dest_path: str | Path, jump_host_ip: str, remote_user: str = ACU_USER, remote_password: Optional[str] = None, jump_user: Optional[str] = None, jump_password: Optional[str] = None, recursive: Optional[bool] = None, strict_host_key_checking: bool = False, timeout: Optional[int] = None, copy_type: ECopyType = ECopyType.SFTP) -> List[str]:
    """Copy remote files/directories through a jump host to local path via SFTP (Paramiko) or SCP."""
    remote_desc = remote_src_paths if isinstance(remote_src_paths, str) else f"{len(remote_src_paths)} source(s)"
    display_dest = format_path_for_display(Path(local_dest_path).expanduser())
    LOG(f"{LOG_PREFIX_MSG_INFO} Copying '{remote_desc}' from {remote_user}@{remote_host_ip} to '{display_dest}' via jump host {jump_user}@{jump_host_ip} using {copy_type.value.upper()}.")
    if copy_type == ECopyType.SCP:
        if jump_user and jump_password:
            setup_passwordless_ssh(user=jump_user, remote_ip=jump_host_ip, remote_password=jump_password)
        if remote_password:
            if not generate_ssh_key(SSH_KEY_TYPE_RSA):
                LOG(f"{LOG_PREFIX_MSG_WARNING} Failed to generate SSH key before remote key install for {remote_user}@{remote_host_ip}")
            else:
                _, public_key_path = check_ssh_key_exists(SSH_KEY_TYPE_RSA)
                setup_host_ssh_key(user=remote_user, host=remote_host_ip, public_key_path=public_key_path, via_jump=jump_host_ip, password=remote_password, jump_user=jump_user, jump_password=jump_password)
        return _copy_to_local_scp_impl(remote_src_paths=remote_src_paths, remote_host_ip=remote_host_ip, local_dest_path=local_dest_path, remote_user=remote_user, jump_host_ip=jump_host_ip, recursive=recursive, timeout=timeout, strict_host_key_checking=strict_host_key_checking)
    if strict_host_key_checking:
        LOG(f"{LOG_PREFIX_MSG_WARNING} strict_host_key_checking is ignored for Paramiko-based copy_to_local_via_jump_host().")
    return _copy_to_local_sftp_impl(remote_src_paths=remote_src_paths, remote_host_ip=remote_host_ip, local_dest_path=local_dest_path, remote_user=remote_user, password=remote_password, jump_host_ip=jump_host_ip, jump_user=jump_user, jump_password=jump_password, recursive=recursive, timeout=timeout)


def setup_passwordless_ssh(user: str, remote_ip: str, remote_password: Optional[str] = None, key_type: str = SSH_KEY_TYPE_RSA) -> bool:
    """Set up passwordless SSH authentication.

    Prefer this for OpenSSH/SCP style workflows. Paramiko SFTP paths can use password auth directly.
    """
    LOG(f"{LOG_PREFIX_MSG_INFO} Setting up passwordless SSH authentication...")

    # Generate SSH key if needed
    if not generate_ssh_key(key_type):
        return False

    _, public_key_path = check_ssh_key_exists(key_type)

    # Copy key to jump hosts first
    if not setup_host_ssh_key(user=user, host=remote_ip, public_key_path=public_key_path, password=remote_password):
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to setup SSH key for jump host {remote_ip}")
        return False

    LOG(f"{LOG_PREFIX_MSG_INFO} Passwordless SSH setup completed successfully!")
    return True


def remove_known_hosts_entries(hosts: List[str]) -> None:
    """Remove known_hosts entries for given hosts to handle key changes."""
    for host in hosts:
        try:
            LOG(f"{LOG_PREFIX_MSG_INFO} Removing known_hosts entry for {host}...")
            subprocess.run(['ssh-keygen', '-R', host],
                           capture_output=True, check=False)
        except Exception as e:
            LOG(f"[WARNING] Failed to remove known_hosts entry for {host}: {e}")


def check_ssh_pwless_statuses(ips: List[str], user: str, public_key_path: Path, max_workers: int = 10) -> SshPwlessStatuses:
    """Check SSH key status for multiple hosts in parallel.

    Returns:
        SshPwlessStatuses with passwordless, password required, and unreachable IPs.
    """
    statuses = SshPwlessStatuses()

    try:
        with open(public_key_path, 'r') as f:
            public_key = f.read().strip()
        key_parts = public_key.split()
        key_fingerprint = key_parts[1] if len(key_parts) > 1 else public_key
    except Exception as exc:
        LOG(f"{LOG_PREFIX_MSG_WARNING} Unable to read public key at {public_key_path}: {exc}")
        key_fingerprint = None

    unreachable_markers = (
        "connection timed out",
        "no route to host",
        "could not resolve hostname",
        "name or service not known",
        "connection refused",
        "connection closed by remote host",
        "connection reset",
        "network is unreachable",
        "host is down",
    )

    permission_markers = (
        "permission denied",
        "authentication failed",
        "publickey,password",
        "publickey,keyboard-interactive",
    )

    def _check_single_ip(ip: str) -> Tuple[str, str]:
        if not key_fingerprint:
            # Without a readable key we cannot check remotely; treat as requiring setup.
            return ip, "password_required"

        cmd = (f'ssh {LEGACY_SSH_RSA_OPTION_STR} {NON_INTERACTIVE_KNOWN_HOST_OPTION_STR} '
               f'-o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=5 '
               f'{user}@{ip} \'grep -q "{key_fingerprint}" ~/.ssh/authorized_keys 2>/dev/null\'')
        try:
            result = run_shell(cmd, show_cmd=False, capture_output=True, timeout=10,
                               check_throw_exception_on_exit_code=False, )
        except Exception as exc:
            LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to execute SSH status check for {ip}: {exc}")
            return ip, "unreachable"

        combined_output = f"{result.stdout or ''}\n{result.stderr or ''}".lower()

        if result.returncode == 0:
            return ip, "passwordless"

        if any(marker in combined_output for marker in unreachable_markers):
            return ip, "unreachable"

        if any(marker in combined_output for marker in permission_markers):
            return ip, "password_required"

        # Default to password-required for other failures so we attempt remediation.
        LOG(f"{LOG_PREFIX_MSG_WARNING} {ip} SSH check failed with unexpected output (treating as password-required). Raw: {combined_output.strip()}")
        return ip, "password_required"

    LOG(f"{LOG_PREFIX_MSG_INFO} Checking SSH key status for {len(ips)} hosts in parallel with max_workers={max_workers}")
    with ThreadPoolExecutor(max_workers=min(max_workers, len(ips))) as executor:
        future_map = {executor.submit(_check_single_ip, ip): ip for ip in ips}

        for future in as_completed(future_map):
            ip = future_map[future]
            try:
                checked_ip, status = future.result()
                if status == "passwordless":
                    statuses.passwordless_ips.append(checked_ip)
                    LOG(f"{LOG_PREFIX_MSG_INFO} [OK] {checked_ip} - SSH key already installed")
                elif status == "password_required":
                    statuses.password_required_ips.append(checked_ip)
                    LOG(f"{LOG_PREFIX_MSG_WARNING} {checked_ip} - SSH key not found, will require password")
                else:
                    statuses.unreachable_ips.append(checked_ip)
                    LOG(f"{LOG_PREFIX_MSG_WARNING} {checked_ip} - Host unreachable, skipping")
            except Exception as exc:
                LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to check SSH status for {ip}: {exc}")
                statuses.unreachable_ips.append(ip)

    return statuses


def is_ssh_key_already_installed(user: str, host: str, public_key_path: Path) -> bool:
    """Check if SSH key is already installed on remote host."""
    try:
        with open(public_key_path, 'r') as f:
            public_key = f.read().strip()

        # Extract just the key part (not the comment)
        key_fingerprint = public_key.split()[1] if len(public_key.split()) > 1 else public_key
        cmd = (f'ssh {LEGACY_SSH_RSA_OPTION_STR} {NON_INTERACTIVE_KNOWN_HOST_OPTION_STR} '
               f'-o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=5 {user}@{host} '
               f'\'grep -q "{key_fingerprint}" ~/.ssh/authorized_keys 2>/dev/null\'')
        # batch mode=yes - Fail if password is needed
        result = run_shell(cmd, show_cmd=False, capture_output=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False


def check_ssh_key_exists(key_type: str = SSH_KEY_TYPE_RSA) -> Tuple[bool, Path]:
    """Check if SSH key pair already exists."""
    ssh_dir = Path.home() / '.ssh'
    if key_type == KEY_TYPE_ED25519:
        private_key = ssh_dir / 'id_ed25519'
        public_key = ssh_dir / 'id_ed25519.pub'
    else:
        private_key = ssh_dir / 'id_rsa'
        public_key = ssh_dir / 'id_rsa.pub'

    exists = private_key.exists() and public_key.exists()
    return exists, public_key


def generate_ssh_key(key_type: str = SSH_KEY_TYPE_RSA) -> bool:
    """Generate SSH key pair if it doesn't exist."""
    ssh_dir = Path.home() / '.ssh'
    ssh_dir.mkdir(mode=0o700, exist_ok=True)

    exists, pub_key_path = check_ssh_key_exists(key_type)

    if exists:
        LOG(f"{LOG_PREFIX_MSG_INFO} SSH key already exists: {pub_key_path}")
        return True

    LOG(f"{LOG_PREFIX_MSG_INFO} Generating {key_type.upper()} SSH key pair...")

    if key_type == KEY_TYPE_ED25519:
        key_path = ssh_dir / 'id_ed25519'
        cmd = ['ssh-keygen', '-t', key_type, '-f', str(key_path), '-N', '']
    else:
        key_path = ssh_dir / 'id_rsa'
        cmd = ['ssh-keygen', '-t', key_type, '-b', '4096', '-f', str(key_path), '-N', '']

    try:
        subprocess.check_call(cmd)
        LOG(f"{LOG_PREFIX_MSG_INFO} SSH key generated successfully: {key_path}")
        return True
    except subprocess.CalledProcessError as e:
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to generate SSH key: {e}", file=sys.stderr)
        return False


def remove_target_ssh_key_from_known_host(ip: str) -> bool:
    """
    Attempts to remove the offending host key from the user's known_hosts file.
    This is the fix suggested by SSH when a host key mismatch occurs.
    """
    known_hosts_path = Path.home() / ".ssh" / "known_hosts"
    if not known_hosts_path.exists():
        LOG(f"{LOG_PREFIX_MSG_INFO} No known_hosts file found, skipping key removal for {ip}.")
        return True  # Nothing to remove, so "success"

    # Use shlex.quote to prevent command injection
    command = f"ssh-keygen -f {shlex.quote(str(known_hosts_path))} -R {shlex.quote(ip)}"
    LOG(f"{LOG_PREFIX_MSG_INFO} Attempting to remove old host key for {ip}: {command}")

    try:
        # Run the command
        result = subprocess.run(shlex.split(command), capture_output=True, text=True, check=True, timeout=10)
        LOG(f"{LOG_PREFIX_MSG_INFO} Successfully removed host key for {ip}.")
        if result.stdout:
            LOG(f"ssh-keygen stdout: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        # Command returned a non-zero exit code
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to remove host key for {ip}. Error: {e.stderr.strip()}")
        return False
    except Exception as e:
        # Other errors (e.g., timeout)
        LOG(f"{LOG_PREFIX_MSG_ERROR} An unexpected error occurred while running ssh-keygen for {ip}: {e}")
        return False


def setup_host_ssh_key(user: str, host: str, public_key_path: Path, via_jump: Optional[str] = None, password: Optional[str] = None, jump_user: Optional[str] = None, jump_password: Optional[str] = None) -> bool:
    """Copy SSH public key to remote host."""
    LOG(f"{LOG_PREFIX_MSG_INFO} Copying SSH key to {user}@{host}...")

    try:
        # Read the public key
        with open(public_key_path, 'r') as f:
            public_key = f.read().strip()
        remote_cmd = f'mkdir -p ~/.ssh && echo "{public_key}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chmod 700 ~/.ssh'
        if password:
            run_ssh_command(host_ip=host, user=user, password=password, command=remote_cmd, timeout=30, jump_host_ip=via_jump, jump_user=jump_user, jump_password=jump_password)
        else:
            # Build key-based command path for environments already configured for passwordless auth.
            if via_jump:
                cmd = ['ssh', '-o', f'ProxyJump={user}@{via_jump}', '-o', 'StrictHostKeyChecking=no', *LEGACY_SSH_RSA_OPTIONS, *NON_INTERACTIVE_KNOWN_HOST_OPTIONS, f'{user}@{host}', remote_cmd]
            else:
                cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', *LEGACY_SSH_RSA_OPTIONS, *NON_INTERACTIVE_KNOWN_HOST_OPTIONS, f'{user}@{host}', remote_cmd]
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)

        LOG(f"{LOG_PREFIX_MSG_INFO} SSH key successfully copied to {host}.")
        return True

    except subprocess.CalledProcessError as e:
        # The command failed. This will now almost certainly be the "Permission denied" error.
        LOG(f"{LOG_PREFIX_MSG_ERROR} Failed to copy key to {host}. Error: {e.stderr.strip()}", file=sys.stderr)
        return False
    except Exception as e:
        # Catch other errors (e.g., file not found, timeout)
        LOG(f"{LOG_PREFIX_MSG_ERROR} An unexpected error occurred while copying key to {host}: {e}", file=sys.stderr)
        return False
