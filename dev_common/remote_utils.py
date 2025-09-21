from pathlib import Path
from typing import Optional


def _escape_for_echo_script(s: str) -> str:
    """
    Escape a script string to be safely embedded inside: echo " ... "
    - Escape backslashes, double quotes, and dollar signs to avoid premature expansion.
    """
    return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("$", "\\$")


def create_scp_and_run_cmd(
    local_path: Path,
    remote_host: str = "root@192.168.100.254",
    remote_dir: str = "/home/root/download",
    run_cmd_on_remote: Optional[str] = None,
) -> str:
    """
    Build a single-line shell command that:
    1) Prompts for a 'source_ip' (jump host) using 'read -e'.
    2) scp -rJ (via jump) the local file to the remote host's target directory.
    3) Prints a ready-to-paste command for the UT that embeds the local MD5 value and
       computes remote MD5 on the target before running the provided command.
    """
    lp = Path(local_path).expanduser().resolve()
    remote_dir_norm = remote_dir.rstrip("/")
    remote_filename = lp.name
    remote_abs_path = f"{remote_dir_norm}/{remote_filename}"

    # Default remote run command
    if run_cmd_on_remote is None:
        run_cmd_on_remote = f"python3 {remote_abs_path}"

    # Compose the full one-liner following the reference style
    # - Prompt for source_ip
    # - chmod local file
    # - scp via jump (-J) through root@${source_ip} to remote_host
    # - On success:
    #     - compute original md5 locally
    #     - notify
    #     - print a clean, ready-to-paste remote command using printf with %s placeholders
    #       so that:
    #         - the original MD5 value is baked in (expanded locally)
    #         - the UT still evaluates $(md5sum ...) and $actual_md5 properly (no local expansion)
    cmd = (
        f"output_path=\"{lp}\" "
        f"&& read -e -i \"192.168.10\" -p \"Enter source IP address: \" source_ip "
        f"&& sudo chmod 644 \"$output_path\" "
        f"&& scp -rJ root@$source_ip \"$output_path\" {remote_host}:{remote_dir_norm}/ "
        f"&& {{ original_md5=$(md5sum \"$output_path\" | cut -d\" \" -f1); "
        f"noti \"SCP copy completed successfully\"; "
        f"echo -e \"File(s) copied completed. Run on target UT $source_ip with this below command:\\n\"; "
        # Print ready-to-paste command for UT; single quotes prevent local $ expansion
        f"printf 'original_md5=\"%s\"; actual_md5=$(md5sum {remote_abs_path} | cut -d\" \" -f1); "
        f"echo \"original md5sum: %s\"; echo \"actual md5sum: $actual_md5\"; "
        f"if [ \"%s\" = \"$actual_md5\" ]; then echo \"MD5 match! Proceeding...\"; {run_cmd_on_remote}; else echo \"MD5 MISMATCH! Not running.\"; fi\\n' "
        f"\"$original_md5\" \"$original_md5\" \"$original_md5\"; }} "
        f"|| {{ noti \"SCP copy failed\"; }} "
    )
    return cmd