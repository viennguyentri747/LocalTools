from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import Optional
from dev_common.core_independent_utils import LOG_EXCEPTION_STR
from dev_common.core_utils import LOG, run_shell

CMD_DOCKER = "docker"


def docker_is_image_exists(image: str) -> bool:
    """
    Checks whether a Docker image exists locally.
    """
    quoted_image = shlex.quote(image)
    check_cmd = f"{CMD_DOCKER} image inspect {quoted_image} > /dev/null 2>&1"
    result = run_shell(
        check_cmd,
        capture_output=True,
        check_throw_exception_on_exit_code=False,
    )
    return result.returncode == 0


def docker_pull_image(image: str) -> bool:
    """
    Pulls a Docker image. Returns True on success.
    """
    quoted_image = shlex.quote(image)
    result = run_shell(
        f"{CMD_DOCKER} pull {quoted_image}",
        check_throw_exception_on_exit_code=False,
    )
    if result.returncode != 0:
        LOG(f"Failed to pull Docker image: {image}", file=sys.stderr)
        return False
    return True


def docker_pull_image_if_missing(image: str, *, auto_pull: bool = True) -> None:
    """
    Ensures the requested Docker image is available locally.

    Args:
        image: Name of the Docker image.
        auto_pull: When True, missing images are pulled automatically.
    """
    if docker_is_image_exists(image):
        LOG(f"Docker image found locally: {image}")
        return

    LOG(f"Docker image {image} not found locally.")
    if not auto_pull:
        LOG_EXCEPTION_STR(f"Docker image '{image}' missing locally and auto-pull disabled.")

    LOG(f"Pulling Docker image {image}...")
    if not docker_pull_image(image):
        LOG_EXCEPTION_STR(f"Failed to pull Docker image: {image}")
    LOG(f"Successfully pulled Docker image: {image}")


def docker_parse_image_from_gitlab_ci(gitlab_ci_path: Path | str) -> str:
    """
    Extracts the Docker image configured in a .gitlab-ci.yml file.
    """
    path = Path(gitlab_ci_path)
    if not path.exists():
        LOG_EXCEPTION_STR(f".gitlab-ci.yml not found at {path}")

    docker_image: Optional[str] = None
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("image:"):
                docker_image = stripped.split("image:", 1)[1].strip()
                if docker_image:
                    break

    if not docker_image:
        LOG_EXCEPTION_STR(f"Docker image not found in {path}")
    return docker_image


def prepare_docker_image_from_gitlab_ci(gitlab_ci_path: Path | str, *, auto_pull: bool = True) -> str:
    """
    Retrieves the Docker image name from .gitlab-ci.yml and ensures it exists locally.
    """
    docker_image = docker_parse_image_from_gitlab_ci(gitlab_ci_path)
    docker_pull_image_if_missing(docker_image, auto_pull=auto_pull)
    return docker_image
