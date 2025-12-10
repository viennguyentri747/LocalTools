import argparse
from dataclasses import dataclass
from dev_common.constants import ARGUMENT_LONG_PREFIX
from dev_common.python_misc_utils import get_arg_value


DEFAULT_SSM_REBOOT_TIMEOUT = 90  # seconds to wait for SSM to respond after reboot
DEFAULT_REQUEST_INTERVAL = 1  # seconds between url request attempts
DEFAULT_GPX_FIX_TIMEOUT = 200  # seconds to wait for gpx fix
DEFAULT_ONLINE_TIMEOUT = 800  # seconds to wait for the host to come back online
DEFAULT_PING_TIMEOUT = 240  # seconds to wait for UT ping to succeed
DEFAULT_TOTAL_ITERATIONS = 10  # number of test cycles to execute
DEFAULT_WAIT_SECS_AFTER_EACH_ITERATION = 5  # seconds to wait between cycles

ARG_SSM_IP = f"{ARGUMENT_LONG_PREFIX}ssm"
ARG_SSM_REBOOT_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}ssm-reboot-timeout"
ARG_REQUEST_INTERVAL = f"{ARGUMENT_LONG_PREFIX}request-interval-secs"
ARG_GPX_FIX_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}gpx-fix-timeout"
ARG_ONLINE_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}online-timeout"
ARG_PING_TIMEOUT = f"{ARGUMENT_LONG_PREFIX}ping-timeout"
ARG_TOTAL_ITERATIONS = f"{ARGUMENT_LONG_PREFIX}total-iterations"
ARG_WAIT_SECS_AFTER_EACH_ITERATION = f"{ARGUMENT_LONG_PREFIX}wait-secs-after-each-iteration"
ARG_PRINT_TIMESTAMP = f"{ARGUMENT_LONG_PREFIX}print-timestamp"


@dataclass(frozen=True)
class TestSequenceConfig:
    """Configuration for constructing the reboot + status command."""

    ssm_ip: str
    request_interval: int = DEFAULT_REQUEST_INTERVAL
    ssm_reboot_timeout: int = DEFAULT_SSM_REBOOT_TIMEOUT
    gpx_fix_timeout: int = DEFAULT_GPX_FIX_TIMEOUT
    aim_status_timeout: int = 200
    ping_timeout: int = DEFAULT_PING_TIMEOUT
    apn_online_timeout: int = DEFAULT_ONLINE_TIMEOUT
    total_iterations: int = DEFAULT_TOTAL_ITERATIONS
    wait_secs_after_each_iteration: int = DEFAULT_WAIT_SECS_AFTER_EACH_ITERATION
    print_timestamp: bool = False

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "TestSequenceConfig":
        return cls(
            ssm_ip=get_arg_value(args, ARG_SSM_IP),
            request_interval=int(get_arg_value(args, ARG_REQUEST_INTERVAL)),
            ssm_reboot_timeout=int(get_arg_value(args, ARG_SSM_REBOOT_TIMEOUT)),
            gpx_fix_timeout=int(get_arg_value(args, ARG_GPX_FIX_TIMEOUT)),
            ping_timeout=int(get_arg_value(args, ARG_PING_TIMEOUT)),
            apn_online_timeout=int(get_arg_value(args, ARG_ONLINE_TIMEOUT)),
            total_iterations=int(get_arg_value(args, ARG_TOTAL_ITERATIONS)),
            wait_secs_after_each_iteration=int(get_arg_value(args, ARG_WAIT_SECS_AFTER_EACH_ITERATION)),
            print_timestamp=bool(get_arg_value(args, ARG_PRINT_TIMESTAMP)),
        )
